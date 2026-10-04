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
  右手前の角  電源スイッチのつまみは枠の外へ出ない（先は外面の 0.6 内）。右の壁を上まで切り欠いて、指か爪で動かす（click_layout.psw_notch）。
          電池は手前の壁の口（上から下まで抜いた溝）から抜き差しする。**蓋（cover_solid）は道具なしで付け外しする落とし込み式**
          （2026-10-04 利用者の決定・決定記録 2026-10-04-cover-latch）: 上からまっすぐ落とす。左右の耳が口の壁の縦の溝に入り、電池が手前へ押す力は
          溝の手前の壁が受ける。手前の面の棒 2 本の先が、口の角の歯（枠）の下に入って、上へ抜けない。棒の真ん中を押し込みながら持ち上げて外す。
          **電池を手前へ止める物は蓋だけ**（open-gaps P25）。基板の穴 H30・H31 は使わない
  試し刷り  ねじ（screw_coupon）と右手前の角（corner_coupon = 蓋の試し刷り・蓋 3 つ）。どちらも本番の枠の立体から切り出す
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
CAP_LAND_BODY = (3.4, 1.8)   # 1206 の外形の最大（3.2 ± 0.2 × 1.6 ± 0.2）
COLORS = {"frame_left": "#9aa0a6", "frame_right": "#b0b6bc", "pcb": "#2f7d32", "caps": "#e8c9a0", "switches": "#303030",
          "parts": "#8a5a2b", "xiao": "#1f4e9c", "battery": "#c8c8c8", "cover": "#e08a3c", "screws": "#d0a000", "sheet": "#202020"}


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


def _prism_y(pts_xz, y0, y1):
    """x–z の多角形（反時計回り）を y0〜y1 へ押し出した立体。"""
    v = extrude(Polygon(*pts_xz, align=None), y1 - y0)            # (x, z, h)
    return Pos(0, y1, 0) * Rot(90, 0, 0) * v                      # → (x, −h, z) を y1 から手前へ


def _prism_x(pts_yz, x0, x1):
    """y–z の多角形（反時計回り）を x0〜x1 へ押し出した立体。"""
    v = extrude(Polygon(*pts_yz, align=None), x1 - x0)            # (y, z, h)
    return Pos(x0, 0, 0) * Rot(0, 0, 90) * Rot(90, 0, 0) * v      # → (h, y, z)


def outline2d(lay=LAY):
    f = lay.frame
    r = lay.s.CORNER_R + lay.s.PCB_INSET_X
    return Pos((f[0] + f[2]) / 2, (f[1] + f[3]) / 2) * RectangleRounded(f[2] - f[0], f[3] - f[1], r)


# ---------------------------------------------------------------------------
# 枠の下の構造（基板の上 0〜3.0）: 壁・ねじの所の厚い壁・柱・（中の押さえの足）。**部品として持つ**（干渉の検査が 1 個ずつ見る）
# ---------------------------------------------------------------------------

def screw_boss(c, lay=LAY):
    """外周のねじの所で、壁を内へ厚くする矩形（キー領域の端から穴の縁まで。角ではその先へ 0.5）。
    幅は click_layout.boss_half（奥と手前の壁・1u のキーの脇は ± SCREW_BOSS_HALF、幅の広いキーの脇は ± SCREW_BOSS_HALF_SIDE）。"""
    s = lay.s
    f, a = lay.frame, lay.key_area
    x, y = c
    d = {"left": x - f[0], "right": f[2] - x, "front": y - f[1], "back": f[3] - y}
    side = min(d, key=d.get)
    h = lay.boss_half(c)
    depth = lay.rib() / 2
    in_corner = any(click_layout.rect_gap((x, y, x, y), lay.corner(side_)) < 6 for side_ in SIDES)
    if in_corner:
        depth, h = depth + 0.5, max(h, s.SCREW_BOSS_HALF_SIDE + 0.6)
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
    out += [("boss", screw_boss(c, lay)) for _, c, _ in lay.wall_screws()]
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

def psw_ceiling(lay=LAY):
    """電源スイッチの上の、枠の下面の高さ（本体の上 ＋ PART_HEADROOM ＋ 0.1）。"""
    return lay.z()["psw_top"] + lay.s.PART_HEADROOM + 0.1


def psw_roof_rect(lay=LAY):
    """電源スイッチの上で屋根を psw_ceiling まで厚くする範囲（つまみの切り欠きの内側の面の裏を塞ぐ。薄い垂れ壁にしない）。"""
    n = lay.psw_notch()
    return (lay.psw_pads()[0] - lay.s.PART_CLEAR, n[0][1], n[0][0], n[-1][1])


def cover_cheeks(lay=LAY):
    """蓋の耳の溝の奥の壁になる塊（口の左右。枠に足す）[矩形, ...]。手前の壁の内面から溝の奥 ＋ COVER_CHEEK まで・溝の底の 1.0 外から口まで。
    電池クリップの空間（corner_cuts の clip）からは、この分を引かない。"""
    cv = lay.cover()
    y0 = lay.key_area[1] - lay.s.PART_CLEAR - 0.2
    return [(cv["gx"][0] - 1.0, y0, cv["x0"], cv["y_cheek"]), (cv["x1"], y0, cv["gx"][1] + 1.0, cv["y_cheek"])]


def cover_teeth(lay=LAY):
    """蓋を上へ抜けなくする歯（口の手前の左右の角で、口の壁から内へ出る。枠に足す）{名前: 立体}。left = 棒 B の先が下に入る・right = 棒 A。
    下面は平ら（棒の上面と直角に当たる）。上の奥の縁は斜め（蓋を押し下げると、棒の先が自分で奥へ逃げる）。上面をベッドに刷るので、宙に浮かない。"""
    s = lay.s
    cv = lay.cover()
    top = cv["z_top"]
    ch = s.COVER_TOOTH[1]
    cam = [(cv["y_lip"] - ch, top + EPS), (cv["y_lip"] + EPS, top - ch - EPS), (cv["y_lip"] + EPS, top + EPS)]
    out = {}
    for name, xa, xb, key in (("left", cv["x0"] - 0.3, cv["tooth"][0], "B"), ("right", cv["tooth"][1], cv["x1"] + 0.3, "A")):
        out[name] = _box((xa, cv["y0"], xb, cv["y_lip"]), cv["ledge"][key], top) - _prism_x(cam, xa - 1.0, xb + 1.0)
    return out


