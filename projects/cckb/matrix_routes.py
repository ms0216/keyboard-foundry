"""キーの行列の配線を決まった形で引く計画（設計書 §12）。**寸法は持たない**（spec.py から読む）。

    行（裏 B.Cu）: スイッチの端子 2 → ダイオードのアノード（L 字）、カソード → 行のバス（縦の短線）、
                    バス（横一直線・キー中心の ROW_BUS_DY 下）
    列（表 F.Cu）: 端子 1 から左へ COL_JOG 寄せて中心穴・ボスの間を縦に下り、段の境目で横に渡り、
                    下の段のキーの端子 1 へ下りる。1 段飛ばすときはあいだの段のキーの境目を縦に抜ける

**板の上のパッドの実際の位置から引く**（pcbnew が回転・裏返しまで解いた世界座標）。
使うのは 2 か所で、同じ関数を通す（形を 2 か所で作るとずれる）:
  - tools/route_pcb.py（KiCad の Python）が板に線を置く
  - interface.corridors が取付の 5 条件の「配線の通り道」として使う（段階 1 の直線の通り道は
    実際には引けなかった: カソードの高さの直線はスイッチのボスと中心穴を貫く）

KiCad の Python（3.9）からも読むので標準ライブラリだけ。座標は CAD（Y 上向き・mm）。
"""

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundry.layout import UNIT, centered   # noqa: E402
from foundry.pcb_rules import JLC, TRACK_W, VIA_D   # noqa: E402

F, B = "F.Cu", "B.Cu"
# **規則の値は pcb_rules から導く**（写すと、規則を変えたとき自前の計画だけ古い値のまま
# ずれる。最終レビュー I1）。機種が持つのは足した余裕だけ
CLEAR = TRACK_W                  # ネットクラスの間隔（foundry.pcb が線幅と同じ値を間隔にも使う）
TRACK_CLEAR = TRACK_W + CLEAR    # 線の中心どうし: 線幅 ＋ 間隔

# 線と障害物の間に残す距離（線の縁から）。規則に少し足す
PAD_GAP = CLEAR + 0.05                    # パッド
HOLE_GAP = JLC["edge_clearance"]          # 穴（NPTH・スルーホールの穴）。外形と同じ扱い
EDGE_GAP = JLC["edge_clearance"] + 0.05   # 外形・スタビの逃げ穴
HALF_W = TRACK_W / 2                      # 線の半幅
VIA_R = VIA_D / 2                         # ビアの半径


def _pads(pads):
    """[{ref, num, net, x, y}] → {(ref, num): (x, y, net)}。"""
    return {(p["ref"], p["num"]): (p["x"], p["y"], p["net"]) for p in pads if p["num"]}


def _seg_box_dist(a, b, box):
    """線分 ab（縦か横）と矩形の距離（交われば 0）。"""
    x0, y0, x1, y1 = box
    lo_x, hi_x = min(a[0], b[0]), max(a[0], b[0])
    lo_y, hi_y = min(a[1], b[1]), max(a[1], b[1])
    dx = max(x0 - hi_x, lo_x - x1, 0.0)
    dy = max(y0 - hi_y, lo_y - y1, 0.0)
    return math.hypot(dx, dy)


