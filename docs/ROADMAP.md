# Eidolarch roadmap

Eidolarch is a local-first Windows media library, cleanup and curation tool. GPU acceleration is optional; browsing, cataloging, hashing and file operations must remain useful on a normal CPU-only Windows PC.

## 2.3 — Exact duplicate workspace

Status: implemented and being stabilized through 2.3.x fixes.

- Exact-file duplicate semantics are isolated behind `exact_duplicate_rows()`.
- Workspace hierarchy: **Duplicate group → Location → File**.
- Same logical file keeps one visual marker across physical copies.
- Groups may overlap; weak redundant bridges are suppressed.
- Reclaim estimates are deduplicated by exact file identity.
- File/location/group cleanup uses preview, server-side revalidation and the Windows Recycle Bin.
- Storage-priority rules influence preferred locations; folder depth breaks equal-priority ties.
- Same-folder physical copies can be reduced to one keeper; the oldest filesystem creation time is kept.

## 2.4 — Video foundation

Goal: add video as a first-class media type without changing the classic photo workflow when **Photos** is selected.

- Global switch: **Photos | Videos | All**; Photos remains the default/classic Eidolarch mode.
- Introduce `IMAGE_EXTS`, `VIDEO_EXTS`, `SUPPORTED_EXTS`.
- Extend the existing `photos` table minimally with `media_type=image|video` and `duration_ms`; keep `photo_id`/table names for compatibility.
- Images continue through Pillow; videos use bundled `ffprobe`/`ffmpeg` for metadata and thumbnails.
- Video MVP: metadata, duration, dimensions, thumbnail, SHA-256, browsing, search scope/filtering, file operations and exact duplicates.
- Duplicate Workspace works for both media types while remaining exact-only.
- Shared viewer shell with separate photo and video renderers; video gets native playback controls/timeline.
- Video cards show thumbnail, play marker and duration.
- Cheap catalog/hash/thumbnail stages must not depend on `embedder.ensure_loaded()`.
- No video AI in MVP: no entities/OCR/VLM/sampled-frame embeddings yet.
- Transcoded/near-duplicate videos are explicitly not Exact duplicates; future video fingerprinting is separate.

## 2.5 — Windows application packaging

Goal: ship Eidolarch as a conventional Windows application instead of a Python folder with batch files.

- `Eidolarch-Setup.exe` style installer.
- Bundled/embedded Python runtime and application dependencies.
- Bundled `ffmpeg`/`ffprobe`.
- Normal launcher with no PowerShell/console experience in ordinary use.
- Start-menu/desktop shortcuts, uninstall and version metadata.
- Explicit repair and debug/diagnostic modes remain available.
- Preserve/migrate the user `data` directory across upgrades.
- Installer/updater can use GitHub Releases; Git is not required on end-user machines.

## 2.6 — Similarity workspace

- Sort a selection/folder by similarity to a reference image.
- Cluster/group visually similar photos (and later compatible video representations).
- Manual triage labels: Keep / Reject / Neutral.
- Filtering and bulk actions by triage label.
- Similar remains separate from Exact duplicates.

## 2.7 — Series

- Detect shooting series from time proximity + perceptual/embedding similarity.
- Present a series as one review unit.
- Cheap CPU quality metrics: sharpness, motion blur, exposure, resolution/noise.

## 2.8 — Best-shot curation

- “These 10 are very similar; keep 2” workflow.
- Ranking combines technical quality with diversity.
- Explanations such as sharper, eyes open, different pose, better exposure.
- AI proposes only; deletion always requires user confirmation.

## 2.9 — People and pets

- Mature the current experimental named-entity pipeline.
- People: usable face → face embedding → candidate/cluster/review.
- Pets: detector/crop verification → identity prototypes/candidates.
- Confirm/reject workflow before broad propagation.
- Named people/pets remain first-class `@name` search filters.

## 3.0 — Unified curator and search

- Unified cleanup dashboard for exact duplicates, near-duplicates/similar groups, series, low-quality frames and reclaim estimates.
- Search combines semantic content, named entities, metadata, folders, tags and OCR when available.
- Guided review rather than irreversible automation.

## Later

- OCR as a first-class index.
- On-demand VLM reasoning for selected groups/series.
- Video sampled-frame embeddings and video fingerprinting for transcoded copies.
- GPS map with privacy-preserving lazy loading.
- Event grouping and richer relationship graph.