def corner_cuts(lay=LAY):
    """{名前: 立体}。XIAO の空間・USB の切り欠き・電池クリップの空間・電池の口（手前の壁を上から下まで抜く溝）・蓋の耳の溝・
    電源スイッチの空間・つまみの切り欠き・入の印。"""
    s = lay.s
    f = lay.frame
    top = s.FRAME_UNDER + s.FRAME_T
    c = s.PART_CLEAR
    xb, xp = lay.xiao(), lay.xiao_pads()
    usb = lay.usb_shell()
    out = {}
    out["xiao"] = _box((xb[0] - c, xp[1] - c, xb[2] + c, xp[3] + c), -1.0, s.XIAO_ROOF_UNDER)       # パッドの外接 ＋ PART_CLEAR
    out["usb"] = _box((f[0] - 1.0, usb[1] - s.PORT_CLEAR, usb[2] + c, usb[3] + s.PORT_CLEAR), -1.0, top + 1.0)
    body = lay.clip_body()
    pads = lay.clip_pads()
    out["clip"] = _box((pads[0][0] - c, body[1] - c, pads[1][2] + c, body[3] + c), -1.0, s.CLIP_ROOF_UNDER) \
        - _union([_box(r, -2.0, top) for r in cover_cheeks(lay)])
    # 電池の口: 手前の壁を上から下まで抜く。蓋は上から落とす
    cv = lay.cover()
    out["cell_slot"] = _box((cv["x0"], f[1] - 1.0, cv["x1"], cv["y1"]), -1.0, top + 1.0)
    # 蓋の耳の溝（口の左右の壁を、上から下まで縦に）。手前の面は、口の縁から外へ 45° で奥へ下がる = 電池に押された蓋の耳を受ける面
    yl, yg = cv["y_face"], cv["y_groove"]
    left = [(cv["x0"] + EPS, yl - EPS), (cv["x0"] + EPS, yg), (cv["gx"][0], yg)]
    right = [(cv["x1"] - EPS, yl - EPS), (cv["gx"][1], yg), (cv["x1"] - EPS, yg)]
    out["cover_groove"] = _union([_prism_z(left, -1.0, top + 1.0), _prism_z(right, -1.0, top + 1.0)])
    pb = lay.psw_body()
    pp = lay.psw_pads()                                                                          # パッドの外接 ＋ PART_CLEAR（本体はその中）
    out["psw"] = _box((min(pp[0], pb[0]) - c, min(pp[1], pb[1]) - c, max(pp[2], pb[2]) + c, max(pp[3], pb[3]) + c), -1.0, psw_ceiling(lay))
    notch = lay.psw_notch()
    x0, sc = notch[0][0], s.PSW_NOTCH[2]
    out["psw_notch"] = _union([
        Pos(0, 0, -1.0) * extrude(Polygon(*notch, align=None), top + 2.0),                       # 壁を上まで抜く
        # 厚い屋根の下で、壁の内面から切り欠きの内側の面までを、切り欠きの幅いっぱいに空ける（スイッチの逃げと切り欠きの間に細い柱を残さない）
        _box((lay.key_area[2] - EPS, notch[0][1], x0 + EPS, notch[-1][1]), -1.0, psw_ceiling(lay)),
        # 内側の面の上の縁を 45° に落とす（指の腹が上から斜めに入る。上面をベッドに刷るので、支え無しで刷れる向き）
        _prism_y([(x0 - sc - 1.0, top + 1.0), (x0 + EPS, top - sc - EPS), (x0 + EPS, top + 1.0)], notch[0][1], notch[-1][1])])
    d_mark, depth = s.ON_MARK
    my = s.PSW_AT[1] + s.PSW_ON * (s.PSW_TRAVEL / 2 + s.PSW_KNOB[0] / 2)                          # 入に寄せたつまみの、奥の縁の高さ
    # 印は、斜めに落とした面のすぐ内の平らな上面に（斜面の上に置くと、上面から掘る印は空を切る）
    out["on_mark"] = Pos(x0 - sc - 1.2, my, top - depth) * Cylinder(d_mark / 2, depth + 1.0, align=CEN_MIN)
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
        _box(psw_roof_rect(lay), psw_ceiling(lay), under + EPS),                                    # 電源スイッチの上の厚い屋根
    ] + [_box(r, 0.0, top - EPS) for r in cover_cheeks(lay)]                                        # 蓋の耳の溝の奥の壁
    body = _union(parts)
    ch = s.HOLE_CHAMFER
    chamfers = _union([Pos(c.cx, c.cy, top - ch) * extrude(P.hole_plan(c, s), ch + EPS, taper=-45.0) for c in cells])
    cuts = [chamfers] + list(corner_cuts(lay).values())
    d, depth = lay.pilot()
    cuts += [Pos(c[0], c[1], -1.0) * Cylinder(d / 2, depth + 1.0, align=CEN_MIN) for _, c, _ in lay.wall_screws()]
    body = body - _union(cuts) + _union(list(cover_teeth(lay).values()))
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
        if ref in s.CAP_LAND_H:                         # 載せないコンデンサのランド: 載せてよいいちばん大きな部品（1206 の最大・背は spec）
            (w, d), h = CAP_LAND_BODY, s.CAP_LAND_H[ref]
        else:
            kind = "U" if ref.startswith("U") else "D" if ref.startswith("D_") else ref[0]
            (w, d), h = PART_BODY[kind], PART_H[kind]
        if deg % 180 == 90:
            w, d = d, w
        out[ref] = Pos(x, y, 0) * Box(w, d, h, align=CEN_MIN)
    out["U_MCU"] = _union([_box(lay.xiao_pads(), 0.0, z["xiao_body_top"]), _box(lay.usb_shell(), 0.0, z["usb_top"])])
    pads = lay.clip_pads()
    body = lay.clip_body()
    out["BT1"] = _union([_box(body, 0.0, z["clip_top"]), _box((pads[0][0], pads[0][1], pads[1][2], pads[1][3]), 0.0, 0.5)])
    pb = lay.psw_body()
    out["SW_PWR"] = _union([_box(pb, 0.0, z["psw_top"]), _box((pb[0] - 1.9, pb[1], pb[0] + EPS, pb[3]), 0.0, 0.6)])
    ks = lay.psw_knob_sweep()
    out["SW_PWR_knob"] = _box(ks, *s.PSW_KNOB_Z)
    return out


