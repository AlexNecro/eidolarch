from __future__ import annotations

import io
import os
import shutil
import subprocess
import threading
import time
import json
import socket
import base64
from datetime import datetime
from pathlib import Path
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, ImageOps, ExifTags
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

from . import db
from .ai import LOCAL_PROFILES, embedder
from .entities import DETECTOR_MODEL, DETECTOR_MODEL_ID, DISPLAY_KIND, entity_indexer
from .indexer import indexer
from .search import vector_index
from .tags import auto_tagger
from .config import SUPPORTED_EXTS, DATA_DIR, THUMB_DIR, DB_PATH
from . import system_ops
from .watcher import watcher
from .diagnostics import tail as log_tail, runtime_info, logger, exception as log_exception, build_error_report

BASE = Path(__file__).resolve().parent
STATIC = BASE / 'static'
_FS_STATS_CACHE = {}
_FS_STATS_LOCK = threading.Lock()
_FS_STATS_TTL = 120.0
db.init_db()
APP_VERSION = '2.3.0'
app = FastAPI(title='Eidolarch', version=APP_VERSION)

@app.middleware('http')
async def _log_unhandled_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        log_exception(f"HTTP {request.method} {request.url.path}", exc)
        raise


class FolderIn(BaseModel):
    path: str


class SettingsIn(BaseModel):
    backend: str = 'auto'
    local_profile: str = 'auto'
    device: str = 'auto'
    remote_base_url: str = ''
    remote_model: str = ''
    remote_api_key: str = ''


class NameDetectionIn(BaseModel):
    name: str
    propagate: bool = True
    threshold: float = 0.88

class UserMetaIn(BaseModel):
    favorite: bool | None = None
    rating: int | None = None
    color_label: str | None = None
    comment: str | None = None

class TagsIn(BaseModel):
    photo_ids: list[int]
    name: str | None = None
    tag_id: int | None = None

class FileOpIn(BaseModel):
    photo_ids: list[int]
    destination: str | None = None
    new_name: str | None = None

class FolderOpIn(BaseModel):
    folder_id: int
    rel: str = ''
    name: str

class IndexControlIn(BaseModel):
    paused: bool | None = None
    intensity: str | None = None

class UiSettingsIn(BaseModel):
    lan_enabled: bool | None = None
    lan_read_only: bool | None = None
    allow_original_download: bool | None = None
    public_url: str | None = None
    duplicate_priority_rules: str | None = None


def _row_get(r, key, default=None):
    try:
        if isinstance(r, dict):
            return r.get(key, default)
        if key in r.keys():
            return r[key]
    except Exception:
        pass
    return default


def photo_json(r, duplicate_count_override=None):
    photo_id = int(_row_get(r, 'id', 0))
    meta = db.get_photo_user_meta(photo_id)
    d = {
        'id': photo_id, 'name': _row_get(r, 'name', ''), 'taken_at': _row_get(r, 'taken_at'),
        'width': _row_get(r, 'width'), 'height': _row_get(r, 'height'),
        'thumbnail': f"/api/photos/{photo_id}/thumbnail?fv={int(_row_get(r, 'mtime_ns', 0) or 0)}-{int(_row_get(r, 'size', 0) or 0)}",
        'preview': f"/api/photos/{photo_id}/original?fv={int(_row_get(r, 'mtime_ns', 0) or 0)}-{int(_row_get(r, 'size', 0) or 0)}",
        'duplicate_count': db.duplicate_count(photo_id) if duplicate_count_override is None else int(duplicate_count_override),
        'path': _row_get(r, 'path', ''),
        'indexed_at': _row_get(r, 'indexed_at'),
        'favorite': bool(_row_get(r, 'favorite', meta['favorite'])),
        'rating': int(_row_get(r, 'rating', meta['rating']) or 0),
        # Vector-search rows historically did not carry file size. Missing optional
        # metadata must never turn a successful AI search into HTTP 500.
        'size': int(_row_get(r, 'size', 0) or 0),
    }
    try:
        if 'score' in r.keys(): d['score'] = r['score']
    except Exception:
        if isinstance(r, dict) and 'score' in r: d['score'] = r['score']
    return d


def photos_json(rows):
    rows=list(rows)
    counts=db.duplicate_counts([int(_row_get(r,'id',0)) for r in rows])
    return [photo_json(r, counts.get(int(_row_get(r,'id',0)),0)) for r in rows]


def _resolve_library_path(folder_id: int, rel: str = '') -> tuple[Path, Path]:
    row = db.get_folder(folder_id)
    if not row:
        raise HTTPException(404, 'Папка библиотеки не найдена')
    root = Path(row['path']).resolve()
    target = (root / rel).resolve() if rel else root
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(400, 'Некорректный путь')
    return root, target


def _lazy_thumb_path(path: Path) -> Path:
    return indexer._thumb_path(path)


def _ensure_browse_photo(folder_id: int, path: Path) -> dict:
    photo_id = db.ensure_photo_stub(folder_id, str(path))
    row = db.get_photo(photo_id)
    return photo_json(row)


@app.get('/api/folder/browse')
def folder_browse(folder_id: int, rel: str = '', limit: int = Query(120, ge=1, le=300), offset: int = Query(0, ge=0), sort: str = 'name_asc'):
    root, target = _resolve_library_path(folder_id, rel)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, 'Папка не существует или недоступна')
    try:
        entries = list(target.iterdir())
    except OSError as e:
        raise HTTPException(500, f'Не удалось прочитать папку: {e}')
    dirs = sorted((x for x in entries if x.is_dir()), key=lambda x: x.name.lower())
    image_files = [x for x in entries if x.is_file() and x.suffix.lower() in SUPPORTED_EXTS]
    def fkey(x):
        try:
            st=x.stat()
            row=db.photo_by_path(str(x))
            if sort in ('size_desc','size_asc'):
                return int((row['size'] if row else None) or st.st_size or 0)
            if sort in ('taken_desc','taken_asc'):
                # Prefer indexed EXIF capture time; before indexing fall back to mtime
                # so the control still has a deterministic visible effect.
                return str((row['taken_at'] if row else None) or datetime.fromtimestamp(st.st_mtime).isoformat())
            if sort=='rating_desc':
                if row:
                    return int(db.get_photo_user_meta(int(row['id'])).get('rating') or 0)
                return 0
            if sort=='added_desc':
                return str((row['indexed_at'] if row else None) or datetime.fromtimestamp(st.st_mtime).isoformat())
        except OSError:
            return 0
        return x.name.lower()
    reverse=sort in ('name_desc','size_desc','taken_desc','rating_desc','added_desc')
    image_files = sorted(image_files, key=fkey, reverse=reverse)
    subfolders = []
    stats=_immediate_subfolder_stats(target)
    for d in dirs:
        st=stats.get(str(d),{})
        subfolders.append({
            'name': d.name,
            'rel': str(d.relative_to(root)),
            'photo_count': int(st.get('direct',0)),
            'recursive_photo_count': int(st.get('recursive',0)),
            'subfolder_count': int(st.get('subfolders',0)),
        })
    page = image_files[offset:offset+limit]
    items = []
    for f in page:
        try:
            items.append(_ensure_browse_photo(folder_id, f))
        except OSError:
            continue
    return {
        'root_id': folder_id,
        'root_path': str(root),
        'rel': str(target.relative_to(root)) if target != root else '',
        'subfolders': subfolders,
        'total': len(image_files),
        'items': items,
    }