class Obstacles:
    """板の上の物（パッド・穴・逃げ穴・外形）。**板から読んだ物**で作る（宣言からではない）。"""

    def __init__(self, pads, reliefs, edge):
        self.items = []                       # (種類, 形, ネット, 層の集合)
        self.reliefs = [list(p) for p in reliefs]     # 穴の中も通れない（辺だけでなく面で塞ぐ: blocked_x）
        for p in pads:
            box = p["box"]
            layers = ({F, B} if (p["npth"] or (p["front"] and p["back"]))
                      else {F} if p["front"] else {B})
            if p.get("round"):
                shape = ("circle", ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
                         (box[2] - box[0]) / 2)
            else:
                shape = ("box", box)
            # 長円の非めっきの穴（V2 の位置決め・スタビのねじと爪）は、pcb_extra が縁に配線禁止の帯
            # （NPTH_KEEPOUT・外形と同じ EDGE_BAND）を置く。帯の外を通るよう外形と同じ EDGE_GAP で離す
            gap = (HOLE_GAP if p.get("round") else EDGE_GAP) if p["npth"] else PAD_GAP
            self.items.append((gap, shape, p["net"] if not p["npth"] else "", layers))
        for poly in reliefs:
            for i in range(len(poly)):
                self.items.append((EDGE_GAP, ("seg", poly[i], poly[(i + 1) % len(poly)]), "", {F, B}))
        x0, y0, x1, y1 = edge
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)),
                     ((x0, y1), (x0, y0))):
            self.items.append((EDGE_GAP, ("seg", a, b), "", {F, B}))

    def blocked_x(self, net, layer, a, b):
        """横の線 ab が近すぎる物の、x の範囲（線の中心が入ってはいけない幅。線の半幅と間隔を足した）。"""
        out = []
        for gap, shape, n, layers in self.items:
            if layer not in layers or (n and n == net):
                continue
            if shape[0] == "box":
                d = _seg_box_dist(a, b, shape[1])
                x0, x1 = shape[1][0], shape[1][2]
            elif shape[0] == "circle":
                d = seg_seg_dist(shape[1], shape[1], a, b) - shape[2]
                x0, x1 = shape[1][0] - shape[2], shape[1][0] + shape[2]
            else:
                d = seg_seg_dist(shape[1], shape[2], a, b)
                x0, x1 = sorted((shape[1][0], shape[2][0]))
            need = gap + HALF_W
            if d < need - 1e-9:
                out.append((x0 - need, x1 + need))
        need = EDGE_GAP + HALF_W
        lo_x, hi_x = sorted((a[0], b[0]))
        for poly in self.reliefs:
            xs, ys = [q[0] for q in poly], [q[1] for q in poly]
            if min(ys) - need < a[1] < max(ys) + need and min(xs) - need < hi_x and max(xs) + need > lo_x:
                out.append((min(xs) - need, max(xs) + need))
        return out

    def problems(self, net, layer, a, b):
        out = []
        for gap, shape, n, layers in self.items:
            if layer not in layers or (n and n == net):
                continue
            if shape[0] == "box":
                d = _seg_box_dist(a, b, shape[1])
            elif shape[0] == "circle":
                d = seg_seg_dist(shape[1], shape[1], a, b) - shape[2]
            else:
                d = seg_seg_dist(shape[1], shape[2], a, b)
            if d < gap + HALF_W - 1e-9:
                out.append((shape, round(d, 3)))
        return out


def escape(project, pads, reliefs=None, edge=None, others=()):
    """XIAO の D2〜D6（パッド内ビア）から行のバスの左端まで（spec.XIAO_ESCAPE）。
    ([(net, layer, a, b)], [(net, (x, y))])。others は先に決まった線（行列）で、ぶつかれば落とす。"""
    s = project.spec
    keys, rc = project.matrix("main")
    positions, _ = centered(keys)
    if reliefs is None or edge is None:
        import interface
        ifc = interface.Interface(project)
        reliefs = ifc.stab_reliefs() if reliefs is None else reliefs
        edge = ifc.pcb if edge is None else edge
    obs = Obstacles(pads, reliefs, edge)
    # XIAO のパッド内ビア（スルーホールのパッド）の位置とネット
    vpad = {p["net"]: (p["x"], p["y"]) for p in pads
            if p["ref"] == "U_MCU" and not p["npth"] and p["front"] and p["back"] and p["net"]}
    # 行ごとのバスの左端（plan と同じ回り道を通した後の、線の始まり）
    bus = {net: b["start"] for net, b in buses(project, pads, obs).items()}
    segs, vias = [], []

    def lay(net, layer, pts):
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9:
                raise ValueError(f"{net}: 斜めの線")
            bad = obs.problems(net, layer, a, b)
            if bad:
                raise ValueError(f"{net} {layer} {a}->{b} が板の物に近い: {bad[:3]}")
            segs.append((net, layer, (round(a[0], 4), round(a[1], 4)),
                         (round(b[0], 4), round(b[1], 4))))

    def via(net, p):
        for layer in (F, B):
            bad = [x for x in obs.problems(net, layer, p, p) if x[1] < VIA_R + 0.25 - HALF_W]
            if bad:
                raise ValueError(f"{net} のビア {p} が板の物に近い: {bad[:3]}")
        vias.append((net, (round(p[0], 4), round(p[1], 4))))

    for net, how in sorted(s.XIAO_ESCAPE.items()):
        if net not in vpad:
            raise ValueError(f"{net}: XIAO のパッド内ビアが無い（circuit.XIAO_PINS と合わない）")
        x0, y0 = vpad[net]
        bx, by = bus[net]
        if "turn_y" in how:
            ty, (vx, vy), lx = how["turn_y"], how["via"], how["lane_x"]
            lay(net, B, [(x0, y0), (x0, ty), (vx, ty), (vx, vy)])
            via(net, (vx, vy))
            lay(net, F, [(vx, vy), (lx, vy), (lx, by)])
            via(net, (lx, by))
            lay(net, B, [(lx, by), (bx, by)])
        elif "lane_x" in how:
            vy, lx = how["via_y"], how["lane_x"]
            lay(net, B, [(x0, y0), (x0, vy)])
            via(net, (x0, vy))
            lay(net, F, [(x0, vy), (lx, vy), (lx, by)])
            via(net, (lx, by))
            lay(net, B, [(lx, by), (bx, by)])
        elif "run_y" in how:
            ry = how["run_y"]
            lay(net, B, [(x0, y0), (x0, ry), (bx, ry), (bx, by)])
        else:
            lay(net, B, [(x0, y0), (x0, by), (bx, by)])
    bad = clashes(list(others) + segs) + [
        f"ビア {n} {p} が {m} {a}->{b} に近い" for n, p in vias
        for m, _, a, b in list(others) + segs
        if m != n and seg_seg_dist(p, p, a, b) < VIA_R + CLEAR + HALF_W - 1e-9]
    if bad:
        raise ValueError("XIAO からの線がぶつかる:\n  " + "\n  ".join(bad[:10]))
    return segs, vias


