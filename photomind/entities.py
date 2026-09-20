from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import db
from .ai import embedder
from .diagnostics import logger, exception as log_exception

DETECTOR_MODEL_ID = "hustvl/yolos-tiny"
DETECTOR_SCAN_KEY = "hustvl/yolos-tiny:eidolarch-detector-v3"
DETECTOR_MODEL = DETECTOR_SCAN_KEY
TARGET_LABELS = {"person": "person", "cat": "cat", "dog": "dog"}
DISPLAY_KIND = {"person": "entity.kind.person", "cat": "entity.kind.cat", "dog": "entity.kind.dog"}

# Post-processing knobs for the MVP object detector.
DETECTION_THRESHOLDS = {"person": 0.45, "cat": 0.40, "dog": 0.40}
MIN_BOX_SIZE_PX = 36
NMS_IOU_THRESHOLD = 0.50
CONTAINMENT_OVERLAP_THRESHOLD = 0.90
CONTAINMENT_MAX_AREA_RATIO = 0.65
CONTAINMENT_SCORE_TOLERANCE = 0.15


@dataclass
class EntityState:
    loaded: bool = False
    loading: bool = False
    model: str = DETECTOR_MODEL_ID
    device: str = "cpu"
    error: str | None = None
    fallback_note: str | None = None
    self_test_ok: bool | None = None

    def json(self):
        return self.__dict__.copy()


