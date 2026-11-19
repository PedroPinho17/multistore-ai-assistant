"""Cor personalizada: os tons calculados pela UI (web/static/js/settings.js) cumprem o contraste AA.

Corre o JavaScript verdadeiro em Node (saltado se o Node não estiver instalado).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js não instalado")
SETTINGS_JS = Path(__file__).resolve().parents[2] / "web" / "static" / "js" / "settings.js"

# Cores difíceis: muito claras, cinzentas, neon, quase pretas e as do teu exemplo (189,189,189)
COLORS = ["#ffff00", "#bdbdbd", "#ffffff", "#000000", "#00ff00", "#ff00ff", "#00e5ff", "#ff5a00",
          "#7a7a7a", "#123456", "#c2185b", "#0f7a5a"]

SCRIPT = """
const vm = require("vm");
const ctx = { console };
vm.createContext(ctx);
vm.runInContext(require("fs").readFileSync(process.argv[1], "utf8") +
  "\\n;this.customPalette = customPalette; this.contrastRatio = contrastRatio; this.hexToRgb = hexToRgb;", ctx);
const W = [255, 255, 255], DARK = [0x14, 0x1a, 0x18];
const out = {};
for (const hex of JSON.parse(process.argv[2])) {
  const p = ctx.customPalette(hex), c = (a, b) => ctx.contrastRatio(typeof a === "string" ? ctx.hexToRgb(a) : a,
                                                                      typeof b === "string" ? ctx.hexToRgb(b) : b);
  out[hex] = {
    white_on_button: c(W, p.light["--btn"]),
    brand_on_white: c(p.light["--brand"], W),
    brand_on_soft: c(p.light["--brand"], p.light["--brand-soft"]),
    dark_brand_on_surface: c(p.dark["--brand"], DARK),
    dark_brand_on_soft: c(p.dark["--brand"], p.dark["--brand-soft"]),
    white_on_dark_button: c(W, p.dark["--btn"]),
    adjusted: p.adjusted,
  };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def palettes():
    run = subprocess.run([NODE, "-e", SCRIPT, str(SETTINGS_JS), json.dumps(COLORS)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@pytest.mark.parametrize("hex_color", COLORS)
def test_every_text_and_background_pair_meets_aa(palettes, hex_color):
    pal = palettes[hex_color]
    for pair, ratio in pal.items():
        if pair != "adjusted":
            assert ratio >= 4.5, f"{hex_color} {pair} = {ratio:.2f}"


def test_light_colours_are_flagged_as_adjusted(palettes):
    """Amarelo ou cinzento claro não dão texto branco legível: a UI escurece-os e avisa."""
    assert palettes["#ffff00"]["adjusted"] and palettes["#bdbdbd"]["adjusted"]


def test_colours_that_already_work_are_left_alone(palettes):
    assert not palettes["#0f7a5a"]["adjusted"] and not palettes["#123456"]["adjusted"]
