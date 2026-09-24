# Eidolarch 2.3.0

First hierarchical duplicate-groups release.

## Duplicate workspace
- Duplicate mode now groups matching files by physical location instead of showing a flat photo list.
- Hierarchy: **Duplicate group → Location → File**.
- Current v1 uses only the isolated exact-duplicate source contract from `db.exact_duplicate_rows()`.
- Direct parent folders are used as locations; no directory-tree inference is performed.
- Matching logical files receive the same per-group color marker across locations.
- Hovering one duplicate highlights its counterparts in the other location sections.
- Weak redundant cross-folder bridges are suppressed without collapsing otherwise distinct folder relationships.
- Same-folder exact duplicates remain visible as one-location groups.

## Compatibility / safety
- Existing `/api/duplicates` and per-photo duplicate APIs are unchanged.
- Viewer duplicate behavior is unchanged.
- Group-level deletion is deliberately not included in this first version.
- HTML release versions are injected from the backend at serve time to reduce cache/version drift between static shells.

## Next
- Validate grouping against the real archive.
- Improve large-group rendering and summaries.
- Add path-priority recommendations.
- Add safe location-level cleanup only after the grouping proves reliable.
