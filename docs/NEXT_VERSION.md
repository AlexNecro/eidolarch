# Eidolarch 2.3 — Duplicate workspace

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
5. The user confirms which copies go to the Windows Recycle Bin.
1. **Photo identity / wrong-photo regression**
   - verify repeated opens against the real library;
   - diagnose `thumbnail photo_id/path` versus `viewer photo_id/path/original` when a mismatch occurs;
   - provide thumbnail rebuild/invalidation diagnostics for stale-cache cases.
- Path-priority rules for any path/subfolder, for example:
2. **Object detection cleanup**
   - duplicate detections can still survive for one physical animal; add a final merge pass using IoU + containment/center similarity and log why candidates were suppressed;
   - partial hands/legs/body fragments can still be returned as `person`; do not offer these as nameable identity candidates (eventually gate person naming through face detection);
   - `Re-detect and save` must preserve confirmed names where a replacement bbox can be matched safely;
   - add library/folder-wide object re-scan controls.
```
3. **Object naming UI state**
   - saving one name must not clear drafts typed into other detection cards;
   - do not rerender/lose unrelated draft inputs after a save;
   - show explicit `saving / saved / unsaved changes` state and redraw the server-confirmed entity name.

4. **Duplicates workspace**
   - render actual duplicate groups instead of wasting a full row per file;
   - show all copy locations, size, dimensions, date, exact/near type and path-priority status directly in the group;
   - group/compare copies by folder/package where useful;
   - current file participates in keeper ranking but is never displayed/counts as its own duplicate.
- Database/results refresh immediately after file removal.
- Duplicate-mode sorting and Grid / Content / Details parity.
   - profile refresh latency on the real library and cache results by photo + embedding revision;
   - remove remaining N+1 work;
   - reference photo stays separate from results and empty state must be explicit;
   - if brute-force search is still slow, introduce an ANN index.
Eidolarch may recommend; it must not silently remove originals or choose irreversible actions on the user's behalf.
6. **Sorting audit**
   - verify Search/Folders/Tags/Duplicates end-to-end;
   - add explicit `Relevance` for semantic search;
   - semantic search should choose its relevance shortlist first, then apply the selected secondary sort consistently.
   - add autocomplete/chips for `@` and `#`;
   - plain text should eventually combine semantic, OCR, filename/path and metadata;
   - OCR is required for photographed documents/screens/signs, not an optional afterthought.

8. **Tooltips and help UX**
   - replace native browser `title` tooltips with one styled, localized Eidolarch tooltip/popover component;
   - search-field help must explain the query language;
   - constrain the large Help/About logo to roughly 240–320 px instead of filling the content pane.

9. **Localization cleanup**
   - user-visible backend/frontend strings should be localization IDs;
   - missing keys fall back to English with a development warning, never expose raw identifiers.
