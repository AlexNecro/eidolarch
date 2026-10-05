# UX clarity audit

This file tracks controls/states that are easy to misunderstand and should either explain themselves in the UI or link to contextual Help.

## Current conventions

- Top-level modes are Folders, Tags, Favorites and Duplicates. The active mode button is the mode label; the UI must not repeat the same label beside the buttons.
- `Reset all` is for clearing an actual folder/tag/search scope and returning to library root. It is not shown merely because Favorites or Duplicates is active.
- Back/Forward restores Eidolarch window state, not browser history.
- Duplicates means **byte-identical exact files**. Similar means visually/semantically related media and is never a synonym for Duplicate.
- Duplicate cleanup is explicit and reversible through the Windows Recycle Bin.
- Same-folder duplicate cleanup keeps the oldest physical file by creation time; filename suffixes are not used as the keeper rule.
- Search similarity values are ranking scores, not probabilities.
- AI: GPU/CPU/API describes the actual inference backend.
- Browsing remains available while background indexing runs.
- Viewer, Settings, Help and Graph may live in independent application windows but share one backend/database.

## Still needs product treatment

### Folder layout
Folder cards should use a responsive grid that calculates how many cards fit in the available width; folder cards do not need the large right-side context area used by media cards.

### Reconciliation after file restore
The filesystem is the source of truth. A file restored from the Windows Recycle Bin must be rediscovered even if watchdog misses the event. Regression scenario: two exact copies → trash one → restore it → duplicate count returns to two.

### Video foundation (2.4)
Add a prominent Photos / Videos / All switch. Photos must preserve classic Eidolarch behavior. Video needs its own renderer inside a shared viewer shell, while exact duplicate semantics remain unchanged.

### Entities
The Objects inspector should explain that a name applies to a detected person/pet entity and that automatic propagation is heuristic. Mature identity confirmation/review remains future work.

### Automatic tags
Expose tag source (automatic/manual/metadata/entity) and confidence where useful.

### Search quality
Add an explicit relevance threshold/adaptive cut-off affordance or clearer explanation when weak results are included.

### Internal clipboard and undo
Show persistent Copy/Cut state and favor operation toasts with Undo over keyboard-only discovery.

### LAN security
If LAN access is enabled, show a persistent but unobtrusive network indicator and clearly distinguish read-only from full-access mode.

### Empty states
Each empty state should explain why it is empty and what action is available: library, folder, tags, AI index, search, Favorites, Duplicates.

### Localization
All user-visible strings, dynamic counters, backend status labels and errors must use locale resources. Cache/version changes must not leave JS and locale dictionaries out of sync.