def _ratio(value):
    try:
        if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
            return float(value.numerator) / float(value.denominator)
        if isinstance(value, tuple) and len(value) == 2:
            return float(value[0]) / float(value[1])
        return float(value)
    except Exception:
        return None

def _gps_decimal(values, ref):
    try:
        d,m,s = [_ratio(x) for x in values]
        v = d + m/60 + s/3600
        return -v if str(ref).upper() in ('S','W') else v
    except Exception:
        return None

def _photo_exif_info(path: Path):
    info = {}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            tags = {ExifTags.TAGS.get(k,k): v for k,v in exif.items()}
            # Pillow stores GPS IFD separately in recent versions.
            gps = {}
            try:
                gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
                gps = {ExifTags.GPSTAGS.get(k,k): v for k,v in gps_ifd.items()}
            except Exception:
                raw = tags.get('GPSInfo')
                if isinstance(raw, dict):
                    gps = {ExifTags.GPSTAGS.get(k,k): v for k,v in raw.items()}
            lat = _gps_decimal(gps.get('GPSLatitude'), gps.get('GPSLatitudeRef')) if gps else None
            lon = _gps_decimal(gps.get('GPSLongitude'), gps.get('GPSLongitudeRef')) if gps else None
            alt = _ratio(gps.get('GPSAltitude')) if gps else None
            if gps and gps.get('GPSAltitudeRef') == 1 and alt is not None: alt = -alt
            def txt(name):
                v=tags.get(name)
                if v is None: return None
                if isinstance(v, bytes):
                    try: v=v.decode('utf-8','ignore').strip('\x00 ')
                    except Exception: return None
                return str(v).strip() or None
            info = {
                'make': txt('Make'), 'model': txt('Model'), 'lens': txt('LensModel'),
                'software': txt('Software'), 'artist': txt('Artist'),
                'datetime_original': txt('DateTimeOriginal') or txt('DateTimeDigitized') or txt('DateTime'),
                'iso': tags.get('PhotographicSensitivity') or tags.get('ISOSpeedRatings'),
                'fnumber': _ratio(tags.get('FNumber')) if tags.get('FNumber') is not None else None,
                'exposure_time': _ratio(tags.get('ExposureTime')) if tags.get('ExposureTime') is not None else None,
                'focal_length': _ratio(tags.get('FocalLength')) if tags.get('FocalLength') is not None else None,
                'orientation': tags.get('Orientation'), 'latitude': lat, 'longitude': lon, 'altitude': alt,
            }
    except Exception:
        pass
    return info

def _visual_signature_uncached(path: Path):
    import numpy as np
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        # Keep rough composition and colour. A square fit is intentional: this is a
        # low-level visual reranker, not a semantic recogniser.
        small = ImageOps.fit(im, (16,16), method=Image.Resampling.BILINEAR)
        a = np.asarray(small, dtype=np.float32) / 255.0
        # 8-bin histogram per channel.
        hist=[]
        for c in range(3):
            h,_ = np.histogram(a[:,:,c], bins=8, range=(0,1), density=False)
            h=h.astype(np.float32); h/=max(1.0,float(h.sum())); hist.append(h)
        return a, np.concatenate(hist)

@lru_cache(maxsize=4096)
def _visual_signature_cached(path_s: str, mtime_ns: int, size: int):
    return _visual_signature_uncached(Path(path_s))

def _visual_signature(path: Path):
    st = path.stat()
    return _visual_signature_cached(str(path), int(st.st_mtime_ns), int(st.st_size))

def _visual_similarity(sig_a, sig_b):
    import numpy as np
    a,ha=sig_a; b,hb=sig_b
    mse=float(np.mean((a-b)**2))
    pixel=float(np.exp(-7.0*mse))
    hist=float(np.minimum(ha,hb).sum()/3.0)
    return max(0.0,min(1.0,0.72*pixel+0.28*hist))

def _adaptive_similar(items):
    if len(items) < 3: return items
    scores=[float(x.get('score',0)) for x in items]
    gaps=[scores[i]-scores[i+1] for i in range(min(len(scores)-1,15))]
    if not gaps: return items
    import statistics
    med=statistics.median(gaps) if gaps else 0
    best=max(range(len(gaps)), key=lambda i:gaps[i])
    g=gaps[best]
    # Only trust a clearly exceptional gap. Never hide everything: at least one match.
    if g >= 0.08 or (g >= 0.035 and g >= max(0.012, med*2.8)):
        return items[:best+1]
    return items[:20]

def _path_prefix_for_filter(folder_id: int | None, rel: str = '') -> str | None:
    if not folder_id:
        return None
    root, target = _resolve_library_path(folder_id, rel)
    # Prefix includes a separator so sibling folders with similar names do not match.
    return str(target) + os.sep


@app.on_event('startup')
def auto_start_indexing():
    # Give the server a moment to become responsive, then continue all background
    # indexes automatically. Repeated starts are incremental and cheap.
    def later():
        time.sleep(1.2)
        try:
            if db.list_folders() and not indexer.status.running:
                indexer.start()
            # Periodic reconciliation catches files changed outside Eidolarch without a heavy watcher dependency.
            while True:
                time.sleep(60)
                if db.list_folders() and not indexer.status.running:
                    indexer.start()
        except Exception:
            pass
    threading.Thread(target=later, daemon=True, name='EidolarchAutoStart').start()
    try: watcher.start()
    except Exception: pass


@app.middleware('http')
async def lan_safety(request: Request, call_next):
    remote = bool(request.client and request.client.host not in ('127.0.0.1','::1'))
    if remote:
        st=db.get_settings(['lan_enabled','lan_read_only','allow_original_download'])
        if st.get('lan_enabled','1')=='0': return Response('LAN access disabled',status_code=403)
        if request.method not in ('GET','HEAD','OPTIONS') and st.get('lan_read_only','1')!='0': return Response('Read-only LAN mode',status_code=403)
        if request.url.path.endswith('/original') and st.get('allow_original_download','1')=='0': return Response('Original download disabled',status_code=403)
    return await call_next(request)

@app.get('/api/health')
def health(): return {'ok': True}


@app.get('/api/info')
def info():
    active = None
    try:
        if embedder.state.loaded: active = (embedder.state.provider_key, embedder.state.model)
    except Exception:
        pass
    embeddings = db.count_embeddings(*active) if active and active[1] else 0
    entity_stats = {'scanned': 0, 'detections': 0}
    if active and active[1]:
        entity_stats = db.entity_index_stats(DETECTOR_MODEL, active[0], active[1])
    return {
        'version': APP_VERSION, 'settings': embedder.settings(), 'model_state': embedder.state.json(),
        'entity_state': entity_indexer.state.json(), 'entity_stats': entity_stats, 'entities': db.list_entities(),
        'photos': db.count_photos(), 'embeddings': embeddings, 'embedding_sets': db.embedding_sets(),
        'ai_errors': db.count_ai_errors(), 'last_ai_error': db.last_ai_error(), 'index_status': indexer.status.json(), 'profiles': LOCAL_PROFILES,
    }


