from __future__ import annotations
import sqlite3, threading, shutil, json
from pathlib import Path
from datetime import datetime
from .config import DB_PATH, DATA_DIR
_local = threading.local()
_recovery_done = False

def _raw_connect(path: Path, readonly: bool=False):
    if readonly:
        c=sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    else:
        c=sqlite3.connect(path, timeout=30, check_same_thread=False)
    c.row_factory=sqlite3.Row
    return c

def _check_db(path: Path):
    if not path.exists() or path.stat().st_size == 0:
        return True, 'new database'
    try:
        c=_raw_connect(path, readonly=True)
        try:
            row=c.execute('PRAGMA quick_check').fetchone()
            ok=bool(row and str(row[0]).lower()=='ok')
            return ok, str(row[0]) if row else 'quick_check returned no result'
        finally:
            c.close()
    except Exception as e:
        return False, f'{type(e).__name__}: {e}'

def _safe_rows(c, sql, args=()):
    rows=[]
    try:
        cur=c.execute(sql,args)
        while True:
            try:
                r=cur.fetchone()
            except Exception:
                break
            if r is None:
                break
            rows.append(dict(r))
    except Exception:
        pass
    return rows

def _collect_salvage(path: Path):
    out={'folders':[], 'settings':[], 'photos':[], 'manual_tags':[], 'user_meta':[], 'entities':[]}
    try:
        c=_raw_connect(path, readonly=True)
    except Exception:
        return out
    try:
        out['folders']=_safe_rows(c,'SELECT id,path FROM folders ORDER BY id')
        out['settings']=_safe_rows(c,'SELECT key,value FROM settings')
        out['photos']=_safe_rows(c,'''SELECT id,folder_id,path,name,size,mtime_ns,taken_at,width,height,thumb_path,error,ai_error FROM photos ORDER BY id''')
        out['manual_tags']=_safe_rows(c,'''SELECT p.path photo_path,t.name,pt.source,pt.score FROM photo_tags pt JOIN photos p ON p.id=pt.photo_id JOIN tags t ON t.id=pt.tag_id WHERE pt.source IN ('manual','entity')''')
        out['user_meta']=_safe_rows(c,'''SELECT p.path photo_path,m.favorite,m.rating,m.color_label,m.comment FROM photo_user_meta m JOIN photos p ON p.id=m.photo_id''')
        out['entities']=_safe_rows(c,'SELECT name,kind FROM entities')
    finally:
        c.close()
    return out

def _archive_corrupt(reason: str):
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    rec=DATA_DIR/'recovery'/stamp
    rec.mkdir(parents=True,exist_ok=True)
    copied=[]
    for suffix in ('','-wal','-shm'):
        src=Path(str(DB_PATH)+suffix)
        if src.exists():
            dst=rec/(DB_PATH.name+suffix)
            try:
                shutil.copy2(src,dst); copied.append(str(dst))
            except Exception:
                pass
    (rec/'README.txt').write_text(
        'Eidolarch detected SQLite corruption and preserved the original database files here.\n'
        f'Reason: {reason}\n'
        'Do not delete this folder until you are satisfied with the recovered library.\n', encoding='utf-8')
    return rec,copied

