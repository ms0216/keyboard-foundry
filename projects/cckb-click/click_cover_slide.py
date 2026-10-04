"""電池の蓋の**別案 S（横ずらしで掛ける蓋）の試し刷り**。本番の蓋（click_case.cover_solid・落とし込み式）と基板は変えない。**刷る物だけ**。

    .venv/bin/python3 projects/cckb-click/click_cover_slide.py     # STL と数 → build/cckb-click/coupon_cover_slide_plate.stl

なぜ作るか（決定記録 2026-10-04-cover-latch の「満たせていないこと」）: いまの蓋は、樹脂の棒 2 本を爪 1 つで押しながら上へ擦ると開く。
S は「上へ抜けない」を**ばねを通さず、樹脂の塊どうしの掛かり**で作り、開ける動きを 3 つの別の向きに分ける。

しくみ（座標は CAD・基板の上面 = 0・蓋は**掛けた位置**で書く。x は右・y は奥）:
  入れる   蓋を、掛ける位置より SLIDE だけ右で上から落とす（蓋の右端の「当て」が、枠の板ばねを奥へ押しのける）→ 左へ SLIDE ずらす
           → 板ばねが、当ての端の後ろへ戻る（カチッ）
  電池の力 電池 → 蓋の足 → 蓋の胴 → 左右の耳（上から下まで）の手前の平らな面 → 口の左右の縁（枠の手前の壁の残り）の奥の面
  上へ     耳の奥の「出っ張り」（上面が 45° の斜面）が、枠の屋根（左）と出っ張り（右）の下に入る。持ち上げる力は、斜面で「下へ・手前へ」に変わり、
           手前は縁が受ける = **ばねを通らない**
  留め     枠の右の壁の上面に切れ目で作った板ばね（**前後に撓む・立った板**。先は左）。先の面が、蓋の当ての端面と直角に突き合って、蓋が右へ戻れない。
           板ばねは蓋の自分の重さと横からの押しだけを受ける（電池の力も、持ち上げる力も通らない）。
           上下に撓む薄い舌（厚さ 0.6）は捨てた: 蓋が右へ押す力で座屈する（計算 1.6 N < 蓋の重さ × 1500 G = 4 N）。立った板は高さを取れる
  開ける   板ばねの先を、手前の爪の入るくぼみから奥へ押す（奥）→ 蓋を右へずらす（押している爪の方へ）→ 蓋を持ち上げる（上）。
           くぼみは蓋の右の外（枠）にある = くぼみの中の物が蓋を動かせる向きは左（閉まる向き）だけ
  がた取り 枠の屋根と出っ張りの下面（斜面）の細い筋（つぶれる筋）が、蓋の出っ張りの斜面を「下へ・手前へ」押す = 上下と前後の遊びを 1 つで取る。
           蓋 3 つで斜面の隙を振る（VARIANTS）
刷る向き: 枠も蓋も**上面をベッドに**（支え無し）。蓋の低い出っ張りは 45° の斜面で耳から生える。枠の板ばねはベッドから立つ・板ばねの溝の底は橋（幅 = TRENCH）。
本番の枠の角の切れ端（click_case.corner_coupon）を読むだけで使い、口のまわりを埋めて S の形に掘り直す。寸法はこのファイルが持つ（本番の spec には入れない:
採るかどうかは、利用者が刷って決める）。
"""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build123d import Compound, Cylinder, Polygon, Pos, Rot, export_stl, extrude, offset  # noqa: E402

import click_case as C  # noqa: E402
import click_parts as P  # noqa: E402

LAY, S = C.LAY, C.S
EPS = C.EPS
OUT = C.OUT
TOP = S.FRAME_UNDER + S.FRAME_T
_box, _union = C._box, C._union

