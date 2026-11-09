import importlib.util, sys
import extract


def load(rel):
    name = rel.replace("/", "__").replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, f"desc/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


for rel in sys.argv[1:]:
    d = load(rel).DESC
    keys = [p["key"] for p in extract.pieces(rel)]
    miss = [k for k in keys if k not in d]
    extra = [k for k in d if k not in keys]
    print(rel, "missing:", miss, "extra:", extra)
