"""電池の蓋の**別案 B（左右のばねの腕で掛ける蓋）の試し刷り**。本番の蓋（click_case.cover_solid）・本番の枠・基板は変えない。**刷る物だけ**。

    .venv/bin/python3 projects/cckb-click/click_cover_snap.py     # STL・絵・数 → build/cckb-click/coupon_cover_snap_plate.stl

なぜ作るか: 利用者の問い「こんなに複雑でないといけないのか。口の両側に爪があって、蓋がそれに掛かる、ふつうの板ばね式では駄目なのか」。
B は、その形をいちばん素直に作った物: **蓋 1 個 = 手前の板 ＋ 左右に 1 本ずつのばねの腕 ＋ 腕の先のかぎ**。手前からまっすぐ押し込むと、左右がカチッと掛かる。
外すときは、手前の面に出ている 2 本の腕の先（つまみ）を、2 本の指の爪で**内へつまんで**引き抜く。

測って分かった場所の制約（docs/coupon-cover-snap.md の表）:
  - かぎの掛かり 1.0 以上を、この機種のひずみの上限（spec.PLA_STRAIN_USE × PLA_BEND / PLA_E = 1.52 %）の中で外すには、線 2 本の腕（0.85）で長さ 10.4 以上が要る
  - 口の脇で奥行きが取れるのは、クリップのランド（手前の縁 y = −43.5）の手前まで = 6.5 → 足りない。**腕はランドの外側（x < 109.5・x > 134.5）を通す**
  - 右は、外周のねじ H15（x = 136.5）の下穴が、ちょうど腕の通り道にある → **H15 を 140.0 へ動かした基板を前提にする**（基板は変えていない。提案だけ）
  - 腕を根元から長く取るので、腕は「奥で付いて、手前へ戻る」形（先が手前の面に出る = つまめる）。電池が押す力は、腕を**押し縮める向き**に通り、
    かぎは外へ開く向きに押される（外へは口の縁が止める）= 押されるほど掛かる
  - 蓋は平らに刷る（**底をベッドに**）。腕とかぎは平面の形そのまま（宙に浮かない・層を跨がない）。高さは 2 段: 屋根の下に入る所 HS・口の真ん中（上まで）
座標は CAD（基板の上面 = 0・x 右・y 奥）。左右は電池の中心 x = 122 で対称。寸法はこのファイルが持つ（本番の spec には入れない: 採るかは利用者が刷って決める）。
"""

from __future__ import annotations

import math
import random
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build123d import Compound, Cylinder, Plane, Polygon, Pos, Rot, export_stl, extrude, mirror, offset  # noqa: E402

import click_case as C  # noqa: E402
import click_cover_slide as K  # noqa: E402  （読むだけ: vol・section・_place）
import click_parts as P  # noqa: E402

LAY, S = C.LAY, C.S
EPS = C.EPS
OUT = C.OUT
TOP = S.FRAME_UNDER + S.FRAME_T
_box, _union = C._box, C._union
vol = K.vol