def _prepare_database():
    global _recovery_done
    if _recovery_done:
        return
    _recovery_done=True
    ok,reason=_check_db(DB_PATH)
    if ok:
        return
    rec,_=_archive_corrupt(reason)
    # First try the least destructive repair: keep the main DB and discard only a bad WAL/SHM.
    main_copy=rec/'main-only.sqlite3'
    try:
        shutil.copy2(DB_PATH,main_copy)
    except Exception:
        pass
    main_ok,main_reason=_check_db(main_copy) if main_copy.exists() else (False,'main DB unavailable')
    if main_ok:
        for suffix in ('-wal','-shm'):
            try: Path(str(DB_PATH)+suffix).unlink(missing_ok=True)
            except Exception: pass
        shutil.copy2(main_copy,DB_PATH)
        (rec/'RECOVERY.txt').write_text(
            'Recovered automatically by discarding a malformed WAL/SHM. The main database passed quick_check.\n',
            encoding='utf-8')
        return

    # The main image itself is damaged. Preserve what can still be read, then recreate derived state.
    salvage=_collect_salvage(rec/DB_PATH.name)
    try:
        (rec/'salvage.json').write_text(json.dumps(salvage,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        pass
    for suffix in ('','-wal','-shm'):
        try: Path(str(DB_PATH)+suffix).unlink(missing_ok=True)
        except Exception: pass
    # A fresh schema will be created by init_db(); restoration happens afterwards.
    setattr(_local,'pending_salvage',salvage)
    (rec/'RECOVERY.txt').write_text(
        'The main SQLite image was malformed. Eidolarch created a fresh database and will restore readable folders, settings, photos, manual tags and user metadata where possible. Derived AI indexes will rebuild automatically.\n'
        f'Main DB check: {main_reason}\n', encoding='utf-8')

def conn():
    _prepare_database()
    c=getattr(_local,'conn',None)
    if c is None:
        c=sqlite3.connect(DB_PATH,timeout=30,check_same_thread=False); c.row_factory=sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON'); _local.conn=c
    return c

def _column_exists(table,column): return any(r['name']==column for r in conn().execute(f'PRAGMA table_info({table})'))
def _pk_columns(table): return [r['name'] for r in conn().execute(f'PRAGMA table_info({table})') if r['pk']]

def init_db():
    c=conn(); c.executescript('''
    CREATE TABLE IF NOT EXISTS folders(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS photos(id INTEGER PRIMARY KEY AUTOINCREMENT,folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,path TEXT NOT NULL UNIQUE,name TEXT NOT NULL,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,taken_at TEXT,width INTEGER,height INTEGER,thumb_path TEXT,indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,error TEXT,ai_error TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS embeddings(photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,provider_key TEXT NOT NULL DEFAULT 'local',model TEXT NOT NULL,dim INTEGER NOT NULL,vector BLOB NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(photo_id,provider_key,model));
    CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE COLLATE NOCASE,kind TEXT NOT NULL DEFAULT 'auto');
    CREATE TABLE IF NOT EXISTS photo_tags(photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,source TEXT NOT NULL DEFAULT 'auto',provider_key TEXT,model TEXT,score REAL,PRIMARY KEY(photo_id,tag_id,source));
    CREATE INDEX IF NOT EXISTS idx_photos_folder ON photos(folder_id); CREATE INDEX IF NOT EXISTS idx_photos_taken ON photos(taken_at);
    CREATE INDEX IF NOT EXISTS idx_photo_tags_tag ON photo_tags(tag_id,photo_id);
    CREATE TABLE IF NOT EXISTS photo_hashes(photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,sha256 TEXT,dhash TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX IF NOT EXISTS idx_hash_sha ON photo_hashes(sha256);
    CREATE INDEX IF NOT EXISTS idx_hash_dhash ON photo_hashes(dhash);
    CREATE TABLE IF NOT EXISTS entities(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL COLLATE NOCASE,kind TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(name,kind));
    CREATE TABLE IF NOT EXISTS detections(id INTEGER PRIMARY KEY AUTOINCREMENT,photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,kind TEXT NOT NULL,score REAL NOT NULL,x1 REAL NOT NULL,y1 REAL NOT NULL,x2 REAL NOT NULL,y2 REAL NOT NULL,detector_model TEXT NOT NULL,provider_key TEXT NOT NULL,embedding_model TEXT NOT NULL,dim INTEGER NOT NULL,vector BLOB NOT NULL,entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX IF NOT EXISTS idx_det_photo ON detections(photo_id);
    CREATE INDEX IF NOT EXISTS idx_det_kind ON detections(kind,provider_key,embedding_model);
    CREATE INDEX IF NOT EXISTS idx_det_entity ON detections(entity_id);
    CREATE TABLE IF NOT EXISTS entity_scans(photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,detector_model TEXT NOT NULL,provider_key TEXT NOT NULL,embedding_model TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'done',error TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(photo_id,detector_model,provider_key,embedding_model));
    CREATE TABLE IF NOT EXISTS photo_user_meta(photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,favorite INTEGER NOT NULL DEFAULT 0,rating INTEGER NOT NULL DEFAULT 0,color_label TEXT,comment TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS action_log(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,payload TEXT NOT NULL,undo_payload TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,undone INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS idx_user_favorite ON photo_user_meta(favorite);
    CREATE INDEX IF NOT EXISTS idx_user_rating ON photo_user_meta(rating);
    ''')
    if not _column_exists('photos','ai_error'): c.execute('ALTER TABLE photos ADD COLUMN ai_error TEXT')
    if _pk_columns('embeddings') == ['photo_id']:
        c.executescript('''ALTER TABLE embeddings RENAME TO embeddings_old;
        CREATE TABLE embeddings(photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,provider_key TEXT NOT NULL DEFAULT 'local',model TEXT NOT NULL,dim INTEGER NOT NULL,vector BLOB NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(photo_id,provider_key,model));
        INSERT INTO embeddings(photo_id,provider_key,model,dim,vector,created_at) SELECT photo_id,'local',model,dim,vector,created_at FROM embeddings_old; DROP TABLE embeddings_old;''')
    c.commit()
    salvage=getattr(_local,'pending_salvage',None)
    if salvage:
        _restore_salvage(salvage)
        try: delattr(_local,'pending_salvage')
        except Exception: pass

def _restore_salvage(salvage):
    c=conn()
    old_folder_to_new={}
    for r in salvage.get('folders',[]):
        try:
            c.execute('INSERT OR IGNORE INTO folders(path) VALUES(?)',(r['path'],))
            nr=c.execute('SELECT id FROM folders WHERE path=?',(r['path'],)).fetchone()
            if nr: old_folder_to_new[int(r['id'])]=int(nr['id'])
        except Exception: pass
    for r in salvage.get('settings',[]):
        try: c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(r['key'],r['value']))
        except Exception: pass
    for r in salvage.get('photos',[]):
        try:
            fid=old_folder_to_new.get(int(r['folder_id']))
            if not fid: continue
            c.execute('''INSERT OR IGNORE INTO photos(folder_id,path,name,size,mtime_ns,taken_at,width,height,thumb_path,error,ai_error,indexed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)''',
                (fid,r['path'],r.get('name') or Path(r['path']).name,int(r.get('size') or 0),int(r.get('mtime_ns') or 0),r.get('taken_at'),r.get('width'),r.get('height'),r.get('thumb_path'),r.get('error'),r.get('ai_error')))
        except Exception: pass
    for r in salvage.get('entities',[]):
        try: c.execute('INSERT OR IGNORE INTO entities(name,kind) VALUES(?,?)',(r['name'],r['kind']))
        except Exception: pass
    for r in salvage.get('manual_tags',[]):
        try:
            p=c.execute('SELECT id FROM photos WHERE path=?',(r['photo_path'],)).fetchone()
            if not p: continue
            kind='entity' if r.get('source')=='entity' else 'manual'
            c.execute('INSERT OR IGNORE INTO tags(name,kind) VALUES(?,?)',(r['name'],kind))
            t=c.execute('SELECT id FROM tags WHERE name=? COLLATE NOCASE',(r['name'],)).fetchone()
            if t: c.execute('INSERT OR REPLACE INTO photo_tags(photo_id,tag_id,source,score) VALUES(?,?,?,?)',(p['id'],t['id'],r.get('source') or 'manual',r.get('score')))
        except Exception: pass
    for r in salvage.get('user_meta',[]):
        try:
            p=c.execute('SELECT id FROM photos WHERE path=?',(r['photo_path'],)).fetchone()
            if p: c.execute('''INSERT OR REPLACE INTO photo_user_meta(photo_id,favorite,rating,color_label,comment,updated_at) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)''',(p['id'],int(r.get('favorite') or 0),int(r.get('rating') or 0),r.get('color_label'),r.get('comment')))
        except Exception: pass
    c.commit()

def set_setting(key,value): c=conn(); c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value)); c.commit()
def get_settings(keys):
    ks=list(keys)
    if not ks:return {}
    q=','.join('?'*len(ks)); return {r['key']:r['value'] for r in conn().execute(f'SELECT key,value FROM settings WHERE key IN ({q})',ks)}
