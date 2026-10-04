"""cckb-click の試し刷り v2（刷る物だけ。**基板も本番の枠も変えない**）。docs/coupon-test.md 8 章。

    .venv/bin/python3 projects/cckb-click/click_coupon_v2.py        # STL と絵を build/cckb-click/ に
    .venv/bin/python3 projects/cckb-click/tools/slice_v2.py         # スライスして G-code を検査 → coupon_v2_plate_n04.gcode.3mf

2026-10-04 に利用者が角とねじの試し刷り（v1）を刷った結果: ねじが空回りする・蓋が留まらない・つまみが奥すぎる。v2 はその 3 つを 1 枚で試す:

  A ねじ    本番の枠から切り出した壁（奥の壁 = 内の肉 0.7・左の壁 = 斜めの肉 0.49）に、下穴 φ1.5 / 1.6 / 1.7（外面の溝の数 1・2・3）
  B つまみ  電源スイッチの位置 2 つを並べた壁の切れ端: (i) いまの位置・(ii) 0.75 外。切り欠きは外へ広がる形＋内側の上の縁を斜めに
  C 蓋      留め方 3 通りの蓋（点の数 1・2・3）と、枠の切れ端 1 つ（口の上の壁の下面の溝を深くした物。3 つの蓋が同じ枠に入る）

**寸法は持たない**（spec.COUPON_V2_*）。ばねの数は、蓋の立体を作るのと同じ値から作った梁の骨組みを解いて出す（spring）。
掛かりは、枠の切れ端と蓋の立体の重なりから測る（detent）。座標は本番と同じ（CAD・基板の上面 = 0）。
"""

from __future__ import annotations

import copy
import math
import sys
import types
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build123d import Axis, Box, Compound, Cylinder, Polygon, Pos, Rot, Sphere, chamfer, export_stl, extrude  # noqa: E402

import click_case as C  # noqa: E402
import click_parts as P  # noqa: E402
from foundry.layout import UNIT  # noqa: E402

LAY, S = C.LAY, C.S
EPS = C.EPS
OUT = C.OUT
TOP = S.FRAME_UNDER + S.FRAME_T
_box, _union, _prism_x, _prism_y = C._box, C._union, C._prism_x, C._prism_y
FENCE = 1.8                  # 当て板の縁の当て（幅）。高さ 2.0（v1 の角の試し刷りと同じ）


def vol(a, b):
    c = a & b
    try:
        return 0.0 if c is None else float(c.volume)
    except (AttributeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# A ねじ
# ---------------------------------------------------------------------------

def thread_engagement(d):
    """下穴 d に M2 を切ったときの掛かり（半径）と、山の高さに対する割合。"""
    major, minor = S.M2_THREAD
    e = min(major - d, major - minor) / 2
    return e, e / ((major - minor) / 2)


def flesh(piece, x, y, d, zs=(0.3, 1.4, 2.5), step=10):
    """下穴（径 d）の縁から外へ、立体の中にいる間の距離のいちばん短い物（全方位）。(肉, 角度)。"""
    loc = piece & (Pos(x, y, 2.0) * Box(10.0, 10.0, 8.0))
    best = (9.0, 0)
    for z in zs:
        for a in range(0, 360, step):
            r = d / 2 + 0.01
            while r < 4.0 and loc.is_inside((x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a)), z)):
                r += 0.02
            best = min(best, (round(r - d / 2, 2), a))
    return best


def _repilot(part, c, d):
    """本番の下穴（SCREW_PILOT_D）を埋めて、径 d で開け直す（深さは本番と同じ）。"""
    old, depth = LAY.pilot()
    x, y = c
    part = part + Pos(x, y, 0.0) * Cylinder(old / 2 + 0.03, depth + 0.03, align=C.CEN_MIN)
    return part - Pos(x, y, -1.0) * Cylinder(d / 2, depth + 1.0, align=C.CEN_MIN)


def _marks(n, at, along, face, sign):
    """外面の縦の溝 n 本。at = ねじの中心の、壁に沿う座標・along = "x" / "y"・face = 外面の座標・sign = 外へ向かう向き。"""
    w, depth, pitch, first = S.COUPON_V2_MARK
    out = []
    for j in range(n):
        u = at + first + pitch * j
        lo, hi = sorted((face - sign * depth, face + sign * 1.0))
        r = (u - w / 2, lo, u + w / 2, hi) if along == "x" else (lo, u - w / 2, hi, u + w / 2)
        out.append(_box(r, -1.0, TOP + 1.0))
    return out


