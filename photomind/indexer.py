from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

from . import db
from .ai import embedder
from .config import SUPPORTED_EXTS, THUMB_DIR, THUMB_SIZE
from .entities import DETECTOR_MODEL, entity_indexer
from .tags import auto_tagger
from .diagnostics import logger, exception as log_exception


@dataclass
class IndexStatus:
    running: bool = False
    phase: str = 'idle'
    message: str = 'Готов к работе'
    current_file: str = ''
    total: int = 0
    done: int = 0
    added_or_updated: int = 0
    embeddings_done: int = 0
    hashes_done: int = 0
    entity_total: int = 0
    entity_done: int = 0
    detections_done: int = 0
    skipped: int = 0
    errors: int = 0
    ai_errors: int = 0
    entity_errors: int = 0
    removed: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_photo: float | None = None
    eta_seconds: float | None = None
    photos_per_minute: float | None = None
    last_error: str | None = None
    entity_suspended: bool = False
    entity_suspend_reason: str | None = None
    entity_last_error: str | None = None

    def json(self):
        d = asdict(self)
        if self.phase == 'entities' and self.entity_total:
            d['percent'] = round(self.entity_done * 100 / self.entity_total, 1)
        else:
            d['percent'] = round(self.done * 100 / self.total, 1) if self.total else 0
        d['elapsed_seconds'] = round(max(0, (self.finished_at or time.time()) - self.started_at), 1) if self.started_at else 0
        if self.avg_seconds_per_photo is not None:
            d['avg_seconds_per_photo'] = round(self.avg_seconds_per_photo, 3)
        if self.eta_seconds is not None:
            d['eta_seconds'] = round(max(0, self.eta_seconds), 1)
        if self.photos_per_minute is not None:
            d['photos_per_minute'] = round(self.photos_per_minute, 2)
        return d