# ---------------------------------------------------------------------------
# 寸法（全部 [試し刷り]。本番には入っていない）
# ---------------------------------------------------------------------------
SLIDE = 1.6                  # 横へずらす量
CL = 0.15                    # 蓋と枠の隙（片側。本番の蓋と同じ）
Y0 = LAY.frame[1]            # 枠の外面
YF = Y0 + 0.25               # 蓋の手前の面（外面から引っ込める。本番の蓋と同じ）
FRONT_T = 1.05               # 蓋の手前の板の厚さ（本番の蓋と同じ）
A0, A1 = 112.5, 131.0        # 口の左右の縁の端（電池 φ16 の道 113.5〜130.5 の外）
LIP_L, LIP_R = 1.25, 1.0     # 口の左右の縁の厚さ（手前の壁 3.0 のうち、耳の手前に残す分）
YB = LAY.clip_body()[1] - 0.2          # 耳の奥の面 = 足の奥の端（クリップの板の端の 0.2 手前。これより奥は、板の下を通れない）
TAB_D = 1.1                  # 出っ張りの奥行き（耳の奥の面から奥へ）
YT = YB + TAB_D              # 出っ張りの奥の面
YC = YT + CL                 # 枠の空洞の奥の面
YH = YB + CL                 # 枠の屋根・出っ張りの手前の面
ROOF_Z = 3.4                 # 枠の屋根・出っ張りの下面の、奥の端での高さ（そこから手前へ 45° で上がる。付け根の厚さ 1.6・先 0.5）
XLE = 110.3                  # 左の耳の左の端（縁の裏に 2.2 掛かる）
XRE = 132.5                  # 右の耳の右の端（縁の裏に 1.5 掛かる）
CLIP_L, CLIP_R = LAY.clip_body()[0] - 0.2, LAY.clip_body()[2] + 0.2   # クリップの板の左右の端 ∓ 0.2: YB より奥の蓋は、この外にいる（113.35・130.65）
P0 = CLIP_L - SLIDE          # 左の屋根の右の端（落とす位置の出っ張りの左の端 − CL）
HEAD = (CLIP_R + 0.2, CLIP_R + SLIDE - CL)    # 右の出っ張り（枠）の x の範囲（板の端から 0.4 = PART_CLEAR）
FLOOR_T = 0.8                # 右の空洞の底（縁の下の端を奥の壁につなぐ。刷るときは橋）
EAR_LIFT = 1.1               # 右の耳・出っ張りの下面（底の上 0.3）
FOOT_IN = (117.95, 126.05)   # 足の内の端（本番の蓋と同じ: 電池が足に当たる）
STRIP_Z = 3.9                # 上の帯の下面（本番の蓋と同じ）
# 留め（枠の板ばねと、蓋の当て）
RIB_Y = (Y0 + LIP_R + CL, Y0 + LIP_R + CL + 0.7)   # 蓋の当て（右の耳の端から右へ SLIDE 伸びる縦の板）の前後の範囲 = 右の耳の手前の 0.7
RIB_Z = 3.7                  # 当ての下面（板ばねの溝の底の 0.4 上: 底は刷るとき橋になる。垂れても擦らないように）
TIP_CL = 0.25                # 当ての端面と板ばねの先の隙（どちらもベッドから立つ面 = 1 層目の太り 2 つぶん）
LEAF_Y = (RIB_Y[1] + 0.05, RIB_Y[1] + 1.05)        # 板ばねの胴の前後の範囲（厚さ 1.0）。当ての通る所（当ての奥の面）のすぐ奥
NOSE = (0.8, 0.65)           # 板ばねの先の「鼻」（手前へ出る・当ての通る所に入る）: 長さ・当てと前後に重なる量（蓋が手前へ座ると 0.5）
LEAF_Z = 3.7                 # 板ばねの下の端（溝の底の 0.4 上: 底は刷るとき橋になる。垂れても付かないように）
LEAF_L = 9.0                 # 板ばねの長さ
LEAF_ROOM = 0.8              # 板ばねの奥の空き（先が奥へ動ける量 = 行き過ぎの止め）
LEAF_SLIT = 0.4              # 板ばねの手前の切れ目（爪を入れる所より右）
CAM = (0.55, 0.35)           # 鼻の手前の上の縁・当ての奥の下の縁を斜めに落とす量（蓋を落とすと、鼻が自分で奥へ逃げる。2 つの和 0.9 > 重なり 0.65 ＋ 蓋の遊び 0.15）
RIB_CL = 0.25                # 当ての通る所の、手前の壁との隙
TRENCH_Z = 3.3               # 板ばねの溝の底（H15 の下穴の上の端 2.8 の 0.5 上）
NAIL_L = 2.3                 # 爪を入れる所（当ての通る所を、そのまま右へ伸ばした溝。幅 = 当ての通る所）の長さ
BED_FOOT = 0.2               # ベッドの面の縁を落とす量（1 層目の太り）
# がた取り: 枠の斜面の筋（斜面に垂直な高さ・幅・入り口を斜めに落とす長さ）
RIDGE = (0.30, 0.6, 0.3)
RIDGE_X = {"left": (XLE - CL, XLE + 0.85), "right": (HEAD[0], HEAD[0] + 0.65)}
# 蓋 3 つ: 出っ張りの斜面と、枠の下面の、上下の隙（蓋が名目の位置のとき）。蓋が座る（足が基板・耳が縁）と、斜面に垂直な隙は (gap + CL) / √2
VARIANTS = {1: 0.05, 2: 0.15, 3: 0.25}
MARK = S.COVER_MARK          # 見分ける切り欠き（本番の蓋の試し刷りと同じ: 上の板の奥の縁・右寄り）
PRINT_ERR = 0.15             # 刷りの誤差の見込み（片側）

