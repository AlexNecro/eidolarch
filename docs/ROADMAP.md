# Eidolarch roadmap

Eidolarch is a local-first photo triage and curation tool. GPU acceleration is optional; the product must remain useful on a normal CPU-only Windows PC.

## 2.2 — Foundation and stabilization

### 2.2.4 — current stabilization release
- Eidolarch branding and application icons for Windows, PWA and in-app header.
- AI-search crash fixed when vector-search rows lack optional metadata.
- Error-report ZIP from Diagnostics with runtime/index/model state and recent logs, without photos, database or API keys.
- Duplicate-mode sorting fixed to use the selected order on the backend.
- Cache/version synchronization tightened across launcher, frontend and service worker.
- Git-safe `.gitignore` suitable for publishing directly from a working installation.

### Foundation already present
- PhotoMind → Eidolarch data compatibility.
- Stable indexing/recovery and background jobs.
- Eco / Balanced / Performance; CPU / CUDA / Auto.
- Viewer zoom, pan, 100%, fit and fullscreen.
- QR-first LAN access and optional custom public URL.
- Folder picker, first-run onboarding, recursive folder counts and Explorer-style `[..]`.
- Grid / Content / Details views and floating scroll-to-top.
- Settings tabs and diagnostics.

## 2.3 — Duplicate workspace (next version)

Goal: turn duplicate detection into a safe decision workflow rather than a red border and a count.

- Show duplicate locations directly in Duplicate mode: current path + first 2–3 duplicate paths + `… more N`.
- Expand a duplicate group to the full list with path, file size, dimensions, capture date and metadata differences.
- Apply configurable path-priority rules to recommend which copy to keep, including rules for arbitrary subfolders, not only library roots.
- Combine path priority with technical evidence: original resolution, EXIF retention, file size/encoding and manual rating.
- Clearly explain `recommended to keep` and `candidate for removal`; never delete automatically.
- Package/folder comparison: detect when the same duplicate set exists in organized folders and in import dumps such as `Photo\...` versus `Camera Roll\...`.
- Bulk review and Recycle Bin workflow with confirmation and post-delete database synchronization.
- Ensure sorting, Grid/Content/Details and central-photo preservation work identically inside Duplicate mode.

## 2.4 — Similarity workspace
- Sort a selection/folder by similarity to a reference image.
- Cluster/group visually similar photos.
- Manual triage labels: Keep / Reject / Neutral.
- Filtering and bulk actions by triage label.

## 2.5 — Series
- Detect shooting series from time proximity + perceptual/embedding similarity.
- Present a series as one review unit.
- Cheap CPU quality metrics: sharpness, motion blur, exposure, resolution/noise.

## 2.6 — Best-shot curation
- “These 10 are very similar; keep 2” workflow.
- Ranking combines technical quality with diversity so selected frames are not near-identical.
- Explanations such as sharper, eyes open, different pose, better exposure.
- AI proposes only; deletion always requires user confirmation.

## 2.7 — People
- Face detection → face embeddings → clustering → naming.
- Named people are first-class entities, not merely tags.

## 2.8 — Pets
- Dog/cat detection → crop embeddings → per-pet prototypes.
- Interactive identification for pets such as Tera and Nyusha; uncertain matches require confirmation.
- Multiple prototypes per animal to handle age, pose and lighting.

## 2.9 — Unified search
- Combine semantic image search, named entities, EXIF/time, folders, tags and user triage.
- Queries such as “Nyusha in the car”, “Tera at the dacha”, “Vladislav with the dog”.

## 3.0 — Curator
- Unified cleanup dashboard: duplicates, near-duplicates, similar series, low-quality frames and estimated reclaimable space.
- Guided group-by-group review instead of unsafe one-click cleanup.
- Highlights: automatically surface technically strong and diverse photos/series, locally by default.

## Later
- On-demand VLM reasoning for a selected series, optionally remote.
- OCR.
- GPS map in the viewer with privacy-preserving lazy loading and links to Google Maps / Yandex Maps / 2GIS.
- Event grouping and richer relationship graph.