def add_folder(path):
    p=str(Path(path).expanduser().resolve()); c=conn(); c.execute('INSERT OR IGNORE INTO folders(path) VALUES(?)',(p,)); c.commit(); return int(c.execute('SELECT id FROM folders WHERE path=?',(p,)).fetchone()['id'])
def remove_folder(folder_id): c=conn(); c.execute('DELETE FROM folders WHERE id=?',(folder_id,)); c.commit()
def list_folders(): return conn().execute('SELECT f.*,COUNT(p.id) photo_count FROM folders f LEFT JOIN photos p ON p.folder_id=f.id AND p.error IS NULL GROUP BY f.id ORDER BY f.path').fetchall()
def get_folder(i): return conn().execute('SELECT * FROM folders WHERE id=?',(i,)).fetchone()
def get_photo(i): return conn().execute('SELECT * FROM photos WHERE id=?',(i,)).fetchone()
def photo_by_path(path): return conn().execute('SELECT * FROM photos WHERE path=?',(path,)).fetchone()
def upsert_photo(folder_id,path,name,size,mtime_ns,**meta):
    c=conn(); c.execute('''INSERT INTO photos(folder_id,path,name,size,mtime_ns,taken_at,width,height,thumb_path,error,ai_error,indexed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(path) DO UPDATE SET folder_id=excluded.folder_id,name=excluded.name,size=excluded.size,mtime_ns=excluded.mtime_ns,taken_at=excluded.taken_at,width=excluded.width,height=excluded.height,thumb_path=excluded.thumb_path,error=excluded.error,ai_error=excluded.ai_error,indexed_at=CURRENT_TIMESTAMP''',(folder_id,path,name,size,mtime_ns,meta.get('taken_at'),meta.get('width'),meta.get('height'),meta.get('thumb_path'),meta.get('error'),meta.get('ai_error'))); c.commit(); return int(c.execute('SELECT id FROM photos WHERE path=?',(path,)).fetchone()['id'])


def ensure_photo_stub(folder_id,path):
    p=Path(path)
    st=p.stat()
    c=conn()
    c.execute("""INSERT INTO photos(folder_id,path,name,size,mtime_ns,indexed_at,error,ai_error) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP,NULL,NULL)
        ON CONFLICT(path) DO UPDATE SET folder_id=excluded.folder_id,name=excluded.name,size=excluded.size,mtime_ns=excluded.mtime_ns""",
        (int(folder_id),str(p),p.name,int(st.st_size),int(st.st_mtime_ns)))
    c.commit()
    return int(c.execute('SELECT id FROM photos WHERE path=?',(str(p),)).fetchone()['id'])

def set_thumbnail(photo_id,thumb_path,width=None,height=None,taken_at=None):
    c=conn(); c.execute('UPDATE photos SET thumb_path=?,width=COALESCE(?,width),height=COALESCE(?,height),taken_at=COALESCE(?,taken_at) WHERE id=?',
        (str(thumb_path),width,height,taken_at,int(photo_id))); c.commit()


def clear_thumbnail(photo_id):
    c=conn(); c.execute('UPDATE photos SET thumb_path=NULL WHERE id=?',(int(photo_id),)); c.commit()

def set_ai_error(photo_id,msg): c=conn(); c.execute('UPDATE photos SET ai_error=? WHERE id=?',(msg,photo_id)); c.commit()
def has_embedding(photo_id,provider_key,model): return conn().execute('SELECT 1 FROM embeddings WHERE photo_id=? AND provider_key=? AND model=?',(photo_id,provider_key,model)).fetchone() is not None
def set_embedding(photo_id,provider_key,model,vector):
    import numpy as np
    v=np.asarray(vector,dtype=np.float32).reshape(-1); c=conn(); c.execute('''INSERT INTO embeddings(photo_id,provider_key,model,dim,vector) VALUES(?,?,?,?,?) ON CONFLICT(photo_id,provider_key,model) DO UPDATE SET dim=excluded.dim,vector=excluded.vector,created_at=CURRENT_TIMESTAMP''',(photo_id,provider_key,model,int(v.shape[0]),sqlite3.Binary(v.tobytes()))); c.execute('UPDATE photos SET ai_error=NULL WHERE id=?',(photo_id,)); c.commit()
def replace_auto_tags(photo_id,provider_key,model,tags):
    c=conn(); c.execute("DELETE FROM photo_tags WHERE photo_id=? AND source='auto' AND provider_key=? AND model=?",(photo_id,provider_key,model))
    for name,score in tags:
        c.execute("INSERT OR IGNORE INTO tags(name,kind) VALUES(?,'auto')",(name,)); tid=c.execute('SELECT id FROM tags WHERE name=? COLLATE NOCASE',(name,)).fetchone()['id']
        c.execute("INSERT OR REPLACE INTO photo_tags(photo_id,tag_id,source,provider_key,model,score) VALUES(?,?,'auto',?,?,?)",(photo_id,tid,provider_key,model,float(score)))
    c.commit()

