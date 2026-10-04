"""ねじで留める蓋の試し刷り（coupon_corner_plate）と、本番の蓋（cover_battery）を精度優先の設定で**実際にスライスし**、G-code を設計と突き合わせる。

    .venv/bin/python3 projects/cckb-click/click_case.py               # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_cover.py        # 0.4 ノズル・Bambu Studio → build/cckb-click/coupon_corner_plate_n04.gcode.3mf

スライスの仕方は tools/slice_precise.py（設定の継承をたどる・回さずベッドの真ん中に置く・G-code の設定の欄と突き合わせる）。
G-code から確かめること（1 つでも外れたら NG・刷るファイルを置かない）:
  1. 設定が効いている・警告 0
  2. 蓋の下穴 2 つ（と、枠の切れ端のねじ H15 の下穴）が、**利用者が締めて確かめた径**で線になっている
     （試し刷り v2 の A で止まった φ1.6 は、線が空ける径で ふつうの壁 1.54・薄い壁 1.50。tools/slice_main.py の PILOT_PRINTED と同じ物差し:
     薄い壁の下の端 1.47 から、ふつうの壁の上の端 1.57 まで。入れ始めが固かった φ1.5 は線で 1.44／1.40・空回りした φ1.8 は 1.76〜1.79）
  3. 蓋の下穴のまわり（左右と手前）に、線が 2 本以上ある（肉が 1 本の線だけになっていない）
"""

import math
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import slice_main as SM  # noqa: E402
import slice_precise as SP  # noqa: E402
import slice_v2 as SV  # noqa: E402

STEMS = ("coupon_corner_plate", "cover_battery")


def placed(stem):
    """(板の外接, {名前: [下穴の中心（板の座標）]}, 下穴の始まる高さ)。"""
    import click_case as C

    top = C.S.FRAME_UNDER + C.S.FRAME_T
    z_hole = top - C.S.SCREW_PILOT_DEPTH
    if stem == "cover_battery":
        cv = C.LAY.cover()
        group = C.P.flip_to_bed(C._marked(C.cover_solid(), [(x, y, 1.0) for x, y in cv["screws"]]))
        solids = list(group.solids())
        return solids[0].bounding_box(), {"cover": [(m.bounding_box().center().X, m.bounding_box().center().Y) for m in solids[1:]]}, z_hole
    return C.corner_coupon_plate().bounding_box(), {n: h for n, _, h in C.corner_coupon_layout() if h}, z_hole


def lines_from(layer, cx, cy, ux, uy, reach=1.6):
    """穴の中心から (ux, uy) の向きへ reach まで行く間に横切る線の数（同じ線の折り返しは 0.15 以内なら 1 本）。"""
    hits = []
    for lp in layer:
        for (ax, ay), (bx, by) in zip(lp["pts"], lp["pts"][1:]):
            ax, ay, bx, by = ax - cx, ay - cy, bx - cx, by - cy
            # 向き (ux, uy) の半直線と線分の交点: 線分を、向きに垂直な成分 v と、向きの成分 u に分ける
            av, bv = -ax * uy + ay * ux, -bx * uy + by * ux
            if av * bv < 0:
                k = av / (av - bv)
                u = (ax + k * (bx - ax)) * ux + (ay + k * (by - ay)) * uy
                if 0 < u <= reach:
                    hits.append(u)
    hits.sort()
    out = []
    for h in hits:
        if not out or h - out[-1] > 0.15:
            out.append(h)
    return len(out)