# ---------------------------------------------------------------------------
# 寸法（全部 [試し刷り]。本番には入っていない）
# ---------------------------------------------------------------------------
(CX, CY), CELL_R = LAY.cell()
Y0 = LAY.frame[1]             # 枠の外面
REC = 0.15                    # 蓋の手前の面を、外面から引っ込める量（かぎが縁に当たった位置で）
YF = Y0 + REC
CL = 0.15                     # 蓋と枠の隙（片側）
A0, A1 = 112.5, 2 * CX - 112.5          # 口の真ん中（上まで開いた溝。電池 φ16 の道 113.5〜130.5 ＋ 足）
YB = LAY.clip_body()[1] - 0.2           # 蓋の真ん中の塊の奥の面（クリップの板の端の 0.2 手前）
STRIP_Z = 3.5                 # 真ん中の塊の、電池の上に渡る帯の下面（電池の上面 3.2 の 0.3 上。刷るときは橋 → 垂れの分を見て 0.3）
POCKET_R = 7.5                # 電池を受けるくぼみの半径（電池 8.0 より小さい = 電池は、くぼみの左右の角 2 点で当たる。真ん中は当たらない）
CELL_GAP = 0.2                # くぼみの角と電池の、前後の隙
LIP_T = 1.6                   # 口の左右の縁（手前の壁の残り）の厚さ。この奥の面に、かぎが掛かる
YL = Y0 + LIP_T
SEAT = 0.05                   # かぎと縁の、前後の隙（名目の位置）
XLIP = 106.9                  # 左の縁の端（腕の先の外の面が、ここに当たる）。右は対称
XPK = 105.6                   # かぎの入る空洞の、外の壁（ねじ H14 の下穴の縁 104.8 から 0.8）
HOOK = 1.15                   # かぎの出のいちばん大きい値（= 縁との掛かり。空洞の壁と 0.15）。蓋ごとの値は VARIANTS
HOOK_FLAT, HOOK_RAMP = 0.45, 1.3        # かぎの平らな所の長さ・斜めの所の長さ ÷ 出（入れるとき、縁の角に乗って腕を内へ押す）
ZW = S.FRAME_UNDER            # 腕の通る窓の上の端 = 枠の屋根の下面（3.0）。その上は、枠の手前の壁を残す（まぐさ）
HS = ZW - 0.2                 # 蓋の、屋根の下に入る所の高さ
XRO = 106.95                  # 腕の付け根の、外の面（縁の端 XLIP より内 = 抜くとき、腕の付け根の側が縁に引っ掛からない）
YR = -37.4                    # 腕の付け根（ここから手前へ伸びる。右のコンデンサ C_BAT〔y ≥ −34.7〕の手前に、付け根の塊と奥の壁が入る所）
YJ = -36.1                    # 付け根の塊の、奥の面
ARM_L = YR - YF               # 腕の長さ
XSI = LAY.clip_pads()[0][0] - S.PART_CLEAR      # 蓋の柱（ランドの脇を通る所）の、内の面 = ランドの外の縁の 0.4 外（109.5）
YWB = LAY.clip_pads()[0][1] - 0.375             # ランドの手前で、蓋の胴が内へ広がれる所の、奥の端
XWI = LAY.clip_body()[0] - 0.2                  # その内の端（クリップの板の端の 0.2 外）
T_MAX = 1.00                  # 腕のいちばん厚い蓋の、腕の厚さ（胴の外の縁は、これで決める）
DTIP = 1.65                   # 腕の先が内へ動ける量（胴に当たって止まる = 行き過ぎの止め）
GAP_MIN = 0.35                # 腕と胴の間の、いちばん狭い隙（付け根の近く。線で埋まらない幅）
GUIDE_CL = 0.15               # 付け根の塊と、枠の案内の壁の隙（左右）
BACK_CL = 0.15                # 付け根の塊と、枠の奥の壁の隙（押し込める量 = 蓋の前後の遊び − SEAT）
BED = 0.15                    # ベッドの面（底）の縁を落とす量（1 層目の太り）
SCALLOP = 0.9                 # 縁の手前の角を斜めに落とす量（爪が、腕の先の外の面に掛かる所。入れるときの案内も兼ねる）
ASM = 0.02                    # 立体どうしの重なりを見るとき、腕の先を縁から離しておく量（計算上の接触を重なりに数えない）
H15_NEW = (2 * CX - 104.0, -48.225)             # **動かした先のねじ H15**（H14 と対称 = 140.0）。いまの基板は (136.5, −48.225)
H15_OLD = next(c for n, c, _ in LAY.screws() if n == "H15")
PRINT_ERR = 0.15              # 刷りの誤差の見込み（片側）
MARK = S.COVER_MARK           # 見分ける切り欠き（幅・深さ・間隔）
# 蓋 3 つ: 腕の厚さ t・かぎの出 hook・予圧 pre（腕の先が、縁より外へ出て刷られている量 = 掛けた後も縁を押す → がたを取る）。
# **外すときの付け根のひずみが上限（1.52 %）に入る組み合わせだけ**（厚い腕 × 大きいかぎ は入らない: 検査が見る）。嵌めの隙（案内 0.15・奥 0.15）は 3 つとも同じ
VARIANTS = {1: dict(t=0.85, hook=1.15, pre=0.20),      # やわらかい腕（線 2 本）・大きいかぎ
            2: dict(t=0.95, hook=1.15, pre=0.15),      # 本番の候補
            3: dict(t=1.00, hook=1.05, pre=0.15)}      # 固い腕・少し小さいかぎ
MAIN = 2
BOX = (100.5, LAY.frame[1], LAY.frame[2], S.COUPON_CORNER_BOX[1])        # 切り出す範囲（ねじ H14 の座まで入れる。本番の角の試し刷りは 106.0 から）
MOD = (XPK - EPS, Y0 - 1.0, 2 * CX - XPK + EPS, -35.0)                     # B が本番の枠から変えた範囲（平面）。ほかに、H15 の座と下穴（H15_MOD）
H15_MOD = (2 * CX - XPK - EPS, Y0 - 1.0, H15_NEW[0] + S.SCREW_BOSS_HALF + EPS, -46.0)
GS = (100.0, 500.0, S.DROP_G)                                            # 電池の慣性を見る落下の加速度 [G]。**どれも仮定**（S.DROP_G は携帯機器の規格から借りた値）
PUSH = 20.0                   # 指で電池を強く押す力 [N]（仮定）