def clip_solid(lay=LAY):
    """電池クリップの金属が**ある所**（図面 MY-CP-0247 から。board_parts の BT1 は外接の箱で、電池の入る空間まで詰まっている）。
      板    外接の矩形（本物は六角 ＋ 口の側は丸い 2 つの出っ張りで、これより小さい）× 下面のいちばん低い所（CLIP_H − 板厚 − CLIP_TOL）〜上面
      止め  幅 CLIP_STOP_W・板の上面から CLIP_STOP_DROP ＋ CLIP_TOL 下まで
      脚    ＋のランドの上（板の両脇から基板へ下りる所。ランドの奥行きの範囲）
    **電池を押さえる 2 本の舌（板から下へ曲げてある）は入れていない**: 電池の円の中にある（検査は、蓋が電池の円 ＋ 隙の外にいることで見る）。"""
    s = lay.s
    b = lay.clip_body()
    top = lay.z()["clip_top"]
    x = s.CLIP_AT[0]
    parts = [_box(b, s.CLIP_H - s.CLIP_SHEET_T - s.CLIP_TOL, top),
             _box((x - s.CLIP_STOP_W / 2, b[3] - s.CLIP_SHEET_T - s.CLIP_TOL, x + s.CLIP_STOP_W / 2, b[3]), top - s.CLIP_STOP_DROP - s.CLIP_TOL, top)]
    for pad, (xa, xb) in zip(lay.clip_pads(), ((None, b[0] + s.CLIP_SHEET_T + s.CLIP_TOL), (b[2] - s.CLIP_SHEET_T - s.CLIP_TOL, None))):
        parts.append(_box((pad[0] if xa is None else xa, pad[1], pad[2] if xb is None else xb, pad[3]), 0.0, top))
    return _union(parts)


def knob_solid(pos, lay=LAY, dy=0.0):
    """つまみ（pos = +1 奥 / −1 手前。dy は行程の公差ぶんずらす量）。"""
    k = lay.psw_knob(pos)
    return _box((k[0], k[1] + dy, k[2], k[3] + dy), *lay.s.PSW_KNOB_Z)


def nail_envelope(pos, lay=LAY):
    """爪の入る場所（検査の包絡）: つまみが pos にあるとき、反対の端へ押し切るまでに爪が通る所。つまみの脇の矩形（click_layout.psw_nail）を
    行程ぶん掃いた物。高さは、つまみの下面の少し上から枠の上面の 5 上まで（**上からも横からも入る** = この立体のどこにも枠が無い）。"""
    s = lay.s
    r = lay.psw_nail(pos)
    travel = s.PSW_TRAVEL + s.PSW_TRAVEL_TOL
    y0, y1 = (r[1] - travel, r[3]) if pos > 0 else (r[1], r[3] + travel)
    return _box((r[0], y0, r[2], y1), s.PSW_KNOB_Z[0] + 0.1, s.FRAME_UNDER + s.FRAME_T + 5.0)


# ---------------------------------------------------------------------------
# 電池の蓋（落とし込み式。寸法は click_layout.cover・spec.COVER_*）
# ---------------------------------------------------------------------------

def _prism_z(pts_xy, z0, z1):
    """x–y の多角形（反時計回り）を z0〜z1 へ押し出した立体。"""
    return Pos(0, 0, z0) * extrude(Polygon(*pts_xy, align=None), z1 - z0)


def _leaf_ends(name, cv):
    """棒 name（"A" / "B"）の (付け根の x, 先の x, 先の向き ±1)。"""
    xr, xt = cv["root"][name], cv["tip"][name]
    return xr, xt, (1 if xt > xr else -1)