def power_runs(project, pads, reliefs=None, edge=None, others=()):
    """電源の長い線を決まった形で（spec.POWER_RUNS）。[(net, layer, a, b)]。太さは spec.POWER_TRACK_W。

    端はパッドの中心（宣言したパッドのネットが違えば落とす）。板の物との間隔は太い線の半幅で確かめ、
    先に決まった線（others・行列と XIAO からの線）との間隔も見る。
    """
    s = project.spec
    if reliefs is None or edge is None:
        import interface
        ifc = interface.Interface(project)
        reliefs = ifc.stab_reliefs() if reliefs is None else reliefs
        edge = ifc.pcb if edge is None else edge
    obs = Obstacles(pads, reliefs, edge)
    pd = _pads(pads)
    extra = s.POWER_TRACK_W / 2 - HALF_W          # 太い線の半幅の増し分
    out = []
    for net, how in sorted(getattr(s, "POWER_RUNS", {}).items()):
        pts = [tuple(p) for p in how["pts"]]
        for end, ref in ((pts[0], how["frm"]), (pts[-1], how["to"])):
            x, y, n = pd[tuple(ref)]
            if n != net or math.hypot(x - end[0], y - end[1]) > 1e-3:
                raise ValueError(f"{net}: 端 {end} が {ref} のパッド ({x}, {y}, {n}) でない")
        for a, b in zip(pts, pts[1:]):
            bad = [x for x in obs.problems(net, how["layer"], a, b)
                   if x[1] < (HOLE_GAP if x[0][0] != "box" else PAD_GAP) + HALF_W + extra - 1e-9]
            bad += [(m, p, q) for m, l, p, q in others
                    if l == how["layer"] and m != net and seg_seg_dist(a, b, p, q) < TRACK_CLEAR + extra - 1e-9]
            if bad:
                raise ValueError(f"{net} {a}->{b} が近い: {bad[:3]}")
            out.append((net, how["layer"], (round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))))
    return out


