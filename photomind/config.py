from __future__ import annotations
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("EIDOLARCH_DATA", os.environ.get("PHOTOMIND_DATA", ROOT / "data")))
THUMB_DIR = DATA_DIR / "thumbs"
LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "eidolarch.log"
# New installs use eidolarch.sqlite3. Existing PhotoMind installations keep using
# the legacy database automatically, so an in-place upgrade does not trigger a reindex.
_NEW_DB_PATH = DATA_DIR / "eidolarch.sqlite3"
_LEGACY_DB_PATH = DATA_DIR / "photomind.sqlite3"
DB_PATH = _NEW_DB_PATH if _NEW_DB_PATH.exists() or not _LEGACY_DB_PATH.exists() else _LEGACY_DB_PATH
THUMB_SIZE = int(os.environ.get("PHOTOMIND_THUMB_SIZE", "480"))
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic", ".heif"}
DATA_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
