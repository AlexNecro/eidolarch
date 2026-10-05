# Eidolarch 2.3.7

Final Duplicate Workspace polish before the 2.4 video foundation.

## Duplicate cleanup

- Same-folder exact-copy cleanup now keeps the physically oldest file by filesystem creation time.
- Duplicate filename patterns such as `(2)`, `copy` or localized equivalents are not used to decide which file survives.
- Existing preview, exact-copy revalidation and Windows Recycle Bin safeguards remain in place.

## Main-window cleanup

- Removed the redundant current-section breadcrumb/title next to the main mode buttons at library root, Favorites and Duplicates.
- Folder breadcrumbs remain available once the user actually navigates into a library folder.
- `Reset all` is no longer shown in Favorites or Duplicates; those modes already have explicit top-level navigation.

## Documentation

- Roadmap renumbered around the scope of the upcoming video work.
- 2.4 is now Video foundation.
- 2.5 is Windows application packaging.
- Similarity, Series, Best-shot and mature People/Pets work move to later minor releases.
- README, Help, Architecture, Implementation Status and UX notes were refreshed to match current behavior.
