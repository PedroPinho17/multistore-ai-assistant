"""CSS guard for the Vue SPA: one way in for styles, no overrides on the side.

- The only stylesheet entry is ``frontend/src/styles/main.css``, imported once from ``main.ts``.
  No other app file under ``frontend/src`` (``.ts``/``.vue``/``.js``…) mentions a stylesheet
  outside comments: no other ``.css`` import, no ``node_modules`` CSS, no ``?inline``/``?url``/
  ``?raw`` and no dynamic ``import()`` of CSS. Tests (``__tests__/``, ``*.test.ts``) are skipped.
- ``main.css`` imports every partial in ``styles/`` exactly once, in ``MAIN_CSS_ORDER`` (with
  equal specificity the later file wins), and nothing else; the partials import nothing.
- No SFC ``<style>`` blocks and no stylesheet ``<link>`` in Vue templates.
- Inline ``style`` / ``:style`` / ``v-bind:style`` in Vue *templates* only where listed in
  ``ALLOWED_INLINE``, matched per element (file, tag, attribute, normalised value) and per
  occurrence. Style objects built in ``.ts`` code (``h()``, ``el.style``, CSS variables set
  from script) are not covered by this guard.
- ``frontend/index.html`` only loads Google Fonts: no ``<style>``, no inline ``style=``, and no
  other stylesheet or ``preload``-as-style link (quoted or unquoted attributes).
"""
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
VUE_SRC = FRONTEND / "src"
VUE_STYLES = VUE_SRC / "styles"
MAIN_CSS = VUE_STYLES / "main.css"
MAIN_TS = VUE_SRC / "main.ts"
VUE_INDEX = FRONTEND / "index.html"

MAIN_CSS_SPEC = "@/styles/main.css"
CODE_SUFFIXES = (".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx", ".vue")
STYLE_EXT = r"(?:css|scss|sass|less|styl|stylus|pcss|postcss)"
GOOGLE_FONTS_CSS = "https://fonts.googleapis.com/"

# Order of the partials in main.css: the old UI's order, which the layout was built against.
# A new partial goes in here and in main.css.
MAIN_CSS_ORDER = ["base.css", "chat.css", "common.css", "home.css", "auth.css", "pages.css",
                  "dialogs.css", "shell.css"]

# Exact inline styles that may stay: (file under src/, tag, attribute, normalised value: see
# normalise_style). Each entry allows one element; repeat it for each element that has it.
# Dynamic values (sizes, colours, delays and widths from data) plus a few one-off tweaks.
ALLOWED_INLINE = Counter([
    # SVG sprite: hidden container + gradient/stroke colours that follow the accent variables
    ("components/IconSprite.vue", "svg", "style", "position:absolute;width:0;height:0;overflow:hidden"),
    ("components/IconSprite.vue", "stop", "style", "stop-color: var(--logo-1, #14905f)"),
    ("components/IconSprite.vue", "stop", "style", "stop-color: var(--logo-2, #0b6b4e)"),
    ("components/IconSprite.vue", "path", "style", "stroke: var(--logo-2, #0b6b4e)"),
    # avatar colour from the user name (computed `style` in UserAvatar.vue)
    ("components/UserAvatar.vue", "span", ":style", "style"),
    # bar widths/heights and animation delays from data
    ("views/AdminView.vue", "span", ":style", "{ width: r.pct + '%' }"),
    ("views/ProfileView.vue", "span", ":style", "{ width: k.pct + '%' }"),
    ("views/ChatView.vue", "button", ":style", "{ animationDelay: i * 80 + 'ms' }"),
    ("views/ChatView.vue", "button", ":style", "{ animationDelay: i * 80 + 'ms' }"),
    ("views/HomeView.vue", "span", ":style", "{ height: b.v + '%', animationDelay: i * 70 + 'ms' }"),
    ("views/SettingsView.vue", "span", ":style", "accentSwatchStyle(a)"),
    ("views/SettingsView.vue", "span", ":style", "accentSwatchStyle(a)"),
    # chart canvas heights
    ("views/AdminView.vue", "div", "style", "height: 58px"),
    ("views/DashboardView.vue", "div", "style", "height: 58px"),
    ("views/ReviewView.vue", "div", "style", "height: 150px"),
    ("views/ReviewView.vue", "div", "style", "height: 60px"),
    ("views/UsersView.vue", "div", "style", "height: 120px"),
    # one-off spacing/alignment tweaks
    ("views/AdminView.vue", "p", "style", "text-align: center"),
    ("views/HomeView.vue", "span", "style", "margin-left: auto"),
    ("views/ProfileView.vue", "div", "style", "font-size: 18px"),
    ("views/ProfileView.vue", "div", "style", "font-size: 18px"),
    ("views/ProfileView.vue", "p", "style", "margin-top: 0"),
    ("views/ProfileView.vue", "h2", "style", "margin: 0 0 6px"),
    ("views/SettingsView.vue", "label", "style", "margin: 0"),
    ("views/UsersView.vue", "fieldset", "style", "border: 0; padding: 0; margin: 0"),
    ("views/UsersView.vue", "p", "style", "margin: 0 0 4px"),
    ("views/UsersView.vue", "p", "style", "margin: 0"),
    ("views/UsersView.vue", "div", "style", "margin: 0"),
])

