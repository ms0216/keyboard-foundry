"""蓋の別案 B3 の試し刷り（coupon_cover_snap_plate = B3 の枠の角・当て板・電池の代わり・蓋 3 つ）を精度優先の設定で**実際にスライスし**、
G-code を設計と突き合わせる。

    .venv/bin/python3 projects/cckb-click/click_cover_snap.py           # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_cover_snap.py     # 0.4 ノズル・Bambu Studio → build/cckb-click/coupon_cover_snap_plate_n04.gcode.3mf

スライスの仕方は tools/slice_precise.py（設定の継承をたどる・回さずベッドの真ん中に置く・G-code の設定の欄と突き合わせる）。支えは付けない。
G-code から確かめること（1 つでも外れたら NG・刷るファイルを置かない）:
  1. 設定が効いている・警告 0・支えの線が 1 本も無い
  2. 蓋の腕（左右 × 蓋 3 つ × 3 か所）: **線が 2 本以上**並んでいる・腕と胴の間の隙に、中ほどの層でも 1 層目でも線が無い（腕が胴に付かない）・かぎが線になっている
  3. 蓋の真ん中の、電池の上に渡る帯（刷るときは橋）: 最初の層が、宙を渡る線（Bridge・Overhang wall）で、左右へ渡っている（奥の縁は支えが無いので、前後へは渡れない）。
     そのすぐ下の層には、くぼみの中に線が無い
  4. 枠（上面をベッドに）: かぎの入る空洞と、腕の通る窓に線が無い・口の縁と、奥の案内の壁が線になっている・動かした H15 の下穴が空いている
検査器が生きていること: 見る点を左右へ 0.6 ずらすと「埋まっている」と言う。
絵: build/cckb-click/slice_cover_snap.png（見ること）。
"""

import math
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import slice_cover_slide as SS  # noqa: E402  （読むだけ: nearest・layer_at）
import slice_precise as SP  # noqa: E402
import slice_v2 as SV  # noqa: E402

STEM = "coupon_cover_snap_plate"
GAP_CLEAR = 0.3              # 空いているはずの所の真ん中から、いちばん近い線の中心まで
ON_LINE = 0.3                # 線があるはずの所から、いちばん近い線の中心まで
MIN_LINES = 2


def crossings(layer, p0, p1):
    """p0〜p1 の線分を横切る線（中心線）の本数（0.15 以内の交点は 1 本に数える）。"""
    (x1, y1), (x2, y2) = p0, p1
    ts = []
    for lp in layer:
        for (ax, ay), (bx, by) in zip(lp["pts"], lp["pts"][1:]):
            den = (x2 - x1) * (by - ay) - (y2 - y1) * (bx - ax)
            if abs(den) < 1e-12:
                continue
            t = ((ax - x1) * (by - ay) - (ay - y1) * (bx - ax)) / den
            u = ((ax - x1) * (y2 - y1) - (ay - y1) * (x2 - x1)) / den
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                ts.append(t * math.hypot(x2 - x1, y2 - y1))
    ts.sort()
    return sum(1 for i, t in enumerate(ts) if i == 0 or t - ts[i - 1] > 0.15)