def check(stem, gcode, rc):
    problems, facts = [], {}
    layers = SV.read_loops(gcode)
    pb, holes, z_hole = placed(stem)
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2
    oy = max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2
    lo, hi = SM.PILOT_PRINTED["thin"][0], SM.PILOT_PRINTED["normal"][1]
    top = SP.S.FRAME_UNDER + SP.S.FRAME_T                  # 蓋も枠の切れ端も、刷る向きで高さ 5.0（当て板の上の代わりの物はもっと高い）
    layers = {z: v for z, v in layers.items() if z <= top + 1e-6}
    zs = [z for z in sorted(layers) if z >= z_hole + 0.25]
    mid = zs[len(zs) // 2]
    for name, centres in holes.items():
        for i, (hx, hy) in enumerate(centres):
            per = SV.hole_diameters(layers, hx + ox, hy + oy, z_hole + 0.25)
            mean = sum(per) / len(per)
            key = f"{name} の下穴 {i + 1}（線が空ける径の平均・最小・層の数）"
            facts[key] = (round(mean, 3), round(min(per), 3), len(per))
            if not (lo <= mean <= hi) or len(per) < 20:
                problems.append(f"{key}: {facts[key]}（利用者が確かめた径 {lo}〜{hi}・20 層以上）")
            if name == "cover":
                # 下穴から 4 つの向きへ 1.6 の間にある線の数。奥の 1 つの向きは斜めの面で薄くなるので、残りの 3 つを見る
                n = {d: lines_from(layers[mid], hx + ox, hy + oy, *u) for d, u in (("+x", (1, 0)), ("-x", (-1, 0)), ("+y", (0, 1)), ("-y", (0, -1)))}
                facts[f"{name} の下穴 {i + 1} のまわりの線の数（z {mid}）"] = n
                if sorted(n.values())[1] < 2:                     # 4 つの向きのうち 3 つ（左右と手前）に 2 本以上
                    problems.append(f"{name} の下穴 {i + 1} のまわりの線が少ない: {n}")
    return problems, facts


def main(argv):
    engine = next((a for a in argv if a in ("bambu", "orca")), "bambu")
    variant = next((a for a in argv if a in SP.S.PRINT_RECIPES), "n04")
    rc = SP.recipe(variant, SP.S, engine)
    print(f"== {variant}・{engine}: {rc['preset']['name']}（{rc['machine']['name']}・{rc['filament']['name']}）")
    newest = max(q.stat().st_mtime for q in SP.PROJECT.glob("*.py"))
    bad = 0
    for stem in STEMS:
        stl = SP.BUILD / f"{stem}.stl"
        dst = SP.BUILD / f"{stem}_{variant}.gcode.3mf"
        if engine == "bambu":
            dst.unlink(missing_ok=True)                    # 前の物を、今回の合格と見間違えない
        if not stl.exists() or stl.stat().st_mtime < newest:
            print(f"NG {stem}: STL が無いか、生成器より古い（click_case.py を回し直す）")
            bad += 1
            continue
        gcode, log = SP.slice_stl(rc, stl)
        if gcode is None:
            print(f"NG {stem}: スライスに失敗\n{log.strip()[-800:]}")
            bad += 1
            continue
        text = gcode.read_text(errors="replace")
        info = SP.summarize_gcode(gcode)
        total = re.search(r"total estimated time: ([^\n;]+)", text)
        used = re.search(r"; (?:total )?filament (?:used|length) \[mm\] ?[:=] ?([\d.]+)", text)
        cm3 = info.get("材料") or (f"{float(used.group(1)) * math.pi * 0.875 ** 2 / 1000:.2f}" if used else None)
        warns = sorted({ln.strip()[:160] for ln in log.splitlines() if re.search(r"warn|error|fail|cannot|invalid", ln, re.I)})
        problems, n = SP.applied_problems(rc, SP.gcode_config(text))
        more, facts = check(stem, gcode, rc)
        problems += more + [f"警告: {w}" for w in warns]
        bad += len(problems)
        print(f"{'NG' if problems else 'OK'} {stem}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
              f"材料 {cm3} cm3（約 {round(float(cm3) * SM.PLA, 1) if cm3 else '?'} g）・層 {info.get('層数')}・"
              f"設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}・{SP.cfg_generator(text)}")
        for k, v in facts.items():
            print(f"     {k}: {v}")
        for q in problems:
            print(f"     NG {q}")
        made = gcode.parent / f"{stem}.gcode.3mf"
        if engine == "bambu" and not problems and made.exists():
            shutil.copyfile(made, dst)
            print(f"     刷るファイル {dst}（{dst.stat().st_size} バイト）")
    print("NG" if bad else "OK", f"問題 {bad} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
