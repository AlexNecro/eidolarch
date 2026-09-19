# Eidolarch

Eidolarch is a local-first photo gallery for Windows with local photo triage: folder browsing, duplicate detection, similarity search, semantic search, EXIF inspection and ordinary file-management operations. The Python/FastAPI backend runs locally; the UI is a web app that can be opened as a desktop-style Edge/Chrome app window or from another device on the LAN.

## Current capabilities

- Browse multiple photo folders and subfolders without waiting for AI indexing.
- Natural-language image search using local image/text embeddings.
- Folder and cumulative tag navigation.
- Exact/near duplicate detection and visually similar photos.
- EXIF/details inspector, manual tags, favorites, rating, color labels and comments.
- Background indexing with GPU/CPU fallback and selectable AI backend.
- Multi-selection and common file operations: copy, move, rename, Recycle Bin, Explorer, external viewer and print.
- Multiple independent UI windows over one backend.
- Dark/light/system themes, Russian/English UI, LAN access and PWA shell.
- Built-in help available from the `?` button in the application.

## Quick start on Windows

1. Extract the archive to a writable folder.
2. Run `run.bat`.
3. Add one or more photo folders in **Settings**.
4. Eidolarch starts indexing automatically. Browsing works immediately; AI search improves as indexing progresses.

The bootstrap creates `.venv`, installs Python if necessary and installs a CUDA-enabled PyTorch build when a compatible NVIDIA GPU is available. CPU fallback is supported.

> Keep the `data/` directory when updating. It contains the local database and generated index data. Distribution archives do not intentionally ship a working user database.

## Privacy

Eidolarch is local-first. Originals stay in their existing folders. Thumbnails, metadata and AI indexes are stored separately. Remote AI backends and LAN access are optional.

## Documentation

User documentation is built into the application (`?` in the top bar). Developer-oriented documents are in [`docs/`](docs/):

- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)
- [`ROADMAP.md`](docs/ROADMAP.md)
- [`NEXT_VERSION.md`](docs/NEXT_VERSION.md)

## Development status

Eidolarch is an experimental project. Core browsing, indexing and search work, but some subsystems are still being tuned, especially entity recognition, similarity grouping/ranking and packaging. The design target is CPU-first compatibility with optional GPU acceleration.

## Run from console

Use `run_console.bat` to keep the backend console visible while debugging.

## License

A license has not been selected yet.

### UX / help maintenance

- [`UX_AUDIT.md`](docs/UX_AUDIT.md) tracks controls and states that still need clearer affordances or contextual help.


### v2.1.2

- Автотеги теперь калибруются по распределению всей библиотеки, а не выдаются как top-N для каждого фото.
- Для каждого понятия действует собственный предел распространённости и robust-порог; шумные специальные теги (`текст`, `документ`, `экран`, `селфи`) стали значительно строже.
- Ограничено количество тегов одной категории и общее число автотегов на фотографию.
- После индексации выполняется быстрый векторный пересчёт автотегов без повторного чтения изображений.
- Пересборка тегов записывается одной транзакцией и заметно быстрее на больших библиотеках.

### v2.1.1
Stability hotfix for object recognition and Favorites, with built-in diagnostics and fail-fast background jobs.


## v2.2.1

First Eidolarch-branded foundation release. Keeps legacy PhotoMind data automatically, adds CPU/GPU-oriented performance profiles, QR-first LAN access, richer duplicate hover paths, and a zoom/pan/fullscreen standalone viewer.


### v2.2.3
- Fixed stale desktop/PWA client after upgrades: cache-busted assets, no-cache HTML/service worker, launcher uses a unique versioned URL, and client/backend version mismatch triggers a one-time reload.
- `/api/info` and diagnostics now report the actual application version.
- Added favicon route.


### v2.2.4
- Stabilization release: new Eidolarch icon family, duplicate sorting fix, AI-search error handling/reporting, cache/version synchronization and Git-safe working-folder publishing.
