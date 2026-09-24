# Eidolarch roadmap

Eidolarch is a local-first photo triage and curation tool. GPU acceleration is optional; the product must remain useful on a normal CPU-only Windows PC.

## 2.2 — Foundation and stabilization

### 2.2.14 — Cards and UI polish
- Distinct browse modes:
  - **Tiles** — dense visual browsing;
  - **Cards** — large preview + metadata + contextual right panel;
  - **Table** — compact metadata mode, intentionally deferred for deeper work later.
- Cards expose duplicate copies directly with thumbnail/path/match information.
- Viewer tooltips are control-specific; no large tooltip covers the zoom toolbar.
- Relationship graph uses lighter/thinner interaction styling.
- Favorites, entity search (`@name`), separate Help/Viewer/Settings/Graph windows and cross-window locale/theme propagation are part of the stabilized shell.

### Foundation already present
- PhotoMind → Eidolarch data compatibility.
- Stable indexing/recovery and background jobs.
- Eco / Balanced / Performance; CPU / CUDA / Auto.
- Viewer zoom, pan, 100%, fit and fullscreen.
- QR-first LAN access and optional custom public URL.
- Folder picker, first-run onboarding, recursive folder counts and Explorer-style `[..]`.
- Settings tabs, diagnostics, Favorites, named-entity search and PWA shell.

## 2.3 — Duplicate groups

Goal: expose where matching files have been copied without mixing this workflow with visual similarity.

- Current duplicate workspace uses the hierarchy **Duplicate group → Location → File**.
- In v1 a location is the file's direct physical parent folder.
- The UI does not depend on SHA-256 details; duplicate identity is isolated behind a replaceable matcher/helper.
- Groups may overlap: one physical/logical file may participate in more than one meaningful folder relationship.
- Weak bridge relations are suppressed when the same shared files are already represented through a stronger common location.
- Matching logical files use stable color markers across locations and highlight their peers on hover.
- Same-folder duplicates remain representable as one-location groups.

Next:
- validate grouping on the real archive;
- add scalable compact/expanded rendering for very large groups;
- show overlap/unique counts and reclaimable size;
- use path-priority rules for recommendations;
- add safe location-level cleanup only after validation: confirmed duplicates only, Recycle Bin, immediate UI refresh.

## 2.4 — Entities: people and pets
- Improve object proposals and identity workflow before scaling automation.
- Animals: detector proposes boxes; SigLIP classifies crop as dog/cat and later identifies individual pets via prototypes/candidates.
- People: person detection is not enough for naming; require usable face → face embedding → candidate/cluster.
- Merge duplicate detections of one animal.
- Candidate review: confirm/reject before aggressive propagation.
- Named entities such as Tera, Nyusha, Moyva and people are first-class search filters.

## 2.5 — Similarity workspace
- Sort a selection/folder by similarity to a reference image.
- Cluster/group visually similar photos.
- Manual triage labels: Keep / Reject / Neutral.
- Filtering and bulk actions by triage label.

## 2.6 — Series
- Detect shooting series from time proximity + perceptual/embedding similarity.
- Present a series as one review unit.
- Cheap CPU quality metrics: sharpness, motion blur, exposure, resolution/noise.

## 2.7 — Best-shot curation
- “These 10 are very similar; keep 2” workflow.
- Ranking combines technical quality with diversity.
- Explanations such as sharper, eyes open, different pose, better exposure.
- AI proposes only; deletion always requires user confirmation.

## 2.8 — Unified search + OCR
- Combine semantic image search, named entities, EXIF/time, folders, tags, OCR and user triage.
- Plain text searches semantic/OCR/filename/path/metadata.
- `@name` is an exact named entity.
- `#tag` is an exact tag.
- OCR indexes documents, screenshots, signs and photographed text.

## 2.9 — Product packaging
- One user-facing Eidolarch launcher/application.
- Hidden local backend; no server console in normal use.
- Relaunch opens a window against an already-running backend.
- Optional tray/background indexing mode.
- Keep visible console mode only for development/diagnostics.
- Installer/updater based on GitHub Releases; Git is not required on end-user machines.

## 3.0 — Curator
- Unified cleanup dashboard: duplicate packages, near-duplicates, similar series, low-quality frames and estimated reclaimable space.
- Guided group-by-group review.
- Highlights: technically strong and diverse photos/series, locally by default.

## Later
- On-demand VLM reasoning for selected groups.
- GPS map with privacy-preserving lazy loading.
- Event grouping and richer relationship graph.