# Any string literal that names a stylesheet: import 'x.css', import('x.css'), require('x.css'),
# new URL('x.css', …), import.meta.glob('./*.css'), 'x.css?inline'…
STYLE_LITERAL = re.compile(
    rf"""(['"`])([^'"`\n]*\.{STYLE_EXT}(?:\?[^'"`\n]*)?)\1""")
STATIC_IMPORT = re.compile(r"""^\s*import\s+(['"])([^'"\n]+)\1\s*;?\s*$""", re.M)
DYNAMIC_STYLE_IMPORT = re.compile(rf"""\bimport\s*\(\s*(['"`])[^'"`\n]*\.{STYLE_EXT}\b""")
STYLE_QUERY = re.compile(rf"""\.{STYLE_EXT}\?""")

# An HTML/Vue start tag; quoted attribute values may contain < and >.
ATTR_SRC = r"""[^\s=>"'/<]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>"'=<`]+))?"""
START_TAG = re.compile(rf"""<([A-Za-z][\w.-]*)((?:\s+{ATTR_SRC})*)\s*/?>""")
ATTR = re.compile(r"""([^\s=>"'/<]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"'=<`]+)))?""")
STYLE_ATTRS = {"style", ":style", "v-bind:style"}
# Raw count of style attributes in a template, independent of START_TAG: a tag START_TAG cannot
# read (``class="a"style="…"``, ``data-x=a=b``) would otherwise hide its style silently.
RAW_STYLE_ATTR = re.compile(r"""(?<![\w:.-])(?:v-bind:|:)?style\s*=""")
QUOTED_PARTIAL_IMPORT = re.compile(r"""@import\s+(['"])(\./[\w-]+\.css)\1\s*;""", re.I)
ANY_IMPORT = re.compile(r"@import\b", re.I)          # CSS at-rules ignore case (@IMPORT)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def rel(path: Path) -> str:
    return path.relative_to(VUE_SRC).as_posix()


def is_test_file(path: Path) -> bool:
    return "__tests__" in path.relative_to(VUE_SRC).parts or re.search(r"\.(test|spec)\.\w+$", path.name)


def app_code_files():
    return sorted(p for p in VUE_SRC.rglob("*")
                  if p.is_file() and p.suffix in CODE_SUFFIXES and not is_test_file(p))


# After one of these (or a keyword below) a ``/`` starts a regex literal, not a division.
REGEX_BEFORE_CHARS = set("(,=:[!&|?{};+-*%<>~^")
REGEX_BEFORE_WORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
                      "throw", "case", "do", "else", "yield", "await"}


def regex_literal_end(code: str, i: int) -> int | None:
    """End index of the regex literal starting at ``code[i] == '/'``, or None if it is not one
    (a newline before the closing ``/``). Handles escapes and ``[...]`` classes (``/[/]/``)."""
    j, n, in_class = i + 1, len(code), False
    while j < n:
        ch = code[j]
        if ch == "\n":
            return None
        if ch == "\\":
            j += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "/":
            j += 1
            while j < n and (code[j].isalpha()):      # flags
                j += 1
            return j
        j += 1
    return None


