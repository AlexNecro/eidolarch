# Eidolarch

Eidolarch is a local-first Windows photo gallery and cleanup tool focused on large personal photo archives: browse folders, find duplicates, search by visual meaning, inspect metadata, and gradually build named people/pet entities without uploading the library to a cloud service.

Current version: **2.3.0**.

## What Eidolarch can do now

- Browse multiple photo roots and subfolders immediately, without waiting for AI indexing.
- Natural-language semantic photo search using local image/text embeddings.
- Folder and cumulative tag navigation.
- Exact and near-duplicate detection.
- Visually similar-photo search.
- EXIF/details viewer with zoom, pan, fullscreen and separate viewer windows.
- Object detection for people/cats/dogs with diagnostics and manual naming.
- Manual metadata: tags, favorites, ratings, color labels and comments.
- Common file operations: copy, move, rename, open in Explorer, external viewer, print and move to Windows Recycle Bin.
- Background indexing with CUDA/CPU fallback.
- Multiple independent UI windows over one local backend.
- Russian/English UI, dark/light/system themes, LAN access and PWA shell.
- Built-in Help and Diagnostics.

## Current project focus

The project is still experimental. Current priorities:

1. **Cards / interface polish**
   - Tiles = dense visual browsing;
   - Cards = large preview + metadata + contextual right panel;
   - Table is intentionally deferred until the first two modes are clearly distinct.

2. **Duplicate groups**
   - current v2.3 workspace groups matching files as **Group → Location → File**;
   - locations are direct physical parent folders in the first version;
   - matching files keep the same visual marker across locations;
   - group-level cleanup is intentionally deferred until grouping is validated on the real library.

3. **Named entities**
   - `@name` exact entity search and autocomplete are already implemented;
   - next: duplicate-animal suppression, SigLIP crop classification for dog/cat, face gating for people and candidate review.

4. **Product packaging**
   - hide the local backend in normal use;
   - relaunch the client against an already-running backend;
   - keep visible console mode for development only.

The detailed active backlog is in [`docs/NEXT_VERSION.md`](docs/NEXT_VERSION.md).

## Quick start on Windows

1. Download the latest Windows ZIP from GitHub Releases.
2. Extract it to a writable folder.
3. Run `run.bat`.
4. Add the first photo folder when prompted, or use **+ Add folder** in the main window.
5. Browsing works immediately; AI indexes continue in the background.

On first launch Eidolarch creates `.venv`, installs Python if required, installs the application dependencies, and configures a compatible PyTorch/torchvision stack. An NVIDIA GPU is optional; CPU fallback is supported.

> Keep the `data/` directory when upgrading. It contains the local database and generated indexes. Release archives must not contain a user database, thumbnail cache, logs or browser profile.

## Search model

Current search supports a mixed query language:

- `@name` — exact named person/pet entity filter (implemented);
- `#tag` — exact tag/filter;
- plain text — semantic image search today, later expanded with OCR / filename / path / metadata.

Examples:

- `@Тера на диване`
- `@Алексей @Тера`
- `#документ 1С`

OCR is planned as a first-class search index for photographed documents, screenshots, signs and similar images.

## Privacy

Eidolarch is local-first:

- original photos stay in their existing folders;
- thumbnails, metadata and AI indexes are stored separately;
- local AI is the default design target;
- LAN access is optional;
- remote AI backends, if configured, are optional rather than required.

## Hardware

Eidolarch is designed to run without a discrete GPU.

Processing is layered:

1. cheap CPU work — metadata, thumbnails, hashes and duplicate analysis;
2. visual embeddings — CPU or CUDA;
3. specialized analysis — people/pets and future OCR/faces;
4. expensive reasoning — future optional VLM workflows.

## Development / diagnostics

Use `run_console.bat` to keep the backend console visible.

The application includes diagnostics for:
- AI/runtime state;
- torch / torchvision;
- object detector;
- indexing jobs;
- error reports.

Release builds are checked with `tools/check_release.py`.

## Documentation

Developer-oriented documents:

- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)
- [`NEXT_VERSION.md`](docs/NEXT_VERSION.md)
- [`ROADMAP.md`](docs/ROADMAP.md)
- [`UX_AUDIT.md`](docs/UX_AUDIT.md)

Release notes:
- [`RELEASE_NOTES_2.3.0.md`](docs/RELEASE_NOTES_2.3.0.md)

## Known experimental areas

- Named people/pet recognition is still experimental.
- Similar-photo ranking and performance are still being tuned.
- Duplicate groups are now experimental v1; bulk group cleanup is not enabled yet.
- Semantic search can return weak results for ambiguous short queries.
- OCR is not implemented yet; `@entity` search is implemented but the entity-recognition pipeline is still experimental.
- Some UI strings/tooltips still need localization cleanup.

## Safety of file operations

Eidolarch may recommend which duplicates to keep, but it should not silently delete originals or make irreversible decisions. Destructive operations should go through explicit confirmation and the Windows Recycle Bin where possible.

## License

A license has not been selected yet.
