# Eidolarch v2.0.2 architecture

```text
Edge/Chrome app-mode / PWA / LAN browser
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
 ratings   recycle     object detector
 entities  explorer    similar search
 hashes    print/open
     │
 background Indexer + watchdog + periodic reconciliation
```

## Principles

- Original files are not modified for metadata operations.
- User metadata is stored in SQLite and backed up separately from rebuildable thumbnails/embeddings.
- Remote LAN clients are read-only by default; local-only shell/file mutation routes reject non-loopback clients.
- Multiple UI windows share one backend/model/database but keep navigation state independently in each JS context.
- AI embedding sets are versioned by provider/model, so model changes do not overwrite older indexes.
- Background jobs are lower priority than interactive UI/search and can be paused or throttled.
- UI text lives in locale resource files; theme and language support `System/Auto` modes.

## Documentation ownership

- `README.md`: user-facing installation and current-version overview.
- `PRODUCT_SPEC.md`: product/UX requirements and intended behavior.
- `ROADMAP.md`: unfinished backlog and research-heavy future work.
- `IMPLEMENTATION_STATUS.md`: factual implementation state only.
- `ARCHITECTURE.md`: technical structure and engineering principles.


## Hardware and AI policy (2.2+)

Eidolarch must not require a discrete GPU. The processing cascade is intentionally layered:

1. **Tier 0 / CPU-cheap** — metadata, thumbnails, SHA-256, perceptual hashes, simple quality metrics.
2. **Tier 1 / embedding** — one general visual embedding model for semantic search and similarity. CPU is supported; CUDA only accelerates it.
3. **Tier 2 / specialized** — faces, people/pets, OCR only where useful.
4. **Tier 3 / expensive reasoning** — VLM analysis only for explicitly selected groups/series, locally when hardware permits or through an optional remote provider.

Performance profiles are Eco, Balanced and Performance. Model/provider identity is part of persisted embeddings; changing models must not silently mix incompatible vectors.
