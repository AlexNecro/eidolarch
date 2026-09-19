from __future__ import annotations
import threading, time
from pathlib import Path
from . import db
from .indexer import indexer

class LibraryWatcher:
    def __init__(self):
        self.observer=None; self._lock=threading.Lock(); self._last=0.0
    def start(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except Exception:
            return False
        if self.observer: return True
        owner=self
        class Handler(FileSystemEventHandler):
            def on_any_event(self,event):
                if getattr(event,'is_directory',False) and event.event_type=='modified': return
                now=time.time()
                with owner._lock:
                    if now-owner._last<1.0:return
                    owner._last=now
                def later():
                    time.sleep(1.5)
                    if not indexer.status.running:indexer.start()
                threading.Thread(target=later,daemon=True).start()
        obs=Observer(); n=0
        for f in db.list_folders():
            p=Path(f['path'])
            if p.exists():
                try: obs.schedule(Handler(),str(p),recursive=True); n+=1
                except Exception: pass
        if not n:return False
        obs.daemon=True; obs.start(); self.observer=obs; return True

watcher=LibraryWatcher()