def replace_auto_tags_bulk(assignments,provider_key,model):
    """Replace the complete auto-tag set for one embedding model in one transaction."""
    c=conn()
    c.execute("DELETE FROM photo_tags WHERE source='auto' AND provider_key=? AND model=?",(provider_key,model))
    tag_ids={}
    for photo_id,tags_for_photo in assignments:
        for name,score in tags_for_photo:
            tid=tag_ids.get(name)
            if tid is None:
                c.execute("INSERT OR IGNORE INTO tags(name,kind) VALUES(?,'auto')",(name,))
                tid=int(c.execute('SELECT id FROM tags WHERE name=? COLLATE NOCASE',(name,)).fetchone()['id'])
                tag_ids[name]=tid
            c.execute("INSERT OR REPLACE INTO photo_tags(photo_id,tag_id,source,provider_key,model,score) VALUES(?,?,'auto',?,?,?)",
                      (int(photo_id),tid,provider_key,model,float(score)))
    c.commit()

def list_tags(selected_ids=None,folder_id=None,provider_key=None,model=None,limit=200,path_prefix=None):
    c=conn(); where=['p.error IS NULL']; args=[]
    if folder_id: where.append('p.folder_id=?'); args.append(folder_id)
    if path_prefix:
        where.append('instr(p.path, ?)=1'); args.append(str(path_prefix))
    if provider_key and model:
        where.append("(pt.source!='auto' OR (pt.provider_key=? AND pt.model=?))"); args += [provider_key,model]
    selected_ids=[int(x) for x in (selected_ids or [])]
    if selected_ids:
        q=','.join('?'*len(selected_ids)); where.append(f'''p.id IN (SELECT photo_id FROM photo_tags WHERE tag_id IN ({q}) GROUP BY photo_id HAVING COUNT(DISTINCT tag_id)=?)'''); args += selected_ids+[len(selected_ids)]
    sql='''SELECT t.id,t.name,COUNT(DISTINCT p.id) count FROM tags t JOIN photo_tags pt ON pt.tag_id=t.id JOIN photos p ON p.id=pt.photo_id WHERE '''+' AND '.join(where)+''' GROUP BY t.id HAVING count>0 ORDER BY count DESC,t.name LIMIT ?'''
    args.append(limit); return [dict(r) for r in c.execute(sql,args)]
def photo_ids_for_filters(folder_id=None,tag_ids=None,provider_key=None,model=None,path_prefix=None):
    c=conn(); where=['p.error IS NULL']; args=[]
    if folder_id: where.append('p.folder_id=?');args.append(folder_id)
    if path_prefix:
        where.append('instr(p.path, ?)=1'); args.append(str(path_prefix))
    tag_ids=[int(x) for x in (tag_ids or [])]
    if tag_ids:
        q=','.join('?'*len(tag_ids)); where.append(f'''p.id IN (SELECT photo_id FROM photo_tags WHERE tag_id IN ({q}) AND (source!='auto' OR (provider_key=? AND model=?)) GROUP BY photo_id HAVING COUNT(DISTINCT tag_id)=?)'''); args+=tag_ids+[provider_key or '',model or '',len(tag_ids)]
    return {int(r['id']) for r in c.execute('SELECT p.id FROM photos p WHERE '+' AND '.join(where),args)}
def delete_missing(folder_id,existing):
    c=conn(); rows=c.execute('SELECT id,path,thumb_path FROM photos WHERE folder_id=?',(folder_id,)).fetchall(); dead=[r for r in rows if r['path'] not in existing]
    for r in dead:
        c.execute('DELETE FROM photos WHERE id=?',(r['id'],))
        if r['thumb_path']:
            try: Path(r['thumb_path']).unlink(missing_ok=True)
            except Exception: pass
    c.commit(); return len(dead)
def list_gallery(limit=200,offset=0,folder_id=None,tag_ids=None,provider_key=None,model=None,path_prefix=None):
    where=['p.error IS NULL'];args=[]
    if folder_id:where.append('p.folder_id=?');args.append(folder_id)
    if path_prefix:
        where.append('instr(p.path, ?)=1'); args.append(str(path_prefix))
    tag_ids=[int(x) for x in (tag_ids or [])]
    if tag_ids:
        q=','.join('?'*len(tag_ids));where.append(f'''p.id IN (SELECT photo_id FROM photo_tags WHERE tag_id IN ({q}) AND (source!='auto' OR (provider_key=? AND model=?)) GROUP BY photo_id HAVING COUNT(DISTINCT tag_id)=?)''');args+=tag_ids+[provider_key or '',model or '',len(tag_ids)]
    args += [limit,offset]
    return conn().execute('SELECT p.* FROM photos p WHERE '+' AND '.join(where)+' ORDER BY COALESCE(p.taken_at,p.indexed_at) DESC,p.id DESC LIMIT ? OFFSET ?',args).fetchall()
def count_gallery(folder_id=None,tag_ids=None,provider_key=None,model=None,path_prefix=None): return len(photo_ids_for_filters(folder_id,tag_ids,provider_key,model,path_prefix))
def count_photos(): return int(conn().execute('SELECT COUNT(*) c FROM photos WHERE error IS NULL').fetchone()['c'])
def count_ai_errors(): return int(conn().execute('SELECT COUNT(*) c FROM photos WHERE ai_error IS NOT NULL').fetchone()['c'])
def last_ai_error():
    r=conn().execute('SELECT ai_error FROM photos WHERE ai_error IS NOT NULL ORDER BY indexed_at DESC,id DESC LIMIT 1').fetchone(); return r['ai_error'] if r else None
def count_embeddings(provider_key,model): return int(conn().execute('SELECT COUNT(*) c FROM embeddings e JOIN photos p ON p.id=e.photo_id WHERE e.provider_key=? AND e.model=? AND p.error IS NULL',(provider_key,model)).fetchone()['c'])
def load_embeddings(provider_key,model): return conn().execute('''SELECT p.id,p.name,p.path,p.size,p.mtime_ns,p.taken_at,p.indexed_at,p.width,p.height,p.thumb_path,e.dim,e.vector FROM embeddings e JOIN photos p ON p.id=e.photo_id WHERE e.provider_key=? AND e.model=? AND p.error IS NULL ORDER BY p.id''',(provider_key,model)).fetchall()
def embedding_sets(): return [dict(r) for r in conn().execute('SELECT provider_key,model,COUNT(*) count,MAX(dim) dim FROM embeddings GROUP BY provider_key,model ORDER BY count DESC')]

