"""cckb-click の本番の枠（左右 2 枚）・キャップ（4 つの幅）・基板の上の物・組んだ状態（build123d）。**寸法は持たない**（spec.py・click_layout.py）。

    .venv/bin/python3 projects/cckb-click/click_case.py      # STL（刷る向き）・断面図・分解図・.blend を build/cckb-click/ に

形の出どころは click_parts.py と同じ（Salicylic_acid3 さんの ClickBoard を測って作り直した物。LICENSE: CC BY-NC 4.0）。
1 マスの形（穴・つば・くぼみ・面取り・継ぎ目の溝）は click_parts の関数をそのまま使う——試し刷りで利用者が触って決めた形と同じ物になる。

構造（基板の上面 = 0）:
  枠      厚さ 2.0 の板（3.0〜5.0）に 62 個の穴。外周に基板まで下りる壁（0〜3.0）。リブの中点に柱（0〜3.0）。
          角（XIAO・電池）は穴の無い屋根で、部品の所だけ下から掘る。**上面をベッドに刷る**（支え無し）
  留め方  基板の下から M2 のねじを外周の壁に切る（20 本）。頭は基板の下面
  分け方  A1 mini に入るように左右 2 枚。継ぎ目のリブは左が持つ。基板が継ぎ目をまたぐ背骨
  キャップ 62 個（1u 51・1.5u 5・1.75u 2・2.25u 4）。枠の下から入れ、基板をかぶせる
座標: CAD（キー領域の中心が原点・X 右・Y 奥）・Z は基板の上面が 0。
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build123d import (Align, Box, Compound, Cylinder, Polygon, Pos, Rectangle, RectangleRounded,  # noqa: E402
                       Rot, export_stl, extrude)

import click_layout  # noqa: E402
import click_parts as P  # noqa: E402
from foundry import paths  # noqa: E402
from foundry.layout import UNIT  # noqa: E402
from foundry.mech import SKRA_TACT  # noqa: E402

LAY = click_layout.Layout()
S = LAY.s
OUT = paths.BUILD / HERE.name
EPS = P.EPS
CEN_MIN = P.CEN_MIN
SIDES = ("left", "right")
CAP_WIDTHS = (1.0, 1.5, 1.75, 2.25)
# 基板の上の部品の背（組み立ての包絡。データシートの最大）: SOD-123 1.35・0805 1.35・TSSOP-16 1.2
PART_H = {"D": 1.35, "R": 1.35, "C": 1.35, "U": 1.2}
# 部品の本体の大きさ（x, y）。向きは spec.PART_AT の角度（0 か 90）で入れ替える
PART_BODY = {"D": (2.8, 1.8), "R": (2.0, 1.25), "C": (2.0, 1.25), "U": (6.4, 5.0)}
COLORS = {"frame_left": "#9aa0a6", "frame_right": "#b0b6bc", "pcb": "#2f7d32", "caps": "#e8c9a0", "switches": "#303030",
          "parts": "#8a5a2b", "xiao": "#1f4e9c", "battery": "#c8c8c8", "screws": "#d0a000", "sheet": "#202020"}


def cell(k, s=S):
    return P.Cell(k.x, k.y, s.HOLE_B, w_u=k.w)


def _box(r, z0, z1):
    """矩形 (x0, y0, x1, y1) を z0〜z1 の箱に。"""
    return Pos(r[0], r[1], z0) * Box(r[2] - r[0], r[3] - r[1], z1 - z0, align=P.MIN)


def _rect2d(r):
    return Pos((r[0] + r[2]) / 2, (r[1] + r[3]) / 2) * Rectangle(r[2] - r[0], r[3] - r[1])


def _union(shapes):
    shapes = list(shapes)
    out = shapes[0]
    if len(shapes) > 1:
        out = out.fuse(*shapes[1:])
    return out


def outline2d(lay=LAY):
    f = lay.frame
    r = lay.s.CORNER_R + lay.s.PCB_INSET_X
    return Pos((f[0] + f[2]) / 2, (f[1] + f[3]) / 2) * RectangleRounded(f[2] - f[0], f[3] - f[1], r)


# ---------------------------------------------------------------------------
# 枠の下の構造（基板の上 0〜3.0）: 壁・ねじの所の厚い壁・柱・（中の押さえの足）。**部品として持つ**（干渉の検査が 1 個ずつ見る）
# ---------------------------------------------------------------------------

def screw_boss(c, lay=LAY):
    """外周のねじの所で、壁を内へ厚くする矩形（キー領域の端から穴の縁まで。角ではその先へ 0.5）。"""
    s = lay.s
    f, a = lay.frame, lay.key_area
    x, y = c
    h = s.SCREW_BOSS_HALF
    depth = lay.rib() / 2
    in_corner = any(click_layout.rect_gap((x, y, x, y), lay.corner(side)) < 6 for side in SIDES)
    if in_corner:
        depth, h = depth + 0.5, h + 0.6
    d = {"left": x - f[0], "right": f[2] - x, "front": y - f[1], "back": f[3] - y}
    side = min(d, key=d.get)
    if side == "front":
        return (x - h, a[1] - EPS, x + h, a[1] + depth)
    if side == "back":
        return (x - h, a[3] - depth, x + h, a[3] + EPS)
    if side == "left":
        return (a[0] - EPS, y - h, a[0] + depth, y + h)
    return (a[2] - depth, y - h, a[2] + EPS, y + h)


def lower_rects(lay=LAY):
    """柱と、ねじの所の厚い壁の矩形 [(種類, 矩形)]。"""
    out = [("post", click_layout.rect(*p)) for p in lay.all_posts()]
    out += [("boss", screw_boss(c, lay)) for _, c, kind in lay.screws() if kind == "perimeter"]
    return out


def lower_solids(lay=LAY):
    """柱と厚い壁の立体 {名前: 立体}（0〜FRAME_UNDER）。**枠と同じに、穴とくぼみで削った後の形**
    （段がずれて並ぶ所の横長の柱は、くぼみの下に掛かる分が削られる）。"""
    s = lay.s
    cells = [cell(k) for k in lay.keys]
    cut = _union([Pos(c.cx, c.cy) * P.hole_plan(c, s) for c in cells] + [Pos(c.cx, c.cy) * P.tab_plan(c, s, s.POCKET_CLEAR) for c in cells])
    out = {}
    for i, (kind, r) in enumerate(lower_rects(lay)):
        sk = _rect2d(r) - cut
        if sk is not None and sum(f.area for f in sk.faces()) > 1e-6:
            out[f"{kind}{i}"] = extrude(sk, s.FRAME_UNDER)
    return out


def feet(lay=LAY):
    """中の押さえの足（円柱。spec.HOLDDOWN_FEET のときだけ枠に付く）。[(中心, 立体)]"""
    s = lay.s
    return [(c, Pos(c[0], c[1], 0) * Cylinder(s.HOLDDOWN_D / 2, s.HOLDDOWN_H, align=CEN_MIN))
            for _, c, kind in lay.screws() if kind == "holddown"]


# ---------------------------------------------------------------------------
# 角の逃げ（枠から引く立体）
# ---------------------------------------------------------------------------

def corner_cuts(lay=LAY):
    """{名前: 立体}。XIAO の空間・USB の切り欠き・電池クリップの空間・電池の口・指の切り欠き・電源スイッチの空間・つまみの溝・入の印。"""
    s = lay.s
    f = lay.frame
    top = s.FRAME_UNDER + s.FRAME_T
    z = lay.z()
    c, h = s.PART_CLEAR, s.PART_HEADROOM
    xb, xp = lay.xiao(), lay.xiao_pads()
    usb = lay.usb_shell()
    out = {}
    out["xiao"] = _box((xb[0] - c, xp[1] - 0.3, xb[2] + c, xp[3] + 0.3), -1.0, s.XIAO_ROOF_UNDER)
    out["usb"] = _box((f[0] - 1.0, usb[1] - s.PORT_CLEAR, usb[2] + c, usb[3] + s.PORT_CLEAR), -1.0, top + 1.0)
    (cx, cy), r = lay.cell()
    body = lay.clip_body()
    pads = lay.clip_pads()
    out["clip"] = _box((pads[0][0] - c, body[1] - c, pads[1][2] + c, body[3] + c), -1.0, s.CLIP_ROOF_UNDER)
    slot_top = z["cell_top"] + s.CELL_SLOT_CLEAR + 0.1
    out["cell_slot"] = _box((cx - r - s.CELL_SLOT_CLEAR, f[1] - 1.0, cx + r + s.CELL_SLOT_CLEAR, body[1] - c + EPS), -1.0, slot_top)
    w, d = s.FINGER_NOTCH
    out["finger"] = _box((cx - w / 2, f[1] - 1.0, cx + w / 2, f[1] + d), slot_top - EPS, top + 1.0)
    pb = lay.psw_body()
    psw_top = z["psw_top"] + h + 0.1
    out["psw"] = _box((pb[0] - 2.2, pb[1] - 0.3, pb[2] + 0.3, pb[3] + 0.3), -1.0, psw_top)      # 端子の側（左）へ 2.2: 端子とはんだ
    ks = lay.psw_knob_sweep()
    out["knob"] = _box((pb[2], ks[1] - c, f[2] + 1.0, ks[3] + c), -1.0, psw_top)
    d_mark, depth = s.ON_MARK
    my = s.PSW_AT[1] + s.PSW_ON * (s.PSW_TRAVEL / 2 + s.PSW_KNOB[0] / 2 + c + 1.2)
    out["on_mark"] = Pos(f[2] - 1.5, my, top - depth) * Cylinder(d_mark / 2, depth + 1.0, align=CEN_MIN)
    return out


# ---------------------------------------------------------------------------
# 枠
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def frame_full(with_feet=None):
    """1 枚のままの枠。層ごとに平面の形を作って押し出す（62 個の穴を 1 個ずつ立体で引くより速い）。"""
    lay, s = LAY, S
    with_feet = s.HOLDDOWN_FEET if with_feet is None else with_feet
    lv = P.levels(s)
    top, under, latch = lv["frame_top"], lv["frame_under"], lv["latch"]
    cells = [cell(k) for k in lay.keys]
    outline = outline2d(lay)
    holes = _union([Pos(c.cx, c.cy) * P.hole_plan(c, s) for c in cells])
    pockets = _union([Pos(c.cx, c.cy) * P.tab_plan(c, s, s.POCKET_CLEAR) for c in cells])
    nw, nd = s.SEAM_NOTCH
    notches = _union([Pos(c.cx, c.cy + P.hole_size(c)[1] / 2 + (nd - 0.5) / 2) * Rectangle(nw, nd + 0.5) for c in cells])
    wall = outline - _rect2d(lay.key_area)
    low = _union([wall] + [_rect2d(r) for _, r in lower_rects(lay)])
    # 層どうしは EPS だけ重ねて足す（面の一致で継ぎ目を残さない）。**重ねるのは狭い方の層を広い方へ**——逆にすると、
    # くぼみの底が EPS 低くなって、掛かったつばに食い込む（検査が 62 個ぶん 3.7 mm3 を見つけた）
    parts = [
        Pos(0, 0, latch) * extrude(outline - holes - notches, top - latch),                         # くぼみの底より上
        Pos(0, 0, under) * extrude(outline - holes - notches - pockets, latch - under + EPS),        # くぼみの層
        extrude(low - holes - pockets, under),                                                      # 壁・柱
        Pos(0, 0, under - EPS) * extrude(low - holes - pockets - notches, 2 * EPS),                 # 壁・柱と上の層をつなぐ重なり
    ]
    body = _union(parts)
    ch = s.HOLE_CHAMFER
    chamfers = _union([Pos(c.cx, c.cy, top - ch) * extrude(P.hole_plan(c, s), ch + EPS, taper=-45.0) for c in cells])
    cuts = [chamfers] + list(corner_cuts(lay).values())
    d, depth = lay.pilot()
    cuts += [Pos(c[0], c[1], -1.0) * Cylinder(d / 2, depth + 1.0, align=CEN_MIN) for _, c, kind in lay.screws() if kind == "perimeter"]
    body = body - _union(cuts)
    if with_feet:
        ft = _union([f for _, f in feet(lay)])
        ft = ft - _union([Pos(c[0], c[1], -1.0) * Cylinder(d / 2, s.HOLDDOWN_H + 2.0, align=CEN_MIN) for c, _ in feet(lay)])
        body = body + ft
    return body.clean()


def left_region(lay=LAY, grow=0.0):
    """左の枠の範囲（平面）。段ごとの帯（上下のリブを含む）の、継ぎ目 ＋ リブの半分 より左。帯が重なるリブは、広い方の段に合わせて左が持つ。"""
    f = lay.frame
    rows = lay.rows()
    half = lay.seam_offsets()[0] + grow
    out = []
    for r, y in enumerate(rows):
        y1 = f[3] + 1.0 if r == 0 else y + UNIT / 2 + half
        y0 = f[1] - 1.0 if r == len(rows) - 1 else y - UNIT / 2 - half
        out.append(_rect2d((f[0] - 1.0, y0, lay.s.FRAME_SPLIT[r] + half, y1)))
    return _union(out)


SEAM_CRUMB_MAX = 2.0        # mm3。継ぎ目で切り離される穴の角の三角（1 個 0.6）より大きな塊が出たら落とす


def _stretch_left(v, d):
    """立体 v と、それを左下・左上へ d ずらした物の和（隙を埋めて左のリブに付ける）。"""
    return _union([v, Pos(-d, 0, 0) * v, Pos(-d, d, 0) * v, Pos(-d, -d, 0) * v, Pos(0, d, 0) * v, Pos(0, -d, 0) * v])


@lru_cache(maxsize=None)
def frame_halves(with_feet=None):
    """{"left": 立体, "right": 立体}。右は左から FRAME_SEAM_GAP 離す。"""
    full = frame_full(with_feet)
    z0, h = -1.0, S.FRAME_UNDER + S.FRAME_T + 2.0
    left = full & (Pos(0, 0, z0) * extrude(left_region(LAY), h))
    right = full - (Pos(0, 0, z0) * extrude(left_region(LAY, S.FRAME_SEAM_GAP), h))
    # 継ぎ目の列の穴の角（R2.25 の丸みの外の三角）は、左のリブ 2 本に挟まれて右から切り離される。つばの角が掛かる所なので
    # 捨てずに左へ付ける（左のリブと面で接する → 隙の分 FRAME_SEAM_GAP だけ左へ寄せて重ねる）
    solids = sorted(right.solids(), key=lambda v: -v.volume)
    crumbs = [v for v in solids[1:]]
    if any(v.volume > SEAM_CRUMB_MAX for v in crumbs):
        raise RuntimeError(f"右の枠が大きな塊に分かれた: {[round(v.volume, 1) for v in solids]}")
    for v in crumbs:
        left = left + _stretch_left(v, S.FRAME_SEAM_GAP + 2 * EPS)
    left, right = left.clean(), solids[0]
    if len(left.solids()) != 1:
        raise RuntimeError(f"左の枠が {len(left.solids())} 個の塊に分かれた")
    return {"left": left, "right": right}


def frame_print(part):
    """刷る向き（上面をベッドに）。"""
    return P.flip_to_bed(part)


# ---------------------------------------------------------------------------
# キャップ
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def cap_shape(w_u):
    """幅 w_u のキャップ（マスの中心が原点・掛かった位置）。試し刷りと同じ形（つば F）。"""
    return P.cap(P.Cell(0.0, 0.0, S.HOLE_B, w_u=w_u), S)


def cap_counts(lay=LAY):
    out = {}
    for k in lay.keys:
        out[k.w] = out.get(k.w, 0) + 1
    return out


def descent_max(s=S):
    return P.levels(s)["descent_max"]


def cap_pose(k, mode, lay=LAY, s=S, descent=None):
    """キー k のキャップを置いた立体。mode:
      "latched"  掛かった位置（いちばん上）
      "pressed"  まっすぐ押し切り（公差の端: ステムがいちばん低く・ON までがいちばん長く・底を突くまで）
      "+x" "-x" "+y" "-y"  その縁を押し切った傾き。反対側のつばの外の縁（掛かる面の高さ）を支点に、真ん中が descent だけ沈むまで回す。
                 **真ん中のスイッチの本体は無いものとして回す**（実物は本体の角に当たって、ここまでは傾かない = 安全側）
    """
    cap = cap_shape(k.w)
    d = descent_max(s) if descent is None else descent
    if mode == "latched":
        return Pos(k.x, k.y, 0) * cap
    if mode == "pressed":
        return Pos(k.x, k.y, -d) * cap
    lv = P.levels(s)
    c = P.Cell(0.0, 0.0, s.HOLE_B, w_u=k.w)
    hw, hd = P.hole_size(c)
    axis, sgn = mode[1], (1 if mode[0] == "+" else -1)
    reach = (hw if axis == "x" else hd) / 2 + s.TAB_REACH
    th = math.degrees(math.atan2(d, reach))
    if axis == "x":
        piv = Pos(-sgn * reach, 0, lv["latch"])
        rot = Rot(0, sgn * th, 0)
    else:
        piv = Pos(0, -sgn * reach, lv["latch"])
        rot = Rot(-sgn * th, 0, 0)
    return Pos(k.x, k.y, 0) * piv * rot * piv.inverse() * cap


POSES = ("pressed", "+x", "-x", "+y", "-y")


def caps_plates(lay=LAY, s=S, gap=2.5):
    """刷る板 {名前: 立体}。1u を 1 枚に、幅の広いキーを 1 枚に（刷る向き = 下面がベッド）。A1 mini に入るだけ並べる。"""
    def lay_out(widths):
        placed, x, y, row = [], 0.0, 0.0, 0.0
        for w in widths:
            c = P.Cell(0.0, 0.0, s.HOLE_B, w_u=w)
            part = P.cap_print_pose(c, cap_shape(w), s)
            size = part.bounding_box().size
            if x + size.X > s.PRINT_MAX:
                x, y, row = 0.0, y + row + gap, 0.0
            placed.append(Pos(x + size.X / 2, y + size.Y / 2, 0) * part)
            x += size.X + gap
            row = max(row, size.Y)
        return Compound(placed)
    n = cap_counts(lay)
    wide = [w for w in sorted(n, reverse=True) if w > 1.0 for _ in range(n[w])]
    return {"caps_1u": lay_out([1.0] * n[1.0]), "caps_wide": lay_out(wide)}


# ---------------------------------------------------------------------------
# 基板と、その上の物（組み立ての包絡）
# ---------------------------------------------------------------------------

def diode_at(k, lay=LAY):
    """キー k のダイオードの中心（spec.DIODE_OVERRIDE があればそれ。基板の生成器 foundry.pcb と同じ読み方）。"""
    dx, dy = SKRA_TACT.diode_offset
    dx, dy, _ = lay.p.diode_override("main").get(k.i, (dx, dy, 0))
    return (k.x + dx, k.y - dy)


def board_parts(lay=LAY):
    """基板の上の物 {名前: 立体}（スイッチ・電池を除く）。位置は spec と layout から。板の実物との突き合わせは tests。"""
    s = lay.s
    z = lay.z()
    out = {}
    for k in lay.keys:
        x, y = diode_at(k)
        out[f"D{k.i}"] = Pos(x, y, 0) * Box(*PART_BODY["D"], PART_H["D"], align=CEN_MIN)
    for ref, (x, y, deg) in s.PART_AT.items():
        kind = "U" if ref.startswith("U") else "D" if ref.startswith("D_") else ref[0]
        w, d = PART_BODY[kind]
        if deg % 180 == 90:
            w, d = d, w
        out[ref] = Pos(x, y, 0) * Box(w, d, PART_H[kind], align=CEN_MIN)
    out["U_MCU"] = _union([_box(lay.xiao_pads(), 0.0, z["xiao_body_top"]), _box(lay.usb_shell(), 0.0, z["usb_top"])])
    pads = lay.clip_pads()
    body = lay.clip_body()
    out["BT1"] = _union([_box(body, 0.0, z["clip_top"]), _box((pads[0][0], pads[0][1], pads[1][2], pads[1][3]), 0.0, 0.5)])
    pb = lay.psw_body()
    out["SW_PWR"] = _union([_box(pb, 0.0, z["psw_top"]), _box((pb[0] - 1.9, pb[1], pb[0] + EPS, pb[3]), 0.0, 0.6)])
    ks = lay.psw_knob_sweep()
    out["SW_PWR_knob"] = _box(ks, 0.2, 1.2)
    return out


def switch_solids(lay=LAY, stem=None, populated_only=True):
    """スイッチ {参照名: 立体}（本体 ＋ ステム。ステムの上面 stem。既定は名目）。"""
    s = lay.s
    stem = s.SW_STEM_TOP if stem is None else stem
    return {ref: P.standin(P.Cell(x, y, s.HOLE_B, standin=stem), s)
            for ref, x, y, pop in lay.switch_sites() if pop or not populated_only}


def cell_solid(lay=LAY, dy=0.0):
    (x, y), r = lay.cell()
    return Pos(x, y + dy, 0) * Cylinder(r, lay.s.CELL_T, align=CEN_MIN)


def pcb_solid(lay=LAY):
    p = lay.pcb
    s = lay.s
    board = Pos((p[0] + p[2]) / 2, (p[1] + p[3]) / 2, -s.PCB_T) * extrude(RectangleRounded(p[2] - p[0], p[3] - p[1], s.CORNER_R), s.PCB_T)
    holes = _union([Pos(c[0], c[1], -s.PCB_T - 1) * Cylinder(s.SCREW_HOLE_D / 2, s.PCB_T + 2, align=CEN_MIN) for _, c, _ in lay.screws()])
    return board - holes


def screw_solids(lay=LAY, with_feet=None):
    """ねじ {参照名: 立体}（頭は基板の下面・軸は上へ）。中の押さえは、足を付けるときだけ。"""
    s = lay.s
    with_feet = s.HOLDDOWN_FEET if with_feet is None else with_feet
    out = {}
    for ref, c, kind in lay.screws():
        if kind == "holddown" and not with_feet:
            continue
        length = s.SCREW_L if kind == "perimeter" else s.HOLDDOWN_SCREW_L
        out[ref] = _union([Pos(c[0], c[1], -s.PCB_T - s.SCREW_HEAD_H) * Cylinder(s.SCREW_HEAD_D / 2, s.SCREW_HEAD_H, align=CEN_MIN),
                           Pos(c[0], c[1], -s.PCB_T - EPS) * Cylinder(s.SCREW_D / 2, length + EPS, align=CEN_MIN)])
    return out


def sheet_solid(lay=LAY):
    """底のシート（基板の外形から 0.5 内側。ねじの頭の所に φ5 の穴）。"""
    p = click_layout.grow(lay.pcb, -0.5)
    s = lay.s
    z0 = -s.PCB_T - s.BOTTOM_SHEET_T
    sheet = Pos((p[0] + p[2]) / 2, (p[1] + p[3]) / 2, z0) * extrude(RectangleRounded(p[2] - p[0], p[3] - p[1], s.CORNER_R), s.BOTTOM_SHEET_T)
    holes = _union([Pos(c[0], c[1], z0 - 1) * Cylinder(s.SCREW_HEAD_D / 2 + 0.5, s.BOTTOM_SHEET_T + 2, align=CEN_MIN)
                    for _, c, kind in lay.screws() if kind == "perimeter"])
    return sheet - holes


def usb_plug(lay=LAY):
    """挿しきった USB-C プラグ（金属のシェルと樹脂）。樹脂は口から USB_SHELL_EXPOSED 外。"""
    s = lay.s
    usb = lay.usb_shell()
    y = s.XIAO_AT[1]
    zc = s.XIAO_USB_Z + s.XIAO_SOLDER_T
    w, h = s.USB_PLUG_SHELL
    out_x = usb[0] - s.USB_SHELL_EXPOSED
    shell = _box((out_x, y - w / 2, usb[0] + 6.0, y + w / 2), zc - h / 2, zc + h / 2)
    body = _box((out_x - 20.0, y - s.USB_PLUG_BODY_W / 2, out_x, y + s.USB_PLUG_BODY_W / 2),
                zc - s.USB_PLUG_BODY_H / 2, zc + s.USB_PLUG_BODY_H / 2)
    return shell, body


# ---------------------------------------------------------------------------
# 重さ（計算）
# ---------------------------------------------------------------------------
PLA_DENSITY = 1.24e-3        # g/mm3（PLA の一般値 1.24 g/cm3）
FR4_DENSITY = 1.85e-3        # g/mm3（FR-4 の一般値）


def weights(lay=LAY, fill=None):
    """重さの見積もり [g]（部品ごと）。枠は中まで詰まるほど薄いので体積 × 密度。キャップは中が 15% の充填だが、
    壁 3 本・上 7 層・下 5 層で厚さ 2.4 の大半が詰まる → 体積 × 密度 × CAP_FILL（スライスの結果で直す）。"""
    s = lay.s
    halves = frame_halves()
    n = cap_counts(lay)
    caps = sum(cap_shape(w).volume * c for w, c in n.items())
    out = {
        "枠（左）": halves["left"].volume * PLA_DENSITY,
        "枠（右）": halves["right"].volume * PLA_DENSITY,
        "キャップ 62 個": caps * PLA_DENSITY * (1.0 if fill is None else fill),
        "基板": pcb_solid(lay).volume * FR4_DENSITY,
        "スイッチ 62 個": 62 * 0.12, "ダイオードほか": 0.6, "XIAO": 3.0, "電池クリップ": 0.6, "CR1632": 1.9,
        "ねじ 20 本": 20 * 0.09, "底のシート": sheet_solid(lay).volume * 1.2e-3,
    }
    out["合計"] = sum(out.values())
    return out


# ---------------------------------------------------------------------------
# 書き出し
# ---------------------------------------------------------------------------

def printables():
    """刷る物（STL の名前 → 刷る向きの立体）。"""
    halves = frame_halves()
    out = {f"frame_{side}": frame_print(halves[side]) for side in SIDES}
    out.update(caps_plates())
    for w in CAP_WIDTHS:
        c = P.Cell(0.0, 0.0, S.HOLE_B, w_u=w)
        out[f"cap_{str(w).replace('.', '_')}u"] = P.cap_print_pose(c, cap_shape(w), S)
    return out


def assembly(exploded=0.0, stem=None):
    """組んだ状態 {グループ: [(名前, 立体)]}。exploded > 0 で上下に離す。"""
    halves = frame_halves()
    lay = LAY
    rest = (S.SW_STEM_TOP if stem is None else stem) - P.levels(S)["pad"]
    e = exploded
    out = {
        "frame_left": [("frame_left", Pos(0, 0, 3 * e) * halves["left"])],
        "frame_right": [("frame_right", Pos(0, 0, 3 * e) * halves["right"])],
        "caps": [(f"cap_{k.i}", Pos(0, 0, 2 * e + min(0.0, rest)) * cap_pose(k, "latched")) for k in lay.keys],
        "pcb": [("pcb", pcb_solid(lay))],
        "switches": [(n, Pos(0, 0, 0) * v) for n, v in switch_solids(lay, stem).items()],
        "parts": [(n, v) for n, v in board_parts(lay).items() if n not in ("U_MCU", "BT1")],
        "xiao": [("U_MCU", board_parts(lay)["U_MCU"])],
        "battery": [("BT1", board_parts(lay)["BT1"]), ("cell", cell_solid(lay, -1.5 * e))],
        "screws": [(n, Pos(0, 0, -2 * e) * v) for n, v in screw_solids(lay).items()],
        "sheet": [("sheet", Pos(0, 0, -e) * sheet_solid(lay))],
    }
    return out


def export(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    made = {}
    for stem, part in printables().items():
        size = part.bounding_box().size
        assert max(size.X, size.Y) <= S.PRINT_MAX, f"{stem}: {size.X:.1f} × {size.Y:.1f} が A1 mini に置けない"
        export_stl(part, str(out / f"{stem}.stl"))
        made[stem] = (size.X, size.Y, size.Z)
    asm = out / "assembly_main"
    asm.mkdir(exist_ok=True)
    for old in asm.glob("*.stl"):
        old.unlink()
    style = {}
    for tag, e in (("asm", 0.0), ("exploded", 8.0)):
        for group, items in assembly(e).items():
            export_stl(Compound([v for _, v in items]), str(asm / f"{tag}__{group}.stl"))
            style[f"{tag}__{group}"] = (COLORS[group], 1.0)
    (asm / "style.json").write_text(json.dumps(style))
    return made, style


def export_blend(style, out=OUT):
    """組んだ状態と分解した状態を .blend にする。**Blender は失敗しても 0 を返す**ので「OK <数>」とできたファイルで判定する。"""
    if not Path(paths.BLENDER).exists():
        return None
    r = subprocess.run([paths.BLENDER, "-b", "-P", str(HERE / "tools" / "blend_main.py")],
                       capture_output=True, text=True, timeout=1800)
    ok = [line for line in r.stdout.splitlines() if line.startswith("OK ")]
    n = int(ok[-1].split()[1]) if ok else 0
    asm = out / "assembly_main"
    files = [asm / "cckb-click.blend", asm / "cckb-click_assembled.png", asm / "cckb-click_exploded.png"]
    assert n == len(style) and all(f.exists() for f in files), r.stdout[-2000:] + r.stderr[-2000:]
    return files


def main():
    import click_case_figs

    made, style = export()
    for stem, size in sorted(made.items()):
        print(f"OK {stem}.stl  {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}")
    for name, g in weights().items():
        print(f"   {name}: {g:.1f} g")
    for p in click_case_figs.render_all(OUT):
        print("絵", p)
    b = export_blend(style)
    print("Blender:", *(b or ["無い（BLENDER の場所: foundry/paths.py）"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