@app.get('/api/diagnostics')
def diagnostics(lines: int = Query(80, ge=1, le=500)):
    return {
        'version': APP_VERSION,
        'runtime': runtime_info(),
        'model_state': embedder.state.json(),
        'entity_state': entity_indexer.state.json(),
        'index_status': indexer.status.json(),
        'log_tail': log_tail(lines),
    }


@app.get('/api/diagnostics/report')
def diagnostics_report():
    payload = build_error_report(
        app_version=APP_VERSION,
        model_state=embedder.state.json(),
        index_status=indexer.status.json(),
        entity_state=entity_indexer.state.json(),
        settings=embedder.settings(),
    )
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    return Response(
        content=payload,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename=Eidolarch-error-report-{stamp}.zip'},
    )


@app.get('/api/settings')
def settings(): return {'settings': embedder.settings(), 'profiles': LOCAL_PROFILES, 'model_state': embedder.state.json()}


@app.post('/api/settings')
def save_settings(body: SettingsIn):
    if indexer.status.running: raise HTTPException(409, 'Нельзя менять AI-настройки во время индексирования')
    if body.backend not in ('auto', 'local', 'remote'): raise HTTPException(400, 'Некорректный backend')
    if body.local_profile not in ('auto', 'fast', 'quality'): raise HTTPException(400, 'Некорректный профиль')
    if body.device not in ('auto', 'cuda', 'cpu'): raise HTTPException(400, 'Некорректное устройство')
    embedder.save_settings(body.model_dump())
    vector_index._count = -1; vector_index._key = None
    return {'ok': True, 'settings': embedder.settings(), 'model_state': embedder.state.json()}


@app.get('/api/ui-settings')
def ui_settings():
    st=db.get_settings(['lan_enabled','lan_read_only','allow_original_download','public_url','duplicate_priority_rules'])
    return {
        'lan_enabled':st.get('lan_enabled','1')!='0',
        'lan_read_only':st.get('lan_read_only','1')!='0',
        'allow_original_download':st.get('allow_original_download','1')!='0',
        'public_url':st.get('public_url',''),
        'duplicate_priority_rules':st.get('duplicate_priority_rules',''),
    }

@app.post('/api/ui-settings')
def save_ui_settings(body:UiSettingsIn,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403)
    if body.lan_enabled is not None: db.set_setting('lan_enabled','1' if body.lan_enabled else '0')
    if body.lan_read_only is not None: db.set_setting('lan_read_only','1' if body.lan_read_only else '0')
    if body.allow_original_download is not None: db.set_setting('allow_original_download','1' if body.allow_original_download else '0')
    if body.public_url is not None:
        url=body.public_url.strip()
        if url and not (url.startswith('http://') or url.startswith('https://')): raise HTTPException(400,'Внешний адрес должен начинаться с http:// или https://')
        db.set_setting('public_url',url.rstrip('/'))
    if body.duplicate_priority_rules is not None: db.set_setting('duplicate_priority_rules',body.duplicate_priority_rules.strip())
    return ui_settings()

@app.post('/api/model/load')
def load_model():
    if indexer.status.running: raise HTTPException(409, 'Идёт индексирование')
    try:
        embedder.ensure_loaded(); return {'ok': True, 'model_state': embedder.state.json()}
    except Exception as e:
        raise HTTPException(500, f'{type(e).__name__}: {e}')


def _filesystem_tree_counts(root: Path) -> tuple[int,int]:
    key=('root',str(root))
    now=time.time()
    with _FS_STATS_LOCK:
        cached=_FS_STATS_CACHE.get(key)
        if cached and now-cached[0] < _FS_STATS_TTL:
            return cached[1]
    photos=0; folders=0
    try:
        for _, dirs, files in os.walk(root):
            folders += len(dirs)
            photos += sum(1 for fn in files if Path(fn).suffix.lower() in SUPPORTED_EXTS)
    except OSError:
        pass
    value=(photos,folders)
    with _FS_STATS_LOCK:_FS_STATS_CACHE[key]=(now,value)
    return value

def _immediate_subfolder_stats(target: Path):
    key=('children',str(target))
    now=time.time()
    with _FS_STATS_LOCK:
        cached=_FS_STATS_CACHE.get(key)
        if cached and now-cached[0] < _FS_STATS_TTL:
            return cached[1]
    try:
        children=[d for d in target.iterdir() if d.is_dir()]
    except OSError:
        children=[]
    stats={str(d):{'direct':0,'recursive':0,'subfolders':0} for d in children}
    child_by_name={d.name:d for d in children}
    try:
        for walk_root,walk_dirs,walk_files in os.walk(target):
            wr=Path(walk_root)
            try:rel=wr.relative_to(target)
            except ValueError:continue
            parts=rel.parts
            if not parts:continue
            top=child_by_name.get(parts[0])
            if not top:continue
            st=stats[str(top)]
            count=sum(1 for fn in walk_files if Path(fn).suffix.lower() in SUPPORTED_EXTS)
            st['recursive']+=count
            st['subfolders']+=len(walk_dirs)
            if len(parts)==1:st['direct']=count
    except OSError:
        pass
    with _FS_STATS_LOCK:_FS_STATS_CACHE[key]=(now,stats)
    return stats

@app.get('/api/folders')
def folders():
    out=[]
    for r in db.list_folders():
        p=Path(r['path'])
        photos,subfolders=_filesystem_tree_counts(p) if p.exists() else (int(r['photo_count']),0)
        out.append({'id':int(r['id']),'path':r['path'],'photo_count':photos,'indexed_photo_count':int(r['photo_count']),'subfolder_count':subfolders})
    return out

@app.post('/api/folders/pick')
def pick_folder(request: Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403)
    if os.name != 'nt': raise HTTPException(501,'Системный выбор папки доступен в Windows')
    result={'path':''}
    error={'text':''}
    def choose():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root=tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
            result['path']=filedialog.askdirectory(title='Eidolarch — выбрать папку с фотографиями') or ''
            root.destroy()
        except Exception as e:
            error['text']=str(e)
    th=threading.Thread(target=choose,daemon=True); th.start(); th.join()
    if error['text']: raise HTTPException(500,error['text'])
    return result


@app.post('/api/folders')
def add_folder(body: FolderIn):
    p = Path(body.path).expanduser()
    if not p.exists() or not p.is_dir(): raise HTTPException(400, 'Папка не существует или недоступна')
    i = db.add_folder(str(p))
    # New folders should start indexing without another button press.
    if not indexer.status.running: indexer.start()
    return {'id': i, 'path': str(p.resolve())}