XL, XR = A0 + CL, A1 - SLIDE - CL                 # 蓋の手前の板の左右の端
YLL, YLR = Y0 + LIP_L, Y0 + LIP_R                 # 縁の奥の面（左・右）
CAV = (XLE - CL, XRE + SLIDE + CL)                # 枠の空洞の左右の端
XTIP = XRE + SLIDE + TIP_CL                       # 板ばねの先
TRENCH = (RIB_Y[0] - RIB_CL, LEAF_Y[1] + LEAF_ROOM)       # 板ばねの溝の前後の範囲（手前は、当ての通る所。爪を入れる所より右は、切れ目 LEAF_SLIT まで狭める）
NOSE_Y = RIB_Y[1] - NOSE[1]                               # 鼻の手前の面
XLANE = XRE + 2 * SLIDE + CL + NAIL_L                     # 当ての通る所 ＋ 爪を入れる所の右の端
FILL = (109.0, Y0, 135.2, LAY.cover()["y_cheek"])  # 本番の口・溝・歯を埋め直す範囲（奥は、本番の溝の奥の壁の奥の面）


def roof_z(y):
    """枠の屋根・出っ張りの下面の高さ（奥の端 YC で ROOF_Z・手前へ 45° で上がる）。"""
    return ROOF_Z + (YC - y)


def _ccw(pts):
    a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    return pts if a > 0 else pts[::-1]


def prism_x(pts_yz, x0, x1):
    return C._prism_x(_ccw(list(pts_yz)), x0, x1)


def prism_y(pts_xz, y0, y1):
    return C._prism_y(_ccw(list(pts_xz)), y0, y1)


