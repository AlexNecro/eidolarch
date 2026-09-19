from __future__ import annotations

import json
import threading
from dataclasses import dataclass

import numpy as np

from . import db
from .ai import embedder

# v3 changes the tagger from "top-N on every photo" to a library-calibrated
# classifier. This is deliberately conservative: a missing tag is much less
# annoying than a tag page filled with unrelated photos.
TAGGER_VERSION = "3"


@dataclass(frozen=True)
class TagDef:
    name: str
    prompt: str
    category: str
    max_fraction: float
    z: float = 2.1


# max_fraction is a safety ceiling used during calibration. It is not a target:
# the robust-score floor can make a tag substantially rarer.
TAG_DEFS = [
    TagDef("кошка", "a clear photo of a cat", "animal", .12, 2.2),
    TagDef("собака", "a clear photo of a dog", "animal", .16, 2.2),
    TagDef("животное", "an animal is clearly visible in the photo", "animal", .22, 2.0),
    TagDef("человек", "a person is clearly visible in the photo", "people", .40, 1.8),
    TagDef("ребёнок", "a child is clearly visible in the photo", "people", .16, 2.2),
    TagDef("семья", "a family together in a photo", "people", .10, 2.4),
    TagDef("группа людей", "a group of several people posing or standing together", "people", .16, 2.2),
    TagDef("портрет", "a portrait photo with a person as the main subject", "special", .12, 2.3),
    TagDef("селфи", "a selfie photo taken at arm's length", "special", .06, 2.8),
    TagDef("машина", "a car is clearly visible in the photo", "transport", .16, 2.2),
    TagDef("автобус", "a bus is clearly visible in the photo", "transport", .05, 2.8),
    TagDef("велосипед", "a bicycle is clearly visible in the photo", "transport", .05, 2.8),
    TagDef("дом", "a house or residential building is the main visible subject", "place", .18, 2.2),
    TagDef("комната", "an indoor room interior", "place", .16, 2.3),
    TagDef("кухня", "a kitchen interior", "place", .07, 2.7),
    TagDef("улица", "an outdoor street scene", "place", .18, 2.2),
    TagDef("город", "an urban city scene with buildings or streets", "place", .18, 2.2),
    TagDef("деревня", "a rural village scene", "place", .08, 2.6),
    TagDef("лес", "a forest is the main scene", "nature", .18, 2.2),
    TagDef("деревья", "trees are a prominent part of the photo", "nature", .22, 2.0),
    TagDef("трава", "grass is a prominent part of the photo", "nature", .18, 2.2),
    TagDef("цветы", "flowers are clearly visible", "nature", .08, 2.6),
    TagDef("горы", "mountains are clearly visible in the landscape", "nature", .08, 2.6),
    TagDef("вода", "a body of water is clearly visible", "water", .18, 2.2),
    TagDef("река", "a river is clearly visible", "water", .07, 2.7),
    TagDef("озеро", "a lake is clearly visible", "water", .07, 2.7),
    TagDef("море", "the sea or ocean is clearly visible", "water", .06, 2.8),
    TagDef("снег", "snow is clearly visible in the photo", "season", .10, 2.5),
    TagDef("зима", "a winter outdoor scene", "season", .10, 2.5),
    TagDef("лето", "a summer outdoor scene", "season", .14, 2.3),
    TagDef("осень", "an autumn outdoor scene with autumn colors", "season", .09, 2.6),
    TagDef("весна", "a spring outdoor scene", "season", .09, 2.6),
    TagDef("ночь", "a photo taken outdoors at night", "time", .07, 2.8),
    TagDef("закат", "a visible sunset sky", "time", .04, 3.0),
    TagDef("еда", "food is clearly visible and is a main subject", "object", .10, 2.5),
    TagDef("напиток", "a drink, cup, glass or bottle is a main visible subject", "object", .07, 2.7),
    # Special tags intentionally have very low prevalence ceilings. SigLIP is
    # not OCR, so #текст/#документ/#экран must require exceptional scores.
    TagDef("документ", "a photographed paper document or printed page", "special", .035, 3.2),
    TagDef("текст", "a photo dominated by clearly readable written text", "special", .025, 3.5),
    TagDef("экран", "a computer monitor or device screen is the main subject", "special", .04, 3.1),
    TagDef("мебель", "furniture is a prominent subject of the photo", "object", .10, 2.5),
    TagDef("игрушка", "a toy is clearly visible and prominent", "object", .07, 2.7),
    TagDef("стройка", "construction, building work or renovation is clearly visible", "event", .07, 2.7),
    TagDef("праздник", "a celebration or party scene", "event", .07, 2.8),
    TagDef("спорт", "people actively doing sports", "event", .06, 2.9),
    TagDef("природа", "a natural landscape with little or no urban content", "scene", .24, 2.0),
]

# At most this many labels from one semantic family may be attached to one photo.
CATEGORY_LIMITS = {
    "animal": 2,
    "people": 2,
    "transport": 1,
    "place": 2,
    "nature": 2,
    "water": 1,
    "season": 1,
    "time": 1,
    "object": 2,
    "event": 1,
    "scene": 1,
    "special": 1,
}
MAX_TAGS_PER_PHOTO = 7