@app.delete('/api/folders/{folder_id}')
def delete_folder(folder_id: int):
    if not db.get_folder(folder_id): raise HTTPException(404, 'Папка не найдена')
    db.remove_folder(folder_id); vector_index._count = -1
    return {'ok': True}


@app.post('/api/index/start')
def start_index(): return {'started': indexer.start(), 'status': indexer.status.json()}


@app.get('/api/index/status')
def index_status():
    d=indexer.status.json(); d['paused']=indexer._pause.is_set(); return d


@app.post('/api/tags/rebuild')
def rebuild_tags():
    if indexer.status.running: raise HTTPException(409, 'Дождитесь завершения индексирования')
    try: return {'ok': True, 'done': auto_tagger.rebuild_all()}
    except Exception as e: raise HTTPException(500, f'{type(e).__name__}: {e}')


@app.get('/api/tags')
def tags(selected: str = '', folder_id: int | None = None, rel: str = ''):
    embedder.ensure_loaded(); ids = [int(x) for x in selected.split(',') if x.strip().isdigit()]
    prefix = _path_prefix_for_filter(folder_id, rel) if rel else None
    return {'items': db.list_tags(ids, folder_id, embedder.provider_key, embedder.model_id, path_prefix=prefix), 'selected': ids}


@app.get('/api/entities')
def entities():
    return {'items': db.list_entities(), 'detector': DETECTOR_MODEL}


@app.get('/api/photos')
def gallery(limit: int = Query(120, ge=1, le=300), offset: int = Query(0, ge=0), folder_id: int | None = None, tags: str = '', rel: str = '', sort: str = 'taken_desc', favorite: bool = False, min_rating: int = 0):
    ids = [int(x) for x in tags.split(',') if x.strip().isdigit()]
    pk = embedder.provider_key if embedder.state.loaded else None
    model = embedder.model_id if embedder.state.loaded else None
    prefix = _path_prefix_for_filter(folder_id, rel) if rel else None
    rows = db.list_gallery_sorted(limit, offset, folder_id, ids, pk, model, path_prefix=prefix, sort=sort, favorite_only=favorite, min_rating=min_rating)
    return {'total': db.count_gallery_extended(folder_id, ids, pk, model, path_prefix=prefix, favorite_only=favorite, min_rating=min_rating), 'items': photos_json(rows)}


@app.get('/api/search')
def search(q: str = Query(min_length=1), limit: int = Query(80, ge=1, le=300), folder_id: int | None = None, tags: str = '', rel: str = '', sort: str = 'relevance_desc'):
    try:
        import re
        query=q.strip()
        tag_ids = [int(x) for x in tags.split(',') if x.strip().isdigit()]
        prefix = _path_prefix_for_filter(folder_id, rel) if rel else None

        # @name is an exact named-entity filter. Multiple @tokens use AND semantics.
        # Keep the remaining plain text as an optional semantic query.
        tokens=re.findall(r'(?<!\S)@([^\s@#]+)', query)
        entities=db.list_entities()
        by_name={str(e['name']).casefold():e for e in entities}
        entity_ids=[]; unknown=[]
        for token in tokens:
            ent=by_name.get(token.casefold())
            if ent: entity_ids.append(int(ent['id']))
            else: unknown.append(token)
        semantic_query=re.sub(r'(?<!\S)@[^\s@#]+',' ',query)
        semantic_query=' '.join(semantic_query.split())

        pk = embedder.provider_key if embedder.state.loaded else None
        model = embedder.model_id if embedder.state.loaded else None
        scope_ids=db.photo_ids_for_filters(folder_id, tag_ids, pk, model, path_prefix=prefix) if (folder_id or tag_ids or prefix) else None
        entity_photo_ids=db.photo_ids_for_entities(entity_ids) if entity_ids else None

        if unknown:
            return {'query':q,'mode':'entity','unknown_entities':unknown,'indexed':db.count_embeddings(pk,model) if pk and model else 0,'indexing':bool(indexer.status.running),'model':model,'items':[]}

        allowed=None
        if scope_ids is not None: allowed=set(scope_ids)
        if entity_photo_ids is not None: allowed=set(entity_photo_ids) if allowed is None else allowed.intersection(entity_photo_ids)

        # Pure @entity query does not need the embedding model at all.
        if entity_ids and not semantic_query:
            rows=db.list_photos_by_ids(allowed or set(), limit=limit, sort=sort if sort!='relevance_desc' else 'taken_desc')
            return {'query':q,'mode':'entity','entities':entity_ids,'indexed':db.count_embeddings(pk,model) if pk and model else 0,'indexing':bool(indexer.status.running),'model':model,'items':photos_json(rows)}

        embedder.ensure_loaded(); indexed = db.count_embeddings(embedder.provider_key, embedder.model_id)
        if indexed == 0: raise HTTPException(409, 'Для выбранной модели ещё нет AI-индекса. Запустите индексирование.')
        if allowed is not None and not allowed:
            return {'query':q,'mode':'entity+semantic' if entity_ids else 'semantic','entities':entity_ids,'indexed':indexed,'indexing':bool(indexer.status.running),'model':embedder.model_id,'items':[]}

        # Fetch a wider relevance shortlist when a non-relevance ordering is requested,
        # then order the visible result set explicitly.
        raw = vector_index.search(semantic_query or query, max(limit, 300 if sort!='relevance_desc' else limit), allowed)
        items=photos_json(raw)
        def sk(x):
            if sort=='taken_desc' or sort=='taken_asc': return x.get('taken_at') or ''
            if sort=='name_asc' or sort=='name_desc': return (x.get('name') or '').lower()
            if sort=='size_desc' or sort=='size_asc': return int(x.get('size') or 0)
            if sort=='rating_desc': return int(x.get('rating') or 0)
            if sort=='added_desc': return x.get('indexed_at') or ''
            return float(x.get('score') or 0)
        rev=sort in ('relevance_desc','taken_desc','name_desc','size_desc','rating_desc','added_desc')
        if sort!='relevance_desc': items=sorted(items,key=sk,reverse=rev)
        items=items[:limit]
        return {'query': q, 'mode':'entity+semantic' if entity_ids else 'semantic', 'entities':entity_ids, 'indexed': indexed, 'indexing': bool(indexer.status.running), 'model': embedder.model_id, 'items': items}
    except HTTPException:
        raise
    except Exception as e:
        log_exception('AI search', e)
        raise HTTPException(500, f'Ошибка AI-поиска: {type(e).__name__}: {e}')


