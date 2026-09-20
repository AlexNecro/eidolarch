# Eidolarch 2.2.14

Cards and UI-polish release.

## Cards
- Reworked the former Content mode into **Cards**.
- Each card now has a large preview, a compact metadata area and a dedicated context panel.
- Duplicate context shows up to four duplicate copies with thumbnail, path, match type and file size when available.
- Grid/Tiles remains the dense visual mode; Details/Table is deliberately not redesigned in this release.

## Viewer and graph
- Removed the large viewer-stage shortcut tooltip that could cover the zoom toolbar.
- Kept short control-specific tooltips.
- Relationship-graph edges are thinner and hover emphasis is softer.

## Fixes
- Corrected view-switch active-state collection handling.
- Corrected Cards duplicate-context hydration so all visible cards can be populated.

## Planning
- Documented the Duplicate Package workspace: duplicated folders/branches become package columns rather than repeated file-pair groups.
- Documented product-mode launcher/backend lifecycle.
- Documented detector refinement: object boxes from YOLOS, stronger crop classification for pets, face gating for people.
