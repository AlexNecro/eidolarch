# Eidolarch 2.3.3

Duplicate storage policy UI and library-wide reclaim estimate.

## Duplicate storage priority
- Replaced numeric priority controls with an ordered folder list.
- Select a folder and move it up/down: higher entries are preferred keep locations; lower entries become stronger removal candidates.
- Folder selection uses the native folder picker.
- Existing `weight|path` settings remain readable; the UI now generates compatibility weights automatically.
- Nested rules use the most specific matching folder instead of accumulating parent weights.

## Reclaim estimate
- Added a library-wide exact-duplicate summary that does not double-count overlapping UI groups.
- Duplicate mode now shows the total `reclaimable` amount next to the group counter.
- Settings show the same exact-duplicate reclaim estimate and candidate-file count.

## Compatibility
- Exact duplicates remain separate from Similar.
- Existing duplicate endpoints and Viewer behavior remain available.
- Safe deletion still revalidates that another exact physical copy exists before moving anything to the Recycle Bin.
