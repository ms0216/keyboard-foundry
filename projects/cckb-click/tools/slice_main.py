"""cckb-click の本番の刷る物（枠 2 枚・キャップの板 2 枚）を、精度優先の設定で**実際にスライスする**。

    .venv/bin/python3 projects/cckb-click/click_case.py                 # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_main.py            # 0.4 ノズル・Bambu Studio
    .venv/bin/python3 projects/cckb-click/tools/slice_main.py orca       # OrcaSlicer で

スライスの仕方（設定の継承をたどる・ベッドの真ん中に回さず置く・G-code の設定の欄と突き合わせる）は、試し刷りと同じ
tools/slice_precise.py。出すのは時間・材料・層の数・効いた設定の数・警告。**出力を捨てない。**各行の頭に OK / NG。
結果は build/cckb-click/slice_main.json にも書く（文書の表はここから写す）。

枠は、**ねじの下穴 22 個を G-code で測る**（線が空けている径。tools/slice_v2.hole_diameters = 試し刷り v2 と同じ測り方）。
利用者が試し刷り v2 で締めた φ1.6 の切れ端は、線ではふつうの壁 1.54・薄い壁（幅の広いキーの脇）1.50 だった。本番の枠の下穴が
それと同じ径で刷られること（= 利用者が確かめた物と同じ）を見る。入れ始めが固かった φ1.5 は、線で 1.44／1.40。
"""

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import slice_precise as SP  # noqa: E402
import slice_v2 as SV       # noqa: E402

# 下穴 φ1.6 が線で空ける径の許す幅。**利用者が締めて確かめた径**（試し刷り v2 の G-code: ふつうの壁 1.54・薄い壁 1.50）の ± 0.03。
# 下の端 1.47 は、入れ始めが固かった φ1.5（線で 1.44）との真ん中。上の端は、空回りした φ1.8（線で 1.76〜1.79）よりずっと下
PILOT_PRINTED = {"normal": (1.51, 1.57), "thin": (1.47, 1.53)}


def frame_pilots(side):
    """枠 side（left / right）を刷る向きに置いたときの、下穴の中心 [(参照名, (x, y), 薄い壁か)]（STL の座標）。
    枠と一緒に小さな印を同じ手順で裏返して、印の行き先を読む（変換を式で写さない）。"""
    import click_case as C
    from build123d import Compound, Pos, Sphere

    lay = C.LAY
    mine = [(ref, c) for ref, c, _ in lay.wall_screws() if (c[0] < lay.seam_x(c[1])) == (side == "left")]
    group = C.frame_print(Compound([C.frame_halves()[side]] + [Pos(c[0], c[1], 1.0) * Sphere(0.05) for _, c in mine]))
    marks = [m.bounding_box().center() for m in list(group.solids())[1:]]
    return [(ref, (m.X, m.Y), lay.boss_half(c) != lay.s.SCREW_BOSS_HALF) for (ref, c), m in zip(mine, marks)]


def pilot_check(stem, gcode, rc, stl):
    """(問題, 行)。行 = [(参照名, 薄い壁か, 平均の径, 最小の径, 層の数)]。"""
    import trimesh

    s = SP.S
    b = trimesh.load(str(stl)).bounds
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (b[0][0] + b[1][0]) / 2
    oy = max(p[1] for p in area) / 2 - (b[0][1] + b[1][1]) / 2
    layers = SV.read_loops(gcode)
    z_from = s.FRAME_UNDER + s.FRAME_T - s.SCREW_PILOT_DEPTH + 0.25
    rows, problems = [], []
    for ref, (x, y), thin in frame_pilots(stem.split("_")[1]):
        per = SV.hole_diameters(layers, x + ox, y + oy, z_from)
        mean = sum(per) / len(per)
        rows.append((ref, thin, round(mean, 3), round(min(per), 3), len(per)))
        lo, hi = PILOT_PRINTED["thin" if thin else "normal"]
        if not (lo <= mean <= hi) or len(per) < 20:
            problems.append(f"{stem} {ref}（{'薄い壁' if thin else 'ふつうの壁'}）: 下穴 φ{s.SCREW_PILOT_D} が、線では平均 {mean:.3f}・最小 {min(per):.3f}・{len(per)} 層"
                            f"（利用者が確かめた径 {lo}〜{hi}）")
    return problems, rows