def mx(x):
    """左右を入れ替える（電池の中心で折り返す）。"""
    return 2 * CX - x


def _mirror(part):
    return mirror(part, about=Plane.YZ.offset(CX))


def shape(a):
    """先に力を掛けた片持ち梁の撓みの形（付け根から a の所・先で 1）。"""
    a = min(max(a, 0.0), ARM_L)
    return (3 * a * a * ARM_L - a ** 3) / (2 * ARM_L ** 3)


def arm_outer(y, pre, d=0.0):
    """左の腕の、外の面の x（y の所）。pre = 予圧（刷った形で、先が縁より外へ出ている量）・d = 先を、刷った形から内へ動かした量。"""
    a = YR - y
    return XRO + (XLIP - pre - XRO) * a / ARM_L + d * shape(a)


def body_edge(y):
    """左の胴の、外の縁の x（腕が DTIP 動いても当たらない線。付け根の近くは GAP_MIN）。"""
    a = YR - y
    return XRO + (XLIP - XRO) * a / ARM_L + T_MAX + max(GAP_MIN, 0.1 + DTIP * shape(a))


YS = YL + SEAT                                   # かぎの、掛かる面
A_HOOK = YR - (YS + HOOK_FLAT / 2)               # 付け根から、かぎの掛かる所まで


def release_tip(pre, hook):
    """外すのに要る、腕の先の動き（刷った形から）: かぎの所で 予圧 ＋ 掛かり ＋ 0.15 動かす。"""
    return (pre + hook + 0.15) / shape(A_HOOK)


def _arm_pts(t, pre, d, hook, n=24):
    """左の腕の平面の形（付け根 → 先 → 付け根）。かぎは外（−x）へ出る。先の外の角は斜め。"""
    def xo(y):
        return arm_outer(y, pre, d)

    end = YS + HOOK_FLAT + hook * HOOK_RAMP              # かぎの奥の端
    ys = [YR + 0.3 - (YR + 0.3 - end) * i / n for i in range(n + 1)]
    outer = [(xo(y), y) for y in ys]
    if hook > 0:
        outer += [(xo(YS + HOOK_FLAT) - hook, YS + HOOK_FLAT), (xo(YS) - hook, YS), (xo(YS), YS)]
    outer += [(xo(YF + 0.3), YF + 0.3), (xo(YF) + 0.3, YF)]
    inner = [(xo(YF) + t, YF)] + [(xo(y) + t, y) for y in reversed(ys)]
    return outer + inner


def _poly(pts):
    return Polygon(*K._ccw(list(pts)), align=None)


def _side_pts(n=24):
    """左の胴（屋根の下に入る所）の平面の形: 外の縁（腕から離れた線）・ランドの脇の柱・ランドの手前の広い所。"""
    ys = [YF + (YR - YF) * i / n for i in range(n + 1)]
    return [(body_edge(y), y) for y in ys] + [(XSI, YR), (XSI, YWB), (XWI, YWB), (XWI, YF)]


def pocket_center():
    """電池を受けるくぼみの円の中心。くぼみの左右の角（蓋の奥の面 YB の上）で、電池との前後の隙が CELL_GAP になる所に置く。"""
    dy = CY - YB - CELL_GAP
    hw = math.sqrt(CELL_R ** 2 - dy ** 2)                # 角の、中心からの x
    return (CX, YB + math.sqrt(POCKET_R ** 2 - hw ** 2)), hw


