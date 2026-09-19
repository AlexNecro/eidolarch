from __future__ import annotations

import base64
import io
import json
import threading
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import db

LOCAL_PROFILES = {
    "fast": {
        "label": "Быстрая",
        "model": "google/siglip2-base-patch16-224",
        "min_vram_gb": 0.0,
        "description": "Меньше требований, подходит для CPU и слабых GPU",
    },
    "quality": {
        "label": "Качественная",
        "model": "google/siglip2-so400m-patch14-384",
        "min_vram_gb": 3.0,
        "description": "Более тяжёлая модель, предпочтительно GPU",
    },
}

DEFAULT_SETTINGS = {
    "backend": "auto",          # auto | local | remote
    "local_profile": "auto",    # auto | fast | quality
    "device": "auto",           # auto | cuda | cpu
    "remote_base_url": "",
    "remote_model": "",
    "remote_api_key": "",
}


@dataclass
class ModelState:
    loaded: bool = False
    loading: bool = False
    backend: str = "local"
    provider_key: str = "local"
    model: str | None = None
    profile: str | None = None
    device: str = "не определено"
    device_name: str | None = None
    precision: str | None = None
    cuda_available: bool | None = None
    vram_total_gb: float | None = None
    torch_version: str | None = None
    torch_cuda_version: str | None = None
    error: str | None = None
    fallback_note: str | None = None

    def json(self):
        return asdict(self)


class BaseEmbeddingProvider:
    provider_key = "base"
    model_id = ""
    def embed_image(self, image: Image.Image) -> np.ndarray: raise NotImplementedError
    def embed_text(self, text: str) -> np.ndarray: raise NotImplementedError
    def close(self): pass


