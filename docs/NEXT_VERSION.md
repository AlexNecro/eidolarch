# Eidolarch 2.2.x — Stabilization before 2.3

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

### 4. Duplicate workspace
- Render actual duplicate groups instead of one very wide row per file.
- Show all copy locations, size, dimensions, date, exact/near type and path-priority status directly in the group.
- Group/compare copies by folder/package where useful.
- Current file participates in keeper ranking but is never displayed/counts as its own duplicate.
- Database/results refresh immediately after file removal.
- Eidolarch may recommend; it must not silently remove originals or choose irreversible actions.

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
- Replace native browser `title` tooltips with one styled, localized Eidolarch tooltip/popover component.
- Search-field help must explain the query language.
- Constrain the large Help/About logo to roughly 240–320 px instead of filling the content pane.

### 10. Localization cleanup
- User-visible backend/frontend strings should be localization IDs.
- Missing keys fall back to English with a development warning.
- Never expose raw localization identifiers to the user.