@lru_cache(maxsize=None)
def cover(variant=MAIN, mark=True, dl=None, dr=None, t=None, hook=None):
    """B の蓋（掛けた位置）。dl・dr = 左・右の腕の先を、刷った形から内へ動かした量（既定 = 掛けた形: 予圧 ＋ ASM）。
    dl = dr = 0.0 が刷る形。t・hook を渡すと、その厚さの腕・その出のかぎ（検査を壊して見る形。hook = 0 で、かぎ無し）。"""
    v = VARIANTS[variant]
    t = v["t"] if t is None else t
    hook = v["hook"] if hook is None else hook
    pre = v["pre"]
    dl = pre + ASM if dl is None else dl
    dr = pre + ASM if dr is None else dr

    def half(d):
        return [_poly(_arm_pts(t, pre, d, hook)), _poly(_side_pts()), C._rect2d((XRO, YR - EPS, XSI, YJ))]

    low = _union(half(dl) + [_mirror(q) for q in half(dr)])
    mid = C._rect2d((A0 + CL, YF, A1 - CL, YB))
    (px, py), _ = pocket_center()
    pocket = Pos(px, py, -1.0) * Cylinder(POCKET_R, STRIP_Z + 1.0, align=P.CEN_MIN)
    body = extrude(low, HS) + (extrude(mid, TOP) - pocket)
    plan = (low + mid) - _circle2d(POCKET_R, px, py)
    if mark:
        mw, md, mp = MARK
        x1 = A1 - CL - 1.2
        cuts = [(x1 - i * mp - mw, YB - md, x1 - i * mp, YB + 1.0) for i in range(variant)]
        body = body - _union([_box(q, -1.0, TOP + 1.0) for q in cuts])
        plan = plan - _union([C._rect2d(q) for q in cuts])
    # ベッドの面（底）の縁を落とす: 下の 2 層を、平面の形を内へ寄せた段に置き換える
    body = body - _box((XPK - 2.0, Y0 - 1.0, mx(XPK) + 2.0, YJ + 2.0), -1.0, 0.2)
    body = body + extrude(offset(plan, -BED), 0.1 + EPS) + Pos(0, 0, 0.1) * extrude(offset(plan, -BED / 2), 0.1 + EPS)
    body = body.clean()
    if len(body.solids()) != 1:
        raise RuntimeError(f"B の蓋が {len(body.solids())} 個の塊")
    return body


def _circle2d(r, x, y):
    from build123d import Circle

    return Pos(x, y) * Circle(r)


def posed(part, dx=0.0, dy=0.0, dz=0.0, rz=0.0, rx=0.0, pivot=None):
    """part を、pivot（既定は蓋の手前の真ん中）まわりに回して（度）から、平行に動かす。"""
    px, py, pz = pivot or (CX, YF, HS / 2)
    return Pos(px + dx, py + dy, pz + dz) * Rot(rx, 0, rz) * Pos(-px, -py, -pz) * part


# ---------------------------------------------------------------------------
# 枠（本番の枠の右手前の角 → 本番の口を埋める → B の形に掘る。H15 を動かす）
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def prod_corner():
    """本番の枠の右手前の角（BOX の範囲）＋ 切った左の端の壁（当て板に載せるため。本番には無い）。"""
    a = LAY.key_area
    part = C.frame_full() & _box(BOX, -1.0, TOP + 1.0)
    return part + _box((BOX[0], a[1] - EPS, BOX[0] + S.COUPON_CORNER_WALL, BOX[3]), 0.0, S.FRAME_UNDER + EPS)


@lru_cache(maxsize=None)
def frame(lips=True):
    """B の口を掘った枠の角。lips=False = 口の左右の縁なし（検査を壊して見る形）。"""
    cv = LAY.cover()
    d, depth = LAY.pilot()
    wall_in = LAY.key_area[1]                                   # 手前の壁の内面
    boss_back = max(r[3] for n, r in C.lower_rects() if n == "boss" and r[0] < 104.0 < r[2] and r[1] < -40.0)   # 本番のねじの座の奥の面
    part = prod_corner()
    # 本番の口・溝・歯・溝の奥の壁を埋める（クリップの空間の幅で）。いまの H15 の下穴も埋める
    part = part + _box((XSI, Y0, mx(XSI), cv["y_cheek"]), 0.0, TOP) \
        + Pos(H15_OLD[0], H15_OLD[1], 0.0) * Cylinder(d / 2 + EPS, depth + EPS, align=P.CEN_MIN)
    cuts = [
        _box((A0, Y0 - 1.0, A1, YB + CL), -1.0, TOP + 1.0),                                             # 口の真ん中（上まで）
        _box((XSI, LAY.clip_body()[1] - S.PART_CLEAR, mx(XSI), cv["y_cheek"] + EPS), -1.0, S.CLIP_ROOF_UNDER),   # クリップの空間（本番と同じ高さ）
        _box((mx(XSI) - EPS, wall_in - EPS, mx(XPK), boss_back + 0.03), -1.0, ZW),                      # いまの H15 の座（壁の奥へ出た分）
    ]
    for side in (0, 1):
        f = (lambda x: x) if side == 0 else mx
        xa, xb = sorted((f(XLIP if lips else XPK), f(A0 + EPS)))
        cuts.append(_box((xa, Y0 - 1.0, xb, wall_in + EPS), -1.0, ZW))                                   # 腕の通る窓（屋根の下）
        xa, xb = sorted((f(XPK), f(XLIP + EPS)))
        cuts.append(_box((xa, YL, xb, boss_back + 0.03), -1.0, ZW))                                      # かぎの入る空洞（縁の裏）
        if lips:
            tri = [(f(XLIP + EPS), Y0 + SCALLOP), (f(XLIP - SCALLOP), Y0 - EPS), (f(XLIP + EPS), Y0 - EPS)]
            cuts.append(Pos(0, 0, -1.0) * extrude(_poly(tri), ZW + 1.0))                                 # 縁の手前の角（爪の入る所）
    part = part - _union(cuts)
    adds = [_box((mx(XPK), wall_in - EPS, H15_NEW[0] + S.SCREW_BOSS_HALF, boss_back), 0.0, ZW + EPS)]    # 動かした H15 の座
    for side in (0, 1):
        f = (lambda x: x) if side == 0 else mx
        xa, xb = sorted((f(XPK), f(XRO - GUIDE_CL)))
        adds.append(_box((xa, YR - 1.2, xb, YJ + BACK_CL + 0.8), 0.0, ZW + EPS))                         # 案内の壁（付け根の塊の外）
        xa, xb = sorted((f(XPK), f(XSI)))
        adds.append(_box((xa, YJ + BACK_CL, xb, YJ + BACK_CL + 0.8), 0.0, ZW + EPS))                     # 奥の壁（押し込みの止め）
    part = part + _union(adds)
    part = part - Pos(H15_NEW[0], H15_NEW[1], -1.0) * Cylinder(d / 2, depth + 1.0, align=P.CEN_MIN)
    part = part.clean()
    if lips and len(part.solids()) != 1:
        raise RuntimeError(f"B の枠が {len(part.solids())} 個の塊")
    return part


