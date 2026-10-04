"""蓋の別案 S の試し刷り（coupon_cover_slide_plate = S の枠の角・当て板・電池の代わり・蓋 3 つ）を精度優先の設定で**実際にスライスし**、
G-code を設計と突き合わせる。

    .venv/bin/python3 projects/cckb-click/click_cover_slide.py           # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_cover_slide.py     # 0.4 ノズル・Bambu Studio → build/cckb-click/coupon_cover_slide_plate_n04.gcode.3mf

スライスの仕方は tools/slice_precise.py（設定の継承をたどる・回さずベッドの真ん中に置く・G-code の設定の欄と突き合わせる）。支えは付けない。
**刷り方を 1 つだけ変える: 橋の向き（bridge_angle）を 90°（板の前後）に固定する。**自動のままだと、板ばねの溝の底の橋が、溝の長い方（左右 9 mm）へ
渡る（左の端は空洞に面していて、支える物が無い。2026-10-05 に G-code で見た）。この板の橋は、溝の底と右の空洞の底だけで、どちらも前後に渡すのが短い
（ほかに橋の線が出る層も数える: 中の詰め物の上の最初の詰まった層と、入の印の天井 = 向きが変わっても困らない所）。
G-code から確かめること（1 つでも外れたら NG・刷るファイルを置かない）:
  1. 設定が効いている・警告 0・支えの線が 1 本も無い
  2. 枠の板ばね（上面をベッドに刷るので、ベッドから立つ板）が、まわりから離れた線になっている: 手前の切れ目・奥の空き・当ての通る所の真ん中に、
     1 層目でも中ほどの層でも線が無い。板ばねの胴と鼻には線がある
  3. **板ばねの溝の底（刷るときは橋）**: 板ばねの上の端と底の間の層には、板ばねの上に線が無い（付かない）。底の最初の層は、溝の上を渡る線で、
     渡る向きが溝の短い方（前後）。右の空洞の底も同じ
  4. つぶれる筋（枠の斜面の細い畝）が線になっている（筋のある x では線があり、無い x では無い）
  5. 蓋の当て（幅 0.7 の縦の板）が、1 層目から上まで線になっている
絵: build/cckb-click/slice_cover_slide.png（見ること）。
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

STEM = "coupon_cover_slide_plate"
GAP_CLEAR = 0.3              # 空いているはずの所の真ん中から、いちばん近い線の中心まで
ON_LINE = 0.3                # 線があるはずの所から、いちばん近い線の中心まで


def nearest(layer, x, y):
    """点から、その層の線（中心線）までのいちばん短い距離と、その線の (種類, 向き: 0 = x に沿う〜90 = y に沿う)。"""
    best = (99.0, "", 0.0)
    for lp in layer:
        for (ax, ay), (bx, by) in zip(lp["pts"], lp["pts"][1:]):
            dx, dy = bx - ax, by - ay
            n2 = dx * dx + dy * dy
            k = 0.0 if n2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / n2))
            d = math.hypot(x - ax - k * dx, y - ay - k * dy)
            if d < best[0]:
                best = (d, lp["feat"], math.degrees(math.atan2(abs(dy), abs(dx))) if n2 > 1e-12 else 0.0)
    return best


def layer_at(layers, z):
    """高さ z を含む層（層の上面の高さ）。"""
    zs = sorted(layers)
    return next((q for q in zs if q >= z - 1e-6), zs[-1])


def check(gcode, rc, shift=(0.0, 0.0)):
    """返り値 (問題, 測った数)。shift = 見る点をずらす（検査器が生きているかを見る）。"""
    import click_cover_slide as K

    problems, facts = [], {}
    layers = SV.read_loops(gcode)
    pb = K.plate().bounding_box()
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2 + shift[0]
    oy = max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2 + shift[1]
    fns = {name: fn for name, _, fn in K.plate_layout()}
    feats = sorted({lp["feat"] for loops in layers.values() for lp in loops})
    facts["線の種類"] = feats
    if any("support" in f.lower() for f in feats):
        problems.append(f"支えの線がある: {feats}")

    def at(name, x, y, z):
        p = fns[name]((x, y, z))
        zl = layer_at(layers, p[2])
        d, feat, ang = nearest(layers[zl], p[0] + ox, p[1] + oy)
        return round(d, 3), feat, round(ang), zl

    f = "frame"
    xm = K.XLANE + (K.XTIP + K.LEAF_L - K.XLANE) / 2                      # 板ばねの中ほど（爪を入れる所より右）
    xl = (K.CAV[1] + K.XLANE) / 2 + 0.6                                    # 当ての通る所（鼻より右）
    yleaf = (K.LEAF_Y[0] + K.LEAF_Y[1]) / 2
    # 2. 板ばねが離れている（1 層目 = 組んだ高さ TOP − 0.1・中ほど = TOP − 0.7）
    for z in (K.TOP - 0.1, K.TOP - 0.7):
        gaps = {"手前の切れ目": (xm, K.LEAF_Y[0] - K.LEAF_SLIT / 2), "奥の空き": (xm, K.LEAF_Y[1] + K.LEAF_ROOM / 2),
                "当ての通る所": (xl, (K.TRENCH[0] + K.LEAF_Y[0]) / 2), "鼻の手前": (K.XTIP + K.NOSE[0] / 2, (K.TRENCH[0] + K.NOSE_Y) / 2),
                "先の左（空洞）": (K.XTIP - 0.6, yleaf)}
        for label, (x, y) in gaps.items():
            d, feat, _, zl = at(f, x, y, z)
            facts[f"枠: {label}の真ん中から線まで（層 {zl}）"] = d
            if d < GAP_CLEAR:
                problems.append(f"枠: {label}が線で埋まっている（層 {zl}・{d}・{GAP_CLEAR} 以上）")
        for label, (x, y) in {"板ばねの胴": (xm, yleaf), "鼻": (K.XTIP + K.NOSE[0] / 2, (K.NOSE_Y + K.LEAF_Y[0]) / 2 + 0.1)}.items():
            d, feat, _, zl = at(f, x, y, z - (0.35 if label == "鼻" else 0.0))            # 鼻の上の縁は斜めに落としてある
            facts[f"枠: {label}の真ん中から線まで（層 {zl}）"] = d
            if d > ON_LINE:
                problems.append(f"枠: {label}の所に線が無い（層 {zl}・{d}）")
    # 3. 溝の底（橋）。板ばねの上の端（組んだ高さ LEAF_Z）と底（TRENCH_Z）の間は、板ばねの上に線が無い
    z = K.LEAF_Z - 0.05
    while z > K.TRENCH_Z + 0.01:
        d, feat, _, zl = at(f, xm, yleaf, z)
        facts[f"枠: 板ばねと溝の底の間（層 {zl}）の、板ばねの上から線まで"] = d
        if d < GAP_CLEAR:
            problems.append(f"枠: 板ばねの上（層 {zl}）に線がある（{d}）= 溝の底と付く")
        z -= 0.1
    spans = {"板ばねの溝の底・奥の空きの上": (xm, K.LEAF_Y[1] + K.LEAF_ROOM / 2, K.TRENCH_Z - 0.05),
             "板ばねの溝の底・板ばねの上": (xm, yleaf, K.TRENCH_Z - 0.05),
             "板ばねの溝の底・当ての通る所の上": (xl, K.LEAF_Y[0] - 0.3, K.TRENCH_Z - 0.05),          # 溝の縁（橋の線の折り返し）から離す
             "右の空洞の底": ((K.XRE + K.CL + K.CAV[1]) / 2, (K.YLR + K.YC) / 2, K.FLOOR_T - 0.05)}
    for label, (x, y, zz) in spans.items():
        d, feat, ang, zl = at(f, x, y, zz)
        facts[f"枠: {label}（層 {zl}）: 線まで・種類・向き"] = (d, feat, ang)
        if d > ON_LINE:
            problems.append(f"枠: {label}の最初の層（{zl}）に線が無い（{d}）")
        elif not any(q in feat.lower() for q in ("bridge", "overhang")):
            problems.append(f"枠: {label}の最初の層（{zl}）が、宙を渡る線（Bridge・Overhang wall）でない（{feat}）")
        elif ang < 45:
            problems.append(f"枠: {label}の橋が、長い方（左右）へ渡っている（向き {ang}°）")
    # 橋の線のある層（**橋の向きを固定したので、ほかの橋も向きが変わる**。2026-10-05 に見た中身: 当て板・枠・電池の代わりの、中の詰め物の上の
    # 最初の詰まった層〔宙ではない〕と、入の印〔φ1.2 の点〕の天井。宙を 2 mm 以上渡る橋は、溝の底と右の空洞の底だけ）
    a, b = fns[f]((K.A1, K.Y0, 0.0)), fns[f]((K.XTIP + K.LEAF_L + 0.5, K.YC + 2.5, 0.0))        # 橋の線は、溝の奥の壁の上へ 2 mm ほど伸びて掛かる
    box = (min(a[0], b[0]) + ox, min(a[1], b[1]) + oy, max(a[0], b[0]) + ox, max(a[1], b[1]) + oy)
    inside, outside = set(), set()
    for zq, loops in layers.items():
        for lp in loops:
            if "bridge" in lp["feat"].lower():
                (inside if any(box[0] <= px <= box[2] and box[1] <= py <= box[3] for px, py in lp["pts"]) else outside).add(zq)
    facts["橋の線のある層: 板ばねの溝と右の空洞／その外（中の詰め物の上・入の印）"] = (sorted(inside), sorted(outside))
    want = {layer_at(layers, fns[f]((0, 0, K.TRENCH_Z - 0.05))[2]), layer_at(layers, fns[f]((0, 0, K.FLOOR_T - 0.05))[2])}
    if not want <= inside:
        problems.append(f"板ばねの溝の底・右の空洞の底の層 {sorted(want)} に、橋の線が無い（{sorted(inside)}）")
    # 4. つぶれる筋
    ym = (K.YH + K.YT) / 2
    k = K.RIDGE[0] / math.sqrt(2.0)
    zr = K.roof_z(ym) - k * 0.5                                                 # 筋の高さの半分の所
    yr = ym - k * 0.5 - 0.05
    for side, (x0, x1), x_off in (("左", K.RIDGE_X["left"], K.P0 - 0.25), ("右", K.RIDGE_X["right"], K.HEAD[1] - 0.2)):
        d_on = at(f, (x0 + x1) / 2 - 0.1, yr, zr)
        d_off = at(f, x_off, yr, zr)
        facts[f"枠: {side}のつぶれる筋（層 {d_on[3]}）: 筋の所の線まで・筋の無い所の線まで"] = (d_on[0], d_off[0])
        if d_on[0] > 0.25:
            problems.append(f"枠: {side}のつぶれる筋が線になっていない（{d_on[0]}）")
        if d_off[0] < 0.3:
            problems.append(f"枠: {side}の、筋の無い所にも線がある（{d_off[0]}）= 見る点が筋を見ていない")
    # 5. 蓋の当て
    for n in sorted(K.VARIANTS):
        for z in (K.TOP - 0.1, K.TOP - 0.8, K.RIB_Z + K.CAM[1] + 0.15):
            d, feat, _, zl = at(f"cover{n}", K.XRE + K.SLIDE - 0.5, (K.RIB_Y[0] + K.RIB_Y[1]) / 2, z)
            facts[f"蓋 {n}: 当ての真ん中から線まで（層 {zl}）"] = d
            if d > ON_LINE:
                problems.append(f"蓋 {n}: 当てが線になっていない（層 {zl}・{d}）")
    return problems, facts


def draw(gcode, rc, out):
    """枠の板ばねのまわりと蓋 1 つの、1 層目・中ほどの層・溝の底の最初の層の線（見る絵）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import click_cover_slide as K

    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    layers = SV.read_loops(gcode)
    pb = K.plate().bounding_box()
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    ox = max(p[0] for p in area) / 2 - (pb.min.X + pb.max.X) / 2
    oy = max(p[1] for p in area) / 2 - (pb.min.Y + pb.max.Y) / 2
    fns = {name: fn for name, _, fn in K.plate_layout()}
    fn = fns["frame"]
    a, b = fn((K.A1 - 3.0, K.Y0, 0)), fn((K.XTIP + K.LEAF_L + 1.5, K.YC + 1.0, 0))
    win = (min(a[0], b[0]) + ox, max(a[0], b[0]) + ox, min(a[1], b[1]) + oy, max(a[1], b[1]) + oy)
    col = {"bridge": "#c00000", "outer": "#c05a10", "inner": "#d09040"}
    shots = [("1 層目（枠の上面）", K.TOP - 0.1), ("板ばねの中ほど", K.TOP - 0.7), ("板ばねと溝の底の間", K.LEAF_Z - 0.25),
             ("溝の底の最初の層（橋）", K.TRENCH_Z - 0.05), ("右の空洞の底の最初の層（橋）", K.FLOOR_T - 0.05)]
    fig, axs = plt.subplots(len(shots), 1, figsize=(15, 4.4 * len(shots)))
    for ax, (title, z) in zip(axs, shots):
        zl = layer_at(layers, fn((0, 0, z))[2])
        for lp in layers[zl]:
            xs, ys = zip(*lp["pts"])
            c = next((v for k, v in col.items() if k in lp["feat"].lower()), "#909090")
            ax.plot(xs, ys, "-", color=c, lw=1.2)
        ax.set_xlim(win[0], win[1])
        ax.set_ylim(win[2], win[3])
        ax.set_aspect("equal")
        ax.set_title(f"枠の右の口のまわり・{title}（層の上面 {zl}。組んだ高さ {z:.2f}）。赤 = 橋の線・橙 = 外周・灰 = 中", fontsize=11)
    fig.suptitle("蓋の別案 S の G-code（Bambu Studio）: 枠は上面が下。上が手前（枠の外面）・左右は組んだ向きと同じ", fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=90)
    plt.close(fig)
    return out


