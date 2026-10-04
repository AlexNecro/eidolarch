# Eidolarch 2.3.5

Duplicate workspace completion and runtime cleanup.

## Duplicate workspace
- Fixed localization of dynamically rendered duplicate-group counters and actions.
- Group-level preferred location selection.
- Safe preview and Recycle Bin cleanup of confirmed duplicates outside the preferred location.
- Server revalidates exact-copy safety immediately before destructive operations.

## Entity detector v4
- YOLOS remains the proposal detector for person/cat/dog boxes.
- The active SigLIP model semantically verifies the crop class before storage.
- Conservative correction margin avoids blindly replacing YOLOS labels.
- New detector scan key causes existing entity detections to be refreshed.

## Startup / diagnostics
- Fast path skips heavyweight torch/torchvision/transformers probes when the runtime stamp is current.
- `repair.bat` performs an explicit full environment repair.
- `debug.bat` enables startup timing and Python import profiling and writes `data/startup-debug.log`.
- Normal `run.bat` can still fall back to repair after a genuine startup failure.
