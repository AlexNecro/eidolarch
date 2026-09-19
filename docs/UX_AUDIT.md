# UX clarity audit

This file tracks controls and states that are easy to misunderstand and should either explain themselves in the UI or link to contextual help.

## Already covered in v2.0.2 help/tooltips

- Search scope: root vs current folder vs selected tags.
- Back/Forward: restores Eidolarch window state, not browser history.
- Reset all: returns to the library root and clears search/folder/tag filters.
- Folder count: currently means photos directly in the folder; this is intentionally called out until recursive counts are implemented.
- Tag logic: selected tags use AND.
- Semantic score: ranking score, not a probability.
- Red search tint: weaker relative result within the current query.
- Red photo border / duplicate badge: duplicates were found.
- AI: GPU/CPU/API: actual inference location.
- Background indexing: browsing remains available while it runs.
- Grid view buttons and tag-panel collapse button.
- LAN access and network popover.

## Still needs stronger product treatment

### Folder counts
Replace the ambiguous single number with explicit direct/recursive information, e.g. `3 here · 148 total`, and optionally subfolder count.

### Breadcrumbs
Current breadcrumb implementation needs visual separators, truncation for long paths, a clear root/home segment and search-scope synchronization.

### Duplicates mode
Add a first-class top-level Duplicates mode that shows duplicate groups rather than requiring per-photo inspection.

### Viewer
Default photo viewing should move to a separate application window. The current modal overlay competes visually with the system window controls.

### Entities
The Objects inspector should explain that a name applies to a detected person/pet entity and that automatic propagation is heuristic. Add explicit confirm/review flow.

### Automatic tags
Expose tag source (automatic/manual/metadata/entity) and, for automatic tags, confidence. Users otherwise cannot tell why a tag exists.

### Search quality
Add an explicit relevance threshold / adaptive cut-off affordance or at least an explanation when low-confidence results are included.

### Similar vs duplicates
Keep terminology stable everywhere: `Duplicates` = same/near-copy file; `Similar` = visually/semantically close scene. Avoid using one as a synonym for the other.

### File operations
When internal Copy/Cut is active, show a persistent clipboard status (`3 photos copied`, `2 photos cut`) and destination/paste affordance.

### Undo/redo
After file operations, use a temporary toast with Undo instead of relying only on keyboard shortcuts.

### LAN security
If LAN access is enabled, show a persistent but unobtrusive network indicator. Clearly distinguish read-only LAN from full-access LAN.

### First run
Add a short first-run walkthrough: add folder → browse immediately → indexing continues in background → search becomes progressively available.

### Empty states
Each empty state should say why it is empty and what the next action is: empty library, empty folder, no tags yet, no AI index yet, no search matches, no duplicates.

### Background jobs
Show which stage is active and why counters differ (`catalog`, `AI`, `hash`, `objects`, `tags`).

### Localization
All user-visible strings, including backend status labels and errors, must come from localization resources. No mixed-language UI.