@lru_cache(maxsize=None)
def base():
    """当て板（基板の代わり・**H15 を動かした基板**）: ねじ穴 H14・動かした H15・使っていない穴 H30・H31・電池の奥の止め・
    クリップの脚の代わり（ランドの上・電池の左右の案内も兼ねる）・左と奥の縁の当て・電池の代わりを裏から押す長い穴。
    **クリップの板（基板の 3.5〜4.1 上）の代わりは無い**（本番の蓋の試し刷りと同じ）。"""
    s = S
    p = LAY.pcb
    fit, fence = s.COUPON_FIT, 1.8
    plate = _box((BOX[0] - fit - fence, p[1], p[2], BOX[3] + fit + fence), -s.PCB_T, 0.0)
    at = [c for n, c, _ in LAY.screws() if n in ("H14", "H30", "H31")] + [H15_NEW]
    holes = _union([Pos(c[0], c[1], -s.PCB_T - 1.0) * Cylinder(s.SCREW_HOLE_D / 2, s.PCB_T + 2.0, align=P.CEN_MIN) for c in at])
    parts = [plate - holes,
             _box((BOX[0] - fit - fence, p[1], BOX[0] - fit, BOX[3] + fit + fence), -EPS, 2.0),
             _box((BOX[0] - fit - fence, BOX[3] + fit, p[2], BOX[3] + fit + fence), -EPS, 2.0)]
    stop_y = s.CLIP_AT[1] + s.CLIP_STOP - s.CLIP_SHEET_T
    parts.append(_box((CX - s.CLIP_STOP_W / 2, stop_y, CX + s.CLIP_STOP_W / 2, stop_y + 1.0), -EPS, 2.8))
    pad = LAY.clip_pads()[0]
    for f in ((lambda x: x), mx):
        xa, xb = sorted((f(pad[0]), f(CX - CELL_R - fit)))
        parts.append(_box((xa, pad[1], xb, pad[3]), -EPS, LAY.z()["clip_top"]))
    pd, pw, pl = s.COUPON_PUSH
    push = _box((CX - pw / 2, CY - pl, CX + pw / 2, CY + pw / 2), -s.PCB_T - 1.0, 1.0)
    return (_union(parts) - push).clean()


def cell():
    return C.corner_coupon()["cell"]


# ---------------------------------------------------------------------------
# 動かして探す（検査と絵が使う）
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def obstacles(lips=True, with_cell=False):
    """蓋が当たる相手 [立体]: 枠（口のまわりだけ切り出した物）・当て板・クリップの金属（図面から作った形）・（電池の代わり）。"""
    near = frame(lips) & _box((BOX[0], Y0 - 1.0, mx(BOX[0]), YJ + 4.0), -2.0, TOP + 1.0)
    return tuple([near, base(), C.clip_solid()] + ([cell()] if with_cell else []))


def hit(part, obst):
    return sum(vol(part, o) for o in obst)


