# Eidolarch 2.3.7

Duplicate Workspace UX and safety hotfix.

## Changes
- Removed the redundant Duplicate Workspace context title beside the active Duplicates tab.
- Removed the obsolete `run_console.bat`; `run.bat`, `debug.bat`, and `repair.bat` remain the supported launch paths.
- Automatic preferred-location selection now uses folder depth as a tie-breaker after explicit storage priority, so a more specific subfolder is preferred over its parent when priorities are equal.
- Single-location duplicate groups no longer show Preferred location or “remove from others” controls.
- Single-location groups with extra physical exact copies now offer a dedicated safe “Remove additional copies” action.
- The single-location cleanup preview reports files to remove, files remaining, and reclaimable space.
- Destructive actions continue to revalidate exact-copy safety immediately before moving files to the Windows Recycle Bin.

## Compatibility
- Duplicate semantics remain exact-file only.
- Similar remains separate.
- Existing duplicate endpoints and Viewer behavior are preserved.
