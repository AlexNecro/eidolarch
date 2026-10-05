# Next version

## 2.4.0 — Video foundation

Goal: add video files without changing the classic Eidolarch photo workflow when **Photos** is selected.

- Large global **Photos | Videos | All** switch; Photos is the default.
- Add `IMAGE_EXTS`, `VIDEO_EXTS`, `SUPPORTED_EXTS`.
- Extend `photos` with `media_type` and `duration_ms` without renaming legacy tables/IDs.
- Split catalog processing: Pillow for images, bundled `ffprobe`/`ffmpeg` for videos.
- Video MVP: metadata, thumbnail, duration, dimensions, SHA-256, browsing, exact duplicates and file operations.
- Duplicate Workspace respects the media switch and remains exact-only.
- Shared viewer shell with separate photo/video renderers.
- Video cards show thumbnail, play marker and duration.
- Decouple catalog/hash/thumb stages from `embedder.ensure_loaded()` so cheap indexing works without AI.
- Localize all new UI in Russian and English.
- Refresh README, Help, Architecture, Implementation Status and roadmap as video support lands.

## After 2.4

- 2.5: Windows application packaging / installer.
- 2.6: Similarity workspace.
- 2.7: Series.
- 2.8: Best-shot curation.
- 2.9: People and pets.
- 3.0: Unified curator/search.
