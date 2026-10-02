# Eidolarch 2.3.1

Duplicate-workspace actions and physical-copy clarity.

## Duplicate workspace

- Location counters now separate physical files, logical matches, and additional copies inside the same location.
- Russian counters use correct plural forms for files, images, copies, and locations.
- Multiple physical copies of one logical file in the same location receive a shared soft visual treatment while preserving the existing logical-id marker and peer hover.
- Duplicate groups use the available workspace width more effectively.

## Actions

- File-level actions: open externally, open containing folder, move safely to Recycle Bin.
- Location-level actions: open folder and remove only confirmed duplicate files.
- Bulk duplicate removal always runs through preview first: file count, total size, affected locations, and skipped files are shown before confirmation.
- The server revalidates exact duplicates immediately before deletion.
- A file is removable only when an exact SHA-256 copy still exists outside the requested delete set.
- Last confirmed copies and unavailable files are skipped automatically.
- Removal uses the existing Windows Recycle Bin path; no permanent deletion is introduced.

## Compatibility

- Similar remains separate from Duplicates.
- Existing `/api/duplicates`, `/api/photos/{id}/duplicates`, Viewer behavior, and generic file operations remain available.
