from __future__ import annotations
import sys
import json, os, shutil, socket, subprocess, tempfile, time
from pathlib import Path
from typing import Iterable
from . import db
from .config import DATA_DIR, THUMB_DIR, DB_PATH


def lan_addresses(port: int = 8765):
    out=[]
    seen=set()
    # hostname resolution first
    try:
        infos=socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET,socket.SOCK_DGRAM)
        for info in infos:
            ip=info[4][0]
            if ip.startswith('127.') or ip.startswith('169.254.') or ip in seen: continue
            seen.add(ip); out.append({'ip':ip,'url':f'http://{ip}:{port}','kind':'lan'})
    except OSError: pass
    # routing-derived primary IPv4
    for target in [('8.8.8.8',80),('1.1.1.1',80)]:
        try:
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(target); ip=s.getsockname()[0]; s.close()
            if not ip.startswith(('127.','169.254.')) and ip not in seen:
                seen.add(ip); out.insert(0,{'ip':ip,'url':f'http://{ip}:{port}','kind':'primary'})
        except OSError: pass
    return out


def open_in_explorer(path: str):
    p=Path(path)
    if os.name=='nt':
        subprocess.Popen(['explorer.exe','/select,',str(p)])
    elif sys.platform=='darwin':
        subprocess.Popen(['open','-R',str(p)])
    else:
        subprocess.Popen(['xdg-open',str(p.parent)])


def open_external(path: str):
    p=str(Path(path))
    if os.name=='nt': os.startfile(p)  # type: ignore[attr-defined]
    elif sys.platform=='darwin': subprocess.Popen(['open',p])
    else: subprocess.Popen(['xdg-open',p])


def _unique_destination(dest: Path) -> Path:
    if not dest.exists(): return dest
    stem,suffix=dest.stem,dest.suffix
    for i in range(1,10000):
        c=dest.with_name(f'{stem} ({i}){suffix}')
        if not c.exists(): return c
    raise RuntimeError('Не удалось подобрать свободное имя файла')


def copy_or_move(photo_ids: Iterable[int], destination: str, move: bool=False):
    dest=Path(destination).expanduser().resolve()
    if not dest.exists() or not dest.is_dir(): raise ValueError('Папка назначения не существует')
    done=[]
    undo=[]
    for pid in photo_ids:
        row=db.get_photo(int(pid))
        if not row: continue
        src=Path(row['path'])
        if not src.exists(): continue
        target=_unique_destination(dest/src.name)
        if move:
            shutil.move(str(src),str(target)); db.update_photo_path(int(pid),str(target)); undo.append({'photo_id':int(pid),'src':str(target),'dst':str(src)})
        else:
            shutil.copy2(src,target)
        done.append({'photo_id':int(pid),'from':str(src),'to':str(target)})
    if move and done: db.log_action('move',done,undo)
    return done


def rename_photo(photo_id: int, new_name: str):
    row=db.get_photo(photo_id)
    if not row: raise ValueError('Фото не найдено')
    src=Path(row['path']); name=Path(new_name).name
    if not name or name in ('.','..'): raise ValueError('Некорректное имя')
    dst=_unique_destination(src.with_name(name))
    src.rename(dst); db.update_photo_path(photo_id,str(dst)); db.log_action('rename',{'photo_id':photo_id,'from':str(src),'to':str(dst)},{'photo_id':photo_id,'src':str(dst),'dst':str(src)})
    return str(dst)


def trash_photos(photo_ids: Iterable[int]):
    from send2trash import send2trash
    done=[]
    for pid in photo_ids:
        row=db.get_photo(int(pid))
        if not row: continue
        p=Path(row['path'])
        if p.exists(): send2trash(str(p))
        done.append({'photo_id':int(pid),'path':str(p)})
        db.remove_photo_record(int(pid))
    # Windows Recycle Bin restore is not reliably automatable; log audit only.
    if done: db.log_action('trash',done,None)
    return done


def undo_last():
    import json
    a=db.last_action()
    if not a: return {'ok':False,'reason':'empty'}
    if not a.get('undo_payload'): return {'ok':False,'reason':'not_undoable','kind':a['kind']}
    payload=json.loads(a['undo_payload'])
    if a['kind'] in ('move','rename'):
        seq=payload if isinstance(payload,list) else [payload]
        restored=[]
        for item in seq:
            src=Path(item['src']); dst=Path(item['dst'])
            if src.exists():
                dst.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(src),str(dst)); db.update_photo_path(int(item['photo_id']),str(dst)); restored.append(str(dst))
        db.mark_action_undone(a['id']); return {'ok':True,'kind':a['kind'],'restored':restored}
    return {'ok':False,'reason':'unsupported','kind':a['kind']}


def export_backup(target: str | None=None):
    from datetime import datetime
    out=Path(target).expanduser() if target else DATA_DIR/f"eidolarch-backup-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    out.parent.mkdir(parents=True,exist_ok=True)
    src=db.conn(); dst=__import__('sqlite3').connect(out)
    with dst: src.backup(dst)
    dst.close(); return str(out.resolve())


def clear_derived_cache():
    removed=0
    if THUMB_DIR.exists():
        for p in THUMB_DIR.rglob('*'):
            try:
                if p.is_file(): removed+=p.stat().st_size; p.unlink()
            except OSError: pass
    c=db.conn(); c.execute('UPDATE photos SET thumb_path=NULL'); c.commit()
    return removed


def redo_last():
    import json
    a=db.last_undone_action()
    if not a:return {'ok':False,'reason':'empty'}
    payload=json.loads(a['payload'])
    if a['kind']=='move':
        restored=[]
        for item in payload:
            src=Path(item['from']); dst=Path(item['to'])
            if src.exists():
                dst.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(src),str(dst)); db.update_photo_path(int(item['photo_id']),str(dst)); restored.append(str(dst))
        db.mark_action_redone(a['id']); return {'ok':True,'kind':'move','restored':restored}
    if a['kind']=='rename':
        item=payload; src=Path(item['from']); dst=Path(item['to'])
        if src.exists():
            dst.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(src),str(dst)); db.update_photo_path(int(item['photo_id']),str(dst))
        db.mark_action_redone(a['id']); return {'ok':True,'kind':'rename','restored':[str(dst)]}
    return {'ok':False,'reason':'unsupported'}


def open_recycle_bin():
    if os.name != 'nt':
        raise RuntimeError('Recycle Bin is available on Windows only')
    subprocess.Popen(['explorer.exe', 'shell:RecycleBinFolder'])
    return True