class EntityIndexer:
    """Detect people/cats/dogs and store crop embeddings.

    The detector is intentionally small. Re-identification reuses the active Eidolarch
    image embedding model for crops, so local/remote providers work the same way.
    This is an MVP approximation for people; a face-specific encoder is planned.
    """

    def __init__(self):
        self.state = EntityState()
        self.processor = None
        self.model = None
        self.torch = None
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._forced_device = None

    @property
    def scan_key(self) -> tuple[str, str, str]:
        return (DETECTOR_SCAN_KEY, embedder.provider_key, embedder.model_id)

    def ensure_loaded(self):
        if self.state.loaded and self.model is not None:
            return
        with self._load_lock:
            if self.state.loaded and self.model is not None:
                return
            self.state.loading = True
            self.state.error = None
            try:
                import torch
                from transformers import AutoImageProcessor, AutoModelForObjectDetection

                self.torch = torch
                # Keep the detector beside the main model when possible. YOLOS tiny is
                # small, but CPU fallback avoids OOM on tight GPUs.
                # Keep the large semantic model alone on small GPUs. The quality SigLIP
                # model already consumes most of a 6 GB card; YOLOS on the same GPU caused
                # repeated OOM failures in v2.1. Prefer CPU below 10 GB VRAM.
                vram = float(embedder.state.vram_total_gb or 0)
                want_cuda = embedder.state.device == "cuda" and torch.cuda.is_available() and vram >= 10.0
                device = self._forced_device or ("cuda" if want_cuda else "cpu")
                self.processor = AutoImageProcessor.from_pretrained(DETECTOR_MODEL_ID)
                self.model = AutoModelForObjectDetection.from_pretrained(DETECTOR_MODEL_ID)
                self.model.eval().to(device)
                self.state.device = device
                if device == "cpu" and embedder.state.device == "cuda":
                    self.state.fallback_note = "Детектор объектов выполняется на CPU, чтобы не переполнять VRAM"
                self.state.loaded = True
            except Exception as e:
                self.state.error = f"{type(e).__name__}: {e}"
                raise
            finally:
                self.state.loading = False

    def _run_model(self, image: Image.Image, threshold: float):
        self.ensure_loaded()
        torch = self.torch
        rgb = image.convert("RGB")
        inputs = self.processor(images=rgb, return_tensors="pt")
        inputs = {k: v.to(self.state.device) for k, v in inputs.items()}
        with self._infer_lock, torch.inference_mode():
            outputs = self.model(**inputs)
        target_sizes = torch.tensor([rgb.size[::-1]])
        results = self.processor.post_process_object_detection(outputs, threshold=threshold, target_sizes=target_sizes)[0]
        return rgb, results

    @staticmethod
    def _box_area(box):
        x1, y1, x2, y2 = box
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    @staticmethod
    def _intersection_area(a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        return (ix2 - ix1) * (iy2 - iy1)

    @classmethod
    def _iou(cls, a, b):
        inter = cls._intersection_area(a, b)
        if inter <= 0:
            return 0.0
        denom = cls._box_area(a) + cls._box_area(b) - inter
        return inter / denom if denom > 0 else 0.0

    @classmethod
    def _is_contained_fragment(cls, candidate, other):
        if candidate['kind'] != other['kind']:
            return False
        a = candidate['box']
        b = other['box']
        area_a = cls._box_area(a)
        area_b = cls._box_area(b)
        if area_a <= 0 or area_b <= 0 or area_a >= area_b:
            return False
        if area_a / area_b > CONTAINMENT_MAX_AREA_RATIO:
            return False
        inter = cls._intersection_area(a, b)
        if inter / area_a < CONTAINMENT_OVERLAP_THRESHOLD:
            return False
        return candidate['score'] <= other['score'] + CONTAINMENT_SCORE_TOLERANCE

    def _extract_target_predictions(self, rgb: Image.Image, results, raw_threshold: float):
        id2label = self.model.config.id2label
        rows = []
        for score, label_id, box in zip(results["scores"], results["labels"], results["boxes"]):
            label = str(id2label.get(int(label_id), "")).lower()
            score = float(score)
            coords = [float(x) for x in box.tolist()]
            rows.append({
                'raw_label': label,
                'kind': TARGET_LABELS.get(label),
                'score': score,
                'box': coords,
                'target': label in TARGET_LABELS,
                'min_score': DETECTION_THRESHOLDS.get(TARGET_LABELS.get(label, ''), raw_threshold),
            })
        target_rows = []
        for row in rows:
            if not row['target']:
                continue
            x1, y1, x2, y2 = row['box']
            if (x2 - x1) < MIN_BOX_SIZE_PX or (y2 - y1) < MIN_BOX_SIZE_PX:
                continue
            target_rows.append(row)
        return rows, target_rows

    @staticmethod
    def _apply_score_filter(candidates, raw_threshold: float):
        kept = []
        for row in candidates:
            min_score = max(float(raw_threshold), float(DETECTION_THRESHOLDS.get(row['kind'], raw_threshold)))
            if row['score'] >= min_score:
                x = dict(row)
                x['min_score'] = min_score
                kept.append(x)
        kept.sort(key=lambda r: (r['score'], EntityIndexer._box_area(r['box'])), reverse=True)
        return kept

    @classmethod
    def _apply_nms(cls, candidates):
        by_kind = {}
        for row in candidates:
            by_kind.setdefault(row['kind'], []).append(row)
        kept = []
        for kind, items in by_kind.items():
            items = sorted(items, key=lambda r: (r['score'], cls._box_area(r['box'])), reverse=True)
            kind_kept = []
            for row in items:
                if all(cls._iou(row['box'], other['box']) <= NMS_IOU_THRESHOLD for other in kind_kept):
                    kind_kept.append(row)
            kept.extend(kind_kept)
        kept.sort(key=lambda r: (r['score'], cls._box_area(r['box'])), reverse=True)
        return kept

    @classmethod
    def _apply_containment_filter(cls, candidates):
        ordered = sorted(candidates, key=lambda r: (r['score'], cls._box_area(r['box'])), reverse=True)
        removed = set()
        for i, row in enumerate(ordered):
            if i in removed:
                continue
            for j, other in enumerate(ordered):
                if i == j or j in removed:
                    continue
                if cls._is_contained_fragment(row, other):
                    removed.add(i)
                    break
        kept = [row for idx, row in enumerate(ordered) if idx not in removed]
        kept.sort(key=lambda r: (r['score'], cls._box_area(r['box'])), reverse=True)
        return kept

    @staticmethod
    def _serialize_rows(rows, limit=None):
        data = []
        for row in rows[:limit] if limit else rows:
            data.append({
                'label': row.get('raw_label') or row.get('kind'),
                'kind': row.get('kind'),
                'score': round(float(row['score']), 4),
                'box': [round(float(x), 1) for x in row['box']],
                'target': bool(row.get('target', True)),
                'min_score': round(float(row.get('min_score', 0.0)), 4),
            })
        return data

    def detect_with_details(self, image: Image.Image, threshold: float = 0.10):
        rgb, results = self._run_model(image, threshold=threshold)
        all_rows, target_rows = self._extract_target_predictions(rgb, results, threshold)
        after_threshold = self._apply_score_filter(target_rows, threshold)
        after_nms = self._apply_nms(after_threshold)
        final_rows = self._apply_containment_filter(after_nms)
        return {
            'device': self.state.device,
            'threshold': threshold,
            'image_size': [rgb.width, rgb.height],
            'thresholds': DETECTION_THRESHOLDS.copy(),
            'nms_iou_threshold': NMS_IOU_THRESHOLD,
            'containment_overlap_threshold': CONTAINMENT_OVERLAP_THRESHOLD,
            'containment_max_area_ratio': CONTAINMENT_MAX_AREA_RATIO,
            'counts': {
                'raw_predictions': len(all_rows),
                'target_predictions': len(target_rows),
                'after_threshold': len(after_threshold),
                'after_nms': len(after_nms),
                'final': len(final_rows),
            },
            'raw_predictions': self._serialize_rows(sorted(all_rows, key=lambda r: r['score'], reverse=True), limit=50),
            'target_predictions': self._serialize_rows(sorted(target_rows, key=lambda r: r['score'], reverse=True), limit=50),
            'after_threshold': self._serialize_rows(after_threshold, limit=50),
            'after_nms': self._serialize_rows(after_nms, limit=50),
            'after_containment': self._serialize_rows(final_rows, limit=50),
            'final': [(row['kind'], float(row['score']), tuple(float(x) for x in row['box'])) for row in final_rows],
        }

    def detect(self, image: Image.Image, threshold: float = 0.10):
        return self.detect_with_details(image, threshold=threshold)['final']

    def diagnose(self, image: Image.Image, threshold: float = 0.10):
        """Run the detector without storing anything and expose post-processing details."""
        diagnostics = self.detect_with_details(image, threshold=threshold)
        diagnostics['final_detections'] = [
            {'kind': kind, 'score': round(score, 4), 'box': [round(float(x), 1) for x in box]}
            for kind, score, box in diagnostics.pop('final')
        ]
        return diagnostics

    def _fallback_cpu(self, reason: str):
        if self.state.device == "cpu":
            return False
        try:
            self._forced_device = "cpu"
            self.model = self.model.to("cpu")
            self.state.device = "cpu"
            self.state.fallback_note = f"CUDA → CPU: {reason}"
            if self.torch and self.torch.cuda.is_available():
                self.torch.cuda.empty_cache()
            logger().warning("Object detector fallback to CPU: %s", reason)
            return True
        except Exception as e:
            log_exception("entity fallback cpu", e)
            return False

    def self_test(self, image_path: str | Path):
        self.state.self_test_ok = False
        try:
            with Image.open(Path(image_path)) as im:
                image = ImageOps.exif_transpose(im).convert("RGB")
                # Detection may legitimately return zero objects; success means the pipeline ran.
                found = self.detect(image, threshold=0.90)
                # Also test coexistence with the semantic embedder: this caught the v2.1
                # small-VRAM failure where the detector itself loaded but crop embedding failed.
                if found:
                    _, _, (x1, y1, x2, y2) = found[0]
                    probe = image.crop((max(0, int(x1)), max(0, int(y1)), min(image.width, int(x2)), min(image.height, int(y2))))
                else:
                    w, h = image.size
                    probe = image.crop((w // 4, h // 4, max(w // 4 + 1, 3 * w // 4), max(h // 4 + 1, 3 * h // 4)))
                embedder.embed_image(probe)
            self.state.self_test_ok = True
            self.state.error = None
            return {"ok": True, "device": self.state.device}
        except RuntimeError as e:
            msg = str(e).lower()
            if ("out of memory" in msg or "cuda" in msg) and self._fallback_cpu(str(e)):
                try:
                    with Image.open(Path(image_path)) as im:
                        image = ImageOps.exif_transpose(im).convert("RGB")
                        self.detect(image, threshold=0.90)
                        w, h = image.size
                        embedder.embed_image(image.crop((w // 4, h // 4, max(w // 4 + 1, 3 * w // 4), max(h // 4 + 1, 3 * h // 4))))
                    self.state.self_test_ok = True
                    self.state.error = None
                    return {"ok": True, "device": self.state.device, "fallback": True}
                except Exception as e2:
                    self.state.error = f"{type(e2).__name__}: {e2}"
                    log_exception("entity self-test after CPU fallback", e2)
                    return {"ok": False, "error": self.state.error}
            self.state.error = f"{type(e).__name__}: {e}"
            log_exception("entity self-test", e)
            return {"ok": False, "error": self.state.error}
        except Exception as e:
            self.state.error = f"{type(e).__name__}: {e}"
            log_exception("entity self-test", e)
            return {"ok": False, "error": self.state.error}

    def process_photo(self, photo_row, force: bool = False):
        detector_model, provider_key, embedding_model = self.scan_key
        photo_id = int(photo_row["id"])
        if not force and db.has_entity_scan(photo_id, detector_model, provider_key, embedding_model):
            return 0
        try:
            path = Path(photo_row["path"])
            with Image.open(path) as im:
                image = ImageOps.exif_transpose(im).convert("RGB")
                diagnostics = self.detect_with_details(image)
                detections = diagnostics['final']
                rows = []
                for kind, score, (x1, y1, x2, y2) in detections:
                    # Add a little context around the object crop.
                    w, h = image.size
                    bw, bh = x2 - x1, y2 - y1
                    pad_x, pad_y = bw * 0.08, bh * 0.08
                    crop = image.crop((max(0, x1 - pad_x), max(0, y1 - pad_y), min(w, x2 + pad_x), min(h, y2 + pad_y)))
                    vector = embedder.embed_image(crop)
                    rows.append((kind, score, x1, y1, x2, y2, vector))
                # Preserve manually assigned identities across a re-detect when the
                # new box still strongly overlaps the old object of the same kind.
                old_named = [dict(x) for x in db.list_detections(photo_id) if x['entity_id'] is not None]
                db.replace_detections(photo_id, detector_model, provider_key, embedding_model, rows)
                if old_named:
                    for fresh in db.list_detections(photo_id):
                        best = None; best_iou = 0.0
                        fb = (float(fresh['x1']), float(fresh['y1']), float(fresh['x2']), float(fresh['y2']))
                        for old in old_named:
                            if old['kind'] != fresh['kind']: continue
                            ob = (float(old['x1']), float(old['y1']), float(old['x2']), float(old['y2']))
                            iou = self._iou(fb, ob)
                            if iou > best_iou:
                                best_iou, best = iou, old
                        if best is not None and best_iou >= 0.55:
                            db.assign_detection_entity(int(fresh['id']), int(best['entity_id']))
                db.finish_entity_scan(photo_id, detector_model, provider_key, embedding_model, None)
                logger().info(
                    'Entity detection photo=%s raw=%s target=%s threshold=%s nms=%s final=%s',
                    photo_id,
                    diagnostics['counts']['raw_predictions'],
                    diagnostics['counts']['target_predictions'],
                    diagnostics['counts']['after_threshold'],
                    diagnostics['counts']['after_nms'],
                    diagnostics['counts']['final'],
                )
                return len(rows)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self.state.error = msg
            db.finish_entity_scan(photo_id, detector_model, provider_key, embedding_model, msg)
            log_exception(f"entity photo {photo_id}", e)
            raise

    def name_detection(self, detection_id: int, name: str, propagate: bool = True, threshold: float = 0.88):
        name = name.strip()
        if not name:
            raise ValueError("Имя не указано")
        det = db.get_detection(detection_id)
        if not det:
            raise ValueError("Объект не найден")
        entity_id = db.get_or_create_entity(name, det["kind"])
        db.assign_detection_entity(detection_id, entity_id)
        assigned = 1
        if propagate:
            ref = np.frombuffer(det["vector"], dtype=np.float32, count=det["dim"])
            candidates = db.unassigned_detection_vectors(det["kind"], det["provider_key"], det["embedding_model"])
            for row in candidates:
                vec = np.frombuffer(row["vector"], dtype=np.float32, count=row["dim"])
                if vec.shape != ref.shape:
                    continue
                score = float(vec @ ref)
                if score >= threshold:
                    db.assign_detection_entity(int(row["id"]), entity_id)
                    assigned += 1
        db.rebuild_entity_tags(entity_id)
        return {"entity_id": entity_id, "name": name, "kind": det["kind"], "assigned": assigned, "threshold": threshold}


entity_indexer = EntityIndexer()