@lru_cache(maxsize=None)
def screw_v2():
    """{名前: 立体}。frame_back = 奥の壁の切れ端（ねじ 3 本 = 下穴 3 通り・内の肉 0.7 の側）・frame_side = 左の壁の切れ端を 3 つ継いだ物
    （幅の広いキーの脇 = 斜めの肉 0.49 の側）・base_* = 当て板（厚さ PCB_T・穴 SCREW_HOLE_D）。holes = {名前: [(中心, 径)]}。"""
    full = C.frame_full()
    boxes = C.screw_coupon_boxes()
    pilots = S.COUPON_V2_PILOTS
    f, p = LAY.frame, LAY.pcb
    out, holes = {}, {}
    box, screws, _ = boxes["back"]
    part = full & _box(box, -1.0, TOP + 1.0)
    for i, (c, d) in enumerate(zip(screws, pilots)):
        part = _repilot(part, c, d) - _union(_marks(i + 1, c[0], "x", f[3], 1))
    out["frame_back"], holes["back"] = part.clean(), list(zip(screws, pilots))
    out["base_back"] = _plate((max(box[0], p[0]), max(box[1], p[1]), min(box[2], p[2]), min(box[3], p[3])), screws)
    box, (c,), _ = boxes["side"]
    raw = full & _box(box, -1.0, TOP + 1.0)
    pieces, centres = [], []
    for i, d in enumerate(pilots):
        dy = (i - 1) * UNIT
        piece = _repilot(raw, c, d) - _union(_marks(i + 1, c[1], "y", f[0], -1))
        pieces.append(Pos(0, dy, 0) * piece)
        centres.append((c[0], c[1] + dy))
    part = _union(pieces).clean()
    out["frame_side"], holes["side"] = part, list(zip(centres, pilots))
    out["base_side"] = _plate((max(box[0], p[0]), box[1] - UNIT, min(box[2], p[2]), box[3] + UNIT), centres)
    for name in ("frame_back", "frame_side"):
        if len(out[name].solids()) != 1:
            raise RuntimeError(f"ねじの試し刷り v2 {name} が {len(out[name].solids())} 個の塊")
    out["holes"] = holes
    return out


def _plate(r, screws=()):
    """基板の代わりの当て板（厚さ PCB_T）。ねじ穴は基板と同じ径。"""
    plate = _box(r, -S.PCB_T, 0.0)
    if screws:
        plate = plate - _union([Pos(x, y, -S.PCB_T - 1.0) * Cylinder(S.SCREW_HOLE_D / 2, S.PCB_T + 2.0, align=C.CEN_MIN) for x, y in screws])
    return plate


# ---------------------------------------------------------------------------
# B つまみ
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def shifted(dx=0.0):
    """電源スイッチを dx だけ外（+x）へ動かしたときの配置（click_layout の関数がそのまま使える）。"""
    if not dx:
        return LAY
    s2 = types.SimpleNamespace(**{k: getattr(S, k) for k in dir(S) if not k.startswith("__")})
    s2.PSW_AT = (S.PSW_AT[0] + dx, S.PSW_AT[1])
    lay = copy.copy(LAY)
    lay.s = s2
    return lay


def knob_box():
    x0, half = S.COUPON_V2_KNOB_BOX
    y = S.PSW_AT[1]
    return (x0, y - half, LAY.frame[2], y + half)


def notch_v2(lay=LAY):
    """切り欠きの新しい形（平面）: 内側の面（本体の縁 ＋ PART_CLEAR）で幅 PSW_NOTCH[0]・外面で片側 flare ずつ広い。"""
    w, fl = S.PSW_NOTCH[0], S.COUPON_V2_NOTCH["flare"]
    x0, x1, y = lay.psw_body()[2] + S.PART_CLEAR, lay.frame[2], S.PSW_AT[1]
    return [(x0, y - w / 2), (x1, y - w / 2 - fl), (x1 + 1.0, y - w / 2 - fl), (x1 + 1.0, y + w / 2 + fl), (x1, y + w / 2 + fl), (x0, y + w / 2)]