def travel(part, obst, direction, step=0.05, limit=3.0, tol=2e-3, **fixed):
    """part を direction（dx, dy, dz）へ step ずつ動かし、obst に当たらずに進める量（limit まで）。"""
    n = 0
    while (n + 1) * step <= limit + 1e-9:
        k = (n + 1) * step
        if hit(posed(part, dx=direction[0] * k, dy=direction[1] * k, dz=direction[2] * k, **fixed), obst) > tol:
            break
        n += 1
    return n * step


def corner_out(pose, x):
    """蓋の手前の面の、x の所が、pose（posed の引数）で手前へ出た量。"""
    rz = math.radians(pose.get("rz", 0.0))
    return -(pose.get("dy", 0.0) + (x - CX) * math.sin(rz))


def wiggle(part, obst, objective, limits=None, iters=100, seed=1, tol=2e-3):
    """part を、平面の中で 3 つの向き（dx・dy・rz）に少しずつ乱数で動かし、obst に当たらない姿勢のうち objective がいちばん大きい物を探す（山登り）。"""
    rnd = random.Random(seed)
    scale = dict(dx=0.05, dy=0.10, rz=0.2)
    lim = dict(dx=(-0.6, 0.6), dy=(-4.0, 0.5), rz=(-8.0, 8.0))
    lim.update(limits or {})
    cur = dict.fromkeys(scale, 0.0)
    best = (objective(cur), dict(cur))
    for i in range(iters):
        new = dict(cur)
        for k in (list(scale) if i % 3 == 0 else rnd.sample(list(scale), 2)):
            new[k] = min(lim[k][1], max(lim[k][0], cur[k] + rnd.gauss(0.0, scale[k])))
        val = objective(new)
        if val < objective(cur) - 0.02 or hit(posed(part, **new), obst) > tol:
            continue
        cur = new
        if val > best[0]:
            best = (val, dict(new))
    return best


def engagement(variant=MAIN, dx=0.0, hook=None):
    """かぎと縁の掛かり（左, 右）[mm]: かぎを手前へ 0.6 動かしたとき、枠と重なる所の左右の幅（立体から測る）。dx = 蓋を横へずらした量。"""
    out = []
    cv = posed(cover(variant, False, hook=hook), dx=dx, dy=-0.6)
    fr = obstacles()[0]
    for f in ((lambda x: x), mx):
        xa, xb = sorted((f(XPK - 0.5), f(XLIP + 0.6)))
        c = (cv & _box((xa, Y0, xb, YL + 0.3), 0.3, HS - 0.3)) & fr
        try:
            out.append(c.bounding_box().size.X if c is not None and c.volume > 1e-6 else 0.0)
        except (AttributeError, ValueError):
            out.append(0.0)
    return tuple(out)


def measure_moves(variant=MAIN):
    """絵と文書に載せる「動ける量」（検査と同じ探し方）: forward・up・back = 掛けた蓋が進める量・side = 胴が左右に動ける量（腕は縁に触れていて
    撓むので、腕を 0.3 内へ逃がした蓋で測る）・cell = 電池の代わりが手前へ進める量・
    one_arm = 左の腕だけを外す所まで動かしたとき、左の端が手前へ出る量（平面の中で、ずらす・回すを探す）。"""
    cv, ob = cover(variant, False), obstacles()
    a = arm_numbers(variant)
    one = cover(variant, False, a["release"], None)
    slack = cover(variant, False, a["pre"] + 0.3, a["pre"] + 0.3)
    return dict(forward=travel(cv, ob, (0, -1, 0)), up=travel(cv, ob, (0, 0, 1), limit=1.0),
                side=max(travel(slack, ob, (-1, 0, 0), limit=1.0), travel(slack, ob, (1, 0, 0), limit=1.0)),
                back=travel(cv, obstacles(with_cell=True), (0, 1, 0), limit=1.0),
                cell=travel(cell(), (ob[0], ob[1], cv), (0, -1, 0), pivot=(0.0, 0.0, 0.0)),
                one_arm=wiggle(one, ob, lambda q: corner_out(q, XLIP + 1.0))[0])


# ---------------------------------------------------------------------------
# 数（材料の値は TDS = spec.PLA_*・断面は立体から測るか、名目）
# ---------------------------------------------------------------------------

