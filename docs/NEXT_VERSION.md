# Eidolarch — Active work

## 2.3.0 — Duplicate groups v1

Current duplicate workspace is intentionally conservative.

- **Duplicates means matching files**, not visually similar photos.
- The current matcher is isolated behind `db.exact_duplicate_rows()`; the UI and grouping code do not depend on SHA-256 details.
- First-version hierarchy: **Duplicate group → Location → File**.
- A **Location** is the direct physical parent folder of a file. No tree inference, parent lifting, or smart branch reconstruction yet.
- A group represents a meaningful duplicate relationship between locations; groups may overlap.
- Weak cross-folder overlap is suppressed only when those same files are already represented through a stronger common location.
- Same-folder exact duplicates remain visible as a one-location group.
- Matching logical files use the same color marker across locations. Hovering one highlights its counterparts.
- Legacy per-photo duplicate APIs and Viewer duplicate behavior remain unchanged.
- Group-level destructive actions are deliberately deferred until the grouping is validated on the real library.

### Example that defines the grouping rule

If `Photos` shares 10 files with `Photo\Vacation`, 12 with `Photo\Concert`, and 2 of those files also occur in both `Vacation` and `Concert`, the intended result is:

- `Photos ↔ Photo\Vacation` — 10 matching files;
- `Photos ↔ Photo\Concert` — 12 matching files;
- no separate weak `Vacation ↔ Concert` group for those same 2 bridge files.

Distinct duplicate relations must not disappear merely because the folder graph contains a cycle.

## Next duplicate-workspace work

1. Validate grouping against the real library and adjust the redundant-bridge rule if needed.
2. Decide the compact/expanded presentation for very large groups (hundreds or thousands of files).
3. Add overlap/unique counts and reclaimable-space summaries.
4. Add path-priority recommendations at location level.
5. Only after validation, add safe location-level cleanup:
   - remove only files that still have confirmed duplicate copies elsewhere;
   - never remove unique files as part of a duplicate action;
   - use Windows Recycle Bin;
   - refresh the group immediately after every deletion.

## Deferred

- Product launcher / hidden-backend lifecycle.
- Entity detector cleanup and pet/person classifier refinement.
- Full Table-mode redesign.
- OCR and later curator/series work.