@lru_cache(maxsize=None)
def knob_stub(dx=0.0, style="v2", dots=0, leg=True):
    """右の壁の切れ端（つまみの前後 ± COUPON_V2_KNOB_BOX[1]）を**式から**作る: 壁（0〜上面）・屋根（枠の下面〜上面）・スイッチの上の厚い屋根、
    から、スイッチの空間と切り欠きを引く。style="v1" は本番と同じ切り欠き（tests が本番の枠の立体と突き合わせる）。
    leg = 左の端に足す壁（当て板に載せるため。本番には無い）。dots = 上面の点の数。"""
    lay = shifted(dx)
    box = knob_box()
    a2, f2 = LAY.key_area[2], LAY.frame[2]
    ceil = C.psw_ceiling(lay)
    body = [_box((a2, box[1], f2, box[3]), 0.0, TOP), _box((box[0], box[1], f2, box[3]), S.FRAME_UNDER, TOP),
            _box(C.psw_roof_rect(lay), ceil, S.FRAME_UNDER + EPS)]
    if leg:
        body.append(_box((box[0], box[1], box[0] + S.COUPON_CORNER_WALL, box[3]), 0.0, S.FRAME_UNDER + EPS))
    cc = C.corner_cuts(lay)
    cuts = [cc["psw"]]
    if style == "v1":
        cuts += [cc["psw_notch"], cc["on_mark"]]
    else:
        n = notch_v2(lay)
        x0, y, w, sc = n[0][0], S.PSW_AT[1], S.PSW_NOTCH[0], S.COUPON_V2_NOTCH["scoop"]
        cuts += [Pos(0, 0, -1.0) * extrude(Polygon(*n, align=None), TOP + 2.0),
                 _box((a2 - EPS, y - w / 2, x0 + EPS, y + w / 2), -1.0, ceil),
                 _prism_y([(x0 - sc - 1.0, TOP + 1.0), (x0 + EPS, TOP - sc - EPS), (x0 + EPS, TOP + 1.0)], y - w / 2, y + w / 2)]
    d, depth, pitch = S.COUPON_V2_DOT
    cuts += [Pos(box[0] + 3.0, S.PSW_AT[1] + (k - (dots - 1) / 2) * pitch, TOP - depth) * Cylinder(d / 2, depth + 1.0, align=C.CEN_MIN)
             for k in range(dots)]
    part = (_union(body) - _union(cuts)).clean()
    if len(part.solids()) != 1:
        raise RuntimeError(f"つまみの切れ端が {len(part.solids())} 個の塊")
    return part


KNOB_VARIANTS = ((0.0, 1), (S.COUPON_V2_PSW_SHIFT, 2))      # (外へ寄せる量, 点の数)。(i)・(ii)


def knob_pitch():
    return 2 * S.COUPON_V2_KNOB_BOX[1]


def _knob_block(lay):
    """電源スイッチの本体の代わり（溝つき・つまみの出る窓）。v1 の角の試し刷りと同じ作り。"""
    z = lay.z()
    fit = S.COUPON_FIT
    pb, ch, ks = lay.psw_body(), C.knob_channel(lay), lay.psw_knob_sweep()
    return _box(pb, -EPS, z["psw_top"]) - _box(ch, 0.0, z["psw_top"] + 1.0) \
        - _box((ch[2] - EPS, ks[1] - fit, pb[2] + 1.0, ks[3] + fit), 0.0, z["psw_top"] + 1.0)


@lru_cache(maxsize=None)
def knob_v2():
    """{名前: 立体}。frame = 切れ端 2 つを y に並べて継いだ物（手前 = (i) いまの位置・奥 = (ii) 外へ寄せた位置）・
    base = 当て板（基板の縁は本番と同じ）＋ 本体の代わり 2 つ ＋ 左と奥の当て・knob_1 / knob_2 = つまみの代わり（入の位置）。"""
    box, pitch, fit = knob_box(), knob_pitch(), S.COUPON_FIT
    frame = _union([Pos(0, i * pitch, 0) * knob_stub(dx, "v2", dots) for i, (dx, dots) in enumerate(KNOB_VARIANTS)]).clean()
    if len(frame.solids()) != 1:
        raise RuntimeError("つまみの切れ端 2 つが 1 つの塊にならない")
    y1 = box[3] + pitch * (len(KNOB_VARIANTS) - 1)
    p2 = LAY.pcb[2]
    base = [_plate((box[0] - fit - FENCE, box[1], p2, y1 + fit + FENCE)),
            _box((box[0] - fit - FENCE, box[1], box[0] - fit, y1 + fit + FENCE), -EPS, 2.0),
            _box((box[0] - fit - FENCE, y1 + fit, p2, y1 + fit + FENCE), -EPS, 2.0)]
    out = {"frame": frame}
    for i, (dx, _) in enumerate(KNOB_VARIANTS):
        lay = shifted(dx)
        base.append(Pos(0, i * pitch, 0) * _knob_block(lay))
        out[f"knob_{i + 1}"] = Pos(0, i * pitch, 0) * C.knob_standin(1, lay)
    out["base"] = _union(base).clean()
    return out