def vol(a, b):
    if a is None or b is None:
        return 0.0
    c = a & b
    try:
        return 0.0 if c is None else float(c.volume)
    except (AttributeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# 枠（本番の角の切れ端 → 口のまわりを埋める → S の形に掘る）
# ---------------------------------------------------------------------------

def ridge(side):
    """つぶれる筋（枠の斜面の下面から、斜面に垂直に RIDGE[0] 出る三角の畝・x に沿う）。入り口（蓋の出っ張りが入って来る側 = 右）は斜めに落とす。"""
    h, w, ramp = RIDGE
    x0, x1 = RIDGE_X[side]
    ym = (YH + YT) / 2
    k = h / math.sqrt(2.0)
    tri = [(ym - w / 2 - EPS, roof_z(ym - w / 2) + 2 * EPS), (ym - k, roof_z(ym) - k), (ym + w / 2 + EPS, roof_z(ym + w / 2) + 2 * EPS)]
    body = prism_x(tri, x0, x1)
    zlo, zhi = roof_z(ym) - k - 0.05, roof_z(ym - w / 2) + 0.05
    keep = prism_y([(x0 - 1.0, zlo), (x1 - ramp, zlo), (x1, zhi), (x0 - 1.0, zhi)], ym - w, ym + w)
    return body & keep


def leaf(deflect=0.0, n=10):
    """枠の板ばね（先を deflect だけ奥へ押した形。先に力を掛けた片持ち梁の撓みの形 = 付け根に近いほど、まっすぐ傾けた形より撓みが小さい）。"""
    xr = XTIP + LEAF_L
    xs = [XTIP + LEAF_L * i / n for i in range(n + 1)]

    def d(x):
        a = xr - x                                   # 付け根から
        return deflect * (3 * a * a * LEAF_L - a ** 3) / (2 * LEAF_L ** 3)

    pts = [(x, LEAF_Y[0] + d(x)) for x in xs] + [(xr + 0.3, LEAF_Y[0]), (xr + 0.3, LEAF_Y[1])] + [(x, LEAF_Y[1] + d(x)) for x in reversed(xs)]
    body = Pos(0, 0, LEAF_Z) * extrude(Polygon(*_ccw(pts), align=None), TOP - LEAF_Z)
    xn = XTIP + NOSE[0]
    nose = _box((XTIP, NOSE_Y + deflect, xn, LEAF_Y[0] + d(xn) + 0.05), LEAF_Z, TOP)              # 鼻（先の手前へ出る塊）
    if deflect == 0.0:                               # 鼻の手前の上の縁は斜め（蓋の当てが上から来ると奥へ逃げる）。先の面（当ての端面と突き合う）は落とさない
        cm = CAM[0]
        nose = nose - prism_x([(NOSE_Y - EPS, TOP - cm), (NOSE_Y - EPS, TOP + EPS), (NOSE_Y + cm, TOP + EPS)], XTIP - 1.0, xn + 1.0)
        c = BED_FOOT                                 # 胴の上の縁（ベッドの面）: 1 層目の太りの逃げ
        for y, sg, xa in ((LEAF_Y[0], 1, xn), (LEAF_Y[1], -1, XTIP - 1.0)):
            body = body - prism_x([(y - sg * EPS, TOP - c), (y - sg * EPS, TOP + EPS), (y + sg * c, TOP + EPS)], xa, xr)
    body = body + nose
    return body


@lru_cache(maxsize=None)
def frame_body(ridges=True, roof=True, floor=True):
    """S の口を掘った枠の角（板ばねは別: leaf）。ridges=False = つぶれる筋なし（蓋との重なりを見る検査の形）。roof=False = 屋根と出っ張りなし（検査を壊して見る形）。"""
    base = C.corner_coupon()["frame"]
    part = base + _box(FILL, 0.0, TOP)
    cuts = [
        _box((A0, Y0 - 1.0, A1, YH), -1.0, TOP + 1.0),                                          # 口（縁の間・電池の道。上から下まで）
        _box((CAV[0], YLL, A0 + EPS, YH), -1.0, TOP + 1.0),                                     # 左の耳の空洞（上まで）
        _box((A1 - EPS, YLR, CAV[1], YH), -1.0, TOP + 1.0),                                     # 右の耳の空洞（上まで）
        _box((P0, YH - EPS, HEAD[0], YC), -1.0, TOP + 1.0),                                     # 出っ張りの帯: 屋根と出っ張りの間は上まで
        _box((HEAD[1], YH - EPS, CAV[1], YC), -1.0, TOP + 1.0),                                 # 出っ張りの帯: 右の出っ張りより右（落とす位置の出っ張りの上）
        # クリップの空間（本番と同じ箱）のうち、埋め直した所
        _box((A0, LAY.clip_body()[1] - S.PART_CLEAR, HEAD[0], FILL[3] + EPS), -1.0, S.CLIP_ROOF_UNDER),
    ]
    under = [(YH - EPS, -1.0), (YC, -1.0), (YC, ROOF_Z), (YH - EPS, roof_z(YH - EPS))] if roof else None
    for x0, x1 in ((CAV[0], P0 + EPS), (HEAD[0] - EPS, HEAD[1] + EPS)):                          # 屋根・出っ張りの下（斜めの下面）
        cuts.append(prism_x(under, x0, x1) if roof else _box((x0, YH - EPS, x1, YC), -1.0, TOP + 1.0))
    # 板ばねの溝（当ての通る所・爪を入れる所・手前の切れ目・奥の空き・下の空き）。板ばねは leaf() で足す
    xr = XTIP + LEAF_L
    yslit = LEAF_Y[0] - LEAF_SLIT
    cuts.append(_box((CAV[1] - EPS, TRENCH[0], XLANE, TRENCH[1]), TRENCH_Z, TOP + 1.0))
    cuts.append(_box((XLANE - EPS, yslit, xr, TRENCH[1]), TRENCH_Z, TOP + 1.0))
    c = BED_FOOT
    for y, sg, xa, xb in ((TRENCH[0], -1, CAV[1], XLANE), (yslit, -1, XLANE, xr), (TRENCH[1], 1, CAV[1], xr)):   # 溝の縁（ベッドの面）を落とす
        cuts.append(prism_x([(y - sg * EPS, TOP - c), (y - sg * EPS, TOP + EPS), (y + sg * c, TOP + EPS)], xa, xb))
    part = part - _union(cuts)
    adds = []
    if floor:
        adds.append(_box((XRE + CL, YLR - EPS, CAV[1] + EPS, YC + EPS), 0.0, FLOOR_T))          # 右の空洞の底
    if ridges and roof:
        adds += [ridge("left"), ridge("right")]
    if adds:
        part = part + _union(adds)
    return part.clean()


@lru_cache(maxsize=None)
def frame(ridges=True):
    part = (frame_body(ridges) + leaf(0.0)).clean()
    if len(part.solids()) != 1:
        raise RuntimeError(f"S の枠が {len(part.solids())} 個の塊")
    return part


# ---------------------------------------------------------------------------
# 蓋（掛けた位置）
# ---------------------------------------------------------------------------

def tab_z(y, gap):
    return roof_z(y) - gap


def _top_rects():
    """蓋の上面（ベッドの面）の平面の形を作る矩形。"""
    return [(XL, YF, XR, YB),                                   # 手前の板・上の帯・足の上
            (P0 + CL, YB - EPS, HEAD[0] - CL - SLIDE, YT),      # 上の板の奥（左は屋根の右から・右は、落とす位置で枠の出っ張りの左まで）
            (XLE, YLL + CL, XL + EPS, YB),                      # 左の耳
            (XR - EPS, YLR + CL, XRE, YB),                      # 右の耳
            ]


@lru_cache(maxsize=None)
def cover(variant=2, mark=True):
    """S の蓋（掛けた位置）。variant = VARIANTS の番号（斜面の隙）。"""
    gap = VARIANTS[variant]
    zp = TOP - S.COVER_TOP_T
    parts = [
        _box((XL, YF, XR, YF + FRONT_T), 0.1, TOP),                                             # 手前の板（切れ目なし）
        _box((XL, YF, XR, YB), STRIP_Z, TOP),                                                   # 上の帯
        _box((XL, YF, XR, YB + EPS), zp, TOP),
        _box((P0 + CL, YB, HEAD[0] - CL - SLIDE, YT), zp, TOP),                                 # 上の板の奥
        _box((XLE, YLL + CL, XL + EPS, YB), 0.0, TOP),                                          # 左の耳（上から下まで）
        _box((XR - EPS, YLR + CL, A1 + EPS, YB), 0.0, TOP),                                     # 右の耳: 縁の端までは上から下まで
        _box((A1, YLR + CL, XRE, YB), EAR_LIFT, TOP),                                           #        縁の裏は、底の上から
    ]
    (cx, cy), r = LAY.cell()
    keep = Pos(cx, cy, -1.0) * Cylinder(r + S.COVER_CELL_CLEAR, TOP + 2.0, align=P.CEN_MIN)
    for xa, xb in ((XL, FOOT_IN[0]), (FOOT_IN[1], XR)):                                          # 足（基板に立つ・電池を止める）
        parts.append(_box((xa, YF, xb, YB), 0.0, zp + EPS) - keep)
    for x0, x1, z0 in ((XLE, P0, 0.0), (CLIP_R, XRE, EAR_LIFT)):                                 # 出っ張り（上面は 45°・耳の奥の面から生える）
        parts.append(prism_x([(YB - EPS, z0), (YT, z0), (YT, tab_z(YT, gap)), (YB - EPS, tab_z(YB - EPS, gap))], x0, x1))
    body = _union(parts)
    if mark:
        mw, md, mp = MARK
        x1 = HEAD[0] - CL - SLIDE
        body = body - _union([_box((x1 - 3.0 - i * mp - mw, YT - md, x1 - 3.0 - i * mp, YT + 1.0), zp - 1.0, TOP + 1.0) for i in range(variant)])
    # ベッドの面（上面）の縁を落とす: いちばん上の BED_FOOT を、平面の形を内へ寄せた 2 段に置き換える（1 層目の太りが、枠との隙を食わない）
    plan = _union([C._rect2d(q) for q in _top_rects()])
    if mark:
        plan = plan - _union([C._rect2d((x1 - 3.0 - i * mp - mw, YT - md, x1 - 3.0 - i * mp, YT + 1.0)) for i in range(variant)])
    c = BED_FOOT
    body = body - _box((XLE - 1.0, Y0 - 1.0, XRE + 1.0, YT + 1.0), TOP - c, TOP + 1.0)
    steps = [Pos(0, 0, TOP - c - EPS) * extrude(offset(plan, -c / 2), c / 2 + EPS), Pos(0, 0, TOP - c / 2 - EPS) * extrude(offset(plan, -c), c / 2 + EPS)]
    # 当て（右の耳の端から右へ伸びる縦の板）。ベッドの面の縁は落とさない（幅 0.75 の板で、落とすと 1 層目が線 1 本を割る。溝との隙は 0.3 以上ある）。
    # 奥の下の縁は斜め（蓋を落とすと、板ばねが自分で奥へ逃げる）
    rib = _box((XRE - 0.5, RIB_Y[0], XRE + SLIDE, RIB_Y[1]), RIB_Z, TOP)
    cm = CAM[1]
    rib = rib - prism_x([(RIB_Y[1] + EPS, RIB_Z - EPS), (RIB_Y[1] + EPS, RIB_Z + cm), (RIB_Y[1] - cm, RIB_Z - EPS)], XRE - 1.0, XRE + SLIDE + 1.0)
    steps.append(rib)
    body = (body + _union(steps)).clean()
    if len(body.solids()) != 1:
        raise RuntimeError(f"S の蓋が {len(body.solids())} 個の塊")
    return body


def posed(part, dx=0.0, dy=0.0, dz=0.0, rx=0.0, ry=0.0, rz=0.0, pivot=None):
    """part を、pivot（既定は蓋の真ん中）まわりに回して（度）から、平行に動かす。"""
    px, py, pz = pivot or ((XL + XR) / 2, (YF + YT) / 2, TOP / 2)
    return Pos(px + dx, py + dy, pz + dz) * Rot(rx, ry, rz) * Pos(-px, -py, -pz) * part


# ---------------------------------------------------------------------------
# 数
# ---------------------------------------------------------------------------

def leaf_numbers():
    """枠の板ばね（片持ち梁・先に力）。材料の値は TDS（spec.PLA_*）・断面は名目。
      overlap    当ての端面と板ばねの先が、前後に重なる量（蓋が名目の位置）・overlap_seated 蓋が手前へ座ったとき（つぶれる筋が押している = ふだん）
      release    開けるのに要る、先の押し込み（名目の位置 = いちばん大きい。＋ 0.1）・release_seated ふだん
      insert     蓋を落とす位置（当てが鼻の手前に並ぶ）で、鼻が押しのけられている量（蓋が奥へ寄り切っているとき = いちばん大きい）
      force_*    そのとき先に掛ける力 [N]・strain_* 付け根のひずみ [%]・stop 奥の空きで止まるときの先の動き・strain_stop
      freq・gain・drop  自分の重さで、DROP_G（半波 DROP_MS）の衝撃を前後に受けたときの先の揺れ [mm]
      buckle     先を軸の向きに押したとき（蓋が右へ戻ろうとする力）に座屈する力 [N]: free = 先が自由（いちばん小さい見積もり）・held = 先が横へ滑らない"""
    t, h, length = LEAF_Y[1] - LEAF_Y[0], TOP - LEAF_Z, LEAF_L
    e = S.PLA_E
    inertia = h * t ** 3 / 12
    overlap = NOSE[1]
    insert = overlap + CL                        # 当ての奥の面が鼻を押す（蓋が奥へ寄り切っているとき）
    k = 3 * e * inertia / length ** 3
    strain = lambda d: 1.5 * t * d / length ** 2 * 100          # noqa: E731
    acc = S.DROP_G * 9.80665
    wl = C.PLA_DENSITY * h * t * acc * 1e-3
    static = wl * length ** 4 / (8 * e * inertia)
    freq = 1.875104 ** 2 / (2 * math.pi) * math.sqrt(e * inertia / (C.PLA_DENSITY * h * t * length ** 4) * 1e6)
    gain = C.shock_gain(freq, S.DROP_MS)
    out = dict(k=k, overlap=overlap, overlap_seated=overlap - CL, release=overlap + 0.1, release_seated=overlap - CL + 0.1, insert=insert, stop=LEAF_ROOM,
               strain_use=S.PLA_STRAIN_USE * S.PLA_BEND / e * 100, strain_limit=S.PLA_BEND / e * 100,
               freq=freq, gain=gain, drop_static=static, drop=static * gain,
               buckle_free=math.pi ** 2 * e * inertia / (2 * length) ** 2, buckle_held=math.pi ** 2 * e * inertia / (0.7 * length) ** 2)
    for key in ("release", "release_seated", "insert", "stop"):
        out["force_" + key] = k * out[key]
        out["strain_" + key] = strain(out[key])
    return out


def section(body, x, step=0.05, y0=None, y1=None, z0=0.0, z1=None, skip=None):
    """立体を x で切った断面を、step の格子で数える（上下の軸まわりの曲げ = 電池が手前へ押す力）。
    返り値 dict(area, inertia, front, rear): 面積・図心を通る上下の軸まわりの断面二次モーメント・図心から手前／奥の縁まで。"""
    y0 = YF if y0 is None else y0
    y1 = YT if y1 is None else y1
    z1 = TOP if z1 is None else z1
    ys = []
    for i in range(int(round((y1 - y0) / step))):
        y = y0 + (i + 0.5) * step
        for j in range(int(round((z1 - z0) / step))):
            z = z0 + (j + 0.5) * step
            if (skip is None or not skip(y, z)) and body.is_inside((x, y, z)):
                ys.append(y)
    da = step * step
    yc = sum(ys) / len(ys)
    inertia = sum((y - yc) ** 2 for y in ys) * da
    return dict(area=len(ys) * da, inertia=inertia, front=yc - min(ys) + step / 2, rear=max(ys) - yc + step / 2)


@lru_cache(maxsize=None)
def stresses(variant=2):
    """電池が DROP_G で蓋を押すとき（spec.CELL_MASS）の、力の道の応力 [MPa]。**断面は立体から測る**（section）。
    力の入る所 = 足の内の端（FOOT_IN）・受ける所 = 耳が縁の裏に掛かる範囲の真ん中。左右の受ける力は、つり合いから。
      body       蓋の胴（足と足の間でいちばん弱い断面）: 曲げモーメント・手前の縁の引っ張り・奥の縁の圧縮
      neck_left・neck_right  耳の首（縁の端〜蓋の胴の端。耳だけでつながる所）の曲げ
      lip_left・lip_right    枠の縁（空洞の端を付け根にした片持ち。右は底でつないだ所から先）の曲げ
      ear_bearing  耳と縁の当たる面の面圧（左・右）"""
    force = S.CELL_MASS * S.DROP_G * 9.80665 * 1e-3
    xa, xb = (XLE + A0) / 2, (A1 + XRE) / 2
    la, lb = FOOT_IN
    ra = force / 2 * ((xb - la) + (xb - lb)) / (xb - xa)
    rb = force - ra
    cv = cover(variant, False)
    out = dict(force=force, react=(ra, rb), arm=(la - xa, xb - lb))
    worst = None
    for i in range(15):
        x = la + 0.3 + (lb - la - 0.6) * i / 14
        m = ra * (x - xa) - force / 2 * max(0.0, x - la)
        sc = section(cv, x)
        t, cmp_ = m * sc["front"] / sc["inertia"], m * sc["rear"] / sc["inertia"]
        if worst is None or t > worst["tension"]:
            worst = dict(x=x, moment=m, tension=t, compression=cmp_, **sc)
    out["body"] = worst
    for name, x, m in (("neck_left", A0 + 0.05, ra * (A0 + 0.05 - xa)), ("neck_right", A1 - 0.05, rb * (xb - (A1 - 0.05))),
                       ("neck_right_root", XR + 0.05, rb * (xb - XR - 0.05))):
        sc = section(cv, x, y0=Y0, y1=YT)
        out[name] = dict(moment=m, stress=m * max(sc["front"], sc["rear"]) / sc["inertia"], **sc)
    fr = frame_body(False)
    for name, x, m, yl in (("lip_left", CAV[0] + 0.05, ra * (xa - CAV[0]), YLL), ("lip_right", XRE + CL - 0.05, rb * (XRE + CL - xb), YLR)):
        sc = section(fr, x, y0=Y0, y1=yl)
        out[name] = dict(moment=m, stress=m * max(sc["front"], sc["rear"]) / sc["inertia"], **sc)
    out["ear_bearing"] = (ra / ((A0 - XLE) * TOP), rb / ((XRE - A1) * (TOP - EAR_LIFT)))
    return out


def numbers():
    """文書と絵に載せる数。"""
    acc = S.DROP_G * 9.80665 * 1e-3
    mass = cover(2, False).volume * C.PLA_DENSITY
    k = RIDGE[0]
    fits = {}
    for n, gap in VARIANTS.items():
        nominal = k - (gap + CL) / math.sqrt(2.0)                  # 筋のしめしろ（斜面に垂直・蓋が座ったとき）
        solid = gap / math.sqrt(2.0)                               # 筋の無い所の、斜面どうしの隙（蓋が座る前 = 名目の位置）
        fits[n] = dict(gap=gap, interference=nominal, loose=nominal - PRINT_ERR, tight=nominal + PRINT_ERR,
                       solid_seated=(gap + CL) / math.sqrt(2.0), solid_tight=(gap + CL) / math.sqrt(2.0) - PRINT_ERR, solid=solid)
    return dict(leaf=leaf_numbers(), mass=mass, cover_force=mass * acc, cell_force=S.CELL_MASS * acc, fits=fits,
                engage=dict(left=P0 - XLE, right=HEAD[1] - CLIP_R, lip_left=A0 - XLE, lip_right=XRE - A1),
                h15_wall=min(c[0] for n, c, _ in LAY.screws() if n == "H15") - S.SCREW_PILOT_D / 2 - CAV[1],
                h15_cap=TRENCH_Z - LAY.pilot()[1], recess=(A1 - XR, YLR + CL - Y0), slot_top=[(HEAD[0] - (HEAD[0] - CL - SLIDE), TAB_D + CL), (CAV[1] - HEAD[1], TAB_D + CL)])


# ---------------------------------------------------------------------------
# 刷る板
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def pieces():
    """{名前: 立体}（組んだ向き）。frame = S の枠の角・base と cell = 本番の蓋の試し刷りと同じ当て板と電池の代わり・cover1〜3。"""
    cc = C.corner_coupon()
    out = {"frame": frame(), "base": cc["base"], "cell": cc["cell"]}
    for n in sorted(VARIANTS):
        out[f"cover{n}"] = cover(n, True)
    return out


def _place(part, ox, oy, flip):
    """(置いた立体, 組んだ座標 → 板の座標)。flip = 上面をベッドに（x 軸まわりに 180°）。"""
    q = Rot(180, 0, 0) * part if flip else part
    bb = q.bounding_box()
    tx, ty, tz = ox - bb.min.X, oy - bb.min.Y, -bb.min.Z
    sg = -1 if flip else 1
    return Pos(tx, ty, tz) * q, (lambda p: (p[0] + tx, sg * p[1] + ty, sg * p[2] + tz)), bb.size


def plate_layout(gap=4.0):
    """1 枚に並べた刷る物 [(名前, 置いた立体, 組んだ座標 → 板の座標)]: 手前の列に 電池の代わり・蓋 3 つ（**上面をベッドに**）、その奥に 当て板、
    いちばん奥に 枠（上面をベッドに）。"""
    pc = pieces()
    out, x, y, row = [], 0.0, 0.0, 0.0
    for name in ["cell"] + [n for n in sorted(pc) if n.startswith("cover")]:
        part, fn, size = _place(pc[name], x, y, name != "cell")
        if x and x + size.X > 78.0:
            x, y, row = 0.0, y + row + gap, 0.0
            part, fn, size = _place(pc[name], x, y, name != "cell")
        out.append((name, part, fn))
        x += size.X + gap
        row = max(row, size.Y)
    y += row + gap
    for name, flip in (("base", False), ("frame", True)):
        part, fn, size = _place(pc[name], 0.0, y, flip)
        out.append((name, part, fn))
        y += size.Y + gap
    return out


def plate():
    return Compound([part for _, part, _ in plate_layout()])


def export(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    part = plate()
    size = part.bounding_box().size
    assert max(size.X, size.Y) <= S.PRINT_MAX, f"coupon_cover_slide_plate: {size.X:.1f} × {size.Y:.1f} が A1 mini に置けない"
    export_stl(part, str(out / "coupon_cover_slide_plate.stl"))
    return {"coupon_cover_slide_plate": (size.X, size.Y, size.Z)}


def main():
    for name, size in export().items():
        print(f"{name}.stl: {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}")
    n = numbers()
    for k, v in n.items():
        print(k, v)
    for k, v in stresses().items():
        print(k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