# ---- duplicate and entity indexes -------------------------------------------------
def has_hash(photo_id):
    return conn().execute('SELECT 1 FROM photo_hashes WHERE photo_id=?',(photo_id,)).fetchone() is not None

def set_hashes(photo_id,sha256,dhash):
    c=conn()
    c.execute("""INSERT INTO photo_hashes(photo_id,sha256,dhash,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(photo_id) DO UPDATE SET sha256=excluded.sha256,dhash=excluded.dhash,updated_at=CURRENT_TIMESTAMP""",(photo_id,sha256,dhash))
    c.commit()



def duplicate_counts(photo_ids):
    ids=[int(x) for x in photo_ids if x is not None]
    if not ids:return {}
    q=','.join('?'*len(ids))
    rows=conn().execute(f"""
      SELECT a.photo_id, COUNT(DISTINCT b.photo_id) c
      FROM photo_hashes a
      LEFT JOIN photo_hashes b ON b.photo_id<>a.photo_id
       AND a.sha256 IS NOT NULL AND a.sha256<>'' AND b.sha256=a.sha256
      WHERE a.photo_id IN ({q})
      GROUP BY a.photo_id
    """,ids).fetchall()
    out={i:0 for i in ids}
    for r in rows:out[int(r['photo_id'])]=int(r['c'] or 0)
    return out

def entity_scan_status(photo_id, detector_model=None, provider_key=None, embedding_model=None):
    where=['photo_id=?']; args=[int(photo_id)]
    if detector_model is not None: where.append('detector_model=?'); args.append(detector_model)
    if provider_key is not None: where.append('provider_key=?'); args.append(provider_key)
    if embedding_model is not None: where.append('embedding_model=?'); args.append(embedding_model)
    row=conn().execute('SELECT * FROM entity_scans WHERE '+' AND '.join(where)+' ORDER BY updated_at DESC LIMIT 1',args).fetchone()
    return dict(row) if row else None

def duplicate_count(photo_id):
    r=conn().execute('SELECT sha256 FROM photo_hashes WHERE photo_id=?',(photo_id,)).fetchone()
    if not r or not r['sha256']:return 0
    c=conn().execute("""SELECT COUNT(DISTINCT ph.photo_id) c FROM photo_hashes ph
        WHERE ph.photo_id<>? AND ph.sha256=?""",(photo_id,r['sha256'])).fetchone()
    return int(c['c'])

def list_duplicate_photos(limit=120, offset=0, sort='taken_desc'):
    c=conn()
    where = "EXISTS (SELECT 1 FROM photo_hashes a JOIN photo_hashes b ON b.photo_id<>a.photo_id AND a.sha256 IS NOT NULL AND a.sha256<>'' AND b.sha256=a.sha256 WHERE a.photo_id=p.id)"
    order={
      'taken_desc':'COALESCE(p.taken_at,p.indexed_at) DESC,p.id DESC',
      'taken_asc':'COALESCE(p.taken_at,p.indexed_at) ASC,p.id ASC',
      'name_asc':'p.name COLLATE NOCASE ASC,p.id ASC',
      'name_desc':'p.name COLLATE NOCASE DESC,p.id DESC',
      'size_desc':'p.size DESC,p.id DESC',
      'size_asc':'p.size ASC,p.id ASC',
      'rating_desc':'COALESCE(m.rating,0) DESC,COALESCE(p.taken_at,p.indexed_at) DESC,p.id DESC',
      'added_desc':'p.indexed_at DESC,p.id DESC'
    }
    total=int(c.execute(f"SELECT COUNT(*) c FROM photos p WHERE p.error IS NULL AND {where}").fetchone()['c'])
    rows=c.execute(f"""SELECT p.*,COALESCE(m.favorite,0) favorite,COALESCE(m.rating,0) rating,m.color_label,m.comment
        FROM photos p LEFT JOIN photo_user_meta m ON m.photo_id=p.id
        WHERE p.error IS NULL AND {where}
        ORDER BY {order.get(sort,order['taken_desc'])} LIMIT ? OFFSET ?""",(int(limit),int(offset))).fetchall()
    return rows,total

def exact_duplicate_rows():
    """Return only byte-identical duplicate files (same non-empty SHA-256).

    Duplicate-package grouping intentionally depends on this narrow contract.
    If Eidolarch changes what counts as a duplicate later, replace this helper
    rather than leaking hash semantics into the UI.
    """
    return conn().execute("""
        SELECT h.sha256,p.id,p.path,p.name,p.size,p.taken_at,p.width,p.height,p.mtime_ns,p.thumb_path
        FROM photo_hashes h
        JOIN photos p ON p.id=h.photo_id
        JOIN (
            SELECT sha256 FROM photo_hashes
            WHERE sha256 IS NOT NULL AND sha256<>''
            GROUP BY sha256 HAVING COUNT(*)>1
        ) d ON d.sha256=h.sha256
        WHERE p.error IS NULL
        ORDER BY h.sha256,p.path COLLATE NOCASE,p.id
    """).fetchall()

def duplicate_groups(limit=100):
    rows=conn().execute("""SELECT sha256 k, COUNT(*) c, GROUP_CONCAT(photo_id) ids
        FROM photo_hashes WHERE sha256 IS NOT NULL AND sha256<>''
        GROUP BY sha256 HAVING COUNT(*)>1 ORDER BY c DESC LIMIT ?""",(limit,)).fetchall()
    return [dict(r) for r in rows]

def get_embedding(photo_id,provider_key,model):
    return conn().execute("""SELECT e.photo_id,e.provider_key,e.model,e.dim,e.vector,p.path,p.name,p.taken_at,p.width,p.height,p.thumb_path
        FROM embeddings e JOIN photos p ON p.id=e.photo_id
        WHERE e.photo_id=? AND e.provider_key=? AND e.model=?""",(photo_id,provider_key,model)).fetchone()

