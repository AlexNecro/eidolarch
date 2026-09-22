# Eidolarch 2.2.x — Stabilization before 2.3

## 2.2.15 — Cards and UI polish

Target:
- make the three browse modes meaningfully different;
- replace stretched Content rows with Cards;
- surface duplicate context directly in Cards;
- reduce intrusive tooltips;
- make the relationship graph visually lighter and more responsive.

Implemented:
- Content is now **Cards**: large preview + left metadata panel + right context panel.
- The right context panel shows duplicate copies with thumbnails, paths and match metadata.
- Grid/Tiles remains the dense visual browsing mode.
- Details/Table is intentionally left mostly unchanged for now.
- The large viewer-stage shortcut tooltip is removed; only control-specific tooltips remain.
- Relationship-graph edges are thinner and hover de-emphasis is softer.

Deferred from 2.2.15:
- product launcher/backend lifecycle;
- duplicate-package workspace;
- entity detector cleanup and pet/face classification refinements.
### 2.2.15 follow-up observations
- **View switch regression:** Grid / Cards / Table buttons are visible but no longer respond to clicks. Treat as a release-blocking UI regression before further Cards work.
- **Cards duplicate context:** show duplicate copies as **text rows only** (path/name + match metadata). Thumbnails are redundant because duplicates are expected to depict the same image and consume valuable horizontal/vertical space.
- **Viewer zoom controls:** restore concise control-specific tooltips, but do not attach one large tooltip to the whole image stage. Rework **100%** and **Fit** as mutually exclusive/radio-style view modes. Remove the extra textual mode label to the right; the active button itself is sufficient state.
- **Cards hover sizing:** reduce base card height/scale very slightly so the hover-enlarged active card remains fully inside the viewport/grid gutter and its side borders are not clipped. Preserve the subtle enlargement effect.



## Completed in 2.2.10

- Viewer/photo identity hardening:
  - thumbnail cache identity now uses `path + mtime_ns + size`;
  - thumbnail URLs carry a file-version token;
  - originals are served `no-store` in the viewer;
  - viewer image requests and side-panel requests use separate request generations.
- Viewer context navigation:
  - standalone viewer receives the ordered source photo IDs;
  - Left/Right follows that source context;
  - Similar/Duplicate result clicks open a new viewer instead of replacing the parent viewer.
- Object workflow:
  - `Re-detect and save` for the current photo;
  - detector revision/timestamp shown in Objects;
  - bbox highlight on hover/click;
  - manual entity assignment is preserved across re-detect when the replacement bbox strongly overlaps the previous named object.
- Duplicate viewer correctness:
  - current file is returned separately from actual duplicates;
  - current file is never counted as its own duplicate;
  - exactly one keeper is recommended on ranking ties.
- Similar:
  - reference photo is displayed separately;
  - explicit empty state retained;
  - low-level visual signatures are cached by physical file version.
- Native `title` help cursor no longer changes the search input cursor to a question mark.


## Completed in 2.2.11

- Styled/localized tooltip system replaces browser-native tooltip boxes in the main UI.
- Search hint explains plain text / @entity / #tag syntax and marks @entity as planned.
- Duplicate badge remains spatially stable at the tile's top-left and is itself the duplicate action.
- Hover toolbar reveals only the other actions to the right of the persistent duplicate badge.
- Duplicate path preview appears only when hovering the duplicate badge, reducing accidental obstruction.

## Completed in 2.2.13

- `@name` exact named-entity search.
- Entity autocomplete after typing `@`.
- Duplicate hover action reuses the duplicate badge position instead of shifting the target.
- Content/list view exposes several duplicate paths directly under the current path.
- Details no longer shows an unexplained bare dash for a missing capture date.

## Completed in 2.2.15

- Fixed the Grid / Cards / Table switch regression caused by iterating a single element instead of the full tile collection.
- Cards duplicate context now uses compact text rows instead of redundant thumbnails.
- Restored concise tooltips for the 100% and Fit viewer controls.
- 100% and Fit now behave as mutually exclusive view-mode buttons; the redundant textual mode label was removed.
- Cards are slightly smaller and use a gentler hover scale plus wider outer gutter so the active border remains visible.

## Critical fixes still open

### 1. Photo identity / wrong-photo regression
- Verify repeated opens against the real library.
- Diagnose `thumbnail photo_id/path` versus `viewer photo_id/path/original` when a mismatch occurs.
- Provide thumbnail rebuild/invalidation diagnostics for stale-cache cases.

### 2. Object detection cleanup
- Duplicate detections can still survive for one physical animal.
- Add a final merge pass using IoU + containment/center similarity and log why candidates were suppressed.
- Partial hands/legs/body fragments can still be returned as `person`; do not offer these as nameable identity candidates.
- Eventually gate person naming through face detection.
- Add library/folder-wide object re-scan controls.

