"""手前の縁の試し刷り（coupon_front_plate）を精度優先の設定で**実際にスライスし**、G-code を設計と突き合わせる。

    .venv/bin/python3 projects/cckb-click/click_coupon_front.py        # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_front.py         # 0.4 ノズル・Bambu Studio → build/cckb-click/coupon_front_plate_n04.gcode.3mf

スライスの仕方は tools/slice_precise.py（設定の継承をたどる・回さずベッドの真ん中に置く・G-code の設定の欄と突き合わせる）。支えは付けない。
G-code から確かめること（1 つでも外れたら NG・刷るファイルを置かない）:
  1. 設定が効いている・警告 0・支えの線が 1 本も無い
  2. 枠 2 つの、細い所が線になっている: 基板の縁の外を下りる壁・爪のいちばん上の層・くぼみの外の皮・穴の手前の縁。
     それぞれ、線の本数・線が覆っている幅（設計の厚さと比べる）・線の幅の合計（すき間が無いか）
  3. 爪の掛かる面（宙へ張り出す斜面）が、1 層ごとに外へ出る量（線の幅の半分を超えたら、支え無しでは垂れる）
  4. 奥の壁の下穴 6 個が、φ1.6 で出ている（tools/slice_v2.py と同じ測り方）
"""

import math
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import slice_precise as SP  # noqa: E402
import slice_v2 as SV  # noqa: E402

STEM = "coupon_front_plate"
SPAN_TOL = 0.12              # 線が覆っている幅と設計の厚さの差の上限
FILL_MIN = 0.85              # 線の幅の合計 ÷ 設計の厚さ の下限（すき間）
STEP_MAX = 0.5               # 斜面が 1 層で外へ出る量の上限（外周の線の幅に対する割合）
# Bambu Studio が [error] で出す 1 行。**警告 0 件には数えないが、件数を出す**（3 件を超えたら NG）。
# 出どころ（2026-10-05 に部品を分けてスライスして確かめた）: 縁 0.4 の枠の、奥の壁の下穴 3 つ。この枠だけ下穴を 0.4 奥へ寄せてあり、
# 下穴が壁の中に閉じた止まり穴になる（本番と縁 0.8 の枠は、下穴が厚い壁の縁に掛かる）。下穴を埋める・貫通にすると 0 件、枠の手前だけ・
# 爪なしでは 0 件 = 爪とは関係が無い。穴の底の層の線は、縁 0.8 の枠と同じに出ている（穴のまわり φ2.4 の中の線の面積で比べた）
KNOWN = "ZFiller: encounter idx from clip"
KNOWN_MAX = 3


def crossings(layer, x, y0, y1, pad=0.35):
    """x = 一定の線が、y0〜y1（± pad）で横切る線 [(y, 幅, 種類)]。"""
    out = []
    for lp in layer:
        for (ax, ay), (bx, by), w in zip(lp["pts"], lp["pts"][1:], lp["ws"]):
            if (ax - x) * (bx - x) > 0 or ax == bx:
                continue
            y = ay + (by - ay) * (x - ax) / (bx - ax)
            if y0 - pad <= y <= y1 + pad:
                out.append((y, w, lp["feat"]))
    return sorted(out)


def measure(layers, x, y0, y1, z):
    """高さ z を含む層で、(本数, 覆っている幅, 線の幅の合計, 手前の縁, 奥の縁, 層の上面の高さ)。線が無ければ本数 0。"""
    zs = sorted(layers)
    zl = next((q for q in zs if q >= z - 1e-6), zs[-1])
    hit = crossings(layers[zl], x, y0, y1)
    if not hit:
        return dict(n=0, span=0.0, fill=0.0, lo=None, hi=None, z=zl, walls=0)
    lo, hi = min(y - w / 2 for y, w, _ in hit), max(y + w / 2 for y, w, _ in hit)
    return dict(n=len(hit), span=round(hi - lo, 3), fill=round(sum(w for _, w, _ in hit), 3), lo=lo, hi=hi, z=zl,
                walls=sum("wall" in f.lower() for _, _, f in hit))