def finger_reach(dx=0.0, style="v2", r=None, desk=True):
    """指先を半径 r の硬い球と見て、切り欠きへどこまで入るかを**立体を当てて**測る（届きやすさを比べる物差し）。
    球の中心を、切り欠きの幅の中（y）・机より上（z。desk=True のとき球は机 = 底のシートの下面より下へ行けない）で動かし、
    枠・基板・スイッチの本体に当たらないいちばん奥（x）を二分法で探す。返り値:
      bite   つまみの上面の高さで、球がつまみの先より奥へ入る量（負 = 届かない）のいちばん大きい物
      tip_in つまみの先が枠の外面から引っ込んでいる量・open 外面での切り欠きの幅・cy, cz そのときの球の中心"""
    r = S.COUPON_V2_FINGER_R if r is None else r
    lay = shifted(dx)
    stub = knob_stub(dx, style, 0, False)
    box = knob_box()
    pb = lay.psw_body()
    things = Compound([stub, _box((box[0], box[1], LAY.pcb[2], box[3]), -S.PCB_T, 0.0), _box(pb, 0.0, lay.z()["psw_top"])])
    f2 = LAY.frame[2]
    k = lay.psw_knob(1)
    zk = S.PSW_KNOB_Z[1]
    z_min = (-S.PCB_T - S.BOTTOM_SHEET_T + r) if desk else zk
    best = dict(bite=-99.0)
    for cy in (S.PSW_AT[1] + t for t in (-2.0, -1.0, 0.0, 1.0, 2.0)):
        for cz in (z_min + 0.75 * i for i in range(6)):
            if abs(cz - zk) >= r:
                continue
            lo, hi = k[2] - r, f2 + r + 1.0                     # lo = 当たる・hi = 当たらない
            for _ in range(11):
                mid = (lo + hi) / 2
                if vol(things, Pos(mid, cy, cz) * Sphere(r)) > 1e-4:
                    lo = mid
                else:
                    hi = mid
            bite = k[2] - (hi - math.sqrt(r * r - (cz - zk) ** 2))
            if bite > best["bite"]:
                best = dict(bite=round(bite, 2), cx=round(hi, 2), cy=cy, cz=round(cz, 2), r=r)
    n = lay.psw_notch() if style == "v1" else notch_v2(lay)
    ys = [q[1] for q in n if abs(q[0] - f2) < 1e-6]
    best.update(tip_in=round(f2 - k[2], 2), open=round(max(ys) - min(ys), 2), depth=round(f2 - n[0][0], 2))
    return best


# ---------------------------------------------------------------------------
# C 蓋
# ---------------------------------------------------------------------------

def cover_box():
    left, right, back = S.COUPON_V2_COVER_BOX
    cv = LAY.cover()
    return (cv["x0"] - left, LAY.frame[1], cv["x1"] + right, cv["y1"] + back)


def groove_cut():
    """口の上の壁の下面の溝（左右）: 手前に COUPON_V2_LIP の肉を残して、奥は電池クリップの空間まで抜く。上はクリップの屋根の下面まで
    （深さ = CLIP_ROOF_UNDER − 口の上の壁の下面）。v1 の浅い三角の溝（click_case.detent_groove）は、この中に含まれる。"""
    cv = LAY.cover()
    ya = cv["y0"] + S.COUPON_V2_LIP
    yb = LAY.clip_body()[1] - S.PART_CLEAR + 0.1
    return _union([_box((cv["x0"], ya, cv["nx0"] + EPS, yb), cv["z_slot"] - EPS, S.CLIP_ROOF_UNDER),
                   _box((cv["nx1"] - EPS, ya, cv["x1"], yb), cv["z_slot"] - EPS, S.CLIP_ROOF_UNDER)])


@lru_cache(maxsize=None)
def cover_stub(grooves=True):
    """枠の切れ端（本番の枠から切り出した電池の口のまわり）＋ 奥の両端の足（当て板に載せるため）。grooves=True で溝を深くする。"""
    box = cover_box()
    part = C.frame_full() & _box(box, -1.0, TOP + 1.0)
    w = S.COUPON_CORNER_WALL
    for x in (box[0], box[2] - w):
        part = part + _box((x, box[3] - w, x + w, box[3]), 0.0, S.CLIP_ROOF_UNDER + EPS)
    if grooves:
        part = part - groove_cut()
    part = part.clean()
    if len(part.solids()) != 1:
        raise RuntimeError(f"蓋の枠の切れ端が {len(part.solids())} 個の塊")
    return part


def cover_base():
    box, fit = cover_box(), S.COUPON_FIT
    p1 = LAY.pcb[1]
    return _union([_plate((box[0] - fit - FENCE, p1, box[2], box[3] + fit + FENCE)),
                   _box((box[0] - fit - FENCE, p1, box[0] - fit, box[3] + fit + FENCE), -EPS, 2.0),
                   _box((box[0] - fit - FENCE, box[3] + fit, box[2], box[3] + fit + FENCE), -EPS, 2.0)]).clean()


def hook_profile(h):
    """山の断面（y–z・反時計回り）と、山の奥の端の y。手前の面は COUPON_V2_HOOK[0] 度（刷る向きで 45° より寝ない）。"""
    cv = LAY.cover()
    a, b, flat = S.COUPON_V2_HOOK
    z = cv["z_slot"] - S.COVER_CLEAR
    ys = cv["y0"] + S.COUPON_V2_LIP + 0.1
    y1 = ys + h / math.tan(math.radians(a))
    y2 = y1 + flat
    y3 = y2 + h / math.tan(math.radians(b))
    return [(ys, z - EPS), (y3, z - EPS), (y2, z + h), (y1, z + h)], y3