### 3. Object naming UI state
- Saving one name must not clear drafts typed into other detection cards.
- Do not rerender/lose unrelated draft inputs after a save.
- Show explicit `saving / saved / unsaved changes` state.
- Redraw the server-confirmed entity name after save.

### 4. Duplicate package workspace
The primary unit should be a **package of duplicated folder/branch content**, not one pair per file.

Example: ten logical photos duplicated between folder A and folder B should appear as one package with two columns/lanes of ten matching items, not ten unrelated groups of two.

Planned behavior:
- Build low-level logical duplicate sets first, then aggregate them by folder/branch overlap.
- Display one package as a matrix:
  - columns = duplicate locations / folders / branches;
  - rows = logical photos;
  - gaps explicitly show files missing from one copy.
- Support 2, 3 or more duplicate locations in one package.
- Show overlap metrics such as `997 common / 1000 total`, unique-only counts and estimated reclaimable space.
- Folder/branch actions delete only files that are confirmed duplicates elsewhere; unique files are never silently removed.
- If a two-copy row loses one copy after deletion, it disappears from Duplicate workspace immediately because it is no longer duplicated.
- If three copies become two, the row remains with a visible gap in the removed location.
- Allow a package-level action such as “move 997 confirmed duplicates from Camera Roll to Recycle Bin”.
- Apply path-priority rules to recommend a preferred location, but recommendations remain reversible/user-confirmed.
- Refresh database and UI immediately after every file operation.

### 5. Details view / duplicate hover UX
- The current large hover overlay obscures the row being inspected; remove it from Details mode or replace it with a compact non-covering tooltip/popover.
- Duplicate locations and other important metadata should be visible directly in Details columns, not hidden behind hover.
- Details mode should behave like a real details/table view, not a stretched Content view.
- Add a fixed/sticky header row for columns.
- Clicking a column header should sort quickly by that column; clicking again reverses direction.
- Consider columns: Name, Folder/Path, Date, Dimensions, Size, Duplicate count/type, Path priority, Rating, Keeper status.
- Preserve the same central/current photo when switching Grid / Content / Details views.

### 6. Similar performance
- Profile refresh latency on the real library and cache results by photo + embedding revision.
- Remove remaining N+1 work.
- Keep the reference photo separate from results and explicit empty state.
- If brute-force search remains slow, introduce an ANN index.

### 7. Sorting audit
- Verify Search/Folders/Tags/Duplicates end-to-end.
- Add explicit `Relevance` for semantic search.
- Semantic search should choose its relevance shortlist first, then apply the selected secondary sort consistently.
- In Details mode, column-header sorting should use the same backend sort contract rather than a separate client-only implementation.

### 8. Search language / named entities
- `@name` = named person/pet.
- `#tag` = exact tag.
- Plain text = broad search.
- `мойва` and `@Мойва` must remain different queries.
- Add autocomplete/chips for `@` and `#`.
- Plain text should eventually combine semantic, OCR, filename/path and metadata.
- OCR is required for photographed documents/screens/signs, not an optional afterthought.

### 9. Tooltips and help UX
- Continue migrating any remaining secondary-window/browser-native `title` hints to the shared tooltip system.
- Constrain the large Help/About logo to a compact fixed size if it still renders oversized on cached clients.

### 10. Localization cleanup
- User-visible backend/frontend strings should be localization IDs.
- Missing keys fall back to English with a development warning.
- Never expose raw localization identifiers to the user.


### 11. Product-mode launcher and backend lifecycle
- Ordinary users should launch one Eidolarch application and never need to know that a local HTTP backend exists.
- If the backend is already running, launching Eidolarch should simply open a new main window.
- If it is not running, the launcher starts it hidden, waits for health, then opens the client.
- Closing the client must not leave the user unable to reopen it.
- Default product behavior: when the last UI window closes, keep the backend alive briefly and then stop it unless background indexing/tray mode is explicitly enabled.
- Keep `run_console.bat` as the developer/debug path with visible logs.
- Later package this into a real `Eidolarch.exe`/installer rather than exposing Python/Uvicorn.

### 12. Entity classifier refinement
- YOLOS remains useful for proposing object boxes but is not reliable enough as the final cat/dog identity classifier.
- For animal detections, classify the crop with the stronger SigLIP model (`dog` vs `cat`) before treating it as a pet candidate.
- For people, separate generic person-presence from identity candidates; require a usable face before offering naming.
- Merge duplicate animal detections more aggressively using IoU/containment/center similarity.
- Preserve confirmed entity names and unsaved UI drafts across re-detection.
