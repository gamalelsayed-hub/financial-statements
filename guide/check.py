"""Check the guide against the code: every piece of every file in stages.py has a description, and every .py file
of the program is in some stage. Run with no arguments for everything, or name files."""
import glob, importlib.util, os, sys
import extract
from stages import STAGES


def load(rel):
    name = rel.replace("/", "__").replace(".py", "")
    path = f"desc/{name}.py"
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


listed = [f for st in STAGES for f in st["files"]]
files = sys.argv[1:] or listed
bad = 0
for rel in files:
    d = load(rel)
    if d is None:
        print(rel, ": no desc file")
        bad += 1
        continue
    keys = [p["key"] for p in extract.pieces(rel)]
    miss = [k for k in keys if k not in d.DESC]
    extra = [k for k in d.DESC if k not in keys]
    if miss or extra:
        bad += 1
        print(rel, "missing:", miss, "extra:", extra)
if not sys.argv[1:]:
    root = extract.ROOT
    for p in sorted(glob.glob(os.path.join(root, "fsapp", "**", "*.py"), recursive=True)) + [os.path.join(root, "main.py")]:
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        if rel.endswith("__init__.py") or rel in listed:
            continue
        bad += 1
        print(rel, ": not in any stage")
print("OK" if not bad else f"{bad} problem(s)")
