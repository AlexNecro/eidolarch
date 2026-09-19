# Eidolarch 2.2.1 implementation status

## Implemented in this release
- Product branding switched to Eidolarch.
- Legacy `data/photomind.sqlite3` is reused automatically; no forced reindex on an in-place upgrade.
- New installs use `data/eidolarch.sqlite3`; `EIDOLARCH_DATA` is supported with `PHOTOMIND_DATA` fallback.
- Eco / Balanced / Performance indexing profiles, with compatibility mapping from old Background / Max values.
- QR icon for LAN access; existing LAN popup keeps URL/copy/open/QR actions.
- Duplicate-mode context title is now “Duplicate groups” instead of repeating the active “Duplicates” tab.
- Duplicate hover loads current file path plus up to two duplicate paths and an overflow count.
- Standalone viewer: wheel zoom, drag pan, 100%, Fit, fullscreen, side-panel toggle and shortcuts.

## Existing experimental areas
- Object detector / people-pet indexing remains experimental and must fail fast instead of producing thousands of identical errors.
- Auto-tags remain secondary derived metadata; named people/pets will become first-class entities in later releases.
- Similarity grouping, series and best-shot selection are roadmap items for 2.4–2.6.

## 2.2.1
Implemented the UX-foundation pass: folder picker/onboarding, recursive counts, parent navigation, sticky controls, Grid/Content/Details views, settings tabs, public URL for network QR, PWA shell, mobile viewer panel default-hidden, scroll-to-top and first duplicate path-priority scoring.