def main(argv):
    engine = next((a for a in argv if a in ("bambu", "orca")), "bambu")
    variant = next((a for a in argv if a in SP.S.PRINT_RECIPES), "n04")
    rc = SP.recipe(variant, SP.S, engine)
    for part in ("process", "overrides"):                 # 橋の向きを板の前後に固定（上の説明）。G-code の設定の欄とも突き合わせる
        rc[part]["bridge_angle"] = "90"
    print(f"== {variant}・{engine}: {rc['preset']['name']}（{rc['machine']['name']}・{rc['filament']['name']}）")
    stl = SP.BUILD / f"{STEM}.stl"
    newest = max(q.stat().st_mtime for q in SP.PROJECT.glob("*.py"))
    if not stl.exists() or stl.stat().st_mtime < newest:
        print(f"NG {STEM}: STL が無いか、生成器より古い（click_cover_slide.py を回し直す）")
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
    # 検査器が生きている: 見る点を前後に 0.7 ずらす（切れ目の真ん中 → 板ばねの上）と「埋まっている」と言う
    dead = not any("埋まって" in q for q in check(gcode, rc, shift=(0.0, 0.7))[0])
    problems += more + [f"警告: {w}" for w in warns] + (["切れ目の検査が、ずらした点でも合格した（検査器が死んでいる）"] if dead else [])
    print(f"{'NG' if problems else 'OK'} {STEM}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
          f"材料 {cm3} cm3（{grams.group(1) if grams else round(float(cm3) * 1.24, 1)} g）・層 {info.get('層数')}・"
          f"設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}・{SP.cfg_generator(text)}")
    for k, v in facts.items():
        print(f"     {k}: {v}")
    for q in problems:
        print(f"     NG {q}")
    print("     絵", draw(gcode, rc, SP.BUILD / "slice_cover_slide.png"))
    made = gcode.parent / f"{STEM}.gcode.3mf"
    if engine == "bambu" and not problems and made.exists():
        shutil.copyfile(made, dst)
        print(f"     刷るファイル {dst}（{dst.stat().st_size} バイト）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
