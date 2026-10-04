"""試し刷り v2（coupon_v2_plate）を精度優先の設定で**実際にスライスし**、G-code を設計と突き合わせる。

    .venv/bin/python3 projects/cckb-click/click_coupon_v2.py           # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_v2.py            # 0.4 ノズル・Bambu Studio → build/cckb-click/coupon_v2_plate_n04.gcode.3mf

スライスの仕方は tools/slice_precise.py（設定の継承をたどる・回さずベッドの真ん中に置く・G-code の設定の欄と突き合わせる）。
G-code から確かめること（1 つでも外れたら NG・刷るファイルを置かない）:
  1. 設定が効いている・警告 0
  2. ねじの下穴 6 個が、外周の輪として 1.5 / 1.6 / 1.7 の径で出ている（測った径を出す）
  3. 蓋の細い所が線になっている: 蓋 1 の上下の腕・蓋 2 の腕（線の数と幅の和）。隙間（腕の間・腕の下）には線が無い
  4. 蓋 1・2 の山が、設計の高さまで線になっている層が 2 層以上ある（v1 は頂が 1 層だけだった）
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

STEM = "coupon_v2_plate"
NUM = re.compile(r"([XYZEIJ])(-?\d*\.?\d+)")


def read_loops(gcode):
    """層 → [dict(feat, width, pts, ws)]。円弧（G2 / G3）は細かい点にする（穴の径を測るため。slice_precise.read_layers は端点だけ）。
    ws = 区間ごとの線の幅（Arachne は 1 つの輪の途中で幅を変える。輪の頭の幅だけ見ると、細い腕の幅を読み違えた）。"""
    out, z, feat, width, x, y, cur = {}, None, "", None, None, None, None
    for line in gcode.read_text(errors="replace").splitlines():
        if line.startswith(";"):
            if line.startswith("; Z_HEIGHT:"):
                z, cur = round(float(line.split(":")[1]), 3), None
            elif line.startswith("; FEATURE:"):
                feat, cur = line.split(":", 1)[1].strip(), None
            elif line.startswith("; LINE_WIDTH:"):
                width = float(line.split(":")[1])
            continue
        if not line.startswith(("G1 ", "G0 ", "G2 ", "G3 ")):
            continue
        v = dict(NUM.findall(line.split(";")[0]))
        nx, ny = float(v.get("X", x or 0)), float(v.get("Y", y or 0))
        moved = "X" in v or "Y" in v
        if moved and z is not None and x is not None and float(v.get("E", 0)) > 0:
            if cur is None:
                cur = dict(feat=feat, width=width, pts=[(x, y)], ws=[])
                out.setdefault(z, []).append(cur)
            if line[1] in "23" and ("I" in v or "J" in v):
                cx, cy = x + float(v.get("I", 0)), y + float(v.get("J", 0))
                r = math.hypot(x - cx, y - cy)
                a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
                if line[1] == "2" and a1 >= a0:
                    a1 -= 2 * math.pi
                if line[1] == "3" and a1 <= a0:
                    a1 += 2 * math.pi
                cur["pts"] += [(cx + r * math.cos(a0 + (a1 - a0) * i / 12), cy + r * math.sin(a0 + (a1 - a0) * i / 12)) for i in range(1, 13)]
                cur["ws"] += [width] * 12
            else:
                cur["pts"].append((nx, ny))
                cur["ws"].append(width)
        elif moved:
            cur = None
        x, y = nx, ny
    return out


def crossings(layer, x, y0, y1):
    """縦の線 x を横切る押し出しの線 [(y, 幅)]（y0〜y1 の間）。同じ線の折り返しは 0.15 以内なら 1 本に数える。"""
    hits = []
    for lp in layer:
        for (ax, ay), (bx, by), w in zip(lp["pts"], lp["pts"][1:], lp["ws"]):
            if (ax - x) * (bx - x) < 0:
                yy = ay + (by - ay) * (x - ax) / (bx - ax)
                if y0 <= yy <= y1:
                    hits.append((yy, w))
    hits.sort()
    out = []
    for h in hits:
        if not out or h[0] - out[-1][0] > 0.15:
            out.append(h)
    return out


def check(gcode, rc):
    """返り値 (問題, 測った数)。"""
    import click_coupon_v2 as V

    S, LAY = V.S, V.LAY
    problems, facts = [], {}
    layers = read_loops(gcode)
    placed = {tag: part.bounding_box() for tag, _, part in V.plate_layout()}
    pb = V.plate().bounding_box()
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2
    oy = max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2
    # 2. 下穴: 穴の中心（設計）から、まわりの線の縁（線の中心 − 幅の半分）までのいちばん近い距離 × 2 = 線が空けている径。
    #    薄い壁（斜めの肉 0.49）では、穴の外周が 1 つの閉じた輪にならない（壁の線と 1 本になる）ので、輪の外接では測れない
    z_hole = S.FRAME_UNDER + S.FRAME_T - S.SCREW_PILOT_DEPTH
    for tag, holes in V.placed_holes().items():
        dias = []
        for (hx, hy), d in holes:
            per = []
            for z, loops in layers.items():
                if z < z_hole + 0.25:
                    continue
                near = 9.0
                for lp in loops:
                    for (ax, ay), (bx, by), w in zip(lp["pts"], lp["pts"][1:], lp["ws"]):
                        ax, ay, bx, by = ax - ox - hx, ay - oy - hy, bx - ox - hx, by - oy - hy
                        if min(abs(ax), abs(bx)) > 3 or min(abs(ay), abs(by)) > 3:
                            continue
                        ln = (bx - ax) ** 2 + (by - ay) ** 2
                        u = 0.0 if ln == 0 else max(0.0, min(1.0, -(ax * (bx - ax) + ay * (by - ay)) / ln))
                        near = min(near, math.hypot(ax + u * (bx - ax), ay + u * (by - ay)) - w / 2)
                per.append(2 * near)
            dias.append((d, round(sum(per) / len(per), 3), round(min(per), 3), len(per)))
            if abs(dias[-1][1] - d) > 0.12 or dias[-1][2] < d - 0.15:      # 薄い壁では線が 0.10 ほど内へ寄る（本番の枠も同じ切り方）
                problems.append(f"{tag}: 下穴 φ{d} が、線では平均 {dias[-1][1]}・最小 {dias[-1][2]}")
        facts[f"{tag} の下穴（設計の径・線が空けている径の平均・最小・層の数）"] = dias
        if len(dias) != len(S.COUPON_V2_PILOTS):
            problems.append(f"{tag}: 下穴が {len(dias)} 個")
    # 3・4. 蓋（刷る向き: x = CAD の x・y = 上面からの下がり・z = 手前の面からの奥行き）
    cv = LAY.cover()
    top = cv["z_top"]
    zs = sorted(layers)
    mid = min(zs, key=lambda q: abs(q - S.COVER_FRONT_T / 2))
    for n in (1, 2):
        g = V._geom(n)
        b = placed[f"C{2 + n}"]
        x_of = lambda u: b.min.X + ox + (g["xm"] + u - (g["xm"] - g["half"]))                # noqa: E731
        y_of = lambda z: b.min.Y + oy + (top - z)                                            # noqa: E731
        if g["kind"] == "hairpin":
            u = (g["u_u0"] + g["u_riser"]) / 2
            bands = [("上の腕", g["z1"], g["t"]), ("下の腕", g["z2"], g["t"])]
            gaps = [("腕の間", (g["z2"][1], g["z1"][0])), ("下の腕の下", (g["z_slab"], g["z2"][0]))]
        else:
            u = (g["u_post"] + g["hook_u"][0]) / 2
            bands = [("腕", g["z1"], g["t"])]
            gaps = [("腕の下", (g["z_slab"], g["z1"][0]))]
        for sg in (-1, 1):
            for name, (za, zb), t in bands:
                got = crossings(layers[mid], x_of(sg * u), y_of(zb) - 0.05, y_of(za) + 0.05)
                total = sum(w for _, w in got)
                facts[f"蓋 {n} {name}（{'左' if sg < 0 else '右'}）: 線の数・幅の和"] = (len(got), round(total, 2))
                if not got or not (t - 0.12 <= total <= t + 0.2):
                    problems.append(f"蓋 {n} の{name}: 線 {len(got)} 本・幅の和 {total:.2f}（設計の太さ {t}）")
            for name, (za, zb) in gaps:
                got = crossings(layers[mid], x_of(sg * u), y_of(zb) + 0.1, y_of(za) - 0.1)
                if got:
                    problems.append(f"蓋 {n} の隙間（{name}）に線が {len(got)} 本ある")
            # 山: 山の幅の真ん中で、材料の上端（線の中心 − 幅の半分）が設計の頂まで来ている層の数
            uh = sg * sum(g["hook_u"]) / 2
            full = 0
            peak = 0.0
            for z in zs:
                got = crossings(layers[z], x_of(uh), y_of(g["z_arm"] + g["h"]) - 0.3, y_of(g["z_arm"]) - 0.02)
                if got:
                    reach = top - ((got[0][0] - got[0][1] / 2) - (b.min.Y + oy))
                    peak = max(peak, reach)
                    full += reach >= g["z_arm"] + g["h"] - 0.06
            facts[f"蓋 {n} の山（{'左' if sg < 0 else '右'}）: 頂の高さ（設計 {g['z_arm'] + g['h']:.2f}）・そこまで届く層の数"] = (round(peak, 2), full)
            if full < 2:
                problems.append(f"蓋 {n} の山が設計の高さまで線になっている層が {full} 層しか無い")
    return problems, facts


def main(argv):
    engine = next((a for a in argv if a in ("bambu", "orca")), "bambu")
    variant = next((a for a in argv if a in SP.S.PRINT_RECIPES), "n04")
    rc = SP.recipe(variant, SP.S, engine)
    print(f"== {variant}・{engine}: {rc['preset']['name']}（{rc['machine']['name']}・{rc['filament']['name']}）")
    stl = SP.BUILD / f"{STEM}.stl"
    newest = max(q.stat().st_mtime for q in SP.PROJECT.glob("*.py"))
    if not stl.exists() or stl.stat().st_mtime < newest:
        print(f"NG {STEM}: STL が無いか、生成器より古い（click_coupon_v2.py を回し直す）")
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
    warns = sorted({ln.strip()[:160] for ln in log.splitlines() if re.search(r"warn|error|fail|cannot|invalid", ln, re.I)})
    problems, n = SP.applied_problems(rc, SP.gcode_config(text))
    more, facts = check(gcode, rc)
    problems += more + [f"警告: {w}" for w in warns]
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