def has_entity_scan(photo_id,detector_model,provider_key,embedding_model):
    r=conn().execute('SELECT status FROM entity_scans WHERE photo_id=? AND detector_model=? AND provider_key=? AND embedding_model=?',
                     (photo_id,detector_model,provider_key,embedding_model)).fetchone()
    return bool(r and r['status']=='done')

def finish_entity_scan(photo_id,detector_model,provider_key,embedding_model,error=None):
    c=conn()
    c.execute("""INSERT INTO entity_scans(photo_id,detector_model,provider_key,embedding_model,status,error,updated_at)
        VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(photo_id,detector_model,provider_key,embedding_model)
        DO UPDATE SET status=excluded.status,error=excluded.error,updated_at=CURRENT_TIMESTAMP""",
        (photo_id,detector_model,provider_key,embedding_model,'error' if error else 'done',error))
    c.commit()

def replace_detections(photo_id,detector_model,provider_key,embedding_model,rows):
    import numpy as np
    c=conn()
    # Purge legacy detections for the same embedding pipeline so UI does not mix
    # boxes produced by older detector revisions with the current revision.
    c.execute('DELETE FROM detections WHERE photo_id=? AND provider_key=? AND embedding_model=?',
              (photo_id,provider_key,embedding_model))
    for kind,score,x1,y1,x2,y2,vector in rows:
        v=np.asarray(vector,dtype=np.float32).reshape(-1)
        c.execute("""INSERT INTO detections(photo_id,kind,score,x1,y1,x2,y2,detector_model,provider_key,embedding_model,dim,vector)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (photo_id,kind,float(score),float(x1),float(y1),float(x2),float(y2),detector_model,provider_key,embedding_model,int(v.shape[0]),sqlite3.Binary(v.tobytes())))
    c.commit()

def list_detections(photo_id):
    return conn().execute("""SELECT d.*,e.name entity_name FROM detections d
        LEFT JOIN entities e ON e.id=d.entity_id WHERE d.photo_id=? ORDER BY d.kind,d.score DESC""",(photo_id,)).fetchall()

def get_detection(detection_id):
    return conn().execute('SELECT * FROM detections WHERE id=?',(detection_id,)).fetchone()

def get_or_create_entity(name,kind):
    c=conn(); c.execute('INSERT OR IGNORE INTO entities(name,kind) VALUES(?,?)',(name,kind)); c.commit()
    return int(c.execute('SELECT id FROM entities WHERE name=? COLLATE NOCASE AND kind=?',(name,kind)).fetchone()['id'])

def assign_detection_entity(detection_id,entity_id):
    c=conn(); c.execute('UPDATE detections SET entity_id=? WHERE id=?',(entity_id,detection_id)); c.commit()

def unassigned_detection_vectors(kind,provider_key,embedding_model):
    return conn().execute('SELECT id,dim,vector FROM detections WHERE kind=? AND provider_key=? AND embedding_model=? AND entity_id IS NULL',
                          (kind,provider_key,embedding_model)).fetchall()

def rebuild_entity_tags(entity_id):
    c=conn(); ent=c.execute('SELECT * FROM entities WHERE id=?',(entity_id,)).fetchone()
    if not ent:return
    c.execute("INSERT OR IGNORE INTO tags(name,kind) VALUES(?,'entity')",(ent['name'],))
    tid=c.execute('SELECT id FROM tags WHERE name=? COLLATE NOCASE',(ent['name'],)).fetchone()['id']
    c.execute("DELETE FROM photo_tags WHERE tag_id=? AND source='entity'",(tid,))
    for r in c.execute('SELECT DISTINCT photo_id FROM detections WHERE entity_id=?',(entity_id,)).fetchall():
        c.execute("INSERT OR REPLACE INTO photo_tags(photo_id,tag_id,source,score) VALUES(?,?,'entity',1.0)",(r['photo_id'],tid))
    c.commit()

def list_entities():
    return [dict(r) for r in conn().execute("""SELECT e.id,e.name,e.kind,COUNT(DISTINCT d.photo_id) photo_count,COUNT(d.id) detection_count
        FROM entities e LEFT JOIN detections d ON d.entity_id=e.id GROUP BY e.id ORDER BY e.kind,e.name""")]

def photo_ids_for_entities(entity_ids):
    ids=[int(x) for x in entity_ids if x is not None]
    if not ids:return set()
    q=','.join('?'*len(ids))
    rows=conn().execute(f"""SELECT d.photo_id FROM detections d
        WHERE d.entity_id IN ({q})
        GROUP BY d.photo_id
        HAVING COUNT(DISTINCT d.entity_id)=?""",ids+[len(ids)]).fetchall()
    return {int(r['photo_id']) for r in rows}

def list_photos_by_ids(photo_ids, limit=200, sort='taken_desc'):
    ids=[int(x) for x in photo_ids if x is not None]
    if not ids:return []
    q=','.join('?'*len(ids))
    order={
      'taken_desc':'COALESCE(p.taken_at,p.indexed_at) DESC,p.id DESC',
      'taken_asc':'COALESCE(p.taken_at,p.indexed_at) ASC,p.id ASC',
      'name_asc':'p.name COLLATE NOCASE ASC,p.id ASC',
      'name_desc':'p.name COLLATE NOCASE DESC,p.id DESC',
      'size_desc':'p.size DESC,p.id DESC',
      'size_asc':'p.size ASC,p.id ASC',
      'rating_desc':'COALESCE(m.rating,0) DESC,COALESCE(p.taken_at,p.indexed_at) DESC,p.id DESC',
      'added_desc':'p.indexed_at DESC,p.id DESC'
    }
    return conn().execute(f"""SELECT p.*,COALESCE(m.favorite,0) favorite,COALESCE(m.rating,0) rating,m.color_label,m.comment
        FROM photos p LEFT JOIN photo_user_meta m ON m.photo_id=p.id
        WHERE p.error IS NULL AND p.id IN ({q})
        ORDER BY {order.get(sort,order['taken_desc'])} LIMIT ?""",ids+[int(limit)]).fetchall()

def entity_index_stats(detector_model,provider_key,embedding_model):
    c=conn()
    scans=int(c.execute("SELECT COUNT(*) c FROM entity_scans WHERE detector_model=? AND provider_key=? AND embedding_model=? AND status='done'",(detector_model,provider_key,embedding_model)).fetchone()['c'])
    errors=int(c.execute("SELECT COUNT(*) c FROM entity_scans WHERE detector_model=? AND provider_key=? AND embedding_model=? AND status='error'",(detector_model,provider_key,embedding_model)).fetchone()['c'])
    dets=int(c.execute('SELECT COUNT(*) c FROM detections WHERE detector_model=? AND provider_key=? AND embedding_model=?',(detector_model,provider_key,embedding_model)).fetchone()['c'])
    photos_with=int(c.execute('SELECT COUNT(DISTINCT photo_id) c FROM detections WHERE detector_model=? AND provider_key=? AND embedding_model=?',(detector_model,provider_key,embedding_model)).fetchone()['c'])
    return {'scanned':scans,'detections':dets,'photos_with_detections':photos_with,'scanned_without_detections':max(0,scans-photos_with),'errors':errors}

def photos_for_entity_scan(detector_model,provider_key,embedding_model,limit=None):
    sql="""SELECT p.* FROM photos p
        WHERE p.error IS NULL AND EXISTS(SELECT 1 FROM embeddings e WHERE e.photo_id=p.id AND e.provider_key=? AND e.model=?)
        AND NOT EXISTS(SELECT 1 FROM entity_scans s WHERE s.photo_id=p.id AND s.detector_model=? AND s.provider_key=? AND s.embedding_model=? AND s.status='done')
        ORDER BY p.id"""
    args=[provider_key,embedding_model,detector_model,provider_key,embedding_model]
    if limit:
        sql += ' LIMIT ?'; args.append(int(limit))
    return conn().execute(sql,args).fetchall()

def count_unscanned_entities(detector_model,provider_key,embedding_model):
    return len(photos_for_entity_scan(detector_model,provider_key,embedding_model))

def photo_ids_by_hash(photo_id):
    r=conn().execute('SELECT sha256 FROM photo_hashes WHERE photo_id=?',(photo_id,)).fetchone()
    if not r or not r['sha256']:return []
    return [int(x['photo_id']) for x in conn().execute("""SELECT DISTINCT photo_id FROM photo_hashes WHERE photo_id<>? AND sha256=?""",
        (photo_id,r['sha256'])).fetchall()]

def photo_rows_by_ids(ids):
    ids=[int(x) for x in ids]
    if not ids:return []
    q=','.join('?'*len(ids))
    rows=conn().execute(f'SELECT * FROM photos WHERE id IN ({q})',ids).fetchall()
    by={int(r['id']):r for r in rows}
    return [by[i] for i in ids if i in by]


def photo_tags_for_info(photo_id):
    return [dict(r) for r in conn().execute("""SELECT t.id,t.name,t.kind,pt.source,pt.score
        FROM photo_tags pt JOIN tags t ON t.id=pt.tag_id
        WHERE pt.photo_id=? ORDER BY CASE WHEN pt.source='entity' THEN 0 WHEN pt.source='manual' THEN 1 ELSE 2 END,t.name""",(int(photo_id),)).fetchall()]

# --- v2.0 user metadata, manual tags, sorting and action log ---
def get_photo_user_meta(photo_id):
    r=conn().execute('SELECT * FROM photo_user_meta WHERE photo_id=?',(int(photo_id),)).fetchone()
    return dict(r) if r else {'photo_id':int(photo_id),'favorite':0,'rating':0,'color_label':None,'comment':''}

def set_photo_user_meta(photo_id, favorite=None, rating=None, color_label=None, comment=None):
    c=conn(); cur=get_photo_user_meta(photo_id)
    fav=cur['favorite'] if favorite is None else (1 if favorite else 0)
    rat=cur['rating'] if rating is None else max(0,min(5,int(rating)))
    col=cur['color_label'] if color_label is None else (str(color_label) if color_label else None)
    com=cur['comment'] if comment is None else str(comment)
    c.execute("""INSERT INTO photo_user_meta(photo_id,favorite,rating,color_label,comment,updated_at) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
      ON CONFLICT(photo_id) DO UPDATE SET favorite=excluded.favorite,rating=excluded.rating,color_label=excluded.color_label,comment=excluded.comment,updated_at=CURRENT_TIMESTAMP""",
      (int(photo_id),fav,rat,col,com)); c.commit()
    return get_photo_user_meta(photo_id)

def add_manual_tag(photo_ids,name):
    name=str(name).strip()
    if not name:return 0
    c=conn(); c.execute("INSERT OR IGNORE INTO tags(name,kind) VALUES(?,'manual')",(name,)); tid=int(c.execute('SELECT id FROM tags WHERE name=? COLLATE NOCASE',(name,)).fetchone()['id'])
    n=0
    for pid in photo_ids:
        cur=c.execute("INSERT OR IGNORE INTO photo_tags(photo_id,tag_id,source) VALUES(?,?,'manual')",(int(pid),tid)); n+=cur.rowcount
    c.commit(); return n

def remove_manual_tag(photo_ids,tag_id):
    ids=[int(x) for x in photo_ids]
    if not ids:return 0
    q=','.join('?'*len(ids)); c=conn(); cur=c.execute(f"DELETE FROM photo_tags WHERE source='manual' AND tag_id=? AND photo_id IN ({q})",[int(tag_id),*ids]); c.commit(); return cur.rowcount

def photo_row_extended(photo_id):
    return conn().execute("""SELECT p.*,COALESCE(m.favorite,0) favorite,COALESCE(m.rating,0) rating,m.color_label,m.comment
      FROM photos p LEFT JOIN photo_user_meta m ON m.photo_id=p.id WHERE p.id=?""",(int(photo_id),)).fetchone()

def update_photo_path(photo_id,new_path,new_folder_id=None):
    p=Path(new_path); st=p.stat(); c=conn()
    if new_folder_id is None:
        r=get_photo(photo_id); new_folder_id=int(r['folder_id'])
    c.execute('UPDATE photos SET path=?,name=?,folder_id=?,size=?,mtime_ns=?,indexed_at=CURRENT_TIMESTAMP WHERE id=?',
      (str(p),p.name,int(new_folder_id),int(st.st_size),int(st.st_mtime_ns),int(photo_id))); c.commit()

def remove_photo_record(photo_id):
    c=conn(); c.execute('DELETE FROM photos WHERE id=?',(int(photo_id),)); c.commit()

def list_gallery_sorted(limit=200,offset=0,folder_id=None,tag_ids=None,provider_key=None,model=None,path_prefix=None,sort='taken_desc',favorite_only=False,min_rating=0):
    ids=photo_ids_for_filters(folder_id,tag_ids,provider_key,model,path_prefix)
    if not ids:return []
    q=','.join('?'*len(ids)); order={
      'taken_desc':'COALESCE(p.taken_at,p.indexed_at) DESC,p.id DESC','taken_asc':'COALESCE(p.taken_at,p.indexed_at) ASC,p.id ASC',
      'name_asc':'p.name COLLATE NOCASE ASC','name_desc':'p.name COLLATE NOCASE DESC','size_desc':'p.size DESC','size_asc':'p.size ASC',
      'rating_desc':'COALESCE(m.rating,0) DESC,COALESCE(p.taken_at,p.indexed_at) DESC','added_desc':'p.indexed_at DESC,p.id DESC'}
    where=[f'p.id IN ({q})']; args=list(ids)
    if favorite_only: where.append('COALESCE(m.favorite,0)=1')
    if min_rating>0: where.append('COALESCE(m.rating,0)>=?'); args.append(int(min_rating))
    args += [int(limit),int(offset)]
    sql=f"""SELECT p.*,COALESCE(m.favorite,0) favorite,COALESCE(m.rating,0) rating,m.color_label,m.comment
      FROM photos p LEFT JOIN photo_user_meta m ON m.photo_id=p.id WHERE {' AND '.join(where)}
      ORDER BY {order.get(sort,order['taken_desc'])} LIMIT ? OFFSET ?"""
    return conn().execute(sql,args).fetchall()

def count_gallery_extended(folder_id=None,tag_ids=None,provider_key=None,model=None,path_prefix=None,favorite_only=False,min_rating=0):
    ids=photo_ids_for_filters(folder_id,tag_ids,provider_key,model,path_prefix)
    if not ids:return 0
    q=','.join('?'*len(ids)); where=[f'p.id IN ({q})']; args=list(ids)
    if favorite_only: where.append('COALESCE(m.favorite,0)=1')
    if min_rating>0: where.append('COALESCE(m.rating,0)>=?'); args.append(int(min_rating))
    return int(conn().execute(f"SELECT COUNT(*) c FROM photos p LEFT JOIN photo_user_meta m ON m.photo_id=p.id WHERE {' AND '.join(where)}",args).fetchone()['c'])

def log_action(kind,payload,undo_payload=None):
    import json
    c=conn(); cur=c.execute('INSERT INTO action_log(kind,payload,undo_payload) VALUES(?,?,?)',(kind,json.dumps(payload,ensure_ascii=False),json.dumps(undo_payload,ensure_ascii=False) if undo_payload is not None else None)); c.commit(); return int(cur.lastrowid)

def last_action():
    r=conn().execute('SELECT * FROM action_log WHERE undone=0 ORDER BY id DESC LIMIT 1').fetchone(); return dict(r) if r else None

def mark_action_undone(action_id):
    c=conn(); c.execute('UPDATE action_log SET undone=1 WHERE id=?',(int(action_id),)); c.commit()

def storage_stats():
    from .config import DATA_DIR, THUMB_DIR, DB_PATH
    def size_tree(p):
        p=Path(p)
        if not p.exists(): return 0
        if p.is_file(): return p.stat().st_size
        total=0
        for x in p.rglob('*'):
            try:
                if x.is_file(): total += x.stat().st_size
            except OSError: pass
        return total
    return {'db_bytes':size_tree(DB_PATH),'thumb_bytes':size_tree(THUMB_DIR),'data_bytes':size_tree(DATA_DIR)}

def tag_graph(limit=45):
    c=conn()
    nodes=[dict(r) for r in c.execute('''SELECT t.id,t.name,COUNT(*) count FROM tags t JOIN photo_tags pt ON pt.tag_id=t.id GROUP BY t.id ORDER BY count DESC LIMIT ?''',(int(limit),))]
    ids=[n['id'] for n in nodes]
    if not ids:return {'nodes':[],'edges':[]}
    q=','.join('?'*len(ids))
    rows=c.execute(f'''SELECT a.tag_id a,b.tag_id b,COUNT(DISTINCT a.photo_id) weight FROM photo_tags a JOIN photo_tags b ON a.photo_id=b.photo_id AND a.tag_id<b.tag_id WHERE a.tag_id IN ({q}) AND b.tag_id IN ({q}) GROUP BY a.tag_id,b.tag_id HAVING weight>=2 ORDER BY weight DESC LIMIT 160''',ids+ids).fetchall()
    return {'nodes':nodes,'edges':[{'a':int(r['a']),'b':int(r['b']),'weight':int(r['weight'])} for r in rows]}

def last_undone_action():
    r=conn().execute("SELECT * FROM action_log WHERE undone=1 AND undo_payload IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone(); return dict(r) if r else None

def mark_action_redone(action_id):
    c=conn(); c.execute('UPDATE action_log SET undone=0 WHERE id=?',(int(action_id),)); c.commit()