def arm_numbers(variant=MAIN):
    """腕（片持ち梁・先に力）。
      release・insert   外す／入れるときの、先の動き（刷った形から）・strain_*  そのときの付け根のひずみ [%]・strain_stop  胴に当たって止まるとき
      pinch             外すときに 1 本の腕の先をつまむ力 [N]・hold  掛けた後に腕が縁を押している力 [N]（がた取り）
      engage_worst      掛かりのいちばん小さい見込み: 蓋が横へ案内の隙ぶん寄る（予圧で追える分は引く）・かぎと縁が誤差ぶん短く刷れる
      drop              自分の重さで、DROP_G（半波 DROP_MS）の衝撃を横に受けたときの、かぎの所の揺れ [mm]（外れるのは 予圧 ＋ 掛かり）"""
    v = VARIANTS[variant]
    t, pre, hook = v["t"], v["pre"], v["hook"]
    e = S.PLA_E
    inertia = HS * t ** 3 / 12
    k = 3 * e * inertia / ARM_L ** 3
    strain = lambda d: 1.5 * t * d / ARM_L ** 2 * 100          # noqa: E731
    rel = release_tip(pre, hook)
    ins = (pre + hook) / shape(A_HOOK)
    acc = S.DROP_G * 9.80665
    wl = C.PLA_DENSITY * HS * t * acc * 1e-3
    static = wl * ARM_L ** 4 / (8 * e * inertia)
    freq = 1.875104 ** 2 / (2 * math.pi) * math.sqrt(e * inertia / (C.PLA_DENSITY * HS * t * ARM_L ** 4) * 1e6)
    gain = C.shock_gain(freq, S.DROP_MS)
    lose = max(0.0, GUIDE_CL - max(0.0, pre - PRINT_ERR))
    stop = pre + body_edge(YF) - (XLIP + t)
    return dict(t=t, pre=pre, hook=hook, length=ARM_L, k=k, release=rel, insert=ins, stop=stop,
                strain_release=strain(rel), strain_insert=strain(ins), strain_stop=strain(stop),
                strain_use=S.PLA_STRAIN_USE * S.PLA_BEND / e * 100, strain_limit=S.PLA_BEND / e * 100,
                pinch=k * rel, hold=k * pre, engage=hook, engage_worst=hook - lose - 2 * PRINT_ERR,
                freq=freq, gain=gain, drop=static * gain * shape(A_HOOK), drop_margin=(pre + hook) / (static * gain * shape(A_HOOK)),
                front_gap=body_edge(YF) - (XLIP + t))


@lru_cache(maxsize=None)
def plate_sections(variant=MAIN, step=0.1):
    """蓋の真ん中の板の断面（くぼみの左右の角の間の 5 か所）を、立体から測る [(x, 断面)]。"""
    (px, py), hw = pocket_center()
    cv = cover(variant, False)
    xs = [CX - (hw - 0.05) * k for k in (1.0, 0.5, 0.0, -0.5, -1.0)]
    return [(x, K.section(cv, x, step=step, y0=YF, y1=YB, z0=0.0, z1=TOP)) for x in xs]


def stresses(variant=MAIN, force=PUSH):
    """電池が蓋を手前へ force [N] で押すときの、力の道の応力 [MPa]。**力は、左右のかぎを通る**（手前から入れる蓋なので、電池の押す向き = 抜ける向き）。
      plate   蓋の真ん中の板（くぼみの角 2 点で押され、左右のかぎで受ける梁）。断面は立体から測る（click_cover_slide.section）。
              moment = force / 2 ×（くぼみの角 − かぎ）・tension = 手前の縁・compression = 奥の縁。**B でいちばん苦しい所**
      plate_center_hit  電池が、くぼみの角でなく真ん中で当たったとき（刷りの誤差で、角の隙 CELL_GAP と真ん中の隙の差が無くなったとき）の同じ値
      arm     腕（かぎ〜付け根を押し縮める柱。かぎは腕の芯から外れているので、曲げも受ける）: stress・buckle = 座屈する力（付け根は固定・先は縁が横を支える）
      stem    ランドの脇の柱（腕の押す力を、引っ張りで胴へ返す。腕との間が離れているので、曲げも受ける）: いちばん細い所（ランドの手前の角）
      hook    かぎの付け根のせん断・lip 縁の面圧"""
    v = VARIANTS[variant]
    t, hook = v["t"], v["hook"]
    p = force / 2
    (px, py), hw = pocket_center()
    x_hook = XLIP - hook / 2
    out = dict(force=force)
    for name, x_in in (("plate", CX - hw), ("plate_center_hit", CX)):
        worst = None
        m = p * (x_in - x_hook)
        for x, sc in plate_sections(variant):
            ten, cmp_ = m * sc["front"] / sc["inertia"], m * sc["rear"] / sc["inertia"]
            if worst is None or max(ten, cmp_) > max(worst["tension"], worst["compression"]):
                worst = dict(x=x, moment=m, tension=ten, compression=cmp_, **sc)
        out[name] = worst
    area, inertia = t * HS, HS * t ** 3 / 12
    ecc = hook / 2 + t / 2
    buckle = 2.046 * math.pi ** 2 * S.PLA_E * inertia / A_HOOK ** 2
    amp = 1.0 / (1.0 - p / buckle)
    out["arm"] = dict(load=p, ecc=ecc, moment=p * ecc, buckle=buckle, stress=p / area + p * ecc * (t / 2) / inertia * amp)
    ws = XSI - body_edge(YWB)
    dist = (XSI - ws / 2) - (arm_outer(YWB, 0.0) + t / 2)
    ms = p * dist + 0.5 * p * ecc
    out["stem"] = dict(width=ws, dist=dist, moment=ms, stress=p / (ws * HS) + ms * (ws / 2) / (HS * ws ** 3 / 12))
    out["hook"] = p / ((HOOK_FLAT + hook * HOOK_RAMP) * HS)
    out["lip"] = p / (hook * HS)
    return out


