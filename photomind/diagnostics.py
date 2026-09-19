from __future__ import annotations
import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .config import LOG_FILE

_logger = logging.getLogger("photomind")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    h = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
    _logger.addHandler(h)

def logger(): return _logger

def exception(where: str, exc: BaseException):
    _logger.exception("%s: %s: %s", where, type(exc).__name__, exc)

def event(message: str): _logger.info(message)

def tail(lines: int = 80) -> str:
    try:
        data=Path(LOG_FILE).read_text(encoding="utf-8",errors="replace").splitlines()
        return "\n".join(data[-max(1,min(lines,500)):])
    except Exception:
        return ""

def runtime_info():
    out={"python":sys.version.split()[0],"platform":platform.platform()}
    try:
        import torch
        out.update({"torch":torch.__version__,"torch_cuda":getattr(torch.version,"cuda",None),"cuda_available":bool(torch.cuda.is_available())})
        if torch.cuda.is_available(): out["gpu"]=torch.cuda.get_device_name(0)
    except Exception as e: out["torch_error"]=f"{type(e).__name__}: {e}"
    try:
        import torchvision
        out["torchvision"] = torchvision.__version__
    except Exception as e:
        out["torchvision_error"] = f"{type(e).__name__}: {e}"
    try:
        from transformers import AutoImageProcessor
        out["auto_image_processor"] = "ok"
    except Exception as e:
        out["auto_image_processor_error"] = f"{type(e).__name__}: {e}"
    return out


def _redact_settings(settings):
    data = dict(settings or {})
    for key in list(data):
        low = str(key).lower()
        if any(x in low for x in ('key', 'token', 'password', 'secret')) and data.get(key):
            data[key] = '<redacted>'
    return data

def build_error_report(app_version: str, model_state=None, index_status=None, entity_state=None, settings=None) -> bytes:
    """Build a support bundle without photos, thumbnails, database, or API secrets."""
    import io, json, zipfile, datetime
    report = {
        'generated_at': datetime.datetime.now().astimezone().isoformat(),
        'app_version': app_version,
        'runtime': runtime_info(),
        'model_state': model_state or {},
        'index_status': index_status or {},
        'entity_state': entity_state or {},
        'settings': _redact_settings(settings),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('report.json', json.dumps(report, ensure_ascii=False, indent=2, default=str))
        zf.writestr('eidolarch.log.txt', tail(500))
        zf.writestr('README.txt', 'Eidolarch error report. Contains runtime information and recent logs. It does not include photos, thumbnails, the database, or API keys.\n')
    return out.getvalue()