def _geom(n):
    """蓋 n の寸法（立体とばねの骨組みの両方がここから作る）。u = 真ん中からの距離。"""
    v = dict(S.COUPON_V2_COVERS[n])
    cv, cl = LAY.cover(), S.COVER_CLEAR
    v.update(xm=(cv["x0"] + cv["x1"]) / 2, half=(cv["x1"] - cv["x0"]) / 2 - cl, z_arm=cv["z_slot"] - cl, z_bot=0.1,
             root_half=(cv["nx1"] - cv["nx0"]) / 2 - cl)
    if v["kind"] == "hairpin":
        t = v["t"]
        v.update(u_post=v["post"] / 2, u_u1=v["post"] / 2 + v["slit"], u_tip=v["half"] - v["relief"])
        v.update(u_u0=v["u_u1"] + v["u"], u_riser=v["u_tip"] - v["riser"])
        v.update(u_leg1=v["u_riser"] - v["slit"])
        v.update(u_neck=v["u_leg1"] - v["neck"], z1=(v["z_arm"] - t, v["z_arm"]), z2=(v["z_arm"] - 2 * t - v["gap"], v["z_arm"] - t - v["gap"]))
        v.update(z_slab=v["z2"][0] - v["sag"], hook_u=(v["u_riser"], v["u_tip"]), h=cl + v["hook"])
    elif v["kind"] == "arms":
        length, t, gap = v["arm"]
        v.update(u_post=v["half"] - length, t=t, z1=(v["z_arm"] - t, v["z_arm"]), z_slab=v["z_arm"] - t - gap,
                 hook_u=(v["half"] - v["tip"], v["half"]), h=cl + v["hook"])
    return v


@lru_cache(maxsize=None)
def cover_v2(n, hooks=True):
    """蓋 n（1 折り返しばね・2 細い腕・3 つぶれる筋）。組んだ位置・CAD。上の板・付け根・爪の溝・外形は v1 の蓋（click_case.cover_solid）と同じ。
    **外形を作って手前の面の縁を落としてから、隙間を切り抜く**（細い腕の縁は落とさない）。hooks=False は山・筋の無い形（滑る道の検査）。"""
    g = _geom(n)
    cv, cl = LAY.cover(), S.COVER_CLEAR
    y0, yf, yr, y1 = cv["y0"], cv["y_front"], cv["y_root"], cv["y1"] - cl
    xm, half, z_arm, z_root = g["xm"], g["half"], g["z_arm"], cv["z_root"]

    def bx(ua, ub, z0, z1, sg, ya=y0, yb=yf):
        xa, xb = sorted((xm + sg * ua, xm + sg * ub))
        return _box((xa, ya, xb, yb), z0, z1)

    body = [_box((xm - half, y0, xm + half, yf), g["z_bot"], z_arm),
            _prism_y(C._cover_profile(z_root), y0, yr), _prism_y(C._cover_profile(cv["z_plate"]), y0, y1)]
    cuts, adds = [], []
    if g["kind"] == "ribs":
        body.append(_box((xm - g["root_half"], y0, xm + g["root_half"], yf), z_arm - EPS, z_root + EPS))
    else:
        body.append(_box((xm - g["u_post"], y0, xm + g["u_post"], yf), z_arm - EPS, z_root + EPS))        # 真ん中の柱
    for sg in (-1, 1):
        far, ya, yb = half + 1.0, y0 - 1.0, yf + 1.0
        if g["kind"] == "hairpin":
            body.append(bx(g["u_neck"], g["u_leg1"], z_arm - EPS, z_root + EPS, sg))                       # 上の腕の付け根
            cuts += [bx(g["u_post"], far, g["z_slab"], g["z2"][0], sg, ya, yb),                             # 下の腕の下
                     bx(g["u_u0"], g["u_riser"], g["z2"][1], g["z1"][0], sg, ya, yb),                       # 上下の腕の間
                     bx(g["u_post"], g["u_u1"], g["z2"][0] - EPS, z_arm + 1.0, sg, ya, yb),                 # 柱と折り返しの間
                     bx(g["u_leg1"], g["u_riser"], g["z1"][0] - EPS, z_arm + 1.0, sg, ya, yb),              # 上の腕と立ち上がりの間
                     bx(g["u_tip"], far, g["z2"][0] - EPS, z_arm + 1.0, sg, ya, yb)]                        # 端の逃げ
        elif g["kind"] == "arms":
            cuts.append(bx(g["u_post"], far, g["z_slab"], g["z1"][0], sg, ya, yb))                          # 腕の下
        if hooks and g["kind"] in ("hairpin", "arms"):
            pts, _ = hook_profile(g["h"])
            xa, xb = sorted((xm + sg * g["hook_u"][0], xm + sg * g["hook_u"][1]))
            adds.append(_prism_x(pts, xa, xb))
        if hooks and g["kind"] == "ribs":
            (rh, rw), xe = g["rib"], xm + sg * half
            for zc in g["z"]:                                                                               # 筋: 平面で台形（前後に斜面）を z に rw 押し出す
                plan = [(xe - sg * EPS, y0 + 0.3), (xe + sg * rh, y0 + 0.6), (xe + sg * rh, yf - 0.4), (xe - sg * EPS, yf - 0.1)]
                adds.append(Pos(0, 0, zc - rw / 2) * extrude(Polygon(*(plan if sg > 0 else plan[::-1]), align=None), rw))
    part = _union(body).clean()
    part = chamfer(part.edges().group_by(Axis.Y)[0], S.COVER_FOOT)
    if cuts:
        part = part - _union(cuts)
    if adds:
        part = part + _union(adds)
    gw, gd, gz, gy = S.COVER_GRIP                                                                           # 爪の溝（v1 と同じ）
    top, ya = cv["z_top"], y0 + gy
    part = part - _prism_x([(ya, top - gz), (ya + gd - gz, top - gz), (ya + gd + 0.1, top + 0.1), (ya, top + 0.1)], xm - gw / 2, xm + gw / 2)
    d, depth, pitch = S.COUPON_V2_DOT
    part = part - _union([Pos(xm + (k - (n - 1) / 2) * pitch, y1 - 1.0, top - depth) * Cylinder(d / 2, depth + 1.0, align=C.CEN_MIN)
                          for k in range(n)])
    part = part.clean()
    if len(part.solids()) != 1:
        raise RuntimeError(f"蓋 {n} が {len(part.solids())} 個の塊")
    return part