class Indexer:
    def __init__(self):
        self.status = IndexStatus()
        self._lock = threading.Lock()
        self._thread = None
        self._pause = threading.Event()
        self._intensity = 'balanced'

    def start(self):
        with self._lock:
            if self.status.running:
                return False
            self.status = IndexStatus(running=True, phase='scanning', message='Сканирую папки и считаю фотографии…', started_at=time.time())
            self._thread = threading.Thread(target=self._run, daemon=True, name='EidolarchIndexer')
            self._thread.start()
            return True

    def set_paused(self, paused: bool):
        if paused: self._pause.set()
        else: self._pause.clear()
        return self._pause.is_set()

    def set_intensity(self, mode: str):
        mode={'max':'performance','background':'eco'}.get(mode,mode); self._intensity = mode if mode in ('performance','balanced','eco') else 'balanced'
        return self._intensity

    def _yield_background(self):
        while self._pause.is_set(): time.sleep(.2)
        delay={'performance':0.0,'balanced':0.012,'eco':0.07}.get(self._intensity,0.012)
        if delay: time.sleep(delay)

    def _iter_files(self, root):
        for p in root.rglob('*'):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                yield p

    def _thumb_path(self, path):
        # Thumbnail identity follows the physical file version, not just its path.
        # This prevents a replaced file from inheriting a stale thumbnail forever.
        try:
            st = Path(path).stat()
            identity = f"{Path(path)}|{int(st.st_mtime_ns)}|{int(st.st_size)}"
        except OSError:
            identity = str(path)
        h = hashlib.sha1(identity.encode('utf-8', 'ignore')).hexdigest()
        d = THUMB_DIR / h[:2]
        d.mkdir(parents=True, exist_ok=True)
        return d / f'{h}.jpg'

    def _taken_at(self, image):
        try:
            exif = image.getexif()
            for key in (36867, 36868, 306):
                value = exif.get(key)
                if value:
                    return datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S').isoformat(timespec='seconds')
        except Exception:
            pass

    @staticmethod
    def _dhash(image: Image.Image) -> str:
        # 64-bit difference hash. Good enough for identifying resized/re-encoded copies.
        g = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
        px = list(g.getdata())
        bits = 0
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (1 if px[y*9+x] > px[y*9+x+1] else 0)
        return f'{bits:016x}'

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
        return h.hexdigest()

    def _process_semantic(self, folder_id, path, provider_key, model_id):
        st = path.stat()
        old = db.photo_by_path(str(path))
        unchanged = bool(old and old['size'] == st.st_size and old['mtime_ns'] == st.st_mtime_ns)
        have_embedding = bool(old and db.has_embedding(old['id'], provider_key, model_id))
        have_hash = bool(old and db.has_hash(old['id']))
        if unchanged and have_embedding and have_hash:
            self.status.skipped += 1
            self.status.embeddings_done += 1
            self.status.hashes_done += 1
            return 'skipped'

        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            width, height = im.size
            taken_at = self._taken_at(im)
            rgb = im.convert('RGB')
            thumb_path = self._thumb_path(path)
            if not unchanged or not old or not old['thumb_path'] or not Path(old['thumb_path']).exists():
                thumb = rgb.copy()
                thumb.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                thumb.save(thumb_path, 'JPEG', quality=85, optimize=True)
            elif old['thumb_path']:
                thumb_path = Path(old['thumb_path'])

            photo_id = db.upsert_photo(folder_id=folder_id, path=str(path), name=path.name, size=st.st_size,
                                       mtime_ns=st.st_mtime_ns, taken_at=taken_at, width=width, height=height,
                                       thumb_path=str(thumb_path), error=None, ai_error=None)
            self.status.added_or_updated += 1

            if not unchanged or not have_hash:
                db.set_hashes(photo_id, self._sha256(path), self._dhash(rgb))
            self.status.hashes_done += 1

            if not unchanged or not have_embedding:
                try:
                    vec = embedder.embed_image(rgb)
                    db.set_embedding(photo_id, provider_key, model_id, vec)
                    db.replace_auto_tags(photo_id, provider_key, model_id, auto_tagger.tags_for_vector(vec))
                    self.status.embeddings_done += 1
                except Exception as e:
                    msg = f'{type(e).__name__}: {e}'
                    db.set_ai_error(photo_id, msg)
                    self.status.ai_errors += 1
                    self.status.last_error = f'{path}: {msg}'
                    return 'ai_error'
            else:
                self.status.embeddings_done += 1
        return 'ok'

    def _run_entity_phase(self, provider_key, model_id):
        rows = db.photos_for_entity_scan(DETECTOR_MODEL, provider_key, model_id)
        self.status.entity_total = len(rows)
        self.status.entity_done = 0
        self.status.entity_suspended = False
        self.status.entity_suspend_reason = None
        if not rows:
            return
        self.status.phase = 'entities'
        self.status.message = 'Проверяю распознавание людей, кошек и собак…'

        # Fail fast: one real photo must pass through the detector before a long run.
        test = entity_indexer.self_test(rows[0]['path'])
        if not test.get('ok'):
            reason = test.get('error') or 'неизвестная ошибка self-test'
            self.status.entity_suspended = True
            self.status.entity_suspend_reason = reason
            self.status.entity_last_error = reason
            self.status.last_error = reason
            self.status.message = 'Распознавание объектов приостановлено: self-test не пройден'
            logger().error('Entity phase suspended by self-test: %s', reason)
            return

        self.status.message = 'Распознаю людей, кошек и собак…'
        ewma = None
        alpha = .16
        consecutive = 0
        last_signature = None
        for row in rows:
            self.status.current_file = row['path']
            t = time.time()
            try:
                self.status.detections_done += entity_indexer.process_photo(row)
                consecutive = 0
                last_signature = None
            except Exception as e:
                self.status.entity_errors += 1
                msg = f"{type(e).__name__}: {e}"
                self.status.entity_last_error = f"{row['path']}: {msg}"
                self.status.last_error = self.status.entity_last_error
                signature = msg[:500]
                consecutive = consecutive + 1 if signature == last_signature else 1
                last_signature = signature
                log_exception(f"entity phase photo {row['id']}", e)
                if consecutive >= 3:
                    self.status.entity_suspended = True
                    self.status.entity_suspend_reason = f"3 одинаковые ошибки подряд: {msg}"
                    self.status.message = 'Распознавание объектов приостановлено из-за повторяющейся ошибки'
                    logger().error('Entity phase auto-suspended: %s', self.status.entity_suspend_reason)
                    break
            finally:
                dt = max(.001, time.time() - t)
                ewma = dt if ewma is None else alpha * dt + (1-alpha) * ewma
                self.status.entity_done += 1
                self.status.avg_seconds_per_photo = ewma
                self.status.eta_seconds = max(0, self.status.entity_total - self.status.entity_done) * ewma
                self.status.photos_per_minute = 60 / ewma
                self._yield_background()

    def _run(self):
        try:
            batches = []
            for folder in list(db.list_folders()):
                root = Path(folder['path'])
                files = list(self._iter_files(root)) if root.exists() else []
                batches.append((folder, files))
            self.status.total = sum(len(fs) for _, fs in batches)
            if not self.status.total:
                self.status.phase = 'finished'
                self.status.message = 'В выбранных папках фотографии не найдены'
                return

            self.status.phase = 'loading_model'
            self.status.message = 'Подготавливаю AI-модель…'
            embedder.ensure_loaded()
            provider_key, model_id = embedder.provider_key, embedder.model_id

            self.status.phase = 'indexing'
            self.status.message = f'Индексирую фото, теги и дубли: {embedder.state.model} / {embedder.state.device_name}'
            ewma = None
            alpha = .18
            consecutive = 0
            # Process library roots round-robin so a huge first folder does not block later roots.
            chunk_size = 50
            states = [{'folder': folder, 'files': files, 'pos': 0, 'existing': set()} for folder, files in batches]
            while any(st['pos'] < len(st['files']) for st in states):
                for st in states:
                    folder, files, pos = st['folder'], st['files'], st['pos']
                    if pos >= len(files):
                        continue
                    end = min(len(files), pos + chunk_size)
                    for p in files[pos:end]:
                        st['existing'].add(str(p))
                        self.status.current_file = str(p)
                        t = time.time()
                        try:
                            result = self._process_semantic(int(folder['id']), p, provider_key, model_id)
                            consecutive = consecutive + 1 if result == 'ai_error' else 0
                            if consecutive >= 3:
                                raise RuntimeError('AI-индексация три раза подряд завершилась ошибкой. Последняя ошибка: ' + (self.status.last_error or 'неизвестна'))
                        except RuntimeError:
                            raise
                        except Exception as e:
                            self.status.errors += 1
                            self.status.last_error = f'{p}: {type(e).__name__}: {e}'
                        finally:
                            dt = max(.001, time.time() - t)
                            ewma = dt if ewma is None else alpha * dt + (1-alpha) * ewma
                            self.status.done += 1
                            self.status.avg_seconds_per_photo = ewma
                            self.status.eta_seconds = max(0, self.status.total - self.status.done) * ewma
                            self.status.photos_per_minute = 60 / ewma
                    st['pos'] = end
                    self._yield_background()
            for st in states:
                self.status.removed += db.delete_missing(int(st['folder']['id']), st['existing'])

            # Auto-tags need the score distribution of the whole library. Rebuild them
            # globally after semantic embeddings are ready instead of attaching noisy
            # per-photo top-N labels. This pass is vector-only and does not reopen photos.
            self.status.phase = 'tags'
            self.status.message = 'Уточняю автотеги по всей библиотеке…'
            try:
                tag_result = auto_tagger.rebuild_all()
                logger().info('Auto-tags rebuilt: %s', tag_result)
            except Exception as e:
                self.status.last_error = f'Автотеги: {type(e).__name__}: {e}'
                logger().exception('Auto-tag rebuild failed')

            # Lower-priority second stage. The semantic search is fully usable by now.
            self._run_entity_phase(provider_key, model_id)
            self.status.phase = 'finished'
            self.status.eta_seconds = 0
            if self.status.entity_suspended:
                self.status.message = 'Основная индексация завершена; распознавание объектов приостановлено'
            else:
                self.status.message = 'Все виды индексирования завершены'
        except Exception as e:
            self.status.phase = 'error'
            self.status.last_error = f'{type(e).__name__}: {e}'
            self.status.message = 'Индексирование остановлено из-за ошибки'
        finally:
            self.status.current_file = ''
            self.status.running = False
            self.status.finished_at = time.time()


indexer = Indexer()