def plan(project, pads, reliefs=None, edge=None):
    """[(net, layer, (x1, y1), (x2, y2))]。pads は板から読んだパッド（CAD 座標・
    board_geometry.dump と同じ形: ref, num, net, x, y, box, front, back, npth, round）。

    線は**板の上の物との間隔を自分で確かめる**（パッド 0.25・穴 0.3・外形と逃げ穴 0.35。
    違うネットの線どうしは TRACK_CLEAR）。回り道の候補（列を左右どちらへ寄せるか・
    飛ばす段をどこで抜けるか）はここで選び、どれも駄目なら落とす。最後の判定は KiCad の DRC。
    """
    s = project.spec
    keys, rc = project.matrix("main")
    positions, (kw, kh) = centered(keys)
    if reliefs is None or edge is None:
        import interface
        ifc = interface.Interface(project)
        reliefs = ifc.stab_reliefs() if reliefs is None else reliefs
        edge = ifc.pcb if edge is None else edge
    obs = Obstacles(pads, reliefs, edge)
    pd = _pads(pads)
    segs = []

    def ok(net, layer, pts):
        if any(abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9 for a, b in zip(pts, pts[1:])):
            raise ValueError(f"{net}: 斜めの線（縦と横だけで引く）")
        return not any(obs.problems(net, layer, a, b) for a, b in zip(pts, pts[1:]))

    def lay(net, layer, pts, why):
        bad = [(a, b, obs.problems(net, layer, a, b)) for a, b in zip(pts, pts[1:])]
        bad = [x for x in bad if x[2]]
        if bad:
            raise ValueError(f"{net}（{why}）が板の物に近い: {bad[:3]}")
        for a, b in zip(pts, pts[1:]):
            if a != b:
                segs.append((net, layer, (round(a[0], 4), round(a[1], 4)),
                             (round(b[0], 4), round(b[1], 4))))

    # --- 行（裏）------------------------------------------------------------
    bus = buses(project, pads, obs)
    for i, ((kx, ky), (r, c)) in enumerate(zip(positions, rc), start=1):
        x2, y2, n_sd = pd[(f"SW{i}", "2")]
        xa, ya, n_a = pd[(f"D{i}", "2")]          # pinmap: diode A = パッド 2
        xk, yk, n_k = pd[(f"D{i}", "1")]          # K = パッド 1
        if n_sd != n_a or not re.fullmatch(r"ROW\d+", n_k):
            raise ValueError(f"SW{i}/D{i} のネットが行列の形でない: {n_sd} {n_a} {n_k}")
        # 端子 2 → アノード: 端子の高さで横に、アノードの x で縦に
        lay(n_sd, B, [(x2, y2), (xa, y2), (xa, ya)], f"SW{i}→D{i}")
        # カソード → バス（回り道の中のキーは回り道の高さまで下りる）
        lay(n_k, B, [(xk, yk), (xk, bus[n_k]["drop"][round(xk, 4)])], f"D{i}→バス")
    for net, b in bus.items():
        for pts in b["paths"]:
            lay(net, B, pts, "バス")

    # --- 列（表）------------------------------------------------------------
    row_y = sorted({round(y, 4) for _, y in positions}, reverse=True)     # 上の段から
    cols = {}
    for i, ((kx, ky), (r, c)) in enumerate(zip(positions, rc), start=1):
        x1, y1, net = pd[(f"SW{i}", "1")]
        if net != f"COL{c}":
            raise ValueError(f"SW{i} の端子 1 が {net}（COL{c} のはず）")
        cols.setdefault(net, []).append((r, x1, y1, kx, i))
    for net, ks in cols.items():
        ks.sort()
        for (ru, xu, yu, kxu, iu), (rl, xl, yl, kxl, il) in zip(ks, ks[1:]):
            # 左へ寄せる。駄目なら右。段の境目で渡れなければ、境目から少しずらした高さで渡る
            # （V2 のスタビの爪の穴は支点から奥へ 8.37 ± 2.2 で、境目 9.525 をまたぐ。Enter の上）
            path = next((pth for off in CROSS_OFFSETS for side in (-1, 1)
                         for pth in [_column_path(net, s, row_y, ok, (ru, xu, yu, kxu), (rl, xl, yl),
                                                  side, off)] if pth is not None), None)
            if path is None:
                raise ValueError(f"{net}: SW{iu}→SW{il} の道が左右とも無い")
            lay(net, F, path, f"SW{iu}→SW{il}")

    bad = clashes(segs)
    if bad:
        raise ValueError("行列の配線の計画が自分とぶつかる:\n  " + "\n  ".join(bad[:10]))
    return segs


# 回り道の探し方。バスの高さから下へ DETOUR_STEP ずつ、DETOUR_MAX まで。回り道どうしの間が
# DETOUR_JOIN より狭ければ 1 つにまとめる（縦の脚どうしが近すぎないように）
DETOUR_STEP = 0.05
DETOUR_MAX = 12.0
DETOUR_JOIN = 1.0


