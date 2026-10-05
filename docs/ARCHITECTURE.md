# Eidolarch architecture

```text
Windows app window / PWA / LAN browser
            │
            ▼
        FastAPI backend
     ┌──────┼───────────────┐
     │      │               │
 SQLite   File API        AI manager
     │      │        local CUDA/CPU or remote
     │      │               │
 metadata  copy/move   SigLIP embeddings
 tags      rename      auto-tags
 ratings   recycle     person/cat/dog detector
 entities  explorer    similar search
 hashes    print/open
     │
 background Indexer + watchdog + periodic reconciliation
```

## Principles

- Original files are not modified for metadata operations.
- User metadata is stored in SQLite and backed up separately from rebuildable thumbnails/embeddings.
- Filesystem contents remain the source of truth; watchdog plus reconciliation repair missed create/delete/restore events.
- Remote LAN clients are read-only by default; local-only shell/file mutation routes reject non-loopback clients.
- Multiple UI windows share one backend/model/database but keep navigation state independently in each JS context.
- AI embedding sets are versioned by provider/model, so model changes do not overwrite older indexes.
- Background jobs are lower priority than interactive UI/search and can be paused or throttled.
- UI text lives in locale resources; new features must land in Russian and English together.
- Exact duplicates are byte-identical files backed by SHA-256; visual similarity is a separate subsystem.
- Destructive duplicate cleanup always uses preview, server-side revalidation and the Windows Recycle Bin.

## Duplicate workspace

The 2.3 workspace is **Duplicate group → Location → File**. The UI consumes an isolated exact-duplicate contract rather than SHA details directly. Preferred-location cleanup never widens beyond the displayed group. Same-folder cleanup keeps one physical exact copy, preferring the oldest filesystem creation time.

## Processing tiers

Eidolarch must not require a discrete GPU. Processing is layered:

1. **Tier 0 / CPU-cheap** — catalog, metadata, thumbnails, SHA-256 and filesystem reconciliation.
2. **Tier 1 / embedding** — general visual embeddings for semantic search/similarity; CPU supported, CUDA optional.
3. **Tier 2 / specialized** — people/pets and future OCR/faces.
4. **Tier 3 / expensive reasoning** — future VLM workflows on explicitly selected groups.

Cheap Tier-0 work should not require the embedding model to be loaded. This becomes especially important for the 2.4 video pipeline.

## 2.4 media extension direction

Video will be added as another media type while preserving the existing `photos`/`photo_id` compatibility layer. Images continue through Pillow; video metadata/thumbnails use bundled ffprobe/ffmpeg. Exact duplicate identity remains byte-based and therefore naturally supports either media type.

## Documentation ownership

- `README.md`: user-facing installation and current-version overview.
- `ROADMAP.md`: release milestones and future work.
- `NEXT_VERSION.md`: concrete next-release scope.
- `IMPLEMENTATION_STATUS.md`: factual implementation state.
- `ARCHITECTURE.md`: technical structure and engineering principles.
- built-in Help: user-visible behavior and troubleshooting.