STEMS = ("frame_left", "frame_right", "caps_1u", "caps_wide")      # 電池の蓋は入れない（考え直している途中。open-gaps P21）
PLA = 1.24                  # g/cm3


def main(argv):
    only = next((a for a in argv if a in ("bambu", "orca")), "bambu")
    variant = next((a for a in argv if a in SP.S.PRINT_RECIPES), "n04")
    rc = SP.recipe(variant, SP.S, only)
    print(f"== {variant}・{only}: {rc['preset']['name']}（{rc['machine']['name']}・{rc['filament']['name']}）")
    newest = max(q.stat().st_mtime for q in SP.PROJECT.glob("*.py"))
    rows, bad = [], 0
    for stem in STEMS:
        stl = SP.BUILD / f"{stem}.stl"
        if not stl.exists() or stl.stat().st_mtime < newest:
            print(f"NG {stem}: STL が無いか、生成器より古い（click_case.py を回し直す）")
            bad += 1
            continue
        gcode, log = SP.slice_stl(rc, stl)
        if gcode is None:
            print(f"NG {stem}: スライスに失敗\n{log.strip()[-600:]}")
            bad += 1
            continue
        text = gcode.read_text(errors="replace")
        info = SP.summarize_gcode(gcode)
        total = re.search(r"total estimated time: ([^\n;]+)", text)
        used = re.search(r"; (?:total )?filament (?:used|length) \[mm\] ?[:=] ?([\d.]+)", text)
        cm3 = info.get("材料") or (f"{float(used.group(1)) * math.pi * 0.875 ** 2 / 1000:.2f}" if used else None)
        warns = sorted({ln.strip()[:160] for ln in log.splitlines() if re.search(r"warn|error|fail|cannot|invalid", ln, re.I)})
        problems, n = SP.applied_problems(rc, SP.gcode_config(text))
        pilots = []
        if stem.startswith("frame_"):
            more, pilots = pilot_check(stem, gcode, rc, stl)
            problems += more
        bad += len(problems)
        grams = round(float(cm3) * PLA, 1) if cm3 else None
        print(f"{'NG' if problems else 'OK'} {stem}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
              f"材料 {cm3} cm3（約 {grams} g）・層 {info.get('層数')}・設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}")
        for w in warns[:6]:
            print(f"     ! {w}")
        if pilots:
            for kind, thin in (("ふつうの壁", False), ("薄い壁", True)):
                got = [(ref, mean, least) for ref, t, mean, least, _ in pilots if t == thin]
                if got:
                    print(f"     下穴 φ{SP.S.SCREW_PILOT_D}・{kind} {len(got)} 個: 線が空ける径の平均 {min(m for _, m, _ in got):.3f}〜{max(m for _, m, _ in got):.3f}"
                          f"・最小 {min(v for _, _, v in got):.3f}  " + " ".join(f"{ref}={m:.2f}" for ref, m, _ in got))
        for q in problems:
            print(f"     NG {q}")
        rows.append(dict(name=stem, time=info.get("時間"), total=total.group(1).strip() if total else None, cm3=cm3, grams=grams,
                         layers=info.get("層数"), warnings=len(warns),
                         pilots=[dict(ref=ref, thin=t, mean=mean, min=least, layers=nl) for ref, t, mean, least, nl in pilots]))
    (SP.BUILD / "slice_main.json").write_text(json.dumps(dict(variant=variant, engine=only, rows=rows), ensure_ascii=False, indent=1) + "\n")
    print("NG" if bad else "OK", f"問題 {bad} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