class AutoTagger:
    def __init__(self):
        self._lock = threading.Lock()
        self._key = None
        self._matrix = None
        self._thresholds = None

    @property
    def _settings_key(self) -> str:
        return f"autotag_thresholds:{TAGGER_VERSION}:{embedder.provider_key}:{embedder.model_id}"

    def _ensure(self):
        key = (embedder.provider_key, embedder.model_id)
        if self._key == key and self._matrix is not None:
            return
        with self._lock:
            if self._key == key and self._matrix is not None:
                return
            vecs = [embedder.embed_text(d.prompt) for d in TAG_DEFS]
            self._matrix = np.vstack(vecs).astype(np.float32)
            self._key = key
            self._thresholds = None
            raw = db.get_settings([self._settings_key]).get(self._settings_key)
            if raw:
                try:
                    obj = json.loads(raw)
                    values = obj.get("thresholds") if isinstance(obj, dict) else None
                    if isinstance(values, list) and len(values) == len(TAG_DEFS):
                        self._thresholds = np.asarray(values, dtype=np.float32)
                except Exception:
                    pass

    def _select(self, scores: np.ndarray, thresholds: np.ndarray | None):
        if thresholds is None:
            # Until the whole library has been calibrated, be intentionally quiet.
            # The end-of-index pass will populate stable tags for every photo.
            return []
        candidates = []
        for i, score in enumerate(scores):
            if float(score) >= float(thresholds[i]):
                candidates.append((i, float(score)))
        candidates.sort(key=lambda x: x[1], reverse=True)
        counts = {}
        result = []
        for i, score in candidates:
            d = TAG_DEFS[i]
            used = counts.get(d.category, 0)
            if used >= CATEGORY_LIMITS.get(d.category, 1):
                continue
            result.append((d.name, score))
            counts[d.category] = used + 1
            if len(result) >= MAX_TAGS_PER_PHOTO:
                break
        return result

    def tags_for_vector(self, vector):
        self._ensure()
        v = np.asarray(vector, dtype=np.float32).reshape(-1)
        scores = self._matrix @ v
        return self._select(scores, self._thresholds)

    @staticmethod
    def _calibrated_threshold(values: np.ndarray, definition: TagDef) -> float:
        values = np.asarray(values, dtype=np.float32)
        if values.size == 0:
            return float("inf")
        med = float(np.median(values))
        mad = float(np.median(np.abs(values - med)))
        robust_sigma = max(1.4826 * mad, 0.0015)
        # A quantile caps prevalence; the robust floor prevents a flat/noisy score
        # distribution from manufacturing a tag simply because something is top 2%.
        q = float(np.quantile(values, max(0.0, min(1.0, 1.0 - definition.max_fraction))))
        floor = med + definition.z * robust_sigma
        # If the entire model response for this tag is almost flat, suppress it.
        if float(values.max()) - med < max(0.008, definition.z * robust_sigma * 0.75):
            return float("inf")
        return max(q, floor)

    def rebuild_all(self):
        embedder.ensure_loaded()
        self._ensure()
        rows = db.load_embeddings(embedder.provider_key, embedder.model_id)
        if not rows:
            return {"done": 0, "tags": 0, "version": TAGGER_VERSION}

        # Compute all image×tag similarities in bounded batches. This avoids holding
        # a second copy of the complete embedding index in RAM.
        scores = np.empty((len(rows), len(TAG_DEFS)), dtype=np.float32)
        batch_size = 512
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            x = np.vstack([
                np.frombuffer(r["vector"], dtype=np.float32, count=r["dim"])
                for r in batch
            ]).astype(np.float32, copy=False)
            scores[start:start + len(batch)] = x @ self._matrix.T

        thresholds = np.asarray([
            self._calibrated_threshold(scores[:, i], d)
            for i, d in enumerate(TAG_DEFS)
        ], dtype=np.float32)
        self._thresholds = thresholds
        payload = {
            "version": TAGGER_VERSION,
            "model": embedder.model_id,
            "thresholds": [None if not np.isfinite(x) else float(x) for x in thresholds],
        }
        # JSON has no Infinity. Store a very high threshold for suppressed tags.
        stored = [10.0 if x is None else x for x in payload["thresholds"]]
        payload["thresholds"] = stored
        db.set_setting(self._settings_key, json.dumps(payload, ensure_ascii=False))
        thresholds = np.asarray(stored, dtype=np.float32)
        self._thresholds = thresholds

        assignments = []
        total_tags = 0
        for row, row_scores in zip(rows, scores):
            tags = self._select(row_scores, thresholds)
            total_tags += len(tags)
            assignments.append((int(row["id"]), tags))
        db.replace_auto_tags_bulk(assignments, embedder.provider_key, embedder.model_id)
        return {
            "done": len(rows),
            "tags": total_tags,
            "avg_tags_per_photo": round(total_tags / max(1, len(rows)), 3),
            "version": TAGGER_VERSION,
        }


auto_tagger = AutoTagger()
