"""精度優先の刷り方（print/ のプリセット）で実際にスライスし、**設定が効いたか・狙いが線になったか**を G-code から確かめる。

    .venv/bin/python3 projects/cckb-click/tools/slice_precise.py              # 最小の一式（coupon_min_plate）を n04 と n02 で
    .venv/bin/python3 projects/cckb-click/tools/slice_precise.py n04 --all    # coupon_*.stl を全部（時間と材料の表）

スライサーは 2 つ通す: **Bambu Studio**（利用者が刷るときに使う物。あれば）と OrcaSlicer（このリポジトリの検査が使う物）。
継ぎ目の置き方はスライサーごとに違いうるので、両方の G-code で数える。Bambu Studio で切った物を
build/cckb-click/coupon_min_plate_<n04|n02>.gcode.3mf に置く（**検査したその G-code を刷れる**）。

なぜ foundry.slice_check を使わないか: OrcaSlicer の CLI は**設定の継承（inherits）をたどらない**。Bambu の設定ファイルは
ほとんどの値を親に持つので、そのまま渡すと OrcaSlicer の既定値（外周 60 mm/s・線幅 自動・ノズル 200℃・Arachne）で切られる
（2026-10-03 に G-code の設定の欄で確かめた）。ここでは親を自分でたどって 1 枚にしてから渡し、**G-code の設定の欄と突き合わせる**。

確かめること（1 つでも外れたら NG）:
  1. プリセットに書いた値と、土台の設定から継いだ主な値が、G-code の設定の欄に同じ値で出ている
  2. 機能する面の高さ（つばの上面・キャップの上面・くぼみの底・枠の下面・柱の先・台の上面）が、実際の層の境目にある
  3. キャップ・枠の穴の外周の「継ぎ目（線の始まり）」が、滑る面に無い。許す場所は 継ぎ目の溝の中・つばの付け根の入隅（くぼみの空間に向く）・
     くぼみの入隅 だけ
  4. 1 層目の外の縁が、胴・穴の面より内側（外側）に引っ込んでいる（1 層目の太りの逃げ）
絵: build/cckb-click/slice_<n04|n02>.png（見ること。Bambu Studio があればその G-code、無ければ OrcaSlicer）。
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ROOT = PROJECT.parents[1]
for p in (str(PROJECT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from foundry import paths  # noqa: E402
from foundry.project import load  # noqa: E402
from foundry.slice_check import find_binary, summarize_gcode  # noqa: E402

S = load(PROJECT).spec
BUILD = paths.BUILD / PROJECT.name
OUT = BUILD / "slice_precise"
VENDOR = "BBL"
BAMBU = Path(os.environ.get("BAMBU_STUDIO") or "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio")


def engines():
    """使えるスライサー（名前 → 実行ファイル）。Bambu Studio を先に（絵と .gcode.3mf はこれで作る）。"""
    out = {}
    if BAMBU.exists():
        out["bambu"] = BAMBU
    out["orca"] = find_binary()
    return out


def profile_root(binary):
    return binary.parent.parent / "Resources" / "profiles" / VENDOR
# プリセットの中で、スライサーの設定ではない欄（プリセットの管理用）
META = {"type", "name", "from", "inherits", "version", "print_settings_id", "setting_id", "instantiation", "description",
        "compatible_printers", "is_custom_defined"}
# 土台の設定から継ぐ値のうち、効いたことを G-code で確かめる物（CLI が継承をたどらないと既定値に化ける）
INHERITED = ("outer_wall_speed", "outer_wall_acceleration", "outer_wall_line_width", "initial_layer_line_width",
             "initial_layer_print_height", "enable_arc_fitting", "sparse_infill_density")


def flatten(kind, name, root):
    """設定を親までたどって 1 枚にする（子が親を上書き）。返り値 (設定, たどった名前)。
    Bambu Studio の機械の設定は G-code の雛形を別ファイル（include）に持つので、それも取り込む。"""
    index = {p.stem: p for p in (root / kind).glob("*.json")}
    out, chain = {}, []

    def rec(n):
        d = json.loads(index[n].read_text())
        if d.get("inherits"):
            rec(d["inherits"])
        chain.append(n)
        out.update(d)

    rec(name)
    out["inherits"] = ""
    for inc in out.pop("include", []):
        out.update({k: v for k, v in json.loads(index[inc].read_text()).items() if k.endswith("gcode")})
    return out, chain


def recipe(variant, s=S, engine=None):
    """刷り方 1 つ: プリセット（print/*.json）と、その土台・プリンタ・フィラメントを 1 枚ずつにした設定。
    土台はそのスライサーに同梱の Bambu の設定から取る（engine = スライサーの名前。None = OrcaSlicer）。"""
    engine = engine or "orca"
    binary = engines()[engine]
    root = profile_root(binary)
    r = s.PRINT_RECIPES[variant]
    preset = json.loads((PROJECT / r["process"]).read_text())
    process, chain = flatten("process", preset["inherits"], root)
    overrides = {k: v for k, v in preset.items() if k not in META}
    process.update(overrides)
    process["name"] = process["print_settings_id"] = preset["name"]
    machine, _ = flatten("machine", r["machine"], root)
    filament, _ = flatten("filament", r["filament"], root)
    return dict(variant=variant, engine=engine, binary=binary, preset=preset, overrides=overrides, process=process, machine=machine, filament=filament,
                base=chain[-1])


def _plain(v):
    """設定の値を G-code の欄の書き方に寄せる（["0.42"] → 0.42・"15%" はそのまま）。"""
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v).strip().strip('"')


def _same(a, b):
    a, b = _plain(a), _plain(b)
    try:
        return abs(float(a) - float(b)) < 1e-9
    except ValueError:
        return a == b


def gcode_config(text):
    """G-code の末尾の設定の欄（; key = value）。"""
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^; ([a-z_0-9]+) = (.*)$", text, re.M)}


def slice_stl(rc, stl, out=OUT):
    """1 つの STL をスライスする。返り値 (G-code の場所 or None, 出力の文字)。スライスした .gcode.3mf も同じ場所に出す。"""
    outdir = out / rc["engine"] / rc["variant"] / stl.stem
    outdir.mkdir(parents=True, exist_ok=True)
    for old in list(outdir.glob("*.gcode")) + list(outdir.glob("*.3mf")):
        old.unlink()                                  # 前の G-code を成功と見間違えない
    files = {}
    for kind in ("machine", "process", "filament"):
        files[kind] = outdir / f"{kind}.json"
        files[kind].write_text(json.dumps(rc[kind], indent=1, ensure_ascii=False))
    # ベッドの真ん中へ自分で動かしてから、自動配置なしで渡す。**CLI の自動配置は物を回すことがある**（2026-10-03: 180° 回り、
    # 「継ぎ目は奥」の奥が逆になった）。画面から読み込むと回さずに真ん中へ置かれるので、それと同じ向きにする
    import trimesh

    mesh = trimesh.load(str(stl))
    area = [tuple(float(v) for v in p.split("x")) for p in rc["machine"]["printable_area"]]
    bx, by = max(p[0] for p in area), max(p[1] for p in area)
    c = (mesh.bounds[0] + mesh.bounds[1]) / 2
    mesh.apply_translation([bx / 2 - c[0], by / 2 - c[1], -mesh.bounds[0][2]])
    placed = outdir / f"{stl.stem}.stl"
    mesh.export(str(placed))
    cmd = [str(rc["binary"]), "--load-settings", f"{files['machine']};{files['process']}",
           "--load-filaments", str(files["filament"]), "--orient", "0", "--arrange", "0",
           "--slice", "0", "--outputdir", str(outdir), "--export-3mf", f"{stl.stem}.gcode.3mf", str(placed)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=outdir)
    gcodes = sorted(outdir.glob("*.gcode"))
    return (gcodes[-1] if r.returncode == 0 and gcodes else None), (r.stdout or "") + (r.stderr or "")


def applied_problems(rc, cfg):
    """プリセットの値と、継いだ主な値が G-code の設定の欄に出ているか。"""
    out = []
    want = dict(rc["overrides"])
    want.update({k: rc["process"][k] for k in INHERITED})
    want["nozzle_diameter"] = rc["machine"]["nozzle_diameter"]
    want["nozzle_temperature"] = rc["filament"]["nozzle_temperature"]
    for k, v in sorted(want.items()):
        if k not in cfg:
            out.append(f"{k}: G-code の設定の欄に無い（このスライサーが知らない設定）")
        elif not _same(cfg[k], v):
            out.append(f"{k}: プリセット {_plain(v)} ≠ G-code {cfg[k]}")
    return out, len(want)


# ---------------------------------------------------------------------------
# G-code を読む
# ---------------------------------------------------------------------------

NUM = re.compile(r"([XYZEIJF])(-?\d*\.?\d+)")


def read_layers(gcode):
    """層の上面の高さ → [輪]。輪 = dict(feat, width, pts=[(x, y), ...])（切れ目なく押し出した 1 続き）。
    円弧（G2 / G3）は端点だけを取る（継ぎ目と外接を見るには足りる）。"""
    layers, z, feat, width = {}, None, "", None
    x = y = None
    cur = None
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
                cur = dict(feat=feat, width=width, pts=[(x, y)])
                layers.setdefault(z, []).append(cur)
            cur["pts"].append((nx, ny))
        elif moved:
            cur = None                                # 空走り = 輪の切れ目
        x, y = nx, ny
    return layers


def bbox(loops):
    xs = [p[0] for lp in loops for p in lp["pts"]]
    ys = [p[1] for lp in loops for p in lp["pts"]]
    return min(xs), min(ys), max(xs), max(ys)


def outer(layer):
    return [lp for lp in layer if lp["feat"] == "Outer wall"]


# ---------------------------------------------------------------------------
# 最小の一式（coupon_min_plate）の中身と突き合わせる
# ---------------------------------------------------------------------------

def plate_model(s=S):
    """1 枚に並べた立体の、設計の位置（STL の座標）。キャップの中心・穴の中心（枠は裏返っている）・全体の外接。"""
    import click_coupons as CC
    import click_parts as P

    cp = CC.coupons(s)["min"]
    built = CC.build(cp, s)
    parts = CC.print_parts("min", cp, built, s)
    placed = dict(CC.plate_layout(parts, "min"))
    bb = parts["coupon_min_plate"].bounding_box()
    caps = sorted((sol.bounding_box() for sol in placed["caps"].solids()), key=lambda b: b.min.X)
    fb = placed["frame"].bounding_box()
    raw = built["frame"].bounding_box()
    holes = []
    for c in cp.cells:                                # 裏返し（X 軸まわり）: x はそのまま、y は反転
        w, d = P.hole_size(c)
        holes.append(dict(cx=fb.min.X + (c.cx - raw.min.X), cy=fb.min.Y + (raw.max.Y - c.cy), w=w, d=d, dots=c.dots))
    body = P.body_plan(cp.cells[0], s).bounding_box().size
    hole0 = P.hole_size(cp.cells[0])                  # 穴を広げる前の穴（つば・くぼみの位置はこれで決まる）
    # notch_side: 穴の継ぎ目の溝は奥の壁。枠は裏返して刷るので、刷る向きでは手前（−Y）
    return dict(centre=((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2), size=(bb.size.X, bb.size.Y),
                caps=[dict(cx=(b.min.X + b.max.X) / 2, cy=(b.min.Y + b.max.Y) / 2) for b in caps[:len(cp.cells)]],
                body=(body.X, body.Y), holes=holes, hole0=hole0, notch_side=-1, frame=(fb.min.X, fb.min.Y, fb.max.X, fb.max.Y))


def heights_wanted(s=S):
    """最小の一式の、機能する面の高さ（刷る向き・ベッドから）。"""
    import click_parts as P

    h = dict(P.print_heights(s))
    h["台の上面"] = s.COUPON_BASE_T + s.SW_STEM_TOP
    h["板の上面"] = s.COUPON_BASE_T
    h["測る塊の上面"] = s.COUPON_GAUGE[1]
    return h


def analyse(gcode, rc, s=S):
    """最小の一式の G-code を設計と突き合わせる。返り値 (問題, 測った数, 絵に使う物)。"""
    raw = read_layers(gcode)
    zs = sorted(raw)
    m = plate_model(s)
    problems, facts = [], {}
    # スライスした物が設計と同じ向きか（slice_stl は回さずに置く）。キャップ 3 個の外周が設計の場所に見つかる向きを探し、0° でなければ NG
    ref = min(zs, key=lambda z: abs(z - (s.CAP_BOTTOM_CHAMFER + s.PRINT_LAYER)))
    gx0, gy0, gx1, gy1 = bbox(outer(raw[ref]))
    gcx, gcy = (gx0 + gx1) / 2, (gy0 + gy1) / 2
    turn, layers = None, None
    for k in range(4):
        co, si = round(math.cos(-k * math.pi / 2)), round(math.sin(-k * math.pi / 2))

        def back(p, co=co, si=si):
            dx, dy = p[0] - gcx, p[1] - gcy
            return (m["centre"][0] + co * dx - si * dy, m["centre"][1] + si * dx + co * dy)

        cand = [dict(lp, pts=[back(p) for p in lp["pts"]]) for lp in outer(raw[ref])]
        hit = sum(any(abs((b[0] + b[2]) / 2 - c["cx"]) < 0.3 and abs((b[1] + b[3]) / 2 - c["cy"]) < 0.3
                      for b in (bbox([lp]) for lp in cand)) for c in m["caps"])
        if hit == len(m["caps"]):
            turn = k * 90
            layers = {z: [dict(lp, pts=[back(p) for p in lp["pts"]]) for lp in raw[z]] for z in zs}
            break
    if layers is None:
        return ["スライスした物の置き方を設計と突き合わせられない（キャップが設計の場所に無い）"], facts, None
    if turn:
        problems.append(f"スライスした物が設計から {turn}° 回っている（「継ぎ目は奥」の奥が変わる）")
    # 置かれた場所: つばの面取りが終わった高さ（全部の物が設計の外形で出る層）の外周の外接の中心を、設計の中心に合わせる
    x0, y0, x1, y1 = bbox(outer(layers[ref]))
    ox = oy = 0.0                                     # layers はもう設計の座標
    w_out = rc_width(rc, "outer_wall_line_width")
    facts["外接（線の中心 ＋ 線の幅）"] = (x1 - x0 + w_out, y1 - y0 + w_out)
    if abs(x1 - x0 + w_out - m["size"][0]) > 0.15 or abs(y1 - y0 + w_out - m["size"][1]) > 0.15:
        problems.append(f"スライスした外接 {x1 - x0 + w_out:.2f} × {y1 - y0 + w_out:.2f} が設計 {m['size'][0]:.2f} × {m['size'][1]:.2f} と合わない")

    # 2. 層の境目
    missing = {k: v for k, v in heights_wanted(s).items() if not any(abs(z - v) < 1e-6 for z in zs)}
    facts["層"] = (len(zs), zs[0], round(zs[1] - zs[0], 3))
    if missing:
        problems.append(f"機能する面が層の境目に無い: {missing}")

    bw, bd = m["body"]
    first = s.PRINT_LAYER * 0 + zs[0]

    def near(lp, cx, cy, half):
        a = bbox([lp])
        return abs((a[0] + a[2]) / 2 - (cx + ox)) < 1.0 and abs((a[1] + a[3]) / 2 - (cy + oy)) < 1.0 and (a[2] - a[0]) / 2 > half

    seams = {"cap": [], "hole": []}
    cap_first, hole_first, cap_mid = [], [], []
    for z in zs:
        for lp in outer(layers[z]):
            for i, c in enumerate(m["caps"]):
                if near(lp, c["cx"], c["cy"], bw / 2 - 1.5):
                    sx, sy = lp["pts"][0][0] - ox - c["cx"], lp["pts"][0][1] - oy - c["cy"]
                    seams["cap"].append((i, z, sx, sy))
                    a = bbox([lp])
                    ext = ((a[2] - a[0]) + lp["width"], (a[3] - a[1]) + lp["width"])
                    if z == first:
                        cap_first.append(ext)
                    elif abs(z - 1.0) < 1e-6:          # つばより上・面取りより下 = 穴の中で滑る胴
                        cap_mid.append(ext + (lp["width"],))
            for i, h in enumerate(m["holes"]):
                if near(lp, h["cx"], h["cy"], h["w"] / 2 - 1.5) and not near(lp, h["cx"], h["cy"], h["w"] / 2 + 1.5):
                    sx, sy = lp["pts"][0][0] - ox - h["cx"], lp["pts"][0][1] - oy - h["cy"]
                    seams["hole"].append((i, z, sx, sy))
                    a = bbox([lp])
                    if z == first:
                        hole_first.append(((a[2] - a[0]) - lp["width"], h["w"]))
    # 3. 継ぎ目: 滑る面に無いこと。許す場所だけを数え、ほかは全部 NG
    nw, nd = s.SEAM_NOTCH if s.SEAM_NOTCH else (0.0, 0.0)
    hw0, hd0 = m["hole0"]
    pocket = s.TAB_REACH + s.POCKET_CLEAR
    tab_roots = [(sx * (hw0 / 2 - s.TAB_LEN), sy * bd / 2) for sx in (-1, 1) for sy in (-1, 1)] + \
                [(sx * bw / 2, sy * (hd0 / 2 - s.TAB_LEN)) for sx in (-1, 1) for sy in (-1, 1)]
    e = s.TAB_LEN + s.POCKET_CLEAR
    pocket_in = [(sx * (hw0 / 2 - e), sy * (hd0 / 2 + pocket)) for sx in (-1, 1) for sy in (-1, 1)] + \
                [(sx * (hw0 / 2 + pocket), sy * (hd0 / 2 - e)) for sx in (-1, 1) for sy in (-1, 1)]
    cap_h = heights_wanted(s)["キャップの上面"]
    z_pocket = s.FRAME_T - s.POCKET_DEPTH                # 刷る向きで、くぼみはこの高さから枠の下面まで

    def where(kind, i, z, sx, sy):
        if kind == "cap":
            if nw and abs(sx) <= nw / 2 + 0.6 and bd / 2 - nd - 0.6 <= sy <= bd / 2:
                return "溝"
            if z <= s.TAB_T + 1e-6 and min(math.hypot(sx - a, sy - b) for a, b in tab_roots) < 0.6:
                return "つばの付け根"
            # 上の縁の面取りの層は、外形が胴より内側にある。こぶ（大きくて 0.15）が胴の面まで出ない 0.2 以上引っ込んだ層だけ許す
            if (z - s.PRINT_LAYER / 2) - (cap_h - s.CAP_TOP_CHAMFER) >= 0.2 - 1e-6:
                return "上の面取りの層"
            return None
        hd = m["holes"][i]["d"]
        if nw and abs(sx) <= nw / 2 + 0.6 and hd / 2 - 0.6 <= m["notch_side"] * sy <= hd / 2 + nd + 0.6:
            return "溝"
        if z > z_pocket + 1e-6 and min(math.hypot(sx - a, sy - b) for a, b in pocket_in) < 0.6:
            return "くぼみの入隅"
        # 穴の上の縁（刷る向きではベッド側）の面取りの層は、穴の面より外にある。0.2 以上外にある層だけ許す
        if s.HOLE_CHAMFER - (z - zs[0] / 2 if z == zs[0] else z - s.PRINT_LAYER / 2) >= 0.2 - 1e-6:
            return "穴の縁の面取りの層"
        return None

    for kind in ("cap", "hole"):
        pts = seams[kind]
        tally = {}
        for q in pts:
            k = where(kind, *q)
            tally[k] = tally.get(k, 0) + 1
        bad = tally.pop(None, 0)
        facts[f"継ぎ目 {kind}"] = dict(全部=len(pts), 滑る面=bad, **tally)
        if not pts:
            problems.append(f"{kind}: 外周の輪が見つからない（突き合わせの位置がずれている）")
        elif bad:
            worst = [(round(q[2], 1), round(q[3], 1)) for q in pts if where(kind, *q) is None]
            problems.append(f"{kind}: 継ぎ目 {len(pts)} 個のうち {bad} 個が滑る面にある（例 {sorted(set(worst))[:4]}）")
    # 4. 1 層目の逃げ
    if cap_first and cap_mid:
        mid_x = sum(e[0] for e in cap_mid) / len(cap_mid)
        f_x = max(e[0] for e in cap_first)
        facts["キャップの胴（z=1.0 の外周の外寸・設計）"] = (round(mid_x, 3), round(bw, 3))
        facts["キャップの 1 層目の外寸（つば込み）"] = round(f_x, 3)
        if abs(mid_x - bw) > 0.02:
            problems.append(f"キャップの胴の外周の外寸 {mid_x:.3f} が設計 {bw:.3f} と違う")
    else:
        problems.append("キャップの 1 層目・胴の外周が見つからない")
    if hole_first:
        gaps = [(a - b) / 2 for a, b in hole_first]
        facts["枠の穴の 1 層目: 穴の面より外へ（片側）"] = round(min(gaps), 3)
        if min(gaps) < 0.15:
            problems.append(f"枠の穴の 1 層目が穴の面から {min(gaps):.2f} しか引っ込んでいない（太りが穴へ出る）")
    else:
        problems.append("枠の穴の 1 層目の外周が見つからない")
    return problems, facts, dict(layers=layers, model=m, offset=(ox, oy), seams=seams)


def rc_width(rc, key):
    return float(_plain(rc["process"][key]))


# ---------------------------------------------------------------------------
# 絵
# ---------------------------------------------------------------------------

def draw(rc, info, facts, summary, out, s=S):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    colors = {"Outer wall": "#c0392b", "Inner wall": "#e08e0b", "Gap infill": "#8e44ad"}
    layers, m, (ox, oy) = info["layers"], info["model"], info["offset"]
    zs = sorted(layers)
    lw = 72 * rc_width(rc, "outer_wall_line_width") / 25.4      # 線の幅を実寸で描く係数は下で窓に合わせる

    def at(z):
        return min(zs, key=lambda q: abs(q - z))

    def show(ax, z, win, title):
        z = at(z)
        scale = ax.get_figure().get_size_inches()[0] / 3 * 72 / (win[1] - win[0]) * 0.8     # 1 mm あたりの点（おおよそ）
        for lp in layers[z]:
            xs = [p[0] - ox for p in lp["pts"]]
            ys = [p[1] - oy for p in lp["pts"]]
            ax.plot(xs, ys, "-", color=colors.get(lp["feat"], "#95a5a6"), lw=max(0.6, (lp["width"] or 0.4) * scale * 0.85),
                    alpha=0.75, solid_capstyle="round")
            if lp["feat"] == "Outer wall":
                ax.plot(xs[0], ys[0], "o", color="#1565c0", ms=5, zorder=5)
        ax.set_xlim(win[0], win[1])
        ax.set_ylim(win[2], win[3])
        ax.set_aspect("equal")
        ax.grid(True, lw=0.2)
        ax.set_title(f"z={z:.2f}  {title}", fontsize=9)

    fig, axs = plt.subplots(3, 3, figsize=(17, 17))
    c = m["caps"][0]
    bw, bd = m["body"]
    corner = (c["cx"] - bw / 2 - 1.5, c["cx"] - bw / 2 + 5.0, c["cy"] - bd / 2 - 1.5, c["cy"] - bd / 2 + 5.0)
    whole = (c["cx"] - bw / 2 - 2, c["cx"] + bw / 2 + 2, c["cy"] - bd / 2 - 2, c["cy"] + bd / 2 + 2)
    show(axs[0][0], zs[0], corner, "キャップの左手前の角・1 層目（ベッドの面 = 押す面。縁は面取りで内へ）")
    show(axs[0][1], s.TAB_T, corner, "同・つばのいちばん上の層（上面 = 掛かる面）")
    show(axs[0][2], s.TAB_T + s.PRINT_LAYER, corner, "同・つばのすぐ上（胴だけ。ここから穴の中で滑る面）")
    h = m["holes"][0]
    h2 = m["holes"][1]
    rib = ((h["cx"] + h2["cx"]) / 2 - 6.5, (h["cx"] + h2["cx"]) / 2 + 6.5, h["cy"] - h["d"] / 2 - 2.5, h["cy"] - h["d"] / 2 + 10.5)
    lv_pocket = s.FRAME_T - s.POCKET_DEPTH
    show(axs[1][0], zs[0], rib, "枠の穴 1 と 2 の間・1 層目（上面。穴の縁は面取りで外へ）")
    show(axs[1][1], lv_pocket + s.POCKET_DEPTH / 2, rib, "同・くぼみの中（くぼみの間の壁に線があるか）")
    show(axs[1][2], s.FRAME_T + 0.5, rib, "同・枠の下面より上（柱と外の壁だけ）")
    # 継ぎ目の場所（全部の層を重ねる）: キャップ 1 個と、穴 1 個
    ax = axs[2][0]
    show(ax, 1.0, whole, "キャップ 1（胴の層）＋ 全部の層の継ぎ目（青）")
    for i, z, sx, sy in info["seams"]["cap"]:
        if i == 0:
            ax.plot(c["cx"] + sx, c["cy"] + sy, "o", color="#1565c0", ms=4, alpha=0.5)
    ax = axs[2][1]
    hw = (h["cx"] - h["w"] / 2 - 2.5, h["cx"] + h["w"] / 2 + 2.5, h["cy"] - h["d"] / 2 - 2.5, h["cy"] + h["d"] / 2 + 2.5)
    show(ax, lv_pocket - 0.3, hw, "枠の穴 1（くぼみより下の層）＋ 全部の層の継ぎ目（青）")
    for i, z, sx, sy in info["seams"]["hole"]:
        if i == 0:
            ax.plot(h["cx"] + sx, h["cy"] + sy, "o", color="#1565c0", ms=4, alpha=0.5)
    ax = axs[2][2]
    ax.axis("off")
    lines = [f"刷り方 {rc['variant']}: {rc['preset']['name']}", f"土台 {rc['base']}", ""]
    lines += [f"{k}: {v}" for k, v in summary.items()] + [""]
    lines += [f"{k}: {v}" for k, v in facts.items()]
    ax.text(0.0, 1.0, "\n".join(lines), fontsize=9, va="top", family="Hiragino Sans")
    fig.suptitle(f"スライスした線（最小の一式・{rc['preset']['name']}）。赤 = 外周・橙 = 内周・紫 = すき間埋め・灰 = そのほか・"
                 "青い点 = 外周の継ぎ目（線の始まり）。1 目盛 1 mm", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=95)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------

def run(variant, stems, s=S, only=None):
    """返り値 (結果の表 [(スライサー, 名前, 時間, 材料 cm3)], 問題の数)。"""
    stls = sorted(BUILD.glob("coupon_*.stl"))
    newest = max(q.stat().st_mtime for q in PROJECT.glob("*.py"))
    stale = [q.name for q in stls if q.stat().st_mtime < newest]
    if stale:
        print(f"NG 生成器より古い STL: {stale}（click_coupons.py を回し直す）")
        return [], 1
    stls = [q for q in stls if q.stem in stems]
    rows, bad, drawn = [], 0, False
    for engine in engines():
        if only and engine != only:
            continue
        rc = recipe(variant, s, engine)
        print(f"== {variant}・{engine}: {rc['preset']['name']}（土台 {rc['base']}・{rc['machine']['name']}・{rc['filament']['name']}）")
        for stl in stls:
            gcode, log = slice_stl(rc, stl)
            if gcode is None:
                print(f"NG {stl.stem}: スライスに失敗\n{log.strip()[-600:]}")
                bad += 1
                continue
            text = gcode.read_text(errors="replace")
            cfg = gcode_config(text)
            info = summarize_gcode(gcode)
            total = re.search(r"total estimated time: ([^\n;]+)", text)
            used = re.search(r"; (?:total )?filament (?:used|length) \[mm\] ?[:=] ?([\d.]+)", text)
            cm3 = info.get("材料") or (f"{float(used.group(1)) * math.pi * 0.875 ** 2 / 1000:.2f}" if used else None)
            warns = sorted({ln.strip()[:160] for ln in log.splitlines() if re.search(r"warn|error|fail|cannot|invalid", ln, re.I)})
            problems, n = applied_problems(rc, cfg)
            print(f"{'NG' if problems else 'OK'} {stl.stem}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
                  f"材料 {cm3} cm3・層 {info.get('層数')}・設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}")
            for w in warns[:6]:
                print(f"     ! {w}")
            if stl.stem == "coupon_min_plate":
                more, facts, extra = analyse(gcode, rc, s)
                problems += more
                for k, v in facts.items():
                    print(f"     {k}: {v}")
                if extra is not None and not drawn:
                    drawn = True
                    summary = {"スライサー": cfg_generator(text), "造形の時間": info.get("時間"),
                               "準備込み": total.group(1).strip() if total else "?", "材料 [cm3]": cm3, "層の数": info.get("層数")}
                    print(f"     絵 {draw(rc, extra, facts, summary, BUILD / f'slice_{variant}.png', s)}")
                    made = gcode.parent / f"{stl.stem}.gcode.3mf"
                    if made.exists() and not problems:
                        dst = BUILD / f"{stl.stem}_{variant}.gcode.3mf"
                        shutil.copyfile(made, dst)
                        print(f"     刷るファイル {dst}（{engine} で切った物）")
            for q in problems:
                print(f"     NG {q}")
            bad += len(problems)
            rows.append((engine, stl.stem, info.get("時間"), cm3))
    return rows, bad


def cfg_generator(text):
    """G-code の先頭に書いてあるスライサーの名前と版。"""
    m = re.search(r"^; (BambuStudio [\d.]+|generated by [^\n]+|OrcaSlicer [^\n]+)", text, re.M)
    return m.group(1).strip() if m else "?"


def main(argv):
    every = "--all" in argv
    variants = [a for a in argv if a in S.PRINT_RECIPES] or list(S.PRINT_RECIPES)
    stems = None
    names = [a for a in argv if a.startswith("coupon_")]
    only = next((a for a in argv if a in ("bambu", "orca")), None)      # スライサーを 1 つに絞る（既定は両方）
    bad = 0
    for v in variants:
        if every:
            stems = [q.stem for q in BUILD.glob("coupon_*.stl")]
        rows, b = run(v, names or stems or ["coupon_min_plate"], only=only)
        bad += b
        if every:
            print(f"-- {v}: 名前・造形の時間・材料 [cm3]")
            for engine, stem, tm, cm3 in rows:
                print(f"   {engine} {stem} | {tm} | {cm3}")
    print("NG" if bad else "OK", f"問題 {bad} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
