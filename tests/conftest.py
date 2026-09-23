"""検査ぜんぶで共有する足回り。

**外部の道具（KiCad・OrcaSlicer）が要る検査の入口。**約束は 1 つ:

  - 道具が無い環境 …… skip
  - **`REQUIRE_KICAD=1` なら fail**（入れたはずが入っていない、を緑にしない）

HHKB で起きたこと: macOS の固定パスを直に呼んで CI で FileNotFoundError の赤が
7 件常駐し、新しい赤を隠した。逆に黙って飛ばすと「飛んだ検査は無いのと同じ」で
緑になる（4 回起きた）。**guard は fixture の中に置く**——間接的に道具を呼ぶ
fixture が先に落ちると skip ではなく error になる。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from foundry import paths  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def pytest_configure(config):
    # 編集のたびに全部（約 3 分半）を待たない: `pytest tests -q -m "not slow"`。
    # slow は CCKB のケースの 5〜13 秒の検査（経路・水密・干渉・壁厚）。CI と発注前は全部を回す
    config.addinivalue_line("markers", "slow: 5 秒を超える形状の検査（-m 'not slow' で飛ばせる）")


def require(tool_path, what):
    if Path(tool_path).exists():
        return
    if os.environ.get("REQUIRE_KICAD") == "1":
        pytest.fail(f"{what}: {tool_path} が無い。このジョブは飛ばしてはいけない")
    pytest.skip(f"{what}: {tool_path} が無い環境（環境変数で場所を指せる。foundry/paths.py）")


@pytest.fixture(scope="session")
def hhkb_ref(tmp_path_factory):
    """HHKB の参照機種を一時ディレクトリへ写したもの（生成物で fixtures を汚さない）。"""
    d = tmp_path_factory.mktemp("proj") / "hhkb_ref"
    shutil.copytree(FIXTURES / "hhkb_ref", d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    return d


@pytest.fixture(scope="session")
def hhkb_boards(hhkb_ref):
    """foundry.pcb で作った HHKB 参照機種の未配線基板 {部品: パス}。"""
    require(paths.KICAD_PYTHON, "基板の生成")
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(hhkb_ref)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr          # 出力を捨てない
    out = hhkb_ref / "pcb" / "unrouted"
    return {piece: out / f"hhkb_ref_{piece}.kicad_pcb" for piece in ("left", "right")}