@lru_cache(maxsize=None)
def cover_solid(variant=None, deflect=0.0, mark=False):
    """電池の蓋（組んだ位置・CAD）。variant = spec.COVER_VARIANTS の番号（既定は COVER_MAIN）。
      硬い所  手前の板（下の帯・上の帯）＋ 上の板 ＋ 左右の足（基板に立つ・電池を止める）＋ 左右の耳（45° のくさび。口の壁の溝に入る）。
              手前の左右の角は、枠の歯の所だけ欠いてある
      棒      手前の面の 2 本（A = 左の足から右へ・B = 右の足から左へ）。先が枠の歯の下に入る。先の側の足は、棒の高さで抜いてある（先が奥へ逃げる）
    deflect = 棒の先を奥へ押し込んだ量（検査と絵のための形: 棒は付け根から先へまっすぐ傾く）。
    mark = 上の板の奥の縁に、variant の数だけ切り欠き（試し刷りで見分ける）。"""
    lay, s = LAY, S
    cv = lay.cover(variant)
    xl, xr = cv["side"]
    yf, top = cv["yf"], cv["z_top"]
    cl = xl - cv["x0"]
    b, slit, _ = s.COVER_LEAF
    t = cv["t"]
    parts = [
        _box((xl, yf, xr, yf + s.COVER_FRONT_T), cv["z_sill"][0], top),                       # 手前の板（棒の所は下で抜く）
        _box((xl, yf, xr, cv["y1"] - cl), cv["z_plate"], top),                                # 上の板
    ]
    ya, yb = cv["y_ear"]
    wd = s.COVER_WEDGE
    for xs, sg in ((xl, -1), (xr, 1)):                                                        # 耳: 蓋の側面から外へ 45° に広がるくさび（上から下まで）
        tri = [(xs - sg * EPS, ya - EPS), (xs + sg * wd, yb), (xs - sg * EPS, yb)]
        parts.append(_prism_z(tri if sg > 0 else tri[::-1], 0.0, top))
    (cx, cy), r = lay.cell()
    keep = Pos(cx, cy, -1.0) * Cylinder(r + s.COVER_CELL_CLEAR, top + 2.0, align=CEN_MIN)
    for xa, xb in cv["block"]:                                                                # 足: クリップの板の手前まで（板の下へは入れない）
        parts.append(_box((xa, yf, xb, cv["y_block"]), 0.0, cv["z_plate"] + EPS) - keep)
    body = _union(parts)
    # 棒の通る所を抜く: 手前の板は、棒の高さ ± 切れ目の幅で、付け根から先の側の側面まで全部。先の側の足も、同じ高さで手前から奥まで抜く
    # （棒の先が奥へ逃げる場所。足は、耳を通して上下がつながっている）
    for name in ("A", "B"):
        xa, xt, sg = _leaf_ends(name, cv)
        z0, z1 = cv["band"][name]
        xe = xt + sg * EPS                                                                    # 蓋の側面まで（耳は抜かない）
        cut = [_box((min(xa, xe), yf - 1.0, max(xa, xe), yf + s.COVER_FRONT_T + EPS), z0 - slit, z1 + slit)]
        xb0, xb1 = cv["block"][1 if sg > 0 else 0]
        cut.append(_box((min(xb0, xe) if sg < 0 else xb0, yf - 1.0, max(xb1, xe) if sg > 0 else xb1, cv["y_block"] + EPS), z0 - slit, z1 + slit))
        # 歯の所の角は、上から下まで 45° に欠く（歯の内の奥の角を通る線。蓋を上へ抜くとき、歯の下を通る物を残さない。
        # 欠いた面は 45° なので、手前の面をベッドに刷って支えが要らない）
        xn, yn = cv["tooth"][1 if sg > 0 else 0] - sg * cl, cv["y_lip"] + cl
        tri = [(xn - sg * (yn - yf + 1.0), yf - 1.0), (xt + sg * EPS, yf - 1.0), (xt + sg * EPS, cv["y_ear"][0])]
        cut.append(_prism_z(tri if sg > 0 else tri[::-1], -1.0, top + 1.0))
        body = body - _union(cut)
    for name in ("A", "B"):                                                                   # 棒。先の下の手前の角は 45°（上から落とすと自分で奥へ逃げる）
        xa, xt, sg = _leaf_ends(name, cv)
        z0, z1 = cv["band"][name]
        d = deflect
        leaf = [(xa - sg * 0.3, yf), (xt, yf + d), (xt, yf + d + t), (xa - sg * 0.3, yf + t)]
        body = body + _prism_z(leaf if sg > 0 else leaf[::-1], z0, z1)
        ramp = b - 0.2
        xn = cv["tooth"][1 if sg > 0 else 0] - sg * (cl + 0.5)
        body = body - _prism_x([(yf + d - 0.2, z0 + ramp), (yf + d - 0.2, z0 - EPS), (yf + d + ramp, z0 - EPS)], min(xn, xt + sg), max(xn, xt + sg))
    # 指を当てる所（真ん中）: 上の帯の下の縁と、下の帯の上の縁を斜めに落とす
    dw, d_hi, d_lo = s.COVER_DISH
    xm = (xl + xr) / 2
    zs, zt = cv["z_strip"], cv["z_sill"][1]
    body = body - _union([
        _prism_x([(yf - EPS, zs - EPS), (yf + d_hi, zs - EPS), (yf - EPS, zs + d_hi)], xm - dw / 2, xm + dw / 2),
        _prism_x([(yf - EPS, zt + EPS), (yf - EPS, zt - d_lo), (yf + d_lo, zt + EPS)], xm - dw / 2, xm + dw / 2)])
    if deflect == 0.0:
        # 手前の面（ベッドの面）の、棒の縁を落とす: 1 層目が太っても切れ目が埋まらない
        fc = s.COVER_FOOT
        bev = []
        for name in ("A", "B"):
            xa, xt, sg = _leaf_ends(name, cv)
            x_lo, x_hi = min(xa, cv["tooth"][1 if sg > 0 else 0] - sg * (cl + 0.5)), max(xa, cv["tooth"][1 if sg > 0 else 0] - sg * (cl + 0.5))
            for z, up in ((cv["band"][name][0], 1), (cv["band"][name][1], -1)):               # 棒の下の縁（up = 1）・上の縁（−1）
                pts = [(yf - EPS, z - up * EPS), (yf + fc, z - up * EPS), (yf - EPS, z + up * fc)]
                bev.append(_prism_x(pts if up > 0 else pts[::-1], x_lo, x_hi))
        body = body - _union(bev)
    if mark:
        mw, md, mp = s.COVER_MARK
        n = s.COVER_MAIN if variant is None else variant
        ye = cv["y1"] - cl
        body = body - _union([_box((xr - 3.0 - i * mp - mw, ye - md, xr - 3.0 - i * mp, ye + 1.0), cv["z_plate"] - 1.0, top + 1.0) for i in range(n)])
    body = body.clean()
    if len(body.solids()) != 1:
        raise RuntimeError(f"蓋が {len(body.solids())} 個の塊")
    return body


def cover_print(part=None):
    """蓋を刷る向き（**手前の面をベッドに**。棒と切れ目が平面の形になる）。"""
    part = cover_solid() if part is None else part
    return P.to_bed(Rot(90, 0, 0) * part)