def check(gcode, rc, shift=(0.0, 0.0)):
    """返り値 (問題, 測った数)。shift = 見る点をずらす（検査器が生きているかを見る）。"""
    import click_cover_snap as B

    problems, facts = [], {}
    layers = SV.read_loops(gcode)
    pb = B.plate().bounding_box()
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2 + shift[0]
    oy = max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2 + shift[1]
    fns = {name: fn for name, _, fn in B.plate_layout()}
    feats = sorted({lp["feat"] for loops in layers.values() for lp in loops})
    facts["線の種類"] = feats
    if any("support" in f.lower() for f in feats):
        problems.append(f"支えの線がある: {feats}")

    def to_plate(name, x, y, z):
        p = fns[name]((x, y, z))
        return p[0] + ox, p[1] + oy, SS.layer_at(layers, p[2])

    def at(name, x, y, z):
        px, py, zl = to_plate(name, x, y, z)
        d, feat, ang = SS.nearest(layers[zl], px, py)
        return round(d, 3), feat, round(ang), zl

    # 2. 蓋の腕
    fewest = 99
    for n, v in sorted(B.VARIANTS.items()):
        name = f"cover{n}"
        for side, f in (("左", lambda x: x), ("右", B.mx)):
            for label, y in (("先の近く", B.YF + 5.0), ("中ほど", (B.YF + B.YR) / 2), ("付け根の近く", B.YR - 1.5)):
                xo = B.XN - v["pre"] * B.shape(B.YR - y)             # 刷る形（腕が予圧ぶん外へ開いている）
                a = to_plate(name, f(xo - 0.08), y, 1.4)
                b = to_plate(name, f(xo + v["t"] + 0.08), y, 1.4)
                k = crossings(layers[a[2]], a[:2], b[:2])
                fewest = min(fewest, k)
                if k < MIN_LINES:
                    problems.append(f"蓋 {n}・{side}の腕・{label}: 線が {k} 本（{MIN_LINES} 本以上）")
                xm = (xo + v["t"] + B.body_edge(y)) / 2
                for z in (1.4, 0.05):
                    d, _, _, zl = at(name, f(xm), y, z)
                    facts[f"蓋 {n}・{side}・{label}: 腕と胴の隙の真ん中から線まで（層 {zl}）"] = d
                    if d < GAP_CLEAR:
                        problems.append(f"蓋 {n}・{side}の腕と胴の隙（{label}）が線で埋まっている（層 {zl}・{d}・{GAP_CLEAR} 以上）")
            yh = B.YS + B.HOOK_CH + 0.2
            xo = B.XN - v["pre"] * B.shape(B.YR - yh)
            d, _, _, zl = at(name, f(xo - B.HOOK / 2), yh, 1.4)
            facts[f"蓋 {n}・{side}のかぎの真ん中から線まで（層 {zl}）"] = d
            if d > ON_LINE:
                problems.append(f"蓋 {n}・{side}のかぎが線になっていない（層 {zl}・{d}）")
        # 3. 電池の上の帯（橋）
        (px, py), hw = B.pocket_center()
        spot = (px, B.YB - 0.45)
        d, feat, ang, zl = at(name, spot[0], spot[1], B.STRIP_Z + 0.05)
        facts[f"蓋 {n}: 電池の上の帯の最初の層（{zl}）: 線まで・種類・向き（0 = 左右）"] = (d, feat, ang)
        if d > ON_LINE:
            problems.append(f"蓋 {n}: 帯の最初の層（{zl}）に線が無い（{d}）")
        elif not any(q in feat.lower() for q in ("bridge", "overhang")):
            problems.append(f"蓋 {n}: 帯の最初の層（{zl}）が、宙を渡る線でない（{feat}）")
        elif ang > 45:
            problems.append(f"蓋 {n}: 帯の橋が、前後へ渡っている（向き {ang}°）= 奥の縁に支えが無い")
        d, _, _, zl = at(name, spot[0], spot[1] - 0.2, B.STRIP_Z - 0.05)
        facts[f"蓋 {n}: 帯のすぐ下の層（{zl}）の、くぼみの中から線まで"] = d
        if d < GAP_CLEAR:
            problems.append(f"蓋 {n}: 帯の下（層 {zl}）のくぼみの中に線がある（{d}）")
    facts["腕を横切る線のいちばん少ない本数"] = fewest
    # 4. 枠
    fr = "frame"
    for side, f in (("左", lambda x: x), ("右", B.mx)):
        open_pts = {"かぎの入る空洞": (f((B.XPK + B.XLIP) / 2), (B.YL - 46.2) / 2), "腕の通る窓": (f((B.XLIP + B.A0) / 2), B.Y0 + 1.5)}
        for label, (x, y) in open_pts.items():
            d, _, _, zl = at(fr, x, y, 1.5)
            facts[f"枠・{side}の{label}の真ん中から線まで（層 {zl}）"] = d
            if d < GAP_CLEAR:
                problems.append(f"枠・{side}の{label}が線で埋まっている（層 {zl}・{d}）")
        line_pts = {"口の縁": (f(B.XPK + 0.35), B.YL - 0.25), "案内の壁": (f((B.XPK + B.XN - B.GUIDE_CL) / 2), B.YR)}
        for label, (x, y) in line_pts.items():
            d, _, _, zl = at(fr, x, y, 1.5)
            facts[f"枠・{side}の{label}から線まで（層 {zl}）"] = d
            if d > 0.45:
                problems.append(f"枠・{side}の{label}が線になっていない（層 {zl}・{d}）")
    d, _, _, zl = at(fr, B.H15_NEW[0], B.H15_NEW[1], 1.5)
    facts[f"枠: 動かした H15 の下穴の真ん中から線まで（層 {zl}・半径 {B.LAY.pilot()[0] / 2}）"] = d
    if d < 0.5:
        problems.append(f"枠: 動かした H15 の下穴が空いていない（{d}）")
    return problems, facts


