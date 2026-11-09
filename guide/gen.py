import html, re, sys, importlib.util
sys.path.insert(0, ".")
import extract
from stages import STAGES

E = html.escape
KIND = {"head": "بداية الملف", "stmt": "ثوابت", "func": "دالة", "class": "كلاس", "method": "دالة داخل كلاس"}


def load(rel):
    name = rel.replace("/", "__").replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, f"desc/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


LATIN = re.compile(r"[A-Za-z_][A-Za-z0-9_.\[\]'\"()=,:/*+<>#{} -]*[A-Za-z0-9_\])'\"}]|[A-Za-z_]")


def inline(s):
    """Escape, and keep code-like Latin runs left to right inside the Arabic text."""
    out, pos = [], 0
    for m in LATIN.finditer(s):
        out.append(E(s[pos:m.start()]))
        out.append(f'<bdi dir="ltr"><code>{E(m.group(0))}</code></bdi>' if len(m.group(0)) > 1 else E(m.group(0)))
        pos = m.end()
    out.append(E(s[pos:]))
    return "".join(out)


def prose(text):
    """Description text → HTML: '- ' bullets, '1. ' numbered lines, other lines paragraphs."""
    out, lst = [], None
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\d+)\.\s+(.*)", s)
        kind = "ul" if s.startswith("- ") else "ol" if m else None
        if kind != lst:
            if lst:
                out.append(f"</{lst}>")
            if kind:
                out.append(f"<{kind}>")
            lst = kind
        if kind == "ul":
            out.append(f"<li>{inline(s[2:])}</li>")
        elif kind == "ol":
            out.append(f"<li>{inline(m.group(2))}</li>")
        else:
            out.append(f"<p>{inline(s)}</p>")
    if lst:
        out.append(f"</{lst}>")
    return "".join(out)


def slug(rel):
    return "f-" + re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-")


def title_of(p):
    k = p["key"]
    if p["kind"] == "head":
        return "الاستيرادات والثوابت"
    if p["kind"] == "stmt":
        names = re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=", p["code"], re.M)
        return "، ".join(names[:4]) or "سطور عامة"
    return k


def build():
    toc, body = [], []
    n_files = n_pieces = n_lines = 0
    for st in STAGES:
        toc.append(f'<li class="toc-stage"><a href="#{st["id"]}">{E(st["title"])}</a><ul>')
        sec = [f'<section class="stage" id="{st["id"]}"><h2>{E(st["title"])}</h2>']
        sec.append(f'<p class="lead">{inline(st["intro"])}</p>')
        if st.get("code"):
            sec.append(code_block(st["code"]))
        if st["files"]:
            sec.append('<ol class="filelist">' + "".join(
                f'<li><a href="#{slug(f)}" dir="ltr">{E(f)}</a></li>' for f in st["files"]) + "</ol>")
        for rel in st["files"]:
            d = load(rel)
            ps = extract.pieces(rel)
            lines = sum(p["code"].count("\n") + 1 for p in ps)
            n_files += 1
            n_pieces += len(ps)
            n_lines += lines
            sid = slug(rel)
            toc.append(f'<li><label><input type="checkbox" class="done" data-f="{sid}" aria-label="خلصت {E(rel)}"></label>'
                       f'<a href="#{sid}" dir="ltr">{E(rel)}</a></li>')
            f = [f'<details class="file" id="{sid}"><summary><span class="fname" dir="ltr">{E(rel)}</span>'
                 f'<span class="meta">{len(ps)} جزء · {lines} سطر</span></summary>',
                 f'<div class="fintro">{prose(d.FILE)}</div>']
            for p in ps:
                f.append(f'<article class="piece"><header><span class="kind k-{p["kind"]}">{KIND[p["kind"]]}</span>'
                         f'<code class="pname" dir="ltr">{E(title_of(p))}</code>'
                         f'<span class="lines" dir="ltr">L{p["start"]}–{p["end"]}</span></header>'
                         f'<div class="desc">{prose(d.DESC[p["key"]])}</div>{code_block(p["code"])}</article>')
            f.append("</details>")
            sec.append("".join(f))
        sec.append(f'<div class="check"><b>جرّب قبل ما تكمل:</b> {inline(st["check"])}</div></section>')
        body.append("".join(sec))
        toc.append("</ul></li>")
    return "".join(toc), "".join(body), n_files, n_pieces, n_lines


