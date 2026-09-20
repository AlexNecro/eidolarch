# Eidolarch 2.2.11

Interface stabilization release.

## Changed

- Native browser-style tooltip boxes in the main UI are replaced by a styled Eidolarch tooltip component.
- Search tooltip explains the query syntax:
  - plain text = current semantic image search;
  - `@name` = named person/pet (planned);
  - `#tag` = exact tag/filter.
- Duplicate count/status badge stays fixed in the tile top-left.
- The duplicate badge itself opens Duplicates; hover actions no longer replace or move that target.
- Other hover actions appear to the right of the persistent duplicate badge.
- Duplicate path preview is loaded only when hovering the duplicate badge, not whenever the whole photo tile is hovered.

## Still open

The next priorities are the grouped duplicate workspace, entity cleanup/naming workflow, and the Details table mode.