def cover_numbers(variant=None, lay=LAY):
    """棒（板ばね）の計算。片持ち梁（付け根は足・先は自由）。**材料の値は TDS・断面は名目**（刷った物を測った値ではない）。
      k_tip        先を押す固さ [N/mm]
      release      棒の先が歯の奥へ逃げるのに要る押し込み（名目）・release_max 蓋が前へ寄り切ったとき
      push_force   真ん中を押して、先を release_max だけ動かす力（棒 1 本）[N]
      strain       そのときの付け根のひずみ [%]・strain_limit 曲げ強さ ÷ 曲げ弾性率 [%]
      drop_tip     DROP_G の加速度が棒の厚さの向きに掛かったとき、棒の自分の重さで先が動く量（静的）[mm]
      cell_force   同じ加速度で電池が蓋を押す力 [N]・cover_force 蓋の自分の重さの力 [N]
      ear_pressure 電池の力の半分を、耳の斜めの面（45°）が受けるときの面圧 [MPa]"""
    s = lay.s
    cv = lay.cover(variant)
    t, b, length = cv["t"], s.COVER_LEAF[0], cv["leaf_len"]
    e = s.PLA_E
    inertia = b * t ** 3 / 12
    rel = cv["release"] + s.COVER_RECESS
    # 真ん中 a = L/2 を P で押すと、先は P a²(3L − a)/(6EI) = (5/48) P L³/EI 動く。付け根の曲げモーメントは P a
    p = rel * e * inertia / (5 / 48 * length ** 3)
    acc = s.DROP_G * 9.80665                                    # m/s²（g の質量に掛けると mN）
    w = PLA_DENSITY * b * t * acc * 1e-3                        # N/mm
    cell = s.CELL_MASS * acc * 1e-3
    face = s.COVER_WEDGE * math.sqrt(2.0) * cv["z_top"]                   # 耳の斜めの面の面積
    return dict(k_tip=3 * e * inertia / length ** 3, release=cv["release"], release_max=rel, push=rel / 2.5, push_force=p,
                strain=(p * length / 2) * (t / 2) / (e * inertia) * 100, strain_limit=s.PLA_BEND / e * 100,
                drop_tip=w * length ** 4 / (8 * e * inertia),
                cell_force=cell, cover_force=cover_solid(variant).volume * PLA_DENSITY * acc * 1e-3,
                ear_pressure=(cell / 2 * math.sqrt(2.0)) / face)


def _section(pts):
    """多角形の断面（反時計回り [(x, z), ...]）の 面積・図心の高さ・図心を通る水平な軸まわりの断面二次モーメント。"""
    a = cz = i = 0.0
    for (x0, z0), (x1, z1) in zip(pts, pts[1:] + pts[:1]):
        c = x0 * z1 - x1 * z0
        a += c / 2
        cz += (z0 + z1) * c / 6
        i += (z0 * z0 + z0 * z1 + z1 * z1) * c / 12
    cz /= a
    return a, cz, i - a * cz * cz


def notch_strength(lay=LAY, press=10.0):
    """つまみの切り欠きのまわりの強さの見積もり（応力 MPa）。**断面は式で置く・材料は TDS の値・刷る向きの弱さは半分に見る。**
      roof   切り欠きの内側の縁（厚くした屋根の端）を、指で下へ press [N] 押す。切り欠きの内側の幅を渡る両端支持の梁の真ん中。
             断面 = 厚い屋根の端の 2.0 幅から、**上の縁を斜めに落とした三角を引いた台形**（内側の面で roof_edge・2.0 奥で roof_t）
      stub   切り欠きの手前に残る壁（角まで）を、爪が滑って y の向きに press で押す。根元（屋根と手前の壁に付く面）のせん断。
             外面へ向かって広がる分、残る壁は外面で短い（stub_len）= 面積は台形
      knob   つまみを動かす力の最大（PSW_FORCE_MAX）は基板のスイッチが受ける。枠には掛からない（記録だけ）"""
    s = lay.s
    w, fl, sc = s.PSW_NOTCH
    top = s.FRAME_UNDER + s.FRAME_T
    ceil = psw_ceiling(lay)
    h = top - ceil                                               # 厚い屋根の厚さ（3.2）
    b = 2.0
    cut = min(sc, b)                                             # 幅 b の中で、斜めに落とした分
    pts = [(0.0, ceil), (b, ceil), (b, top - cut), (b - cut, top)] + ([(0.0, top)] if cut < b else [])
    area, cz, inertia = _section(pts)
    roof = (press * w / 4) * max(top - cz, cz - ceil) / inertia
    f = lay.frame
    stub_in = (s.PSW_AT[1] - w / 2) - f[1]                       # 切り欠きから角まで（内側の面で）
    stub_len = stub_in - fl                                      # 外面で
    n = lay.psw_notch()
    depth = lay.frame[2] - n[0][0]                               # 広がる区間の奥行き（内側の面から外面まで）
    stub_area = stub_in * s.PLATE_MARGIN_X - fl * depth / 2
    stub = press / stub_area
    return dict(roof=roof, stub=stub, stub_len=stub_len, stub_area=stub_area, roof_t=h, roof_edge=h - cut, limit=76.0 / 2)


def roof_section(frame, width, lay=LAY, dz=0.1):
    """切り欠きの内側の縁の、厚い屋根の断面を**枠の立体から測る**（切り欠きの真ん中の y・内側の面から width 奥まで・厚い屋根の下面から上面まで）。
    高さ dz ごとの帯の幅を立体の重なりから取り、(面積, 図心の高さ, 図心まわりの断面二次モーメント, 図心からいちばん遠い縁までの距離) を返す。"""
    s = lay.s
    x0, y = lay.psw_notch()[0][0], s.PSW_AT[1]
    z0, top = psw_ceiling(lay), s.FRAME_UNDER + s.FRAME_T
    n = int(round((top - z0) / dz))
    rows = []
    for i in range(n):
        hit = frame & _box((x0 - width, y - 0.05, x0, y + 0.05), z0 + i * dz, z0 + (i + 1) * dz)
        v = 0.0 if hit is None else sum(q.volume for q in hit.solids())
        rows.append((z0 + (i + 0.5) * dz, v / (0.1 * dz)))
    area = sum(b * dz for _, b in rows)
    cz = sum(z * b * dz for z, b in rows) / area
    inertia = sum(b * dz ** 3 / 12 + b * dz * (z - cz) ** 2 for z, b in rows)
    zs = [z for z, b in rows if b > 1e-6]
    return area, cz, inertia, max(max(zs) + dz / 2 - cz, cz - (min(zs) - dz / 2))


def notch_roof_stress(frame, width, lay=LAY, press=10.0):
    """notch_strength の roof と同じ梁（切り欠きの内側の幅を渡る両端支持・真ん中を press で押す）の応力を、**立体から測った断面**で出す。"""
    _, _, inertia, far = roof_section(frame, width, lay)
    return (press * lay.s.PSW_NOTCH[0] / 4) * far / inertia