def check(gcode, rc):
    """返り値 (問題, 測った数)。"""
    import click_coupon_front as K

    S = K.S
    problems, facts = [], {}
    layers = SV.read_loops(gcode)
    pb = K.plate().bounding_box()
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2
    oy = max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2
    w_out = SP.rc_width(rc, "outer_wall_line_width")
    feats = sorted({lp["feat"] for loops in layers.values() for lp in loops})
    facts["線の種類"] = feats
    if any("support" in f.lower() for f in feats):
        problems.append(f"支えの線がある: {feats}")
    fns = {tag: fn for tag, _, kind, _, fn in K.plate_layout() if kind == "frame"}
    for m, tag in zip(K.MARGINS, fns):
        fn = fns[tag]
        # 2. 細い所
        for name, (x, ya, yb, z) in K.probes(m).items():
            pa, pb_ = fn((x, ya, z)), fn((x, yb, z))
            y0, y1 = sorted((pa[1] + oy, pb_[1] + oy))
            r = measure(layers, pa[0] + ox, y0, y1, pa[2])
            want = y1 - y0
            facts[f"{tag} {name}（設計 {want:.2f}）"] = dict(本数=r["n"], 外周と内周=r["walls"], 覆う幅=r["span"], 線の幅の合計=r["fill"], 層=r["z"])
            if r["n"] < 2:
                problems.append(f"{tag} {name}: 線が {r['n']} 本（2 本以上のはず）")
            elif abs(r["span"] - want) > SPAN_TOL:
                problems.append(f"{tag} {name}: 線が覆う幅 {r['span']} が設計 {want:.2f} と {SPAN_TOL} より違う")
            elif r["fill"] < FILL_MIN * want:
                problems.append(f"{tag} {name}: 線の幅の合計 {r['fill']} が設計 {want:.2f} の {FILL_MIN} 倍に足りない（すき間）")
        # 3. 爪の斜面: 壁の内面から、爪の先まで。層ごとに、基板の側の縁がどれだけ出るか
        x, ya, yb, _ = K.probes(m)["lip"]
        g = K.geom(m)
        z_from, z_to = fn((x, ya, K.LIP_Z0 + 0.3))[2], fn((x, ya, K.LIP_BOTTOM))[2]
        pa, pb_ = fn((x, ya, 0.0)), fn((x, yb, 0.0))
        y0, y1 = sorted((pa[1] + oy, pb_[1] + oy))
        inner_is_low = pb_[1] < pa[1]                       # 裏返っているので、基板の側（爪の先）は y の小さい方
        edges = []
        for z in sorted(q for q in layers if z_from - 1e-6 <= q <= z_to + 1e-6):
            r = measure(layers, pa[0] + ox, y0, y1, z)
            if r["n"]:
                edges.append((z, r["lo"] if inner_is_low else r["hi"]))
        steps = [abs(b[1] - a[1]) for a, b in zip(edges, edges[1:])]
        reach = abs(edges[-1][1] - edges[0][1]) if edges else 0.0
        facts[f"{tag} 爪の斜面"] = dict(層の数=len(edges), 張り出しの合計=round(reach, 3), 層ごとの最大=round(max(steps, default=0.0), 3),
                                    線の幅に対して=round(max(steps, default=0.0) / w_out, 2))
        if abs(reach - K.LIP_REACH) > SPAN_TOL:
            problems.append(f"{tag}: 爪の張り出しが線では {reach:.3f}（設計 {K.LIP_REACH}）")
        if steps and max(steps) > STEP_MAX * w_out:
            problems.append(f"{tag}: 爪の斜面が 1 層で {max(steps):.3f} 出る（線の幅 {w_out} の {STEP_MAX} 倍を超える）")
        # 4. 下穴
        z_hole = S.FRAME_UNDER + S.FRAME_T - S.SCREW_PILOT_DEPTH
        d = S.SCREW_PILOT_D
        dias = []
        for hx, hy in K.pilots(m):
            p = fn((hx, hy, 0.0))
            per = SV.hole_diameters(layers, p[0] + ox, p[1] + oy, z_hole + 0.25)
            per = per[:int(round((S.SCREW_PILOT_DEPTH - 0.25) / S.PRINT_LAYER))]          # 下穴のある層だけ（その上は爪の層で、ここには線が無い）
            dias.append((round(sum(per) / len(per), 3), round(min(per), 3), len(per)))
            if abs(dias[-1][0] - d) > 0.12 or dias[-1][1] < d - 0.15:
                problems.append(f"{tag}: 下穴 φ{d} が、線では平均 {dias[-1][0]}・最小 {dias[-1][1]}")
        facts[f"{tag} の下穴 φ{d}（線が空けている径の平均・最小・層の数）"] = dias
    return problems, facts


