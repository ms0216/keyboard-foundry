"""落とし込み式の蓋の試し刷り（coupon_corner_plate = 枠の角・当て板・電池とつまみの代わり・蓋 3 つ）と、本番の蓋（cover_battery）を
精度優先の設定で**実際にスライスし**、G-code を設計と突き合わせる。

    .venv/bin/python3 projects/cckb-click/click_case.py               # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_cover.py        # 0.4 ノズル・Bambu Studio → build/cckb-click/coupon_corner_plate_n04.gcode.3mf

スライスの仕方は tools/slice_precise.py（設定の継承をたどる・回さずベッドの真ん中に置く・G-code の設定の欄と突き合わせる）。
G-code から確かめること（1 つでも外れたら NG・刷るファイルを置かない）:
  1. 設定が効いている・警告 0
  2. 蓋の**棒（板ばね）が、まわりから離れた線になっている**（蓋は手前の面をベッドに刷る。切れ目の幅は 0.4 = 線 1 本ぶん）:
     - 切れ目 3 本（下の帯と下の棒の間・棒と棒の間・上の棒と上の帯の間）の真ん中に、1 層目でも中ほどの層でも線が無い（線の中心まで 0.3 以上）
     - 棒の真ん中には線がある
     - 棒の厚さより上の層では、棒のあった所に線が無い（棒は厚さぶんで終わる = 奥へ撓める）
     - 棒の先の下の、硬い受けとの隙（0.2 = いちばん狭い切れ目）にも線が無い
絵: build/cckb-click/slice_cover.png（蓋 3 つの 1 層目と中ほどの層の線。見ること）。
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
SLIT_CLEAR = 0.3            # 切れ目の真ん中から、いちばん近い線の中心まで（切れ目 0.4 の半分 ＋ 線の幅 0.42 の半分 = 0.41 が設計）
REST_CLEAR = 0.24           # 棒の先の下の受けとの隙 0.2 の真ん中から（0.1 ＋ 0.21 = 0.31 が設計。1 層目は面取りで広い）


def covers(stem):
    """(板の外接, {名前: (刷る向きの蓋の外接, 蓋の番号)})。板の座標。"""
    import click_case as C

    if stem == "cover_battery":
        plate = C.printables()["cover_battery"]                             # 予備を含めて COVER_SPARE 個
        return plate.bounding_box(), {f"cover{i + 1}of{C.S.COVER_SPARE}": (q.bounding_box(), C.S.COVER_MAIN)
                                      for i, q in enumerate(sorted(plate.solids(), key=lambda q: q.bounding_box().min.Y))}
    layout = dict(C.corner_coupon_layout())
    return C.corner_coupon_plate().bounding_box(), {n: (p.bounding_box(), int(n[-1])) for n, p in layout.items() if n.startswith("cover")}


def probes(bb, n):
    """蓋の上の、見る点 {名前: (x, y)}（板の座標）。蓋は手前の面をベッドに置いてある: 板の y = 蓋の外接の奥の端 − 組んだ向きの高さ。
    x は、2 本の棒が重なる真ん中。"""
    import click_case as C

    cv = C.LAY.cover(n)
    x = (bb.min.X + bb.max.X) / 2
    at = lambda z: (x, bb.max.Y - z)                                    # noqa: E731
    (a0, a1), (b0, b1) = cv["band"]["A"], cv["band"]["B"]
    return dict(slit={"下の帯と下の棒の間": at((cv["z_sill"][1] + a0) / 2), "棒と棒の間": at((a1 + b0) / 2), "上の棒と上の帯の間": at((b1 + cv["z_strip"]) / 2)},
                leaf={"下の棒": at((a0 + a1) / 2), "上の棒": at((b0 + b1) / 2)}, t=cv["t"], b=a1 - a0,
                # 棒の先の下の受けとの隙（COVER_TIP_REST 0.2 = いちばん狭い切れ目）: 右は下の棒の下・左は上の棒の下
                rest={"下の棒の先の下（右）": (bb.max.X - 5.0, bb.max.Y - (a0 - C.S.COVER_TIP_REST / 2)),
                      "上の棒の先の下（左）": (bb.min.X + 5.0, bb.max.Y - (b0 - C.S.COVER_TIP_REST / 2))})


def nearest(layer, x, y):
    """点 (x, y) から、その層の線（中心線）までのいちばん短い距離。"""
    best = 99.0
    for lp in layer:
        for (ax, ay), (bx, by) in zip(lp["pts"], lp["pts"][1:]):
            dx, dy = bx - ax, by - ay
            n2 = dx * dx + dy * dy
            k = 0.0 if n2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / n2))
            best = min(best, math.hypot(x - ax - k * dx, y - ay - k * dy))
    return best


def offset(rc, pb):
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    return max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2, max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2


def check(stem, gcode, rc, slit_clear=SLIT_CLEAR, shift=(0.0, 0.0)):
    problems, facts = [], {}
    layers = SV.read_loops(gcode)
    pb, cov = covers(stem)
    ox, oy = offset(rc, pb)
    ox, oy = ox + shift[0], oy + shift[1]
    zs = sorted(layers)
    for name, (bb, n) in sorted(cov.items()):
        pr = probes(bb, n)
        low = zs[0]
        mid = min(zs, key=lambda z: abs(z - pr["t"] / 2))
        above = min(zs, key=lambda z: abs(z - (pr["t"] + 0.35)))
        for label, (x, y) in pr["slit"].items():
            d = {z: round(nearest(layers[z], x + ox, y + oy), 3) for z in (low, mid)}
            facts[f"{name}: 切れ目（{label}）の真ん中から線まで（z {low}・{mid}）"] = tuple(d.values())
            if min(d.values()) < slit_clear:
                problems.append(f"{name}: 切れ目（{label}）が線で埋まっている {d}（{slit_clear} 以上）")
        for label, (x, y) in pr["rest"].items():
            d = {z: round(nearest(layers[z], x + ox, y + oy), 3) for z in (low, mid)}
            facts[f"{name}: {label}の隙の真ん中から線まで（z {low}・{mid}）"] = tuple(d.values())
            if min(d.values()) < REST_CLEAR:
                problems.append(f"{name}: {label}の隙（0.2）が線で埋まっている {d}（{REST_CLEAR} 以上）")
        for label, (x, y) in pr["leaf"].items():
            d_in, d_up = round(nearest(layers[mid], x + ox, y + oy), 3), round(nearest(layers[above], x + ox, y + oy), 3)
            facts[f"{name}: {label}の真ん中から線まで（z {mid}・棒より上の z {above}）"] = (d_in, d_up)
            if d_in > pr["b"] / 2 - 0.15:                       # 棒の中（縁から 0.15 より内）に、線の中心が 1 本はある
                problems.append(f"{name}: {label}の所に線が無い（z {mid}・{d_in}・棒の高さ {pr['b']:.1f}）")
            if d_up < 0.5:
                problems.append(f"{name}: {label}が厚さ {pr['t']} より上の層（z {above}）にもある（{d_up}）= 奥へ撓めない")
    return problems, facts


def draw(gcode, rc, out):
    """蓋 3 つの、1 層目と中ほどの層の線（見る絵）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    layers = SV.read_loops(gcode)
    pb, cov = covers("coupon_corner_plate")
    ox, oy = offset(rc, pb)
    zs = sorted(layers)
    fig, axs = plt.subplots(len(cov), 2, figsize=(16, 3.6 * len(cov)))
    for row, (name, (bb, n)) in zip(axs, sorted(cov.items())):
        pr = probes(bb, n)
        for ax, z, title in ((row[0], zs[0], "1 層目"), (row[1], min(zs, key=lambda q: abs(q - pr["t"] / 2)), "棒の厚さの中ほどの層")):
            for lp in layers[z]:
                xs, ys = zip(*lp["pts"])
                ax.plot(xs, ys, "-", color="#c05a10", lw=1.4)
            for (x, y) in pr["slit"].values():
                ax.plot(x + ox, y + oy, "x", color="#0050c0", ms=7)
            ax.set_xlim(bb.min.X + ox - 1, bb.max.X + ox + 1)
            ax.set_ylim(bb.min.Y + oy - 0.8, bb.max.Y + oy + 0.8)
            ax.set_aspect("equal")
            ax.set_title(f"蓋 {n}（棒の厚さ {pr['t']}）・{title}（z {z}）。橙 = 線の中心・青の × = 切れ目の真ん中（線が通っていないこと）", fontsize=10)
    fig.suptitle("蓋の試し刷りの G-code（Bambu Studio）: 蓋は手前の面が下。下の縁 = 蓋の上面・上の縁 = 基板の側", fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=90)
    plt.close(fig)
    return out


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
        # 検査器が生きている: 見る点を 0.6 ずらす（= 棒の上）と「埋まっている」と言う
        dead = not any("埋まって" in q for q in check(stem, gcode, rc, shift=(0.0, 0.6))[0])
        problems += more + [f"警告: {w}" for w in warns] + (["切れ目の検査が、ずらした点でも合格した（検査器が死んでいる）"] if dead else [])
        bad += len(problems)
        print(f"{'NG' if problems else 'OK'} {stem}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
              f"材料 {cm3} cm3（約 {round(float(cm3) * SM.PLA, 1) if cm3 else '?'} g）・層 {info.get('層数')}・"
              f"設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}・{SP.cfg_generator(text)}")
        for k, v in facts.items():
            print(f"     {k}: {v}")
        for q in problems:
            print(f"     NG {q}")
        if stem == "coupon_corner_plate":
            print("     絵", draw(gcode, rc, SP.BUILD / "slice_cover.png"))
        made = gcode.parent / f"{stem}.gcode.3mf"
        if engine == "bambu" and not problems and made.exists():
            shutil.copyfile(made, dst)
            print(f"     刷るファイル {dst}（{dst.stat().st_size} バイト）")
    print("NG" if bad else "OK", f"問題 {bad} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
