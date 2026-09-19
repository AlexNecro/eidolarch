# Eidolarch 2.3 — Duplicate workspace

The next feature release is focused on duplicate cleanup. The goal is not merely to find duplicates, but to help decide which physical copy should remain.

## Core workflow

1. Open **Duplicates**.
2. See the current file and the first duplicate locations immediately.
3. Expand a group for the complete comparison.
4. Eidolarch recommends a copy to keep using path rules and technical evidence.
5. The user confirms which copies go to the Windows Recycle Bin.

## Planned work

- Paths visible directly in duplicate cards: current path + 2–3 duplicate paths + overflow count.
- Full group details: path, size, dimensions, capture date, EXIF and encoding differences.
- Path-priority rules for any path/subfolder, for example:

```text
+100|N:\YandexDisk\Photo
-50|N:\YandexDisk\Camera Roll
```

- Recommendation explanation instead of opaque scoring.
- Folder/package duplicate comparison for organized archive trees versus import/camera-dump folders.
- Safe batch selection, confirmation and Recycle Bin workflow.
- Database/results refresh immediately after file removal.
- Duplicate-mode sorting and Grid / Content / Details parity.

## Safety rule

Eidolarch may recommend; it must not silently remove originals or choose irreversible actions on the user's behalf.
