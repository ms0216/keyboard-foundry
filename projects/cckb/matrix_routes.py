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
        for p in pads:
            box = p["box"]
            layers = ({F, B} if (p["npth"] or (p["front"] and p["back"]))
                      else {F} if p["front"] else {B})
            if p.get("round"):
                shape = ("circle", ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
                         (box[2] - box[0]) / 2)
            else:
                shape = ("box", box)
            gap = HOLE_GAP if p["npth"] else PAD_GAP
            self.items.append((gap, shape, p["net"] if not p["npth"] else "", layers))
        for poly in reliefs:
            for i in range(len(poly)):
                self.items.append((EDGE_GAP, ("seg", poly[i], poly[(i + 1) % len(poly)]), "", {F, B}))
        x0, y0, x1, y1 = edge
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)),
                     ((x0, y1), (x0, y0))):
            self.items.append((EDGE_GAP, ("seg", a, b), "", {F, B}))

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
    # 行ごとのバスの高さと左端（カソードの x の最小）
    bus = {}
    for i, ((kx, ky), (r, c)) in enumerate(zip(positions, rc), start=1):
        xk = next(p["x"] for p in pads if p["ref"] == f"D{i}" and p["num"] == "1")
        y = round(ky + s.ROW_BUS_DY[r], 4)
        bx = bus.get(f"ROW{r}", (math.inf, y))[0]
        bus[f"ROW{r}"] = (min(bx, xk), y)
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
        if "lane_x" in how:
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
    rows = {}
    for i, ((kx, ky), (r, c)) in enumerate(zip(positions, rc), start=1):
        x2, y2, n_sd = pd[(f"SW{i}", "2")]
        xa, ya, n_a = pd[(f"D{i}", "2")]          # pinmap: diode A = パッド 2
        xk, yk, n_k = pd[(f"D{i}", "1")]          # K = パッド 1
        if n_sd != n_a or not re.fullmatch(r"ROW\d+", n_k):
            raise ValueError(f"SW{i}/D{i} のネットが行列の形でない: {n_sd} {n_a} {n_k}")
        # 端子 2 → アノード: 端子の高さで横に、アノードの x で縦に
        lay(n_sd, B, [(x2, y2), (xa, y2), (xa, ya)], f"SW{i}→D{i}")
        ybus = ky + s.ROW_BUS_DY[r]
        lay(n_k, B, [(xk, yk), (xk, ybus)], f"D{i}→バス")
        rows.setdefault(n_k, []).append((xk, ybus))
    for net, pts in rows.items():
        ys = {round(y, 4) for _, y in pts}
        if len(ys) != 1:
            raise ValueError(f"{net}: バスの高さが揃わない {ys}")
        xs = sorted(x for x, _ in pts)
        lay(net, B, [(xs[0], pts[0][1]), (xs[-1], pts[0][1])], "バス")

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
            tried = []
            for side in (-1, 1):                       # 左へ寄せる。駄目なら右
                path = _column_path(net, s, row_y, ok, (ru, xu, yu, kxu), (rl, xl, yl),
                                    side)
                if path is not None:
                    break
                tried.append(side)
            else:
                raise ValueError(f"{net}: SW{iu}→SW{il} の道が左右とも無い")
            lay(net, F, path, f"SW{iu}→SW{il}")

    bad = clashes(segs)
    if bad:
        raise ValueError("行列の配線の計画が自分とぶつかる:\n  " + "\n  ".join(bad[:10]))
    return segs


def _column_path(net, s, row_y, ok, upper, lower, side):
    """上のキーの端子 1 から下のキーの端子 1 まで（表）。通れなければ None。"""
    ru, xu, yu, kxu = upper
    rl, xl, yl = lower
    x = kxu + side * s.COL_JOG
    y = row_y[ru] - UNIT / 2                           # 上のキーの下の段の境目
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