@app.get('/api/photos/{photo_id}/similar')
def similar(photo_id: int, limit: int = Query(80, ge=1, le=200)):
    embedder.ensure_loaded()
    source = db.get_photo(photo_id)
    if not source: raise HTTPException(404, 'Фото не найдено')
    # SigLIP gives a semantic shortlist; a cheap colour/composition signature then
    # reranks it so near-identical scenes beat merely similar subjects.
    semantic = vector_index.similar_photo(photo_id, min(160, max(limit*2, 80)))
    try:
        refsig = _visual_signature(Path(source['path']))
        rescored=[]
        semvals=[float(x.get('score',0)) for x in semantic]
        lo=min(semvals) if semvals else 0; hi=max(semvals) if semvals else 1; span=max(1e-6,hi-lo)
        for r in semantic:
            m=dict(r)
            try: vis=_visual_similarity(refsig,_visual_signature(Path(m['path'])))
            except Exception: vis=0.0
            sem=(float(m.get('score',0))-lo)/span
            m['semantic_score']=float(m.get('score',0)); m['visual_score']=vis
            m['score']=0.68*vis+0.32*sem
            rescored.append(m)
        rescored.sort(key=lambda x:x['score'], reverse=True)
        items=_adaptive_similar(rescored)[:limit]
    except Exception:
        items=semantic[:min(limit,20)]
    try:
        counts=db.duplicate_counts([int(_row_get(r,'id',0)) for r in items])
        result=[]
        for r in items:
            pid=int(_row_get(r,'id',0))
            result.append(photo_json(r,counts.get(pid,0)) | {'visual_score': r.get('visual_score'), 'semantic_score': r.get('semantic_score')})
        return {'photo_id': photo_id, 'items': result}
    except Exception as e:
        log_exception(f'Similar photos for {photo_id}', e)
        raise HTTPException(500, {'code':'error.similarFailed','detail':f'{type(e).__name__}: {e}'})

@app.get('/api/duplicates')
def duplicate_gallery(limit: int = Query(120, ge=1, le=300), offset: int = Query(0, ge=0), sort: str = 'taken_desc'):
    rows, total = db.list_duplicate_photos(limit, offset, sort=sort)
    return {'total': total, 'items': photos_json(rows)}