def buses(project, pads, obs):
    """行ごとのバス（裏・横）。{net: dict(paths=[[点...]...], drop={xk: y}, start=(x, y))}。

    バスはキー中心の ROW_BUS_DY の高さを横一直線に通す。**板の物（スタビの箱・ねじの穴・取付の穴）に
    当たる所だけ、下へ回り道する**（その x の範囲を塞ぎ、左右の脚で下りて渡る）。回り道の中にある
    キーのカソードは、回り道の高さまで下りて繋ぐ。回り道の高さは近い所から探し、無ければ落とす。
    """
    s = project.spec
    keys, rc = project.matrix("main")
    positions, _ = centered(keys)
    rows = {}
    for i, ((kx, ky), (r, c)) in enumerate(zip(positions, rc), start=1):
        xk = next(p["x"] for p in pads if p["ref"] == f"D{i}" and p["num"] == "1")
        net = next(p["net"] for p in pads if p["ref"] == f"D{i}" and p["num"] == "1")
        rows.setdefault(net, []).append((xk, round(ky + s.ROW_BUS_DY[r], 4)))
    out = {}
    for net, pts in sorted(rows.items()):
        ys = {y for _, y in pts}
        if len(ys) != 1:
            raise ValueError(f"{net}: バスの高さが揃わない {ys}")
        y = ys.pop()
        xs = sorted(x for x, _ in pts)
        ivs = sorted(obs.blocked_x(net, B, (xs[0], y), (xs[-1], y)))
        merged = []
        for lo, hi in ivs:
            if merged and lo < merged[-1][1] + DETOUR_JOIN:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        paths, drop, cur = [], {round(x, 4): y for x in xs}, xs[0]
        start = (xs[0], y)
        for lo, hi in merged:
            lo, hi = lo - 0.05, hi + 0.05
            a, b = max(lo, xs[0]), min(hi, xs[-1])
            yd = y - 0.5
            while yd > y - DETOUR_MAX:
                legs = []
                if lo > xs[0]:
                    legs.append([(lo, y), (lo, yd)])
                if hi < xs[-1]:
                    legs.append([(hi, yd), (hi, y)])
                run = [(a, yd), (b, yd)]
                if all(not obs.problems(net, B, p, q) for pl in legs + [run] for p, q in zip(pl, pl[1:])):
                    break
                yd = round(yd - DETOUR_STEP, 4)
            else:
                raise ValueError(f"{net}: x {lo:.2f}〜{hi:.2f} の回り道が {DETOUR_MAX} 下までに無い")
            if lo > xs[0]:
                paths.append([(cur, y), (lo, y), (lo, yd), (b, yd)])
            else:
                start = (xs[0], yd)
                paths.append([(xs[0], yd), (b, yd)])
            if hi < xs[-1]:
                paths[-1] += [(hi, y)]
                cur = hi
            else:
                cur = None
            for x in xs:
                if a - 1e-9 <= x <= b + 1e-9:
                    drop[round(x, 4)] = yd
        if cur is not None and cur < xs[-1]:
            paths.append([(cur, y), (xs[-1], y)])
        out[net] = dict(paths=[[(round(p[0], 4), round(p[1], 4)) for p in pl] for pl in paths],
                        drop=drop, start=(round(start[0], 4), round(start[1], 4)))
    return out


# 列が段の境目を横に渡る高さを、境目からずらす候補（近い順）
CROSS_OFFSETS = (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0)


def _column_path(net, s, row_y, ok, upper, lower, side, off=0.0):
    """上のキーの端子 1 から下のキーの端子 1 まで（表）。通れなければ None。"""
    ru, xu, yu, kxu = upper
    rl, xl, yl = lower
    x = kxu + side * s.COL_JOG
    y = row_y[ru] - UNIT / 2 + off                     # 上のキーの下の段の境目（から off）
    path = [(xu, yu), (x, yu), (x, y)]
    if not ok(net, F, path):
        return None
    for m in range(ru + 1, rl):                        # あいだの段を縦に抜ける
        yb = y - UNIT
        cands = sorted((round(xl + d * 0.05, 4) for d in range(-400, 401)),
                       key=lambda c: (abs(c - x) + abs(c - xl), c))
        xc = next((c for c in cands if ok(net, F, [(x, y), (c, y), (c, yb)])), None)
        if xc is None:
            return None
        path += [(xc, y), (xc, yb)]
        x, y = xc, yb
    tail = [(x, y), (xl, y), (xl, yl)]
    if not ok(net, F, tail):
        return None
    return path + tail[1:]


def seg_seg_dist(a, b, c, d):
    """線分 ab と cd の距離（縦横の線でも斜めでも）。"""
    def pt(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy)
                                                   / (dx * dx + dy * dy)))
        return math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dy)

    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and 0 not in (d1, d2, d3, d4):
        return 0.0
    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def clashes(segs, clear=TRACK_CLEAR):
    """違うネットで同じ層の線が clear 未満に近いもの。"""
    out = []
    for i, (n1, l1, a, b) in enumerate(segs):
        for n2, l2, c, d in segs[i + 1:]:
            if l1 == l2 and n1 != n2:
                g = seg_seg_dist(a, b, c, d)
                if g < clear - 1e-9:
                    out.append(f"{l1} {n1} {a}->{b} と {n2} {c}->{d} が {g:.3f}")
    return out
