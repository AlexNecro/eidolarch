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


## 2.2.10 stabilization
- Thumbnail cache keys now include path + mtime_ns + size; browser thumbnail URLs also carry the file version.
- Viewer original responses are no-store and image requests are request-scoped to reduce stale/race behavior.
- Standalone viewer carries a navigation context; Similar/Duplicate result clicks open a child viewer instead of replacing the parent.
- Object panel supports re-detect-and-save, preserves manual entity assignments when new boxes strongly overlap, and can highlight detector boxes on the image.
- Duplicate viewer separates the current file from actual duplicates and does not count the current file as its own duplicate.
- Similar visual signatures are cached by physical file version; reference photo / empty-result UI is explicit.

## 2.2.11 interface stabilization
- Replaced native browser-style tooltips in the main UI with a single styled/localized Eidolarch tooltip system.
- Search-field tooltip documents current/planned query syntax without claiming @entity is already active.
- Duplicate count badge stays anchored in the top-left and acts as the duplicate action; hover actions no longer replace or reorder it.
- Duplicate path preview is requested only when hovering the duplicate badge, rather than on every tile hover.

## 2.2.12 entity search / duplicate UI
- `@name` now filters by named entities instead of falling through to semantic search.
- Search autocomplete suggests existing named entities after `@`.
- Duplicate hover action overlays the duplicate badge position.
- Content/list view shows the current file path prominently and up to three duplicate paths beneath it.
- Missing capture date in Details is shown as an explicit localized label instead of a bare dash.

## 2.2.13 UI polish
- Fixed view-switch active state and Content duplicate-path hydration.
- Added Favorites as a first-class main mode.
- Removed redundant tile Info action; normal click already opens Info.
- Main/settings/viewer windows now react to language/theme changes from sibling windows.
- Standalone viewer uses Eidolarch tooltips instead of browser-native title popups.
- Relationship graph moved to its own app window; hovering a node highlights its incident edges.
- Restored the detailed Help emblem.

## 2.2.14 Cards and UI polish
- Reworked Content into Cards: preview + metadata + duplicate context panel.
- Cards show duplicate thumbnails, paths, match type and size when available.
- Grid/Tiles stays image-dense; Details/Table is intentionally deferred.
- Removed the large viewer-stage shortcut tooltip that covered the zoom toolbar.
- Relationship graph edges are thinner and hover de-emphasis is softer.
- Fixed collection-selector regressions that prevented Cards duplicate hydration and view-button active state.