def finger_reach(things, lay=LAY, r=None, desk=True, ys=(-2.0, -1.0, 0.0, 1.0, 2.0)):
    """指先を半径 r の硬い球と見て、切り欠きへどこまで入るかを**立体を当てて**測る（届きやすさを比べる物差し。r は仮定: spec.PSW_FINGER_R）。
    things = 当てる相手（枠・基板・スイッチの本体）。球の中心を、切り欠きの幅の中（y）・机より上（z。desk=True のとき球は机 = 底のシートの
    下面より下へ行けない）で動かし、何にも当たらないいちばん奥（x）を二分法で探す。返り値:
      bite   つまみの上面の高さで、球がつまみの先より奥へ入る量（負 = 届かない）のいちばん大きい物
      tip_in つまみの先が枠の外面から引っ込んでいる量・open 外面での切り欠きの幅・depth 内側の面から外面まで・cx, cy, cz そのときの球の中心"""
    from build123d import Sphere

    s = lay.s
    r = s.PSW_FINGER_R if r is None else r
    f2 = lay.frame[2]
    k = lay.psw_knob(1)
    zk = s.PSW_KNOB_Z[1]
    z_min = (-s.PCB_T - s.BOTTOM_SHEET_T + r) if desk else zk
    best = dict(bite=-99.0)
    for cy in (s.PSW_AT[1] + t for t in ys):
        for cz in (z_min + 0.75 * i for i in range(6)):
            if abs(cz - zk) >= r:
                continue
            lo, hi = k[2] - r, f2 + r + 1.0                     # lo = 当たる・hi = 当たらない
            for _ in range(11):
                mid = (lo + hi) / 2
                hit = things & (Pos(mid, cy, cz) * Sphere(r))
                if hit is not None and sum(v.volume for v in hit.solids()) > 1e-4:
                    lo = mid
                else:
                    hi = mid
            bite = k[2] - (hi - math.sqrt(r * r - (cz - zk) ** 2))
            if bite > best["bite"]:
                best = dict(bite=round(bite, 2), cx=round(hi, 2), cy=cy, cz=round(cz, 2), r=r)
    n = lay.psw_notch()
    yo = [q[1] for q in n if abs(q[0] - f2) < 1e-6]
    best.update(tip_in=round(f2 - k[2], 2), open=round(max(yo) - min(yo), 2), depth=round(f2 - n[0][0], 2))
    return best


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


def screw_solids(lay=LAY, with_feet=None, spare=False):
    """ねじ {参照名: 立体}（頭は基板の下面・軸は上へ）。中の押さえは、足を付けるときだけ。spare=True で予備のねじも。
    蓋のねじ穴（H30・H31）には入れない（基板の穴だけ。使っていない）。"""
    s = lay.s
    with_feet = s.HOLDDOWN_FEET if with_feet is None else with_feet
    out = {}
    for ref, c, kind in lay.screws():
        if (kind == "holddown" and not with_feet) or (kind == "spare" and not spare) or kind == "cover":
            continue
        length = s.HOLDDOWN_SCREW_L if kind == "holddown" else s.SCREW_L
        out[ref] = _union([Pos(c[0], c[1], -s.PCB_T - s.SCREW_HEAD_H) * Cylinder(s.SCREW_HEAD_D / 2, s.SCREW_HEAD_H, align=CEN_MIN),
                           Pos(c[0], c[1], -s.PCB_T - EPS) * Cylinder(s.SCREW_D / 2, length + EPS, align=CEN_MIN)])
    return out


def sheet_solid(lay=LAY):
    """底のシート（基板の外形から 0.5 内側。ねじの頭の所に φ5 の穴。使っていない蓋のねじ穴 H30・H31 は塞ぐ）。"""
    p = click_layout.grow(lay.pcb, -0.5)
    s = lay.s
    z0 = -s.PCB_T - s.BOTTOM_SHEET_T
    sheet = Pos((p[0] + p[2]) / 2, (p[1] + p[3]) / 2, z0) * extrude(RectangleRounded(p[2] - p[0], p[3] - p[1], s.CORNER_R), s.BOTTOM_SHEET_T)
    holes = _union([Pos(c[0], c[1], z0 - 1) * Cylinder(s.SCREW_HEAD_D / 2 + 0.5, s.BOTTOM_SHEET_T + 2, align=CEN_MIN)
                    for _, c, kind in lay.screws() if kind in ("perimeter", "spare")])   # 予備のねじの所も開ける
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
        "スイッチ 62 個": 62 * 0.12, "ダイオードほか": 0.6, "XIAO": 3.0, "電池クリップ": 0.6, "CR1632": s.CELL_MASS,
        "ねじ 20 本": 20 * 0.09, "電池の蓋": cover_solid().volume * PLA_DENSITY, "底のシート": sheet_solid(lay).volume * 1.2e-3,
    }
    out["合計"] = sum(out.values())
    return out


# ---------------------------------------------------------------------------
# 書き出し
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ねじの試し刷り（発注の前に刷る。docs/coupon-test.md「ねじ」）
# ---------------------------------------------------------------------------

def screw_coupon_boxes(lay=LAY):
    """切り出す範囲 {名前: (矩形, [ねじの中心], 厚くするねじの中心 か None)}。back = 奥の壁（ねじ 3 本）・side = 左の壁（ねじ 1 本）。"""
    s = lay.s
    f, a = lay.frame, lay.key_area
    want = [tuple(c) for _, c, kind in lay.screws() if kind == "perimeter"]
    back = [c for x in s.COUPON_SCREW_X for c in want if abs(c[0] - x) < 1e-6 and abs(f[3] - c[1] - s.SCREW_FROM_EDGE) < 1e-6]
    side = tuple(s.COUPON_SCREW_SIDE)
    if len(back) != len(s.COUPON_SCREW_X) or side not in want:
        raise ValueError("ねじの試し刷りのねじが、本番の外周のねじ（spec.SCREWS_PERIMETER）に無い")
    inner = lay.rib() / 2 + s.COUPON_SCREW_DEPTH
    half = UNIT * len(back) / 2
    mid = sum(x for x, _ in back) / len(back)
    return {
        "back": ((mid - half, a[3] - inner, mid + half, f[3]), back, back[-1]),
        "side": ((f[0], side[1] - UNIT / 2, a[0] + inner, side[1] + UNIT / 2), [side], None),
    }