def code_block(code):
    return (f'<div class="code"><button type="button" class="copy">نسخ</button>'
            f'<pre dir="ltr"><code>{E(code)}</code></pre></div>')


def tree():
    """Folder tree of the finished project; each file shows the stage it is written in."""
    stage_of = {}
    for i, st in enumerate(STAGES):
        for f in st["files"]:
            stage_of[f] = i
    files = sorted(set(stage_of) | {"fsapp/__init__.py", "fsapp/system/__init__.py", "fsapp/ui/__init__.py",
                                     "requirements.txt"})
    root = {}
    for f in files:
        node = root
        parts = f.split("/")
        for d in parts[:-1]:
            node = node.setdefault(d + "/", {})
        node[parts[-1]] = None
    out = ['<div class="tr d0"><span class="dir">fsapp-project/</span></div>']

    def walk(node, depth, prefix):
        keys = sorted(node, key=lambda k: (not k.endswith("/"), k != "__init__.py", k))
        for k in keys:
            path = prefix + k
            if k.endswith("/"):
                out.append(f'<div class="tr d{depth}"><span class="dir">{E(k)}</span></div>')
                walk(node[k], depth + 1, path)
            else:
                st = stage_of.get(path)
                chip = f'<span class="chip">{st}</span>' if st is not None else '<span class="chip c0">0</span>'
                name = (f'<a href="#{slug(path)}">{E(k)}</a>' if st is not None else f'<span class="file">{E(k)}</span>')
                note = ' <span class="tnote">فاضي</span>' if k == "__init__.py" else ""
                out.append(f'<div class="tr d{depth}">{chip}{name}{note}</div>')

    walk(root, 1, "")
    return "".join(out)


def mindmap():
    """Mind map: the program in the middle, one branch per stage, one leaf per file (painted green when done)."""
    out = ['<section class="mm" id="map"><h2>خريطة البرنامج: أنت فين واصل</h2>'
           '<p class="lead">كل فرع مرحلة، وكل ورقة ملف. الملف اللي تعلّم عليه «خلصت» في الفهرس يصير أخضر، '
           'والملف اللي عليه الدور يتعلّم بـ «أنت هنا». اضغط أي ملف يفتحه لك.</p>'
           '<div class="mm-now" id="mm-now"></div><div class="mm-root"><span>برنامج القوائم المالية</span></div><div class="mm-branches">']
    n = 0
    for st in STAGES:
        if not st["files"]:
            continue
        n += 1
        t = st["title"].split(":", 1)
        name = t[1].strip() if len(t) > 1 else t[0]
        out.append(f'<div class="mm-br b{(n - 1) % 5}" data-stage="{st["id"]}"><a class="mm-st" href="#{st["id"]}">'
                   f'<b>{n}</b><span>{E(name)}</span><em class="mm-cnt">0/{len(st["files"])}</em></a><ul>')
        for f in st["files"]:
            short = f.split("/")[-1]
            out.append(f'<li><a class="mm-f" data-f="{slug(f)}" href="#{slug(f)}" dir="ltr" title="{E(f)}">{E(short)}</a></li>')
        out.append("</ul></div>")
    out.append("</div></section>")
    return "".join(out)


toc, body, nf, np_, nl = build()
tpl = open("template.html", encoding="utf-8").read()
tpl = tpl.replace("{{BASICS}}", open("basics.html", encoding="utf-8").read().replace("{{TREE}}", tree()))
tpl = tpl.replace("{{MAP}}", mindmap()).replace("{{PRACTICE}}", open("practice.html", encoding="utf-8").read())
out = (tpl.replace("{{TOC}}", toc).replace("{{BODY}}", body)
       .replace("{{NF}}", str(nf)).replace("{{NP}}", f"{np_:,}").replace("{{NL}}", f"{nl:,}"))
open("guide.html", "w", encoding="utf-8").write(out)
print(nf, np_, nl, len(out) // 1024, "KB")