@app.get('/api/duplicate-location-groups')
def duplicate_location_groups(limit: int = Query(80, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Group current exact duplicates by physical parent directory.

    The matcher is intentionally isolated in db.exact_duplicate_rows(). The UI does
    not know about SHA-256. If the definition of a duplicate changes later, that
    database helper can be replaced without redesigning this workspace.

    Pair relations may overlap. A weak A<->B relation is omitted only when every
    file in it is already present through a stronger common location C. This avoids
    a couple of cross-folder files gluing otherwise useful groups together.
    """
    from collections import defaultdict
    from itertools import combinations
    import hashlib

    rows=[dict(r) for r in db.exact_duplicate_rows()]
    by_hash=defaultdict(lambda: defaultdict(list))
    for r in rows:
        loc=str(Path(r['path']).parent)
        by_hash[str(r['sha256'])][loc].append(r)

    edge_keys=defaultdict(set)
    local_only=defaultdict(set)
    for key,locmap in by_hash.items():
        locs=sorted(locmap.keys(), key=str.casefold)
        if len(locs)==1:
            loc=locs[0]
            if len(locmap[loc])>1:
                local_only[loc].add(key)
            continue
        for a,b in combinations(locs,2):
            edge=(a,b) if a.casefold()<=b.casefold() else (b,a)
            edge_keys[edge].add(key)

    edge_weight={edge:len(keys) for edge,keys in edge_keys.items()}
    filtered_edges={}
    for (a,b),keys in edge_keys.items():
        keep=set()
        current=edge_weight[(a,b)]
        third_locations=set()
        for key in keys:
            third_locations.update(x for x in by_hash[key].keys() if x not in (a,b))
        for key in keys:
            redundant=False
            for c in third_locations:
                if c not in by_hash[key]:
                    continue
                ac=(a,c) if a.casefold()<=c.casefold() else (c,a)
                bc=(b,c) if b.casefold()<=c.casefold() else (c,b)
                wa=edge_weight.get(ac,0); wb=edge_weight.get(bc,0)
                if wa>=current and wb>=current and (wa>current or wb>current):
                    redundant=True
                    break
            if not redundant:
                keep.add(key)
        if keep:
            filtered_edges[(a,b)]=keep

    specs=[(list(edge),keys) for edge,keys in filtered_edges.items()]
    specs.extend(([loc],keys) for loc,keys in local_only.items())

    def key_sort(key):
        paths=[x['path'] for locrows in by_hash[key].values() for x in locrows]
        return min(paths,key=str.casefold).casefold()

    groups=[]
    for locations,keys_set in specs:
        keys=sorted(keys_set,key=key_sort)
        locations_json=[]
        for loc in locations:
            files=[]
            for logical_index,key in enumerate(keys):
                for r in by_hash[key].get(loc,[]):
                    pid=int(r['id'])
                    files.append({
                        'id':pid,'name':r.get('name') or Path(r['path']).name,'path':r['path'],
                        'size':int(r.get('size') or 0),'taken_at':r.get('taken_at'),
                        'width':r.get('width'),'height':r.get('height'),
                        'thumbnail':f"/api/photos/{pid}/thumbnail?fv={int(r.get('mtime_ns') or 0)}-{int(r.get('size') or 0)}",
                        'logical_index':logical_index,
                        'logical_id':hashlib.blake2s(key.encode('utf-8'),digest_size=8).hexdigest(),
                        'marker_index':int(hashlib.blake2s(key.encode('utf-8'),digest_size=2).hexdigest(),16)%12,
                    })
            locations_json.append({
                'path':loc,
                'priority':_duplicate_path_score(loc),
                'file_count':len(files),
                'files':files,
            })
        reclaimable=0
        for key in keys:
            copies=sum(len(v) for v in by_hash[key].values() if v and (len(locations)==1 or next(iter(v))['path'] and str(Path(next(iter(v))['path']).parent) in locations))
            sample=next(x for locrows in by_hash[key].values() for x in locrows)
            reclaimable+=max(1,copies-1)*int(sample.get('size') or 0)
        groups.append({
            'id':f'g{len(groups)+1}',
            'logical_count':len(keys),
            'file_count':sum(x['file_count'] for x in locations_json),
            'location_count':len(locations_json),
            'reclaimable_bytes':reclaimable,
            'locations':locations_json,
        })

    groups.sort(key=lambda g:(-g['logical_count'],-g['reclaimable_bytes'],tuple(x['path'].casefold() for x in g['locations'])))
    total=len(groups)
    return {'total':total,'groups':groups[offset:offset+limit]}


@app.get('/api/photos/{photo_id}/info')
def photo_info(photo_id: int):
    r=db.get_photo(photo_id)
    if not r: raise HTTPException(404,'Фото не найдено')
    p=Path(r['path'])
    if not p.exists(): raise HTTPException(404,'Файл не найден')
    ex=_photo_exif_info(p)
    return {
        'id': int(r['id']), 'name': r['name'], 'path': r['path'], 'folder': str(p.parent),
        'size': int(r['size'] or p.stat().st_size), 'width': r['width'], 'height': r['height'],
        'taken_at': r['taken_at'], 'modified_at': datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'),
        'suffix': p.suffix.lstrip('.').upper(), 'exif': ex, 'tags': db.photo_tags_for_info(photo_id),
        'duplicate_count': db.duplicate_count(photo_id), 'user_meta': db.get_photo_user_meta(photo_id),
    }


def _duplicate_path_score(path: str) -> int:
    raw=db.get_settings(['duplicate_priority_rules']).get('duplicate_priority_rules','')
    score=0; p=os.path.normcase(os.path.normpath(path))
    for line in raw.splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        try:
            weight_s,pattern=line.split('|',1); weight=int(weight_s.strip()); pattern=os.path.normcase(os.path.normpath(pattern.strip()))
        except Exception:
            continue
        if pattern and (p==pattern or p.startswith(pattern+os.sep)):
            score += weight
    return score

@app.get('/api/photos/{photo_id}/duplicates')
def duplicates(photo_id: int):
    current=db.get_photo(photo_id)
    if not current: raise HTTPException(404, {'code':'error.photoNotFound'})
    current_json=photo_json(current, db.duplicate_count(photo_id))
    current_json['is_current']=True
    current_json['path_priority']=_duplicate_path_score(current_json.get('path',''))
    ids=[photo_id,*db.photo_ids_by_hash(photo_id)]
    ids=list(dict.fromkeys(int(x) for x in ids))
    rows=db.photo_rows_by_ids(ids)
    counts=db.duplicate_counts(ids)
    group=[]
    for r in rows:
        d=photo_json(r,counts.get(int(r['id']),0))
        d['match_type']='exact'
        d['path_priority']=_duplicate_path_score(d.get('path',''))
        d['is_current']=int(r['id'])==int(photo_id)
        d['_rank']=(d['path_priority'], int((d.get('width') or 0)*(d.get('height') or 0)), int(d.get('size') or 0), 1 if d.get('taken_at') else 0)
        group.append(d)
    if group:
        winner=max(group, key=lambda x:(x['_rank'], 1 if x['is_current'] else 0, -int(x['id'])))
        for x in group:
            x['recommended_keep']=x is winner
            x.pop('_rank',None)
    cur=next((x for x in group if x['is_current']),current_json)
    others=[x for x in group if not x['is_current']]
    return {
        'photo_id':photo_id,'current':cur,'items':others,
        'exact_count':len(others),
        'near_count':0
    }


@app.get('/api/photos/{photo_id}/detections')
def detections(photo_id: int):
    if not db.get_photo(photo_id): raise HTTPException(404, {'code':'error.photoNotFound'})
    items = []
    for r in db.list_detections(photo_id):
        items.append({'id': int(r['id']), 'kind': r['kind'], 'kind_label_key': DISPLAY_KIND.get(r['kind'], 'entity.kind.unknown'),
                      'score': float(r['score']), 'entity_id': r['entity_id'], 'entity_name': r['entity_name'],
                      'x1': float(r['x1']), 'y1': float(r['y1']), 'x2': float(r['x2']), 'y2': float(r['y2']),
                      'crop': f"/api/detections/{int(r['id'])}/crop"})
    try:
        pk=embedder.provider_key if embedder.state.loaded else None
        mid=embedder.model_id if embedder.state.loaded else None
    except Exception:
        pk=mid=None
    scan=db.entity_scan_status(photo_id, DETECTOR_MODEL, pk, mid) if pk and mid else db.entity_scan_status(photo_id)
    p=db.get_photo(photo_id)
    return {'photo_id': photo_id, 'items': items, 'scan': scan, 'detector_model': DETECTOR_MODEL_ID, 'scan_key': DETECTOR_MODEL,
            'width': int(p['width'] or 0) if p else 0, 'height': int(p['height'] or 0) if p else 0}

@app.post('/api/photos/{photo_id}/redetect')
def redetect_photo(photo_id: int, request: Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'):
        raise HTTPException(403, {'code':'error.localOnly'})
    r=db.get_photo(photo_id)
    if not r: raise HTTPException(404, {'code':'error.photoNotFound'})
    try:
        found=entity_indexer.process_photo(r, force=True)
        return {'ok':True,'photo_id':photo_id,'detections':found,'scan_key':DETECTOR_MODEL}
    except Exception as e:
        log_exception(f'redetect photo {photo_id}',e)
        raise HTTPException(500, {'code':'error.redetectFailed','detail':f'{type(e).__name__}: {e}'})

@app.get('/api/photos/{photo_id}/detection-diagnostics')
def detection_diagnostics(photo_id: int):
    r=db.get_photo(photo_id)
    if not r: raise HTTPException(404, {'code':'error.photoNotFound'})
    p=Path(r['path'])
    if not p.exists(): raise HTTPException(404, {'code':'error.fileNotFound'})
    try:
        with Image.open(p) as im:
            image=ImageOps.exif_transpose(im).convert('RGB')
            live=entity_indexer.diagnose(image, threshold=0.10)
        stored=detections(photo_id)
        logger().info('Detection diagnostics photo=%s stored=%s live_targets=%s',photo_id,len(stored.get('items',[])),len(live.get('target_predictions',[])))
        return {'photo_id':photo_id,'path':r['path'],'stored':stored,'live':live,'entity_state':entity_indexer.state.json()}
    except Exception as e:
        log_exception(f'detection diagnostics {photo_id}',e)
        raise HTTPException(500, {'code':'error.detectionDiagnosticsFailed','detail':f'{type(e).__name__}: {e}'})


@app.get('/api/detections/{detection_id}/crop')
def detection_crop(detection_id: int):
    d = db.get_detection(detection_id)
    if not d: raise HTTPException(404, 'Объект не найден')
    p = db.get_photo(int(d['photo_id']))
    if not p or not Path(p['path']).exists(): raise HTTPException(404, 'Исходный файл не найден')
    with Image.open(p['path']) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        crop = im.crop((max(0, int(d['x1'])), max(0, int(d['y1'])), min(im.width, int(d['x2'])), min(im.height, int(d['y2']))))
        buf = io.BytesIO(); crop.thumbnail((400, 400), Image.Resampling.LANCZOS); crop.save(buf, 'JPEG', quality=88)
    return Response(buf.getvalue(), media_type='image/jpeg', headers={'Cache-Control': 'public, max-age=86400'})


@app.post('/api/detections/{detection_id}/name')
def name_detection(detection_id: int, body: NameDetectionIn):
    try:
        return {'ok': True, **entity_indexer.name_detection(detection_id, body.name, body.propagate, body.threshold)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f'{type(e).__name__}: {e}')


@app.get('/api/photos/{photo_id}/thumbnail')
def thumbnail(photo_id: int):
    r = db.get_photo(photo_id)
    if not r: raise HTTPException(404, {'code':'error.photoNotFound'})
    src = Path(r['path'])
    if not src.exists(): raise HTTPException(404, {'code':'error.fileNotFound'})
    # Always derive the cache file from current source identity. Stored thumb_path is
    # metadata only; it must not resurrect a thumbnail generated for older contents.
    p = _lazy_thumb_path(src)
    if not p.exists():
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                width, height = im.size
                taken_at = indexer._taken_at(im)
                thumb = im.convert('RGB')
                thumb.thumbnail((480, 480), Image.Resampling.LANCZOS)
                p.parent.mkdir(parents=True, exist_ok=True)
                thumb.save(p, 'JPEG', quality=85, optimize=True)
                db.set_thumbnail(photo_id, str(p), width, height, taken_at)
        except Exception as e:
            raise HTTPException(500, {'code':'error.thumbnailFailed','detail':f'{type(e).__name__}: {e}'})
    etag = f'"{src.stat().st_mtime_ns:x}-{src.stat().st_size:x}"'
    return FileResponse(p, media_type='image/jpeg', headers={'Cache-Control': 'public, max-age=31536000, immutable','ETag':etag})

@app.post('/api/photos/{photo_id}/thumbnail/rebuild')
def rebuild_thumbnail(photo_id: int, request: Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'):
        raise HTTPException(403, {'code':'error.localOnly'})
    r=db.get_photo(photo_id)
    if not r: raise HTTPException(404, {'code':'error.photoNotFound'})
    src=Path(r['path'])
    if not src.exists(): raise HTTPException(404, {'code':'error.fileNotFound'})
    p=_lazy_thumb_path(src)
    try:
        if p.exists(): p.unlink()
    except OSError: pass
    db.clear_thumbnail(photo_id)
    return {'ok':True,'photo_id':photo_id}


@app.get('/api/photos/{photo_id}/original')
def original(photo_id: int):
    r = db.get_photo(photo_id)
    if not r: raise HTTPException(404)
    p = Path(r['path'])
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p, headers={'Cache-Control':'no-store'})


@app.get('/api/system/network')
def network(request: Request):
    port=request.url.port or 80
    addresses=system_ops.lan_addresses(port)
    st=db.get_settings(['public_url'])
    public_url=st.get('public_url','').strip().rstrip('/')
    if public_url and all(a.get('url')!=public_url for a in addresses):
        addresses.append({'url':public_url,'label':'Public / custom','external':True})
    return {'addresses': addresses, 'hostname': socket.gethostname(), 'public_url':public_url}

@app.get('/api/system/network/qr')
def network_qr(url: str):
    try:
        import qrcode
        img=qrcode.make(url); buf=io.BytesIO(); img.save(buf,format='PNG')
        return Response(buf.getvalue(),media_type='image/png',headers={'Cache-Control':'no-store'})
    except Exception as e: raise HTTPException(500,str(e))

@app.post('/api/index/control')
def index_control(body: IndexControlIn):
    if body.paused is not None: indexer.set_paused(body.paused)
    if body.intensity is not None: indexer.set_intensity(body.intensity)
    return {'paused':indexer._pause.is_set(),'intensity':indexer._intensity,'status':indexer.status.json()}

@app.get('/api/jobs')
def jobs():
    s=indexer.status.json(); phase=s.get('phase','idle')
    total=max(1,int(s.get('total') or 0)); done=int(s.get('done') or 0); emb=int(s.get('embeddings_done') or 0); hashes=int(s.get('hashes_done') or 0)
    et=max(1,int(s.get('entity_total') or 0)); ed=int(s.get('entity_done') or 0)
    return {'running':bool(s.get('running')),'paused':indexer._pause.is_set(),'intensity':indexer._intensity,'jobs':[
      {'id':'catalog','label':'Каталогизация','percent':min(100,round(done*100/total,1)),'active':phase in ('scanning','indexing')},
      {'id':'embeddings','label':'Embeddings','percent':min(100,round(emb*100/total,1)),'active':phase=='indexing'},
      {'id':'tags','label':'Автотеги','percent':min(100,round(emb*100/total,1)),'active':phase=='indexing'},
      {'id':'duplicates','label':'Дубликаты','percent':min(100,round(hashes*100/total,1)),'active':phase=='indexing'},
      {'id':'entities','label':'Лица/животные','percent':min(100,round(ed*100/et,1)) if s.get('entity_total') else 0,'active':phase=='entities'}]}

@app.post('/api/photos/{photo_id}/meta')
def save_photo_meta(photo_id:int,body:UserMetaIn):
    if not db.get_photo(photo_id): raise HTTPException(404,'Фото не найдено')
    return db.set_photo_user_meta(photo_id,body.favorite,body.rating,body.color_label,body.comment)

@app.post('/api/tags/manual')
def add_manual_tags(body:TagsIn):
    if not body.name: raise HTTPException(400,'Укажите тег')
    return {'added':db.add_manual_tag(body.photo_ids,body.name)}

@app.delete('/api/tags/manual')
def remove_manual_tags(body:TagsIn):
    if body.tag_id is None: raise HTTPException(400,'Укажите tag_id')
    return {'removed':db.remove_manual_tag(body.photo_ids,body.tag_id)}

@app.post('/api/files/copy')
def file_copy(body:FileOpIn,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Файловые операции доступны только локально')
    try:return {'items':system_ops.copy_or_move(body.photo_ids,body.destination or '',False)}
    except Exception as e:raise HTTPException(400,str(e))

@app.post('/api/files/move')
def file_move(body:FileOpIn,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Файловые операции доступны только локально')
    try:return {'items':system_ops.copy_or_move(body.photo_ids,body.destination or '',True)}
    except Exception as e:raise HTTPException(400,str(e))

@app.post('/api/files/rename/{photo_id}')
def file_rename(photo_id:int,body:FileOpIn,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Файловые операции доступны только локально')
    try:return {'path':system_ops.rename_photo(photo_id,body.new_name or '')}
    except Exception as e:raise HTTPException(400,str(e))

@app.post('/api/files/trash')
def file_trash(body:FileOpIn,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Файловые операции доступны только локально')
    try:return {'items':system_ops.trash_photos(body.photo_ids)}
    except Exception as e:raise HTTPException(400,str(e))

@app.post('/api/files/undo')
def file_undo(request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Undo доступен только локально')
    return system_ops.undo_last()

@app.post('/api/photos/{photo_id}/open-folder')
def open_folder(photo_id:int,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Доступно только локально')
    r=db.get_photo(photo_id)
    if not r: raise HTTPException(404)
    try:system_ops.open_in_explorer(r['path']);return {'ok':True}
    except Exception as e:raise HTTPException(500,str(e))

@app.post('/api/photos/{photo_id}/open-external')
def open_external(photo_id:int,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Доступно только локально')
    r=db.get_photo(photo_id)
    if not r: raise HTTPException(404)
    try:system_ops.open_external(r['path']);return {'ok':True}
    except Exception as e:raise HTTPException(500,str(e))

@app.post('/api/folder/create')
def create_subfolder(body:FolderOpIn,request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403)
    root,target=_resolve_library_path(body.folder_id,body.rel)
    name=Path(body.name).name
    if not name or name in ('.','..'): raise HTTPException(400,'Некорректное имя папки')
    p=target/name
    try:p.mkdir(exist_ok=False);return {'ok':True,'rel':str(p.relative_to(root))}
    except FileExistsError:raise HTTPException(409,'Папка уже существует')
    except OSError as e:raise HTTPException(400,str(e))

@app.get('/api/graph')
def graph(): return db.tag_graph()

@app.post('/api/files/redo')
def file_redo(request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403,'Redo доступен только локально')
    return system_ops.redo_last()

@app.get('/api/storage')
def storage(): return db.storage_stats()

@app.post('/api/cache/clear')
def clear_cache(request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403)
    return {'removed_bytes':system_ops.clear_derived_cache()}

@app.post('/api/backup')
def backup(request:Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'): raise HTTPException(403)
    return {'path':system_ops.export_backup()}

@app.get('/api/locales/{lang}.json')
def locale_file(lang:str):
    lang='ru' if lang.lower().startswith('ru') else 'en'
    p=BASE/'locales'/f'{lang}.json'
    return FileResponse(p,media_type='application/json')

@app.post('/api/system/recycle-bin')
def open_recycle_bin(request: Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'):
        raise HTTPException(403, 'Доступно только локально')
    try:
        system_ops.open_recycle_bin()
        return {'ok': True}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post('/api/window/viewer/{photo_id}')
def open_viewer_window(photo_id: int, request: Request, tab: str = 'info', ctx: str = 'single', ids: str = ''):
    if request.client and request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(403, 'Открытие окна доступно только локально')
    if not db.get_photo(photo_id):
        raise HTTPException(404, 'Фото не найдено')
    candidates = [
        os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
        os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
        os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'),
        os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
    ]
    browser = next((p for p in candidates if p and os.path.isfile(p)), None) or shutil.which('msedge') or shutil.which('chrome')
    if not browser:
        raise HTTPException(500, 'Edge/Chrome не найден')
    base = str(request.base_url).rstrip('/')
    profile = str((BASE.parent / '.browser-profile').resolve())
    safe_tab = tab if tab in ('info','objects','similar','duplicates') else 'info'
    safe_ctx = ctx if ctx in ('main','similar','duplicates','single') else 'single'
    clean_ids = ','.join(str(int(x)) for x in ids.split(',') if x.strip().isdigit())[:5000]
    url = f'{base}/viewer?photo={int(photo_id)}&tab={safe_tab}&ctx={safe_ctx}&ids={clean_ids}&v={APP_VERSION}'
    subprocess.Popen([browser, f'--app={url}', f'--user-data-dir={profile}', '--no-first-run'])
    return {'ok': True}


@app.post('/api/window/help')
def open_help_window(request: Request, lang: str = 'ru'):
    if request.client and request.client.host not in ('127.0.0.1','::1'):
        raise HTTPException(403, {'code':'error.localOnly'})
    candidates = [os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe')]
    browser = next((p for p in candidates if p and os.path.isfile(p)), None) or shutil.which('msedge') or shutil.which('chrome')
    if not browser: raise HTTPException(500, {'code':'error.browserNotFound'})
    base=str(request.base_url).rstrip('/')
    profile=str((BASE.parent/'.browser-profile').resolve())
    safe='ru' if str(lang).lower().startswith('ru') else 'en'
    url=f'{base}/help?lang={safe}&v={APP_VERSION}'
    subprocess.Popen([browser,f'--app={url}',f'--user-data-dir={profile}','--no-first-run'])
    return {'ok':True}

@app.post('/api/window/graph')
def open_graph_window(request: Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'):
        raise HTTPException(403, {'code':'error.localOnly'})
    candidates = [os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe')]
    browser = next((p for p in candidates if p and os.path.isfile(p)), None) or shutil.which('msedge') or shutil.which('chrome')
    if not browser: raise HTTPException(500, {'code':'error.browserNotFound'})
    base=str(request.base_url).rstrip('/')
    profile=str((BASE.parent/'.browser-profile').resolve())
    url=f'{base}/graph?v={APP_VERSION}'
    subprocess.Popen([browser,f'--app={url}',f'--user-data-dir={profile}','--no-first-run'])
    return {'ok':True}

@app.post('/api/window/settings')
def open_settings_window(request: Request):
    if request.client and request.client.host not in ('127.0.0.1','::1'):
        raise HTTPException(403, {'code':'error.localOnly'})
    candidates = [os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe')]
    browser = next((p for p in candidates if p and os.path.isfile(p)), None) or shutil.which('msedge') or shutil.which('chrome')
    if not browser: raise HTTPException(500, {'code':'error.browserNotFound'})
    base=str(request.base_url).rstrip('/')
    profile=str((BASE.parent/'.browser-profile').resolve())
    url=f'{base}/settings?v={APP_VERSION}'
    subprocess.Popen([browser,f'--app={url}',f'--user-data-dir={profile}','--no-first-run'])
    return {'ok':True}


@app.post('/api/window/new')
def new_window(request: Request):
    if request.client and request.client.host not in ('127.0.0.1', '::1'): raise HTTPException(403, 'Открытие окна доступно только локально')
    candidates = [os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'), os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe')]
    browser = next((p for p in candidates if p and os.path.isfile(p)), None) or shutil.which('msedge') or shutil.which('chrome')
    if not browser: raise HTTPException(500, 'Edge/Chrome не найден')
    base = str(request.base_url).rstrip('/')
    profile = str((BASE.parent / '.browser-profile').resolve())
    subprocess.Popen([browser, f'--app={base}/?window={time.time_ns()}', f'--user-data-dir={profile}', '--no-first-run'])
    return {'ok': True}


@app.get('/sw.js')
def service_worker(): return FileResponse(STATIC/'sw.js',media_type='application/javascript',headers={'Service-Worker-Allowed':'/','Cache-Control':'no-cache, no-store, must-revalidate'})

@app.get('/manifest.json')
def manifest(): return FileResponse(STATIC/'manifest.json',media_type='application/manifest+json',headers={'Cache-Control':'no-cache'})

app.mount('/assets', StaticFiles(directory=STATIC), name='assets')


@app.get('/favicon.ico', include_in_schema=False)
def favicon(): return FileResponse(STATIC/'icons'/'app.ico', media_type='image/x-icon', headers={'Cache-Control':'public, max-age=86400'})

def _versioned_html(path: Path):
    # HTML shells contain cache-busting query strings and a visible version badge.
    # Inject the backend version at serve time so releases cannot drift merely
    # because one static HTML file missed a mechanical version bump.
    import re
    html=path.read_text(encoding='utf-8')
    html=re.sub(r'2\.\d+\.\d+', APP_VERSION, html)
    return Response(html, media_type='text/html', headers={'Cache-Control':'no-cache, no-store, must-revalidate'})

@app.get('/graph')
def graph_page():
    return _versioned_html(STATIC / 'graph.html')

@app.get('/viewer')
def viewer_page(): return _versioned_html(STATIC / 'viewer.html')

@app.get('/settings')
def settings_page(): return _versioned_html(STATIC / 'settings.html')

@app.get('/help.css', include_in_schema=False)
def help_css():
    return FileResponse(STATIC / 'help' / 'help.css', media_type='text/css', headers={'Cache-Control':'no-cache, no-store, must-revalidate'})

@app.get('/help')
def help_page(lang: str = 'ru'):
    safe='ru' if str(lang).lower().startswith('ru') else 'en'
    return _versioned_html(STATIC / 'help' / f'{safe}.html')

@app.get('/')
def home(): return _versioned_html(STATIC / 'index.html')