def cover_print(n):
    """蓋を刷る向き（手前の面をベッドに。v1 と同じ）。"""
    return C.cover_print(cover_v2(n))


def detent(stub, cover, step=0.05):
    """蓋を手前へ step ずつ引いて、枠の切れ端との重なりの高さのいちばん大きい物（= 山を越えるのに要るたわみ）を左右で測る。
    {"left": (たわみ, 引いた量), "right": ...}。重なりが無ければ空。"""
    cv = LAY.cover()
    xm = (cv["x0"] + cv["x1"]) / 2
    best = {}
    for i in range(1, int(3.0 / step) + 1):
        hit = stub & (Pos(0, -step * i, 0) * cover)
        for sol in (hit.solids() if hit is not None else []):
            b = sol.bounding_box()
            side = "left" if b.center().X < xm else "right"
            if b.size.Z > 1e-4 and (side not in best or b.size.Z > best[side][0] + 1e-6):
                best[side] = (round(b.size.Z, 3), round(step * i, 2))
    return best


def frame_fe(nodes, elems, fixed, load, b, e=C.PLA_E):
    """平面の骨組み（曲げ ＋ 伸び）を解く。nodes [(x, z)]・elems [(i, j, 太さ)]・fixed = 固定する節・load = 下向きに 1 N 掛ける節。
    返り値 (変位 [[ux, uz, θ], ...], 各要素の、表面のひずみのいちばん大きい値)。"""
    import numpy as np

    n = len(nodes)
    k = np.zeros((3 * n, 3 * n))
    mats = []
    for i, j, t in elems:
        dx, dz = nodes[j][0] - nodes[i][0], nodes[j][1] - nodes[i][1]
        ln = math.hypot(dx, dz)
        c, s = dx / ln, dz / ln
        a, inertia = b * t, b * t ** 3 / 12
        ea, ei = e * a / ln, e * inertia
        kl = np.array([[ea, 0, 0, -ea, 0, 0],
                       [0, 12 * ei / ln ** 3, 6 * ei / ln ** 2, 0, -12 * ei / ln ** 3, 6 * ei / ln ** 2],
                       [0, 6 * ei / ln ** 2, 4 * ei / ln, 0, -6 * ei / ln ** 2, 2 * ei / ln],
                       [-ea, 0, 0, ea, 0, 0],
                       [0, -12 * ei / ln ** 3, -6 * ei / ln ** 2, 0, 12 * ei / ln ** 3, -6 * ei / ln ** 2],
                       [0, 6 * ei / ln ** 2, 2 * ei / ln, 0, -6 * ei / ln ** 2, 4 * ei / ln]])
        r = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        tm = np.zeros((6, 6))
        tm[:3, :3] = tm[3:, 3:] = r
        dof = [3 * i, 3 * i + 1, 3 * i + 2, 3 * j, 3 * j + 1, 3 * j + 2]
        k[np.ix_(dof, dof)] += tm.T @ kl @ tm
        mats.append((dof, kl, tm, t, ei))
    f = np.zeros(3 * n)
    f[3 * load + 1] = -1.0
    free = [d for d in range(3 * n) if d // 3 != fixed]
    u = np.zeros(3 * n)
    u[free] = np.linalg.solve(k[np.ix_(free, free)], f[free])
    strain = []
    for dof, kl, tm, t, ei in mats:
        q = kl @ (tm @ u[dof])
        strain.append(max(abs(q[2]), abs(q[5])) * (t / 2) / ei)
    return u.reshape(n, 3), strain


def spring(n, t_extra=0.0):
    """蓋 n のばねの計算（片側）。**寸法は立体を作るのと同じ _geom から**。骨組みを解いて、山を掛かりの分だけ下げたときの:
      strain ひずみ（腕の表面・いちばん大きい所）・force 山 1 つの力 [N]・hold 引き抜く力の見積もり [N]（左右の和・斜面は COUPON_V2_HOOK[0] 度・摩擦 0.3）・
      sag 腕の先の下がり（下の隙間に収まるか）・lean 山の頂が外（口の壁の側）へ倒れる量・lever 付け根から山までの骨組みの長さ
    t_extra は刷り上がりの太りを見るため（線 2 本で 0.7 → 約 0.76）。筋の蓋（3）は None。"""
    g = _geom(n)
    if g["kind"] == "ribs":
        return None
    b = S.COVER_FRONT_T
    t = g["t"] + t_extra
    delta = g["hook"]
    if g["kind"] == "hairpin":
        zc1, zc2 = sum(g["z1"]) / 2, sum(g["z2"]) / 2
        uu, uh = (g["u_u1"] + g["u_u0"]) / 2, sum(g["hook_u"]) / 2
        nodes = [(g["u_neck"], zc1), (uu, zc1), (uu, zc2), (uh, zc2), (g["u_tip"], zc2)]
        elems = [(0, 1, t), (1, 2, g["u"] + t_extra), (2, 3, t), (3, 4, t)]
        load, tip, lever = 3, 4, (g["u_neck"] - uu) + (zc1 - zc2) + (uh - uu)
        top = g["z_arm"] + g["h"] - zc2
    else:
        zc = sum(g["z1"]) / 2
        nodes = [(g["u_post"], zc), (g["hook_u"][0], zc), (g["half"], zc)]
        elems = [(0, 1, t), (1, 2, t)]
        load, tip, lever = 1, 2, g["hook_u"][0] - g["u_post"]
        top = g["z_arm"] + g["h"] - zc
    u, strain = frame_fe(nodes, elems, 0, load, b)
    per_n = -u[load][1]
    force = delta / per_n
    alpha = math.radians(S.COUPON_V2_HOOK[0])
    force, per = float(force), float(max(strain))
    return dict(strain=per * force, force=force, hold=2 * force * math.tan(alpha + math.atan(0.3)),
                sag=float(-u[tip][1]) * force, lean=float(abs(u[load][2])) * force * top, lever=lever, t=t, delta=delta)


@lru_cache(maxsize=None)
def cover_set():
    """{名前: 立体}: frame（枠の切れ端）・base（当て板）・cover_1〜3。"""
    out = {"frame": cover_stub(), "base": cover_base()}
    for n in S.COUPON_V2_COVERS:
        out[f"cover_{n}"] = cover_v2(n)
    return out


# ---------------------------------------------------------------------------
# 1 枚に並べる
# ---------------------------------------------------------------------------

COVER_NAMES = {"hairpin": "折り返しばね", "arms": "細い腕 2 本", "ribs": "ばね無し・筋"}


# [(記号, 名前, 刷る向きの立体)]。記号は絵（coupon_v2_howto.png）と docs/coupon-test.md 8 章の表と同じ
def pieces():
    sc, kn, cs = screw_v2(), knob_v2(), cover_set()
    turn = lambda v: Rot(0, 0, 90) * v                                    # noqa: E731（長い辺を X に）
    out = [
        ("A1", "ねじ・奥の壁（下穴 3 通り）", P.flip_to_bed(sc["frame_back"])),
        ("A2", "A1 の当て板", P.to_bed(sc["base_back"])),
        ("A3", "ねじ・左の壁（下穴 3 通り）", P.flip_to_bed(turn(sc["frame_side"]))),
        ("A4", "A3 の当て板", P.to_bed(turn(sc["base_side"]))),
        ("B1", "つまみ・壁の切れ端（位置 2 つ）", P.flip_to_bed(turn(kn["frame"]))),
        ("B2", "B1 の当て板", P.to_bed(turn(kn["base"]))),
        ("B3", "つまみの代わり（いまの位置）", P.to_bed(turn(kn["knob_1"]))),
        ("B4", "つまみの代わり（0.75 外）", P.to_bed(turn(kn["knob_2"]))),
        ("C1", "蓋・枠の切れ端", P.flip_to_bed(cs["frame"])),
        ("C2", "C1 の当て板", P.to_bed(cs["base"])),
    ]
    out += [(f"C{2 + n}", f"蓋 {n}（点 {n} 個・{COVER_NAMES[S.COUPON_V2_COVERS[n]['kind']]}）", cover_print(n)) for n in S.COUPON_V2_COVERS]
    return out


def plate_layout(gap=4.0, width=150.0):
    """[(記号, 名前, 置いた立体)]。左から並べ、幅を超えたら次の行。"""
    out, x, y, row = [], 0.0, 0.0, 0.0
    for tag, name, part in pieces():
        bb = part.bounding_box()
        if x > 0 and x + bb.size.X > width:
            x, y, row = 0.0, y + row + gap, 0.0
        out.append((tag, name, Pos(x - bb.min.X, y - bb.min.Y, -bb.min.Z) * part))
        x += bb.size.X + gap
        row = max(row, bb.size.Y)
    return out


def plate():
    return Compound([p for _, _, p in plate_layout()])


def placed_holes():
    """1 枚に並べた板の上での、下穴の中心 {記号: [((x, y), 径)]}（スライスした G-code と突き合わせるため）。
    切れ端と一緒に小さな印を同じ手順で回して置き、印の行き先を読む（変換を式で写さない）。"""
    sc = screw_v2()
    at = {tag: part.bounding_box() for tag, _, part in plate_layout()}
    out = {}
    for tag, name, turn in (("A1", "back", False), ("A3", "side", True)):
        marks = [Pos(x, y, 1.0) * Sphere(0.05) for (x, y), _ in sc["holes"][name]]
        group = Compound([sc[f"frame_{name}"]] + marks)
        group = P.flip_to_bed(Rot(0, 0, 90) * group if turn else group)
        cs = [m.bounding_box().center() for m in list(group.solids())[1:]]
        out[tag] = [((c.X + at[tag].min.X, c.Y + at[tag].min.Y), d) for c, (_, d) in zip(cs, sc["holes"][name])]
    return out


def export(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    part = plate()
    size = part.bounding_box().size
    assert max(size.X, size.Y) <= S.PRINT_MAX, f"coupon_v2_plate: {size.X:.1f} × {size.Y:.1f} が A1 mini に置けない"
    export_stl(part, str(out / "coupon_v2_plate.stl"))
    made = {"coupon_v2_plate": (size.X, size.Y, size.Z)}
    for n in S.COUPON_V2_COVERS:                                          # 蓋だけ刷り直すとき
        export_stl(cover_print(n), str(out / f"coupon_v2_cover_{n}.stl"))
        made[f"coupon_v2_cover_{n}"] = tuple(cover_print(n).bounding_box().size)
    return made


def numbers():
    """文書と絵に載せる数（全部ここで測る・計算する）。"""
    sc = screw_v2()
    out = {"screw": [], "knob": [], "cover": {}}
    for name, wall in (("back", "奥の壁"), ("side", "左の壁")):
        for (x, y), d in sc["holes"][name]:
            e, share = thread_engagement(d)
            out["screw"].append(dict(wall=wall, d=d, engage=round(e, 3), share=round(share, 2), flesh=flesh(sc[f"frame_{name}"], x, y, d)[0]))
    for label, dx, style in (("(i) いまの位置・v1 の切り欠き", 0.0, "v1"), ("(i) いまの位置・新しい切り欠き", 0.0, "v2"),
                             ("(ii) 0.75 外・新しい切り欠き", S.COUPON_V2_PSW_SHIFT, "v2")):
        out["knob"].append(dict(label=label, **finger_reach(dx, style), lifted=finger_reach(dx, style, desk=False)["bite"]))
    stub = cover_stub()
    for n in S.COUPON_V2_COVERS:
        sp, sp_fat = spring(n), spring(n, 0.06)
        out["cover"][n] = dict(detent=detent(stub, cover_v2(n)), spring=sp, strain_printed=None if sp_fat is None else sp_fat["strain"])
    return out


def main():
    import click_coupon_v2_figs as figs

    for stem, size in sorted(export().items()):
        print(f"OK {stem}.stl  {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}")
    num = numbers()
    for row in num["screw"]:
        print("ねじ", row)
    for row in num["knob"]:
        print("つまみ", row)
    for n, row in num["cover"].items():
        print("蓋", n, row)
    print("絵", figs.howto(OUT, num))
    return 0


if __name__ == "__main__":
    sys.exit(main())