class LocalSiglipProvider(BaseEmbeddingProvider):
    provider_key = "local"

    def __init__(self, model_id: str, device: str, state: ModelState):
        self.model_id = model_id
        self.device = device
        self.state = state
        self.model = None
        self.processor = None
        self.torch = None
        self._inference_lock = threading.Lock()

    def load(self):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.torch = torch
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model = AutoModel.from_pretrained(self.model_id, dtype=dtype)
        self.model.eval().to(self.device)
        self.state.precision = "FP16" if self.device == "cuda" else "FP32"

    def _feature_tensor(self, output):
        torch = self.torch
        if torch.is_tensor(output): return output
        for name in ("image_embeds", "text_embeds", "pooler_output"):
            value = getattr(output, name, None)
            if torch.is_tensor(value): return value
        try:
            if len(output) > 1 and torch.is_tensor(output[1]): return output[1]
            if len(output) > 0 and torch.is_tensor(output[0]):
                value = output[0]
                return value.mean(dim=1) if value.ndim == 3 else value
        except Exception:
            pass
        raise TypeError(f"Не удалось извлечь embedding из {type(output).__name__}")

    def _norm(self, x):
        x = self._feature_tensor(x)
        if x.ndim == 1: x = x.unsqueeze(0)
        x = x.detach().float().cpu().numpy()[0].astype(np.float32)
        n = np.linalg.norm(x)
        return x / n if n else x

    def embed_image(self, image: Image.Image) -> np.ndarray:
        torch = self.torch
        inputs = self.processor(images=image.convert("RGB"), return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with self._inference_lock, torch.inference_mode():
            out = self.model.get_image_features(**inputs) if hasattr(self.model, "get_image_features") else self.model(**inputs).image_embeds
        return self._norm(out)

    def embed_text(self, text: str) -> np.ndarray:
        torch = self.torch
        inputs = self.processor(text=[text], padding="max_length", return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with self._inference_lock, torch.inference_mode():
            out = self.model.get_text_features(**inputs) if hasattr(self.model, "get_text_features") else self.model(**inputs).text_embeds
        return self._norm(out)

    def close(self):
        try:
            del self.model
            if self.torch and self.torch.cuda.is_available():
                self.torch.cuda.empty_cache()
        except Exception:
            pass


class RemoteEidolarchProvider(BaseEmbeddingProvider):
    provider_key = "remote"
    def __init__(self, base_url: str, model_id: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id or "remote-default"
        self.api_key = api_key

    def _post(self, path: str, payload: dict) -> np.ndarray:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            obj = json.loads(r.read().decode("utf-8"))
        vec = obj.get("embedding") or obj.get("vector")
        if not vec: raise RuntimeError("Remote API не вернул embedding/vector")
        x = np.asarray(vec, dtype=np.float32)
        n = np.linalg.norm(x)
        return x / n if n else x

    def embed_text(self, text: str) -> np.ndarray:
        return self._post("/embed/text", {"text": text, "model": self.model_id})

    def embed_image(self, image: Image.Image) -> np.ndarray:
        buf = io.BytesIO(); image.convert("RGB").save(buf, "JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return self._post("/embed/image", {"image_base64": b64, "model": self.model_id})


class EmbeddingManager:
    def __init__(self):
        self.state = ModelState()
        self.provider: BaseEmbeddingProvider | None = None
        self._lock = threading.Lock()
        self._probe_runtime()

    def settings(self):
        result = DEFAULT_SETTINGS.copy()
        result.update(db.get_settings(DEFAULT_SETTINGS.keys()))
        return result

    def save_settings(self, values: dict):
        for k in DEFAULT_SETTINGS:
            if k in values: db.set_setting(k, str(values[k]))
        self.unload()
        self._probe_runtime()

    def _probe_runtime(self):
        self.state = ModelState()
        try:
            import torch
            self.state.torch_version = torch.__version__
            self.state.torch_cuda_version = getattr(torch.version, "cuda", None)
            self.state.cuda_available = bool(torch.cuda.is_available())
            if self.state.cuda_available:
                self.state.device = "cuda"
                self.state.device_name = torch.cuda.get_device_name(0)
                self.state.vram_total_gb = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2)
            else:
                self.state.device = "cpu"; self.state.device_name = "CPU"
        except Exception as e:
            self.state.cuda_available = False; self.state.device = "cpu"; self.state.device_name = "CPU"
            self.state.error = f"PyTorch: {type(e).__name__}: {e}"

    def unload(self):
        with self._lock:
            if self.provider:
                self.provider.close()
            self.provider = None
            self.state.loaded = False

    def _select_profile(self, settings):
        requested = settings["local_profile"]
        if requested in LOCAL_PROFILES: return requested
        # Auto: quality on a CUDA GPU with enough VRAM, otherwise fast.
        if self.state.cuda_available and (self.state.vram_total_gb or 0) >= LOCAL_PROFILES["quality"]["min_vram_gb"]:
            return "quality"
        return "fast"

    def _device_candidates(self, settings):
        requested = settings["device"]
        if requested == "cpu": return ["cpu"]
        if requested == "cuda": return ["cuda", "cpu"]
        return ["cuda", "cpu"] if self.state.cuda_available else ["cpu"]

    def ensure_loaded(self):
        if self.state.loaded and self.provider: return
        with self._lock:
            if self.state.loaded and self.provider: return
            self.state.loading = True; self.state.error = None; self.state.fallback_note = None
            settings = self.settings()
            try:
                backend = settings["backend"]
                if backend == "remote" or (backend == "auto" and settings.get("remote_base_url") and not self.state.cuda_available):
                    if not settings.get("remote_base_url"): raise RuntimeError("Не указан адрес Remote API")
                    self.provider = RemoteEidolarchProvider(settings["remote_base_url"], settings.get("remote_model", ""), settings.get("remote_api_key", ""))
                    self.state.backend = "remote"; self.state.provider_key = "remote"; self.state.model = self.provider.model_id
                    self.state.profile = None; self.state.device = "remote"; self.state.device_name = settings["remote_base_url"]; self.state.precision = None
                    # Probe by leaving first real request to test endpoint.
                    self.state.loaded = True; return

                profile = self._select_profile(settings)
                profile_order = [profile] + (["fast"] if profile == "quality" else [])
                errors = []
                for prof in profile_order:
                    model_id = LOCAL_PROFILES[prof]["model"]
                    for dev in self._device_candidates(settings):
                        if dev == "cuda" and not self.state.cuda_available: continue
                        try:
                            p = LocalSiglipProvider(model_id, dev, self.state)
                            p.load()
                            self.provider = p
                            self.state.backend = "local"; self.state.provider_key = "local"; self.state.model = model_id; self.state.profile = prof
                            self.state.device = dev; self.state.device_name = __import__('torch').cuda.get_device_name(0) if dev == 'cuda' else 'CPU'
                            if prof != profile or (settings["device"] == "cuda" and dev == "cpu"):
                                self.state.fallback_note = f"Автооткат: {LOCAL_PROFILES[prof]['label']}, {self.state.device_name}"
                            self.state.loaded = True; return
                        except Exception as e:
                            errors.append(f"{model_id} / {dev}: {type(e).__name__}: {e}")
                            try:
                                import torch
                                if torch.cuda.is_available(): torch.cuda.empty_cache()
                            except Exception: pass
                raise RuntimeError("; ".join(errors[-3:]))
            except Exception as e:
                self.state.error = f"{type(e).__name__}: {e}"
                raise
            finally:
                self.state.loading = False

    @property
    def provider_key(self):
        self.ensure_loaded(); return self.state.provider_key
    @property
    def model_id(self):
        self.ensure_loaded(); return self.state.model or "unknown"

    def embed_image(self, image: Image.Image) -> np.ndarray:
        self.ensure_loaded(); return self.provider.embed_image(image)
    def embed_text(self, text: str) -> np.ndarray:
        self.ensure_loaded(); return self.provider.embed_text(text)


embedder = EmbeddingManager()
