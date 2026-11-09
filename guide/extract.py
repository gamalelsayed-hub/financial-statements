"""Split each source file into ordered pieces: the file head (docstring, imports, constants), top-level
statements between definitions, each function, each class header and each method."""
import ast, json, os, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "")


def pieces(rel):
    src = open(ROOT + rel, encoding="utf-8").read()
    lines = src.splitlines()
    tree = ast.parse(src)
    out = []

    def start(node):
        a = node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno
        while a > 1 and lines[a - 2].strip().startswith("#"):     # comment lines just above belong to it
            a -= 1
        return a

    def add(key, kind, a, b):
        code = "\n".join(lines[a - 1:b]).rstrip()
        if code.strip():
            out.append({"key": key, "kind": kind, "start": a, "end": b, "code": code})

    pending = None   # run of plain statements
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if pending:
                add(pending[2], "head" if pending[2] == "__head__" else "stmt", pending[0], start(node) - 1)
                pending = None
            if isinstance(node, ast.FunctionDef):
                add(node.name, "func", start(node), node.end_lineno)
            else:
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                first = start(methods[0]) - 1 if methods else node.end_lineno
                add(node.name, "class", start(node), first)
                for i, m in enumerate(methods):
                    add(f"{node.name}.{m.name}", "method", start(m), m.end_lineno)
        else:
            if pending is None:
                key = "__head__" if not out else f"__stmt_{node.lineno}__"
                pending = [node.lineno if out else 1, node.end_lineno, key]
            pending[1] = node.end_lineno
    if pending:
        add(pending[2], "head" if pending[2] == "__head__" else "stmt", pending[0], len(lines))
    # contiguous: every piece starts right after the previous one, so no comment line is lost; leading blank
    # lines are trimmed
    prev_end = 0
    for p in out:
        a = prev_end + 1
        while a < p["start"] and not lines[a - 1].strip():
            a += 1
        if a < p["start"]:
            p["start"] = a
            p["code"] = "\n".join(lines[a - 1:p["end"]]).rstrip()
        prev_end = p["end"]
    return out


if __name__ == "__main__":
    for p in pieces(sys.argv[1]):
        print(f"{p['key']:40s} {p['kind']:7s} {p['start']}-{p['end']}")