def draw(gcode, rc, out):
    """蓋 2 の線（1 層目・中ほど・帯の最初の層）と、枠の左の口のまわり（見る絵）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import click_cover_snap as B

    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    layers = SV.read_loops(gcode)
    pb = B.plate().bounding_box()
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2
    oy = max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2
    fns = {name: fn for name, _, fn in B.plate_layout()}
    col = {"bridge": "#c00000", "overhang": "#c00000", "outer": "#c05a10", "inner": "#d09040"}
    shots = [(f"cover{B.MAIN}", "蓋 2・1 層目（底）", 0.05, (B.XPK, B.Y0, B.mx(B.XPK), B.YJ + 0.5)),
             (f"cover{B.MAIN}", "蓋 2・中ほどの層", 1.4, (B.XPK, B.Y0, B.mx(B.XPK), B.YJ + 0.5)),
             (f"cover{B.MAIN}", "蓋 2・電池の上の帯の最初の層（赤 = 宙を渡る線）", B.STRIP_Z + 0.05, (B.XPK, B.Y0, B.mx(B.XPK), B.YJ + 0.5)),
             ("frame", "枠・左の口のまわり（上面が下。組んだ高さ 1.5）", 1.5, (B.BOX[0], B.Y0 - 0.5, B.A0 + 2.0, B.YJ + 2.0)),
             ("frame", "枠・右の口のまわり（動かした H15 の下穴）", 1.5, (B.A1 - 2.0, B.Y0 - 0.5, B.mx(B.BOX[0]), B.YJ + 2.0))]
    fig, axs = plt.subplots(len(shots), 1, figsize=(15, 6.0 * len(shots)))
    for ax, (name, title, z, win) in zip(axs, shots):
        fn = fns[name]
        a, b = fn((win[0], win[1], z)), fn((win[2], win[3], z))
        zl = SS.layer_at(layers, a[2])
        for lp in layers[zl]:
            xs, ys = zip(*lp["pts"])
            c = next((v for k, v in col.items() if k in lp["feat"].lower()), "#909090")
            ax.plot(xs, ys, "-", color=c, lw=1.1)
        ax.set_xlim(min(a[0], b[0]) + ox, max(a[0], b[0]) + ox)
        ax.set_ylim(min(a[1], b[1]) + oy, max(a[1], b[1]) + oy)
        ax.set_aspect("equal")
        ax.set_title(f"{title}（層の上面 {zl}）。赤 = 宙を渡る線・橙 = 外周・灰 = 中", fontsize=11)
    fig.suptitle("蓋の別案 B3 の G-code（Bambu Studio）。蓋は底が下・下が手前。枠は上面が下・上が手前", fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=80)
    plt.close(fig)
    return out


def main(argv):
    engine = next((a for a in argv if a in ("bambu", "orca")), "bambu")
    variant = next((a for a in argv if a in SP.S.PRINT_RECIPES), "n04")
    rc = SP.recipe(variant, SP.S, engine)
    print(f"== {variant}・{engine}: {rc['preset']['name']}（{rc['machine']['name']}・{rc['filament']['name']}）")
    stl = SP.BUILD / f"{STEM}.stl"
    newest = max(q.stat().st_mtime for q in SP.PROJECT.glob("*.py"))
    if not stl.exists() or stl.stat().st_mtime < newest:
        print(f"NG {STEM}: STL が無いか、生成器より古い（click_cover_snap.py を回し直す）")
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
    # 検査器が生きている: 見る点を左右に 0.6 ずらす（隙の真ん中 → 腕や胴の上）と「埋まっている」と言う
    dead = not any("埋まって" in q for q in check(gcode, rc, shift=(0.6, 0.0))[0])
    problems += more + [f"警告: {w}" for w in warns] + (["隙の検査が、ずらした点でも合格した（検査器が死んでいる）"] if dead else [])
    print(f"{'NG' if problems else 'OK'} {STEM}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
          f"材料 {cm3} cm3（{grams.group(1) if grams else round(float(cm3) * 1.24, 1)} g）・層 {info.get('層数')}・"
          f"設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}・{SP.cfg_generator(text)}")
    for k, v in facts.items():
        print(f"     {k}: {v}")
    for q in problems:
        print(f"     NG {q}")
    print("     絵", draw(gcode, rc, SP.BUILD / "slice_cover_snap.png"))
    made = gcode.parent / f"{STEM}.gcode.3mf"
    if engine == "bambu" and not problems and made.exists():
        shutil.copyfile(made, dst)
        print(f"     刷るファイル {dst}（{dst.stat().st_size} バイト）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