def numbers():
    """文書と絵に載せる数。"""
    mass = cover(MAIN, False).volume * C.PLA_DENSITY
    (px, py), hw = pocket_center()
    loads = {"指で強く押す（仮定 %g N）" % PUSH: PUSH}
    for g in GS:
        loads["電池の慣性 %g G（仮定）" % g] = S.CELL_MASS * g * 9.80665e-3
    st = {k: stresses(MAIN, f) for k, f in loads.items()}
    one = stresses(MAIN, 1.0)
    worst_per_n = max(one["plate"]["tension"] / S.PLA_TENSILE, one["plate"]["compression"] / S.PLA_BEND, one["stem"]["stress"] / S.PLA_BEND)
    return dict(arms={n: arm_numbers(n) for n in VARIANTS}, mass=mass, loads=loads, stress=st,
                force_at_strength=1.0 / worst_per_n,
                pocket=dict(center=(px, py), corner=hw, center_gap=(CY - CELL_R) - (py - POCKET_R), plate_t=(py - POCKET_R) - YF),
                h14_wall=XPK - (104.0 + S.SCREW_PILOT_D / 2), h15_wall=(H15_NEW[0] - S.SCREW_PILOT_D / 2) - mx(XPK),
                h15_move=H15_NEW[0] - H15_OLD[0], lip=LIP_T, window=(A0 - XLIP, ZW), hook_span=mx(XLIP - HOOK / 2) - (XLIP - HOOK / 2), gs=GS)


# ---------------------------------------------------------------------------
# 刷る板
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def pieces():
    """{名前: 立体}（組んだ向き。蓋は**刷る形** = 腕が予圧ぶん外へ開いた形）。"""
    out = {"frame": frame(), "base": base(), "cell": cell()}
    for n in sorted(VARIANTS):
        out[f"cover{n}"] = cover(n, True, 0.0, 0.0)
    return out


def plate_layout(gap=4.0):
    """1 枚に並べた刷る物 [(名前, 置いた立体, 組んだ座標 → 板の座標)]: 手前から 電池の代わり・蓋 3 つ（**底をベッドに**）・当て板・枠（上面をベッドに）。"""
    pc = pieces()
    out, x, y, row = [], 0.0, 0.0, 0.0
    for name in ["cell"] + [n for n in sorted(pc) if n.startswith("cover")]:
        part, fn, size = K._place(pc[name], x, y, False)
        if x and x + size.X > 60.0:
            x, y, row = 0.0, y + row + gap, 0.0
            part, fn, size = K._place(pc[name], x, y, False)
        out.append((name, part, fn))
        x += size.X + gap
        row = max(row, size.Y)
    y += row + gap
    for name, flip in (("base", False), ("frame", True)):
        part, fn, size = K._place(pc[name], 0.0, y, flip)
        out.append((name, part, fn))
        y += size.Y + gap
    return out


def plate():
    return Compound([part for _, part, _ in plate_layout()])


def export(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    part = plate()
    size = part.bounding_box().size
    assert max(size.X, size.Y) <= S.PRINT_MAX, f"coupon_cover_snap_plate: {size.X:.1f} × {size.Y:.1f} が A1 mini に置けない"
    export_stl(part, str(out / "coupon_cover_snap_plate.stl"))
    return {"coupon_cover_snap_plate": (size.X, size.Y, size.Z)}


def main():
    for name, size in export().items():
        print(f"{name}.stl: {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}")
    n = numbers()
    for k, v in n.items():
        print(k, v)
    if "--no-figs" not in sys.argv:
        import click_cover_snap_figs

        moves = measure_moves()
        print("moves", moves)
        for q in click_cover_snap_figs.render_all(OUT, moves):
            print("絵", q)
    return 0


if __name__ == "__main__":
    sys.exit(main())