@lru_cache(maxsize=None)
def screw_coupon():
    """{名前: 立体}（組んだ向き・本番の座標）。frame_back / frame_side = 本番の枠の切れ端、base_back / base_side = 当て板（基板の代わり）。
    frame_back の最後のねじだけ、壁を穴の中へ COUPON_SCREW_THICK 厚くする（基板の上 0〜FRAME_UNDER）。"""
    lay, s = LAY, S
    full = frame_full()
    top = s.FRAME_UNDER + s.FRAME_T
    out = {}
    for name, (box, screws, thick) in screw_coupon_boxes(lay).items():
        part = full & _box(box, -1.0, top + 1.0)
        if thick is not None:
            b = screw_boss(thick, lay)                                   # 奥の壁: 厚い壁の矩形（y0 = 穴の縁）
            add = _box((b[0], b[1] - s.COUPON_SCREW_THICK, b[2], b[1] + EPS), 0.0, s.FRAME_UNDER)
            part = part + add
            m = s.COUPON_SCREW_MARK                                      # 厚い方の印: その側の端の外の角を落とす（裏返しても見える）
            # 点は反時計回りに（時計回りだと面が下を向き、押し出しが下へ行って何も削らなかった）
            mark = extrude(Polygon((box[2] + EPS, box[3] - m), (box[2] + EPS, box[3] + EPS), (box[2] - m, box[3] + EPS), align=None), top + 2.0)
            part = part - Pos(0, 0, -1.0) * mark
        solids = part.solids()
        if len(solids) != 1:
            raise RuntimeError(f"ねじの試し刷り {name} が {len(solids)} 個の塊")
        out[f"frame_{name}"] = part.clean()
        p = lay.pcb
        r = (max(box[0], p[0]), max(box[1], p[1]), min(box[2], p[2]), min(box[3], p[3]))     # 基板のある範囲だけ
        plate = _box(r, -s.PCB_T, 0.0)
        holes = _union([Pos(x, y, -s.PCB_T - 1.0) * Cylinder(s.SCREW_HOLE_D / 2, s.PCB_T + 2.0, align=CEN_MIN) for x, y in screws])
        out[f"base_{name}"] = plate - holes
    return out


def screw_coupon_plate(gap=5.0):
    """1 枚に並べた刷る物（枠の切れ端は上面をベッドに・当て板は平らに）。手前から 当て板 2 枚・枠 2 つ。"""
    sc = screw_coupon()
    placed, y = [], 0.0
    for name in ("base_side", "base_back", "frame_side", "frame_back"):
        part = P.flip_to_bed(sc[name]) if name.startswith("frame") else P.to_bed(sc[name])
        bb = part.bounding_box()
        if name.endswith("side"):                                         # 左の壁の切れ端は長い辺を X に（90° 回す）
            part = Rot(0, 0, 90) * part
            bb = part.bounding_box()
        placed.append(Pos(-(bb.min.X + bb.max.X) / 2, y - bb.min.Y, -bb.min.Z) * part)
        y += bb.size.Y + gap
    return Compound(placed)


# ---------------------------------------------------------------------------
# 角の試し刷り = 蓋の試し刷り（発注の前に刷る。docs/coupon-test.md 10 章）: 電池の口・落とし込み式の蓋 3 つ・つまみの切り欠き
# ---------------------------------------------------------------------------

def corner_coupon_box(lay=LAY):
    """切り出す範囲（右手前の角）。"""
    x0, y1 = lay.s.COUPON_CORNER_BOX
    f = lay.frame
    return (x0, f[1], f[2], y1)


def knob_standin(pos=1, lay=LAY):
    """つまみの代わりの小片（組んだ位置。pos = +1 奥 / −1 手前）: 本体の代わりの塊の溝の中を滑る棒 ＋ つまみ（幅・出は本物と同じ。
    下面は当て板に着く = 本物より 0.2 低い）。"""
    s = lay.s
    ch = knob_channel(lay)
    fit = s.COUPON_FIT
    k = lay.psw_knob(pos)
    cy = (k[1] + k[3]) / 2
    half = (ch[3] - ch[1] - s.PSW_TRAVEL) / 2 - fit
    zt = s.PSW_KNOB_Z[1]
    return _union([_box((ch[0] + fit, cy - half, ch[2] - fit, cy + half), 0.0, zt), _box((ch[0] + fit, k[1], k[2], k[3]), 0.0, zt)])


def knob_channel(lay=LAY):
    """本体の代わりの塊の中の溝（小片の棒が y に滑る）。端が行程の止め。"""
    s = lay.s
    b = lay.psw_body()
    y = s.PSW_AT[1]
    half = 4.5 / 2 + s.PSW_TRAVEL / 2 + s.COUPON_FIT
    return (b[0] + 0.8, y - half, b[2] - 0.6, y + half)


