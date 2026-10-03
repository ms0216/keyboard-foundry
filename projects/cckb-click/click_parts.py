"""cckb-click のキャップ・枠・基板の代わりの板（build123d）。**寸法は持たない**（spec.py）。

方式と寸法の出どころは Salicylic_acid3 さんの ClickBoard / 公開データ（LICENSE）。**公開 STEP は写していない**——
測った寸法（spec.py の各行）から、FDM で刷れる形をここで作り直している。変えた所:

  本番の形 "F"（つば）  販売者の足（枠の下に 1.5 出て、上面が枠の下面に掛かる）を、キャップの下面と同じ面にある
      厚さ TAB_T のつばに変え、枠の下面に掘ったくぼみ（深さ POCKET_DEPTH）の底に掛ける。
      **下面をベッドに刷る**ので、押す面（キャップの下面の全部）はベッドの面、掛かる面はつばの上面
      （2 層目の上向きの面）になり、どちらも宙に張り出さない（R4）。販売者が「バリで動作不良」と書いた面を
      支え無しで刷らないための形。押す面は φ3 の当て面ではなく下面の全部（スイッチの本体より上にある）
  比べる形 "S" "C"     販売者と同じ「枠の下に足が出る」形（上面をベッドに刷る）。S は平らな掛かる面（宙に張り出す）、
      C はそれを 45° の斜面にした物。試し刷り「掛かり方」で F と比べるためだけにある

座標: キーの中心が原点・基板の上面が z = 0・上が +Z。キャップは**掛かった位置**（一番上）で作る。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

from build123d import (Align, Axis, Box, Cylinder, Kind, Polygon, Pos, Rectangle, RectangleRounded,
                       Rot, chamfer, extrude, offset)

from foundry.layout import UNIT
from foundry.project import load

HERE = Path(__file__).resolve().parent
S = load(HERE).spec

MIN = (Align.MIN, Align.MIN, Align.MIN)
CEN_MIN = (Align.CENTER, Align.CENTER, Align.MIN)
LATCHES = ("F", "S", "C")
EPS = 0.01                   # 足し合わせる立体どうしを重ねる量（面の一致で継ぎ目が残らないように）


# ---------------------------------------------------------------------------
# 高さ（spec から導く）
# ---------------------------------------------------------------------------

def levels(s=S, latch="F", tab=None):
    """高さの表（基板の上面 = 0）。tab = つばの厚さ（F）または首の高さ（S・C）。"""
    tab = s.TAB_T if tab is None else tab
    frame_top = s.FRAME_UNDER + s.FRAME_T
    if latch == "F":
        latch_z = s.FRAME_UNDER + s.POCKET_DEPTH     # くぼみの底
        pad = latch_z - tab
    else:
        latch_z = s.FRAME_UNDER                      # 枠の下面
        pad = latch_z + tab
    stem_max = s.SW_STEM_TOP + s.SW_STEM_TOP_TOL
    stem_min = s.SW_STEM_TOP - s.SW_STEM_TOP_TOL
    # 掛かった位置から押し切りまで、キャップが下がる最大（ステムが一番低く、ON までが一番長く、そのあと底を突く）
    descent = (pad - stem_min) + s.SW_TRAVEL + s.SW_TRAVEL_TOL + s.SW_OVERTRAVEL
    return dict(frame_under=s.FRAME_UNDER, frame_top=frame_top, cap_top=frame_top + s.CAP_ABOVE_FRAME,
                latch=latch_z, pad=pad, stem_min=stem_min, stem_max=stem_max,
                float_nominal=pad - s.SW_STEM_TOP, float_max=pad - stem_min, preload_max=stem_max - pad,
                descent_max=descent, pad_lowest=pad - descent)


def on_layer(z, s=S, first=None):
    """ベッドからの高さ z が層の境目か: 0（ベッド）か、1 層目（first。既定は PRINT_FIRST_LAYER）＋ 層の倍数。"""
    first = s.PRINT_FIRST_LAYER if first is None else first
    if abs(z) < 1e-6:
        return True
    n = (z - first) / s.PRINT_LAYER
    return n > -1e-6 and abs(n - round(n)) < 1e-6


def print_heights(s=S, latch="F", tab=None):
    """機能する面の、**刷る向きでのベッドからの高さ**（名前 → 高さ）。全部が層の倍数であること（R4）。
    F は下面がベッド（押す面 = 0）。S・C は上面がベッド。枠は上面がベッド。"""
    lv = levels(s, latch, tab)
    out = {"枠の下面": lv["frame_top"] - lv["frame_under"], "柱の先": lv["frame_top"]}
    if latch == "F":
        out.update({"くぼみの底": lv["frame_top"] - lv["latch"], "つばの上面（掛かる面）": lv["latch"] - lv["pad"],
                    "キャップの上面": lv["cap_top"] - lv["pad"]})
    else:
        out.update({"押す面": lv["cap_top"] - lv["pad"], "掛かる面": lv["cap_top"] - lv["latch"],
                    "足の先": lv["cap_top"] - lv["latch"] + s.FOOT_H})
    return out


# ---------------------------------------------------------------------------
# 平面の形
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    """枠の 1 マス。cx, cy = キーの中心。hole = その案の 1u の穴。step = 穴を広げる量。
    latch = 掛かり方（F / S / C）。tab = つばの厚さ（F）・首の高さ（S・C）。standin = スイッチの代わりの台の高さ（None = 無し）。
    dots = 枠の上面に彫る点の数（0 = 無し）。back = 点を奥の縁に彫る。"""
    cx: float
    cy: float
    hole: tuple
    w_u: float = 1.0
    step: float = 0.0
    latch: str = "F"
    tab: float | None = None
    standin: float | None = None
    dots: int = 0
    back: bool = False


def hole_size(c):
    """穴の大きさ (x, y)。幅の広いキーはリブの幅を 1u と同じに保つ。"""
    return (c.hole[0] + (c.w_u - 1.0) * UNIT + c.step, c.hole[1] + c.step)


def rib(c):
    """そのマスの穴とマスの境目の間（x, y）= リブの半分。"""
    w, d = hole_size(c)
    return ((c.w_u * UNIT - w) / 2, (UNIT - d) / 2)


def body_plan(c, s=S):
    """キャップの胴（穴を広げる前の穴から、片側 CAP_CLEAR 引く）。"""
    w, d = hole_size(replace(c, step=0.0))
    return RectangleRounded(w - 2 * s.CAP_CLEAR, d - 2 * s.CAP_CLEAR, s.HOLE_R - s.CAP_CLEAR)


def hole_plan(c, s=S, grow=0.0):
    w, d = hole_size(c)
    return RectangleRounded(w + 2 * grow, d + 2 * grow, s.HOLE_R + grow)


def corners(w, d, length):
    """穴 w × d の四隅から、辺に沿って length の範囲（外へは十分広い）。"""
    big = length + 4.0
    out = None
    for sx in (-1, 1):
        for sy in (-1, 1):
            r = Pos(sx * (w / 2 - length + big / 2), sy * (d / 2 - length + big / 2)) * Rectangle(big, big)
            out = r if out is None else out + r
    return out


def reach_of(c, s=S):
    """穴の縁から外へ出る量。つば（F）は TAB_REACH、比べる形の足（S・C）は FOOT_REACH。"""
    return s.TAB_REACH if c.latch == "F" else s.FOOT_REACH


def tab_plan(c, s=S, grow=0.0, uniform=False):
    """つば（足）の平面: 穴を TAB_REACH 外へ広げた矩形（角の丸み TAB_R）の、四隅だけ。穴を広げる前の穴で決める（キャップは 1 種類）。
    角の丸みを穴の角より小さくするので、穴の角の外に掛かりができる（斜めにずれ切っても残る）。
    grow でくぼみ（つば ＋ POCKET_CLEAR）にする。uniform=True は穴を一様に広げた形（45° の足 C: 斜面を全周で同じ傾きにするため）。"""
    n = replace(c, step=0.0)
    w, d = hole_size(n)
    if uniform:
        return hole_plan(n, s, reach_of(c, s) + grow) & corners(w, d, s.TAB_LEN + grow)
    r = reach_of(c, s) + grow
    return RectangleRounded(w + 2 * r, d + 2 * r, s.TAB_R + grow) & corners(w, d, s.TAB_LEN + grow)


def neck_plan(c, s=S):
    """首（S・C）: 胴の四隅。"""
    w, d = hole_size(replace(c, step=0.0))
    return body_plan(c, s) & corners(w, d, s.TAB_LEN)


def _area(sk):
    return sum(f.area for f in sk.faces()) if sk is not None else 0.0


def latch_overlap(c, s=S, dx=0.0, dy=0.0):
    """掛かっている面積（つば 1 個あたりの最小）。キャップを (dx, dy) ずらしたとき、つばのうち穴の外にある分。"""
    tabs = Pos(dx, dy) * tab_plan(c, s, uniform=(c.latch == "C"))
    out = tabs - hole_plan(c, s)
    areas = sorted(f.area for f in out.faces())
    return areas[0] if len(areas) >= 4 else 0.0


def side_gap(c, s=S):
    """胴と穴の隙（片側・x, y）。**形から測る**（作った断面の外接の差）。"""
    b = body_plan(c, s).bounding_box()
    h = hole_plan(c, s).bounding_box()
    return ((h.size.X - b.size.X) / 2, (h.size.Y - b.size.Y) / 2)


# ---------------------------------------------------------------------------
# キャップ
# ---------------------------------------------------------------------------

def _dots(n, x, y, z0, z1, s=S):
    d, _, pitch = s.COUPON_DOT
    return [Pos(x + (k - (n - 1) / 2) * pitch, y, z0) * Cylinder(d / 2, z1 - z0, align=CEN_MIN) for k in range(n)]


def _fuse(shapes):
    shapes = list(shapes)
    out = shapes[0]
    if len(shapes) > 1:
        out = out.fuse(*shapes[1:])
    return out.clean()


def cap(c, s=S, dots=0):
    """キャップ 1 個（マスの中心が原点・掛かった位置）。dots = 上面に彫る点の数（見分け用）。"""
    lv = levels(s, c.latch, c.tab)
    tab = s.TAB_T if c.tab is None else c.tab
    h = lv["cap_top"] - lv["pad"]
    body = extrude(body_plan(c, s), h)
    body = chamfer(body.edges().group_by(Axis.Z)[-1], s.CAP_TOP_CHAMFER)
    if c.latch == "F":
        # 下面をベッドに刷る。胴とつばの下の縁を面取りして、1 層目の太り（象の足）が穴・くぼみに擦れないようにする
        # （A1 mini の既定は象の足の補正 0。S・C は下面が刷る向きの上なので要らない）
        low = _fuse([body, extrude(tab_plan(c, s), tab)])
        return _finish(Pos(0, 0, lv["pad"]) * chamfer(low.edges().group_by(Axis.Z)[0], s.CAP_BOTTOM_CHAMFER), c, s, dots, lv)
    parts = [Pos(0, 0, lv["pad"]) * body]
    foot_bottom = lv["latch"] - s.FOOT_H
    if c.latch == "S":
        neck_bottom = lv["latch"]
        parts.append(Pos(0, 0, foot_bottom) * extrude(tab_plan(c, s), s.FOOT_H))
    else:
        # 45° の斜面: 首（胴と同じ断面）から足（穴 ＋ FOOT_REACH）まで、横に CAP_CLEAR ＋ FOOT_REACH 広がる。
        # 穴の縁（枠の下面の角）に当たるのは、斜面が首から CAP_CLEAR 広がった所 = 斜面の上端から CAP_CLEAR 下
        fh = s.CAP_CLEAR + s.FOOT_REACH
        neck_bottom = lv["latch"] + s.CAP_CLEAR
        n = replace(c, step=0.0)
        w, d = hole_size(n)
        cone = extrude(hole_plan(n, s, s.FOOT_REACH), fh, taper=45.0)
        cone = cone & extrude(corners(w, d, s.TAB_LEN), fh)
        parts.append(Pos(0, 0, neck_bottom - fh) * cone)
        parts.append(Pos(0, 0, foot_bottom) * extrude(tab_plan(c, s, uniform=True), neck_bottom - fh - foot_bottom))   # 斜面の下端と面で接する（重ねると 0.01 の段が残る）
    parts.append(Pos(0, 0, neck_bottom - EPS) * extrude(neck_plan(c, s), lv["pad"] - neck_bottom + 2 * EPS))
    return _finish(_fuse(parts), c, s, dots, lv)


def seam_notch(y_face, z0, z1, s=S):
    """継ぎ目の溝を切る立体: 辺の真ん中（x = 0）・面 y = y_face から −Y へ SEAM_NOTCH の深さ（+Y 側は十分に外まで）。"""
    w, d = s.SEAM_NOTCH
    return Pos(0, y_face - d, z0) * Box(w, d + 1.0, z1 - z0, align=(Align.CENTER, Align.MIN, Align.MIN))


def _finish(out, c, s, dots, lv):
    """胴の奥の面に継ぎ目の溝を切り、上面に見分ける点を彫る。"""
    if s.SEAM_NOTCH:
        bd = body_plan(c, s).bounding_box().size.Y
        out = out - seam_notch(bd / 2, lv["pad"] - EPS, lv["cap_top"] + EPS, s)
    if dots:
        bd = body_plan(c, s).bounding_box().size.Y
        y = -(bd / 2 - s.CAP_TOP_CHAMFER - s.COUPON_DOT[0])
        out = out - _fuse(_dots(dots, 0.0, y, lv["cap_top"] - s.COUPON_DOT[1], lv["cap_top"] + 1.0, s))
    return out.clean()


def cap_print_pose(c, part, s=S):
    """刷る向き。F は下面（押す面）をベッドに、S・C は上面をベッドに。"""
    if c.latch != "F":
        part = Rot(180, 0, 0) * part
    bb = part.bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * part


# ---------------------------------------------------------------------------
# 枠
# ---------------------------------------------------------------------------

def key_bounds(cells, extra_u=0.0):
    """マスの並びの外接（キー領域）。extra_u = 右へ足す空きの幅（帯の端）。"""
    x0 = min(c.cx - c.w_u * UNIT / 2 for c in cells)
    x1 = max(c.cx + c.w_u * UNIT / 2 for c in cells) + extra_u * UNIT
    y0 = min(c.cy - UNIT / 2 for c in cells)
    y1 = max(c.cy + UNIT / 2 for c in cells)
    return (x0, y0, x1, y1)


def outline_plan(bounds, s=S, grow=0.0):
    """枠の外形（キー領域 ＋ 余白。左手前の角を落として向きの印にする）。grow で外へ広げる（板・立ち上がり）。"""
    x0, y0 = bounds[0] - s.PLATE_MARGIN_X, bounds[1] - s.PLATE_MARGIN_Y
    x1, y1 = bounds[2] + s.PLATE_MARGIN_X, bounds[3] + s.PLATE_MARGIN_Y
    m = s.COUPON_MARK_CHAMFER
    sk = Polygon((x0 + m, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 + m), align=None)
    return offset(sk, grow, kind=Kind.INTERSECTION) if grow else sk


def rib_posts(cells, s=S, border=False):
    """柱の位置 [(x, y, x の長さ, y の長さ)]。リブの中点: 横に隣り合うマスの間と、すぐ奥にマスがある所。
    border=True なら手前・奥の縁の下にも（壁を付けない帯で使う）。"""
    out = []
    for a in cells:
        for b in cells:
            if abs(b.cy - a.cy) < 1e-6 and abs((b.cx - b.w_u * UNIT / 2) - (a.cx + a.w_u * UNIT / 2)) < 1e-6:
                out.append((a.cx + a.w_u * UNIT / 2, a.cy, s.POST_W, s.POST_L))
            if abs(b.cy - a.cy - UNIT) < 1e-6:
                lo = max(a.cx - a.w_u * UNIT / 2, b.cx - b.w_u * UNIT / 2)
                hi = min(a.cx + a.w_u * UNIT / 2, b.cx + b.w_u * UNIT / 2)
                if hi - lo > s.POST_L:
                    out.append(((lo + hi) / 2, a.cy + UNIT / 2, s.POST_L, s.POST_W))
    if border:
        ys = sorted({c.cy for c in cells})
        for c in cells:
            if c.cy == ys[0]:
                out.append((c.cx, c.cy - UNIT / 2 - s.PLATE_MARGIN_Y / 2, s.POST_L, s.POST_W))
            if c.cy == ys[-1]:
                out.append((c.cx, c.cy + UNIT / 2 + s.PLATE_MARGIN_Y / 2, s.POST_L, s.POST_W))
    return sorted(set(out))


def frame(cells, s=S, wall=True, extra_u=0.0, posts=None):
    """枠（穴・上の縁の面取り・F のくぼみ・柱・見分ける点）。wall=True なら外周に基板まで下りる壁。"""
    lv = levels(s)
    bounds = key_bounds(cells, extra_u)
    outline = outline_plan(bounds, s)
    body = [Pos(0, 0, s.FRAME_UNDER) * extrude(outline, s.FRAME_T)]
    if wall:
        inner = Pos((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2) * Rectangle(bounds[2] - bounds[0],
                                                                                         bounds[3] - bounds[1])
        body.append(extrude(outline - inner, s.FRAME_UNDER + EPS))
    posts = rib_posts(cells, s, border=not wall) if posts is None else posts
    for x, y, lx, ly in posts:
        body.append(Pos(x, y, 0) * Box(lx, ly, s.FRAME_UNDER + EPS, align=CEN_MIN))
    cuts = []
    ch = s.HOLE_CHAMFER
    y_front, y_back = bounds[1] - s.PLATE_MARGIN_Y, bounds[3] + s.PLATE_MARGIN_Y
    for c in cells:
        at = Pos(c.cx, c.cy)
        cuts.append(at * Pos(0, 0, -1.0) * extrude(hole_plan(c, s), lv["frame_top"] + 2.0))
        cuts.append(at * Pos(0, 0, lv["frame_top"] - ch) * extrude(hole_plan(c, s), ch + EPS, taper=-45.0))
        if c.latch == "F":
            cuts.append(at * Pos(0, 0, -1.0) * extrude(tab_plan(c, s, s.POCKET_CLEAR), lv["latch"] + 1.0))
        if s.SEAM_NOTCH:                              # 穴の奥の壁の継ぎ目の溝（枠の厚さの中だけ。柱は切らない）。壁の外へ掘る
            d = hole_size(c)[1]                       # 見分ける点は手前の縁にある（奥の列だけ奥。溝との間に 0.6 残る）
            cuts.append(at * Pos(0, d / 2 - 0.5, s.FRAME_UNDER) * Box(s.SEAM_NOTCH[0], s.SEAM_NOTCH[1] + 0.5, s.FRAME_T + EPS,
                                                                       align=(Align.CENTER, Align.MIN, Align.MIN)))
        if c.dots:
            edge = (rib(c)[1] + s.PLATE_MARGIN_Y - ch) / 2          # 縁（外形から穴の面取りまで）の真ん中
            y = (y_back - edge) if c.back else (y_front + edge)
            cuts += _dots(c.dots, c.cx, y, lv["frame_top"] - s.COUPON_DOT[1], lv["frame_top"] + 1.0, s)
    return (_fuse(body) - _fuse(cuts)).clean()


def flip_to_bed(part):
    """上面をベッドに（枠・S / C のキャップ）。"""
    part = Rot(180, 0, 0) * part
    bb = part.bounding_box()
    return Pos(-bb.min.X, -bb.min.Y, -bb.min.Z) * part


# ---------------------------------------------------------------------------
# 基板の代わりの板（スイッチの代わりの台つき）
# ---------------------------------------------------------------------------

def standin(c, s=S):
    """スイッチの代わり: 本体（SW_BODY 角 × SW_BODY_H）＋ステム（φ SW_STEM_D・上面 = c.standin）。"""
    return _fuse([Pos(c.cx, c.cy, 0) * Box(s.SW_BODY, s.SW_BODY, s.SW_BODY_H, align=CEN_MIN),
                  Pos(c.cx, c.cy, s.SW_BODY_H - EPS) * Cylinder(s.SW_STEM_D / 2, c.standin - s.SW_BODY_H + EPS,
                                                                align=CEN_MIN)])


def base(cells, s=S, extra_u=0.0, bumps=None):
    """基板の代わりの板（厚さ COUPON_BASE_T・上面 z = 0）。縁の立ち上がりで枠の位置を決める。
    bumps = {マスの番号: 点の数}（台の手前に盛る点。高さの見分け）。"""
    gap, lip_w, lip_h = s.COUPON_LIP
    bounds = key_bounds(cells, extra_u)
    outer = outline_plan(bounds, s, gap + lip_w)
    parts = [Pos(0, 0, -s.COUPON_BASE_T) * extrude(outer, s.COUPON_BASE_T),
             Pos(0, 0, -EPS) * extrude(outer - outline_plan(bounds, s, gap), lip_h + EPS)]
    for i, c in enumerate(cells):
        if c.standin is not None:
            parts.append(standin(c, s))
        n = (bumps or {}).get(i, 0)
        if n:
            parts += _dots(n, c.cx, c.cy - s.SW_BODY / 2 - 2.0, -EPS, s.COUPON_DOT[1], s)
    return _fuse(parts)


def gauge_block(s=S):
    """測る塊（刷る向き・下面がベッド）: 外寸 SIDE 角 × H。+X 側に、つばと同じ厚さの段（ノギスで厚さを測る）。
    下の縁はキャップと同じ面取り（1 層目の太りがノギスに当たらないように）。**X は段より上で測る。**"""
    side, h, ledge = s.COUPON_GAUGE
    low = _fuse([Box(side, side, h, align=CEN_MIN),
                 Pos(side / 2 - EPS, 0, 0) * Box(ledge + EPS, side, s.TAB_T, align=(Align.MIN, Align.CENTER, Align.MIN))])
    return chamfer(low.edges().group_by(Axis.Z)[0], s.CAP_BOTTOM_CHAMFER).clean()


def gauge_slot(x, y, s=S):
    """枠に開ける測る穴（内寸 SIDE 角・貫通）を切る立体。上の縁（刷るときのベッド側）はキーの穴と同じ面取り。"""
    side = s.COUPON_GAUGE[0]
    top, ch = s.FRAME_UNDER + s.FRAME_T, s.HOLE_CHAMFER
    return _fuse([Pos(x, y, -1.0) * extrude(Rectangle(side, side), top + 2.0),
                  Pos(x, y, top - ch) * extrude(Rectangle(side, side), ch + EPS, taper=-45.0)])


def to_bed(part):
    bb = part.bounding_box()
    return Pos(-bb.min.X, -bb.min.Y, -bb.min.Z) * part


# ---------------------------------------------------------------------------
# 幅の広いキーの端を押したとき（剛体）
# ---------------------------------------------------------------------------

def end_press(c, s=S, press_in=0.4):
    """キーの端を押したときの幾何（剛体・遠い側のつばの外の縁を支点に回る）。

    中心のスイッチが ON になる最大（SW_TRAVEL ＋ TOL）まで沈むとき:
      angle     傾き [度]（スイッチの許す押す面の傾き SW_PUSH_ANGLE_MAX と比べる）
      near_drop 押した側の下の縁が下がる量（押す面の高さ − これ が基板の上の物より上か）
      shift     遠い側の胴が、枠の上面の高さで横へ動く量（胴と穴の隙の中か）
      force_ratio 指の力 ÷ スイッチの力（てこ）
    press_in = 指が端から内側に入る量。"""
    lv = levels(s, c.latch, c.tab)
    w, _ = hole_size(replace(c, step=0.0))
    pivot = w / 2 + reach_of(c, s)                   # 支点（中心から）
    d = s.SW_TRAVEL + s.SW_TRAVEL_TOL
    th = math.atan2(d, pivot)
    body_half = w / 2 - s.CAP_CLEAR
    finger = body_half - press_in
    return dict(angle=math.degrees(th), near_drop=(pivot + body_half) * math.tan(th),
                shift=(lv["frame_top"] - lv["latch"]) * math.sin(th) + (pivot - body_half) * (1 - math.cos(th)),
                force_ratio=pivot / (pivot + finger), pivot=pivot)