def main(argv):
    engine = next((a for a in argv if a in ("bambu", "orca")), "bambu")
    variant = next((a for a in argv if a in SP.S.PRINT_RECIPES), "n04")
    rc = SP.recipe(variant, SP.S, engine)
    print(f"== {variant}・{engine}: {rc['preset']['name']}（{rc['machine']['name']}・{rc['filament']['name']}）")
    stl = SP.BUILD / f"{STEM}.stl"
    newest = max(q.stat().st_mtime for q in SP.PROJECT.glob("*.py"))
    if not stl.exists() or stl.stat().st_mtime < newest:
        print(f"NG {STEM}: STL が無いか、生成器より古い（click_coupon_front.py を回し直す）")
        return 1
    dst = SP.BUILD / f"{STEM}_{variant}.gcode.3mf"
    if engine == "bambu":
        dst.unlink(missing_ok=True)                    # 前の物を、今回の合格と見間違えない
    gcode, log = SP.slice_stl(rc, stl)
    if gcode is None:
        print(f"NG {STEM}: スライスに失敗\n{log.strip()[-800:]}")
        return 1
    text = gcode.read_text(errors="replace")
    info = SP.summarize_gcode(gcode)
    total = re.search(r"total estimated time: ([^\n;]+)", text)
    used = re.search(r"; (?:total )?filament (?:used|length) \[mm\] ?[:=] ?([\d.]+)", text)
    cm3 = info.get("材料") or (f"{float(used.group(1)) * math.pi * 0.875 ** 2 / 1000:.2f}" if used else None)
    grams = re.search(r"; (?:total )?filament (?:used|weight) \[g\] ?[:=] ?([\d.]+)", text)
    lines = [ln.strip()[:160] for ln in log.splitlines() if re.search(r"warn|error|fail|cannot|invalid", ln, re.I)]
    known = [ln for ln in lines if KNOWN in ln]
    warns = sorted({ln for ln in lines if KNOWN not in ln})
    problems, n = SP.applied_problems(rc, SP.gcode_config(text))
    more, facts = check(gcode, rc)
    problems += more + [f"警告: {w}" for w in warns]
    if len(known) > KNOWN_MAX:
        problems.append(f"「{KNOWN}」が {len(known)} 件（下穴の数 {KNOWN_MAX} より多い = 別の所でも出ている）")
    facts[f"除外した出力「{KNOWN}」"] = f"{len(known)} 件（縁 0.4 の枠の奥の下穴 3 つの底の層。下穴は 4. で層ごとに測っている）"
    print(f"{'NG' if problems else 'OK'} {STEM}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
          f"材料 {cm3} cm3（{grams.group(1) if grams else round(float(cm3) * 1.24, 1)} g）・層 {info.get('層数')}・"
          f"設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}・{SP.cfg_generator(text)}")
    for k, v in facts.items():
        print(f"     {k}: {v}")
    for q in problems:
        print(f"     NG {q}")
    made = gcode.parent / f"{STEM}.gcode.3mf"
    if engine == "bambu" and not problems and made.exists():
        shutil.copyfile(made, dst)
        print(f"     刷るファイル {dst}（{dst.stat().st_size} バイト）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
