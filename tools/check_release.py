from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
bad=[]
for p in root.rglob("*"):
    if not p.is_file(): continue
    rel=p.relative_to(root).as_posix()
    if "__pycache__" in rel or p.suffix==".pyc": bad.append(rel)
    if rel.startswith(".browser-profile/"): bad.append(rel)
    if rel.startswith("data/") and rel!="data/README.txt": bad.append(rel)
    if p.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".log"}: bad.append(rel)
if bad:
    print("Release contains runtime files:")
    print("\n".join(" - "+x for x in bad)); sys.exit(1)
print("Release tree OK")
