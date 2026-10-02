# Eidolarch 2.3.3

Settings-window cleanup and duplicate storage-priority UI.

## Settings

- Replaced the raw `weight|path` duplicate-priority textarea with a structured rule editor.
- Existing rules remain compatible with the previous persisted format; no database migration is required.
- A rule now has a folder/branch picker, an explicit keep/remove priority, add/remove controls and normal save feedback.
- Settings window title and AI option labels now come from locale resources instead of embedded English strings.
- Added localized folder-path placeholders and priority-editor labels.

## Compatibility

- The backend still stores `duplicate_priority_rules` in the existing line format so older builds can read the settings.
- Duplicate matching and deletion semantics are unchanged from 2.3.1.