def regex_can_start(out: list[str]) -> bool:
    prev = "".join(out).rstrip()
    if not prev:
        return True
    if prev[-1] in REGEX_BEFORE_CHARS:
        return True
    word = re.search(r"([A-Za-z_$][\w$]*)$", prev)
    return bool(word and word.group(1) in REGEX_BEFORE_WORDS)


def strip_js_comments(code: str) -> str:
    """Drops ``// …`` and ``/* … */`` outside string, template and regex literals.

    ``//`` and ``/*`` can never start a regex, so once regex literals (``/^openai\\//``,
    ``/a\\/*b/``) are copied as a whole, every ``//`` / ``/*`` left is a real comment.
    (``${…}`` nested inside template strings is not tracked.)
    """
    out: list[str] = []
    i, n, quote = 0, len(code), None
    while i < n:
        ch = code[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(code[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
            out.append(ch)
        elif code.startswith("//", i):
            i = code.find("\n", i)
            i = n if i < 0 else i
            continue
        elif code.startswith("/*", i):
            end = code.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
            continue
        elif ch == "/" and regex_can_start(out) and (end := regex_literal_end(code, i)) is not None:
            out.append(code[i:end])
            i = end
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def code_without_comments(path: Path) -> str:
    """Script code without comments; for ``.vue`` the ``<script>`` blocks plus the template
    without ``<!-- -->`` comments (template text is not JS, so it is not run through the JS
    comment stripper)."""
    text = read(path)
    if path.suffix != ".vue":
        return strip_js_comments(text)
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", text, re.S | re.I)
    rest = re.sub(r"<script\b[^>]*>.*?</script>", "", text, flags=re.S | re.I)
    rest = re.sub(r"<!--.*?-->", "", rest, flags=re.S)
    return "\n".join([strip_js_comments(s) for s in scripts] + [rest])


def vue_template(text: str) -> str:
    start, end = text.find("<template"), text.rfind("</template>")
    template = text[start:end] if start >= 0 and end > start else ""
    return re.sub(r"<!--.*?-->", "", template, flags=re.S)


def normalise_style(value: str) -> str:
    """Collapses whitespace and drops trailing commas, so a Prettier re-wrap of
    ``:style="{ a: 1 }"`` over several lines (``{\\n a: 1,\\n}``) still matches."""
    value = " ".join(value.split())
    return re.sub(r",\s*(?=[}\]])", " ", value).replace("  ", " ")


def tag_attrs(tag_src: str):
    """(name, value) for each attribute of a start tag's attribute source; value None if bare."""
    for m in ATTR.finditer(tag_src):
        value = next((g for g in m.groups()[1:] if g is not None), None)
        yield m.group(1), value


def inline_styles():
    """Every inline style in the Vue templates as (file, tag, attribute, normalised value)."""
    found = []
    for path in sorted(VUE_SRC.rglob("*.vue")):
        for tag in START_TAG.finditer(vue_template(read(path))):
            for name, value in tag_attrs(tag.group(2)):
                if name in STYLE_ATTRS:
                    found.append((rel(path), tag.group(1), name, normalise_style(value or "")))
    return found


def css_partials():
    return sorted(p.name for p in VUE_STYLES.glob("*.css") if p.name != "main.css")


def strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


# ---------- one entry point ----------

def test_main_ts_imports_main_css_once_statically():
    text = strip_js_comments(read(MAIN_TS))
    side_effect = [spec for _, spec in STATIC_IMPORT.findall(text)]
    assert side_effect.count(MAIN_CSS_SPEC) == 1, "main.ts must have exactly one `import '@/styles/main.css'`"
    assert [spec for _, spec in STYLE_LITERAL.findall(text)] == [MAIN_CSS_SPEC]


def test_no_other_file_mentions_a_stylesheet():
    """No CSS import anywhere else: not from src/, not from node_modules, not via ?inline/?url/?raw."""
    bad = []
    for path in app_code_files():
        for _, spec in STYLE_LITERAL.findall(code_without_comments(path)):
            if not (path == MAIN_TS and spec == MAIN_CSS_SPEC):
                bad.append(f"{rel(path)}: {spec}")
    assert bad == [], "stylesheet referenced outside main.ts:\n" + "\n".join(bad)


def test_no_css_query_or_dynamic_imports():
    """``?inline`` / ``?url`` / ``?raw`` and ``import('x.css')`` are banned everywhere, main.ts too."""
    bad = []
    for path in app_code_files():
        code = code_without_comments(path)
        if STYLE_QUERY.search(code) or DYNAMIC_STYLE_IMPORT.search(code):
            bad.append(rel(path))
    assert bad == []


def test_no_stylesheets_outside_styles():
    pattern = re.compile(rf"\.{STYLE_EXT}$")
    stray = [rel(p) for p in VUE_SRC.rglob("*")
             if p.is_file() and pattern.search(p.name) and not (p.parent == VUE_STYLES and p.suffix == ".css")]
    assert stray == []


# ---------- main.css = every partial, once, in order ----------

def main_css_imports():
    css = strip_css_comments(read(MAIN_CSS))
    specs = [spec for _, spec in QUOTED_PARTIAL_IMPORT.findall(css)]
    return css, specs


def test_main_css_has_only_quoted_partial_imports():
    """Every ``@import`` must be ``@import './partial.css';`` (catches ``@import url(…)``, remote…)."""
    css, specs = main_css_imports()
    total = len(ANY_IMPORT.findall(css))
    assert total == len(specs), (
        f"main.css has {total} @import rules but only {len(specs)} are `@import './partial.css';`")


def test_main_css_imports_every_partial_exactly_once():
    _, specs = main_css_imports()
    names = [s[2:] for s in specs]
    dupes = sorted(s for s, n in Counter(names).items() if n > 1)
    assert dupes == [], f"main.css imports these more than once: {dupes}"
    assert sorted(names) == css_partials(), (
        f"main.css must import every partial in styles/: missing {sorted(set(css_partials()) - set(names))}, "
        f"unknown {sorted(set(names) - set(css_partials()))}")


def test_main_css_import_order():
    _, specs = main_css_imports()
    names = [s[2:] for s in specs]
    assert sorted(MAIN_CSS_ORDER) == css_partials(), (
        "MAIN_CSS_ORDER in this test must list every partial in styles/ (add the new one where it "
        f"belongs in the cascade): {css_partials()}")
    assert names == MAIN_CSS_ORDER, (
        "main.css imports are out of order (with equal specificity the later file wins).\n"
        f"expected: {MAIN_CSS_ORDER}\nactual:   {names}")


def test_partials_import_nothing():
    bad = [name for name in css_partials() if ANY_IMPORT.search(strip_css_comments(read(VUE_STYLES / name)))]
    assert bad == []


# ---------- no styles on the side in Vue ----------

def test_no_style_blocks_or_stylesheet_links_in_vue():
    bad = []
    for path in VUE_SRC.rglob("*.vue"):
        text = read(path).lower()
        if re.search(r"<style[\s>]", text) or re.search(r"<link\b[^>]*\bstylesheet\b", text):
            bad.append(rel(path))
    assert bad == []


def test_no_style_in_v_bind_objects():
    bad = []
    for path in VUE_SRC.rglob("*.vue"):
        for tag in START_TAG.finditer(vue_template(read(path))):
            for name, value in tag_attrs(tag.group(2)):
                if name in ("v-bind", ":") and "style" in (value or ""):
                    bad.append(f"{rel(path)}: <{tag.group(1)}>")
    assert bad == []


def test_inline_styles_match_the_allowlist_exactly():
    """Per element and per occurrence: a new override fails, and so does a stale allowlist entry."""
    found = Counter(inline_styles())
    extra = sorted((found - ALLOWED_INLINE).elements())
    stale = sorted((ALLOWED_INLINE - found).elements())
    assert extra == [], "inline style not in ALLOWED_INLINE:\n" + "\n".join(map(repr, extra))
    assert stale == [], "ALLOWED_INLINE entry no longer used (remove it):\n" + "\n".join(map(repr, stale))


def test_every_style_attribute_is_parsed():
    """Per template, each ``style=`` / ``:style=`` / ``v-bind:style=`` must be one inline_styles()
    found; otherwise a tag START_TAG cannot read would skip the allowlist check silently."""
    parsed = Counter(f for f, *_ in inline_styles())
    bad = []
    for path in sorted(VUE_SRC.rglob("*.vue")):
        raw = len(RAW_STYLE_ATTR.findall(vue_template(read(path))))
        if raw != parsed[rel(path)]:
            bad.append(f"{rel(path)}: {raw} style attributes in the template, {parsed[rel(path)]} parsed")
    assert bad == [], "style attributes the guard could not parse (fix the tag's HTML):\n" + "\n".join(bad)


def test_user_avatar_style_binding_is_the_computed_one():
    assert [s for s in inline_styles() if s[0] == "components/UserAvatar.vue"] == [
        ("components/UserAvatar.vue", "span", ":style", "style")]


def test_normalise_style():
    assert normalise_style("{\n  width: r.pct + '%',\n}") == "{ width: r.pct + '%' }"
    assert normalise_style("{ a: [1, 2,], b: 1, }") == "{ a: [1, 2 ], b: 1 }"


def test_tag_detection_handles_lt_in_quoted_values():
    tags = [(m.group(1), dict(tag_attrs(m.group(2))))
            for m in START_TAG.finditer('<p :title="1 < 2 ? \'a>b\' : \'c\'" style="margin: 0">x</p>')]
    assert tags == [("p", {":title": "1 < 2 ? 'a>b' : 'c'", "style": "margin: 0"})]


def test_js_comment_stripping_keeps_strings():
    code = "const u = 'http://x/a.css' // see 'b.css'\n/* 'c.css' */ const t = `//d.css`"
    assert STYLE_LITERAL.findall(strip_js_comments(code)) == [("'", "http://x/a.css"), ("`", "//d.css")]


def specs_after_stripping(code: str) -> list[str]:
    return [spec for _, spec in STYLE_LITERAL.findall(strip_js_comments(code))]


def test_js_comment_stripping_keeps_regex_literals():
    # // inside a regex (lib/format.ts) is not a comment: the rest of the line is still checked
    assert specs_after_stripping("x.replace(/^openai\\//, ''); import './a.css'") == ["./a.css"]
    # /* inside a regex does not open a block comment that would swallow the next lines
    assert specs_after_stripping("const re = /a\\/*b/g\nimport './b.css'\nconst z = 1 // */") == ["./b.css"]
    # / inside a [...] class does not end the regex
    assert specs_after_stripping("const re = /[/*]/; import './c.css'") == ["./c.css"]
    # after `return` it is a regex; after a value it is a division, and // is a comment
    assert specs_after_stripping("return /\\/\\//.test(s) && './d.css'") == ["./d.css"]
    assert specs_after_stripping("const h = w / 2 // './e.css'\nconst k = (a) / b / c") == []
    # a regex literal keeps its text (still searched for stylesheet names)
    assert strip_js_comments("const r = /x\\/\\/y/i // c") == "const r = /x\\/\\/y/i "


# ---------- index.html: Google Fonts only ----------

def test_index_html_has_no_style_blocks_or_inline_styles():
    html = read(VUE_INDEX).lower()
    assert not re.search(r"<style[\s>]", html)
    assert not re.search(r"""(?<![\w:-])style\s*=""", html)
    assert "@import" not in html


def test_index_html_only_google_fonts_stylesheets():
    html = read(VUE_INDEX)
    style_links = []
    for tag in START_TAG.finditer(html):
        if tag.group(1).lower() != "link":
            continue
        attrs = {name.lower(): value or "" for name, value in tag_attrs(tag.group(2))}
        rels = attrs.get("rel", "").lower().split()
        as_style = attrs.get("as", "").lower() == "style"
        if "stylesheet" in rels or as_style:
            style_links.append(attrs.get("href", ""))
    assert style_links, "expected the Google Fonts stylesheet link"
    bad = [href for href in style_links if not href.startswith(GOOGLE_FONTS_CSS)]
    assert bad == [], f"non-Google-Fonts stylesheet/preload in index.html: {bad}"


def test_index_html_link_tags_are_all_parsed():
    """Every <link> in index.html is seen by START_TAG (else the check above could skip one)."""
    html = read(VUE_INDEX)
    assert len(re.findall(r"<link\b", html, re.I)) == sum(
        1 for t in START_TAG.finditer(html) if t.group(1).lower() == "link")
