# Eidolarch 2.2.10

Stabilization release focused on viewer correctness, object review, duplicates and Similar.

## Fixed

- Version-aware thumbnail cache prevents stale thumbnails when a file changes at the same path.
- Viewer original image responses bypass browser cache and viewer request races are isolated from side-panel loading.
- Left/Right navigation follows the source list that opened the viewer.
- Similar/Duplicate results open in a new viewer window with their own navigation context.
- Objects can be re-detected and saved for the current photo; manual names are preserved when possible.
- Object cards can highlight their bounding boxes on the original image.
- Current photo is no longer displayed/counts as its own duplicate.
- Similar shows the reference photo separately and caches visual signatures.
- Search field no longer gets the browser `?` help cursor from native title tooltips.
