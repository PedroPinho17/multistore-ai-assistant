"""A nova UI (Vue, /app) tem de ter o mesmo layout que a antiga (/): os mesmos ficheiros CSS,
com o mesmo conteúdo e pela mesma ordem.

Antes: o chat.css do Vue tinha perdido regras que a UI antiga usa noutras páginas (``header``,
``.head-right``…) e os ficheiros eram importados por outra ordem. Na homepage, os botões do
cabeçalho (tema, língua, Entrar) ficavam uns por baixo dos outros, e o dashboard e as definições
tinham diferenças de padding e de posição. Comparado no browser a 1440/1024/768/390 px.

Regras que só o Vue tem ficam entre ``/* vue-only: … */`` e ``/* end vue-only */``.
"""
import difflib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OLD_HTML = ROOT / "web" / "index.html"
OLD_CSS = ROOT / "web" / "static" / "css"
VUE_CSS = ROOT / "frontend" / "src" / "styles"
VUE_SRC = ROOT / "frontend" / "src"
VUE_ONLY = re.compile(r"/\* vue-only:.*?/\* end vue-only \*/\n\n?", re.S)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def old_order() -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="/static/css/([\w-]+\.css)"', read(OLD_HTML))


def vue_order() -> list[str]:
    return re.findall(r"@import '\./([\w-]+\.css)';", read(VUE_CSS / "main.css"))


def test_same_stylesheets_in_the_same_order():
    assert old_order(), "web/index.html sem <link rel=stylesheet>?"
    assert vue_order() == old_order()


@pytest.mark.parametrize("name", old_order())
def test_same_rules_as_the_old_ui(name):
    old = read(OLD_CSS / name)
    vue = VUE_ONLY.sub("", read(VUE_CSS / name))
    if vue != old:
        diff = "".join(difflib.unified_diff(old.splitlines(True), vue.splitlines(True),
                                            f"web/static/css/{name}", f"frontend/src/styles/{name}", n=1))
        pytest.fail(f"{name} difere da UI antiga (marca regras só do Vue com /* vue-only: */):\n{diff[:3000]}")


def test_vue_only_blocks_are_well_formed():
    for path in VUE_CSS.glob("*.css"):
        text = read(path)
        assert text.count("/* vue-only:") == text.count("/* end vue-only */"), path.name


def test_no_other_css_in_the_vue_app():
    """Nada de CSS fora destes ficheiros (que mudaria o layout sem este teste ver)."""
    assert sorted(p.name for p in VUE_CSS.glob("*.css")) == sorted(old_order() + ["main.css"])
    sfc_styles = [p.name for p in VUE_SRC.rglob("*.vue") if "<style" in read(p)]
    assert sfc_styles == []
    css_imports = [p.relative_to(VUE_SRC).as_posix() for p in VUE_SRC.rglob("*.ts")
                   if re.search(r"""import\s+['"][^'"]+\.css['"]""", read(p))]
    assert css_imports == ["main.ts"]
