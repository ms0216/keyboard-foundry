"""取付ネジを置ける場所を、生成した基板の実物から探す（候補を出すだけ。選ぶのは人）。

    tools/kb cckb pcb
    "$KICAD_PYTHON" projects/cckb/tools/board_geometry.py projects/cckb/pcb/unrouted/cckb_main.kicad_pcb build/cckb/board_geometry.json
    .venv/bin/python3 projects/cckb/tools/find_mounts.py build/cckb/board_geometry.json

条件は interface.mount_problems（5 条件）。HHKB の find_mounts は条件を別々に確かめて
3 往復した（docs/knowledge/pcb.md）ので、ここは 1 つの関数で同時に見る。
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interface import Interface, corridors, mount_problems  # noqa: E402


def main(argv):
    geo = json.loads(Path(argv[0]).read_text())
    ifc = Interface()
    step = 0.5
    # 配線の通り道は**基板全体のパッドから**作って先に入れる（下の前ふるいで
    # パッドを絞った geo から作ると通り道が欠ける。初版で 5 か所を見逃した）
    cache = {"corr": corridors(ifc, geo)}
    # 速さのため、パッドの無い所だけ残した粗い前ふるい（ナット・ボスの半径 ＋ 余裕）
    reach = 4.0
    pads = geo["pads"]
    e = ifc.pcb
    ok = []
    x = e[0]
    while x <= e[2]:
        y = e[1]
        while y <= e[3]:
            near = [q for q in pads if q["box"][0] - reach < x < q["box"][2] + reach
                    and q["box"][1] - reach < y < q["box"][3] + reach]
            g = dict(geo, pads=near)
            if not mount_problems(ifc, g, (x, y), cache=cache):
                ok.append((round(x, 2), round(y, 2)))
            y += step
        x += step
    cells = defaultdict(list)
    for p in ok:
        cells[(round(p[0] / 10) * 10, round(p[1] / 10) * 10)].append(p)
    print(f"置ける点 {len(ok)}（{step}mm 刻み）・区画 {len(cells)}")
    for k in sorted(cells):
        pts = cells[k]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        best = min(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        print(f"  区画 {k}: {len(pts):4d} 点  中ほど {best}")
    for p in ifc.mounts():
        prob = mount_problems(ifc, geo, p, corner_ok=True)
        print(f"{'OK' if not prob else 'NG'} 採用 {p} {prob}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
