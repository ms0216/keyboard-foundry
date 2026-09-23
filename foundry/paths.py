"""外部の道具とリポジトリ内の場所。**ここが唯一の出どころ。**

HHKB で起きたこと: KiCad・OrcaSlicer の場所が 5 つのファイルに
macOS の固定パスで書かれ、環境変数で差し替えられるのは一部だけだった。
CI（Ubuntu）では `FileNotFoundError` の赤が 7 件常駐し、新しい赤を隠した。

**すべて環境変数で上書きでき、無ければ macOS の既定を使う。**
KiCad の Python（3.9）からも import されるので、標準ライブラリだけで書く。
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
LIB = ROOT / "lib"                     # リポジトリ同梱のフットプリント・3D モデル
BUILD = ROOT / "build"                 # 生成物（gitignore）

_KICAD_APP = Path("/Applications/KiCad/KiCad.app/Contents")


def _env(name, default):
    return os.environ.get(name) or str(default)


KICAD_CLI = _env("KICAD_CLI", _KICAD_APP / "MacOS/kicad-cli")
# pcbnew は KiCad 同梱の Python にしか無い
KICAD_PYTHON = _env(
    "KICAD_PYTHON",
    _KICAD_APP / "Frameworks/Python.framework/Versions/3.9/bin/python3.9")
# KiCad 標準フットプリント（Diode_SMD.pretty など）の置き場
KICAD_FOOTPRINTS = Path(_env("KICAD_FOOTPRINTS", _KICAD_APP / "SharedSupport/footprints"))
ORCA = _env("ORCA_SLICER", "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer")