@lru_cache(maxsize=None)
def corner_coupon():
    """{名前: 立体}（組んだ向き・本番の座標）。
      frame  本番の枠の右手前の角の切れ端 ＋ 切った左の端の壁（当て板に載せるため。本番には無い）
      base   当て板（基板の代わり・厚さ PCB_T・ねじ穴 H15 と、使っていない基板の穴 H30・H31）＋ 電源スイッチの本体の代わり（溝つき）＋ 電池クリップの代わり
             （止めと、蓋の足より奥の左右の案内。**クリップの板〔基板の 3.75 上〕の代わりは無い**）＋ 左と奥の縁の当て（枠の切れ端の位置決め）
      knob   つまみの代わりの小片（入の位置）
      cell   電池の代わり（φ CELL_D × CELL_T・止めに当てた位置。真ん中に、押す棒を差す穴）
      cover1〜3  蓋 3 つ（spec.COVER_VARIANTS。上の板の奥の縁の切り欠きの数で見分ける。**同じ枠に入る**）"""
    lay, s = LAY, S
    z = lay.z()
    top = s.FRAME_UNDER + s.FRAME_T
    box = corner_coupon_box(lay)
    a = lay.key_area
    part = frame_full() & _box(box, -1.0, top + 1.0)
    w = s.COUPON_CORNER_WALL
    part = part + _box((box[0], a[1] - EPS, box[0] + w, box[3]), 0.0, s.FRAME_UNDER + EPS)
    solids = part.solids()
    if len(solids) != 1:
        raise RuntimeError(f"角の試し刷りの枠が {len(solids)} 個の塊")
    out = {"frame": part.clean()}
    p = lay.pcb
    fit = s.COUPON_FIT
    fence = 1.8
    plate = _box((box[0] - fit - fence, p[1], p[2], box[3] + fit + fence), -s.PCB_T, 0.0)
    holes = _union([Pos(c[0], c[1], -s.PCB_T - 1.0) * Cylinder(s.SCREW_HOLE_D / 2, s.PCB_T + 2.0, align=CEN_MIN)
                    for _, c, _ in lay.screws() if box[0] < c[0] < box[2] and box[1] < c[1] < box[3]])
    base = [plate - holes,
            _box((box[0] - fit - fence, p[1], box[0] - fit, box[3] + fit + fence), -EPS, 2.0),          # 左の当て
            _box((box[0] - fit - fence, box[3] + fit, p[2], box[3] + fit + fence), -EPS, 2.0)]           # 奥の当て
    pb, ch, ks = lay.psw_body(), knob_channel(lay), lay.psw_knob_sweep()
    block = _box(pb, -EPS, z["psw_top"]) - _box(ch, 0.0, z["psw_top"] + 1.0) \
        - _box((ch[2] - EPS, ks[1] - fit, pb[2] + 1.0, ks[3] + fit), 0.0, z["psw_top"] + 1.0)             # 溝と、つまみの出る窓（上へ開く）
    base.append(block)
    (cx, cy), r = lay.cell()
    stop_y = s.CLIP_AT[1] + s.CLIP_STOP - s.CLIP_SHEET_T                                               # 止めの内面
    base.append(_box((cx - 6.35 / 2, stop_y, cx + 6.35 / 2, stop_y + 1.0), -EPS, 2.8))                # 止め（屋根の下 3.0 に入る高さ）
    guide_y = lay.cover()["y_ear"][1] + 1.0                                                            # 蓋の耳より奥から
    for sx in (-1, 1):                                                                                 # 左右の案内（電池の代わりを真ん中に保つ）
        x = cx + sx * (r + fit)
        base.append(_box((min(x, x + sx * 1.0), guide_y, max(x, x + sx * 1.0), stop_y), -EPS, z["clip_top"]))
    # 電池の代わりを蓋の方へ押す試しのための穴: 電池の代わりの真ん中の穴と、その下の当て板の長い穴（裏から細い棒を差して手前へ押す。本番の基板には無い）
    pd, pw, pl = s.COUPON_PUSH
    push = _box((cx - pw / 2, cy - pl, cx + pw / 2, cy + pw / 2), -s.PCB_T - 1.0, 1.0)
    out["base"] = (_union(base) - push).clean()
    out["knob"] = knob_standin(1, lay)
    out["cell"] = cell_solid(lay) - Pos(cx, cy, -1.0) * Cylinder(pd / 2, s.CELL_T + 2.0, align=CEN_MIN)
    for n in sorted(s.COVER_VARIANTS):
        out[f"cover{n}"] = cover_solid(n, 0.0, True)
    return out


def corner_coupon_layout(gap=4.0):
    """1 枚に並べた刷る物 [(名前, 置いた立体)]: 手前の列に 電池の代わり・つまみの代わり・蓋 3 つ（**手前の面をベッドに**）、
    その奥に 当て板（平ら）、いちばん奥に 枠の切れ端（上面をベッドに）。"""
    cc = corner_coupon()
    small = [("cell", P.to_bed(cc["cell"])), ("knob", P.to_bed(cc["knob"]))] + [(n, cover_print(cc[n])) for n in sorted(cc) if n.startswith("cover")]
    out, x, y = [], 0.0, 0.0
    row = 0.0
    for name, part in small:
        bb = part.bounding_box()
        if x and x + bb.size.X > 78.0:                                        # 当て板の幅を超えたら次の行
            x, y, row = 0.0, y + row + gap, 0.0
        out.append((name, Pos(x - bb.min.X, y - bb.min.Y, -bb.min.Z) * part))
        x += bb.size.X + gap
        row = max(row, bb.size.Y)
    y += row + gap
    for name, part in (("base", P.to_bed(cc["base"])), ("frame", P.flip_to_bed(cc["frame"]))):
        bb = part.bounding_box()
        out.append((name, Pos(-bb.min.X, y - bb.min.Y, -bb.min.Z) * part))
        y += bb.size.Y + gap
    return out


def corner_coupon_plate(gap=4.0):
    """1 枚に並べた刷る物（corner_coupon_layout の立体だけ）。"""
    return Compound([part for _, part in corner_coupon_layout(gap)])


def printables():
    """刷る物（STL の名前 → 刷る向きの立体）。"""
    halves = frame_halves()
    out = {f"frame_{side}": frame_print(halves[side]) for side in SIDES}
    out["cover_battery"] = cover_print()                          # 電池の蓋（落とし込み式。1 個・手前の面をベッドに）
    out["coupon_screw_plate"] = screw_coupon_plate()
    out["coupon_corner_plate"] = corner_coupon_plate()
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
        "cover": [("cover", Pos(0, 0, 4 * e) * cover_solid())],
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
    # 右手前の角を、上からと手前から（2 枚。蓋を付けた状態）
    corner = [asm / f"corner_{v}.png" for v in ("top", "front")]
    for f in corner + [asm / f"corner_{v}_{c}.png" for v in ("top", "front") for c in ("cover", "nocover")]:   # 後ろは前の名前（蓋あり・なし）
        f.unlink(missing_ok=True)
    r = subprocess.run([paths.BLENDER, "-b", "-P", str(HERE / "tools" / "blend_corner.py")], capture_output=True, text=True, timeout=1800)
    assert "OK 2" in r.stdout and all(f.exists() for f in corner), r.stdout[-2000:] + r.stderr[-2000:]
    return files + corner


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
