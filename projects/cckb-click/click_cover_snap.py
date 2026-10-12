"""電池の蓋の**別案 B4（左右のばねの腕で掛ける蓋・B → B2 → B3 → B4 と直した物）の試し刷り**。本番の蓋（click_case.cover_solid）・本番の枠・基板は変えない。**刷る物だけ**。

    .venv/bin/python3 projects/cckb-click/click_cover_snap.py     # STL・絵・数 → build/cckb-click/coupon_cover_snap_plate.stl

形: **蓋 1 個 = 手前の板 ＋ 左右に 1 本ずつのばねの腕 ＋ 腕の先のかぎ**。手前からまっすぐ押し込むと、左右がカチッと掛かる。
外すときは、手前の面に出ている 2 本の腕の先（つまみ）を、2 本の指の爪で**内へつまんで**引き抜く。

B（コミット c62fe4c）から直した所（弱い所 → 直し方。数は docs/coupon-cover-snap.md）:
  1. 手前の板が薄い（1.27）      → **クリップと電池を奥へ DBACK = 2.0 動かした基板を前提にする**（板が 3.2 になる）。基板は変えていない（提案だけ）
  2. 右の腕の通り道に H15       → H15 を 140.0 へ（B と同じ。ほかの手は数で捨てた）
  3. 片方ずつ 2 回で開く         → かぎの外の角を斜めに落とす（HOOK_CH）: 片方だけつまんで引ける量より大きく取る = 手を離すと、腕のばねが蓋を引き戻して掛かり直す
  4. 押さえが弱い・座りが決まらない → 腕の先と口の縁を 45° の面で当てる（腕が外へ開く力が、蓋を手前 = かぎが縁に当たる向きへ押す）。奥の隙を広げて、カチッと入る余裕にする
  5. 爪の掛かり・付け根の角       → つまみの外の面を奥行き 0.9 見せる・腕の付け根と、かぎの付け根に丸み
測って分かった場所の制約（B と同じ）: かぎの掛かり 1.0 以上を、ひずみの上限 1.52 %（spec.PLA_STRAIN_USE × PLA_BEND / PLA_E）の中で外すには、腕の長さが
10 以上要る → 腕はクリップのランドの外側（x < 109.5・x > 134.5）を通す → 左右のかぎは 31 mm 離れる。蓋は平らに刷る（**底をベッドに**）。
B2（コミット 8dd3d54）から直した所（独立の見直しを受けて。「外れない」側ではなく「入らない・戻らない・抜けない」側）:
  - 蓋 3 つで、奥の案内の隙を振る（0.10／0.15／0.25）。腕と予圧は 1 種類にした
  - つまみの手前の端に、外へ出る段 = 爪が引っ掛かる面（B4 でやめた）
  - 腕の付け根の丸みを、本当に腕の付け根に置く（B2 は、隣の柱を削っていた）
  - 腕の先の 45° の面を、縁の 45° の面と面で当てる（B2 は、ほぼ角で当たっていた）
  - 奥の壁を C_BAT のランドから離す・帯の下の隙を 0.4 に・枠の角に、クリップの板の代わりを足す（電池を出す動きを試せる）
B3（コミット ffae732）から直した所（**利用者が刷った結果**: 入る・外れそうにない。**致命的: 付けたら外せない**〔つまんでから引くのが無理・爪が掛からない〕。
3 つのうち 2 つは、刷っている途中でベッドから剥がれた）:
  - **つまむだけで、蓋が出てくる**: 腕の先を高くして（つまみ・枠の上面のすぐ下まで）、その内の奥の角 K が、枠の手前の壁の残り（まぐさ）の端の斜めの面に当たる。
    かぎが縁から外れた後、さらに CAM_I つまむと、斜めの面が蓋を手前へ CAM_F 押し出す。指を離すと、かぎは縁の裏へ戻れず（縁の 45° の面に乗る）、
    腕のばねが蓋をさらに押し出す。引く動きは要らない
  - つまむ所を大きく: つまみの高さ 2.8 → 4.85・枠の縁の手前を、幅 SCOOP の斜めのくぼみにした（指の先・爪の横で、内へ押すだけ）。爪の段はやめた
  - 予圧は 0.05 に減らした（つまむ量が増えた分、ひずみの上限に入れるため）。**座りの力は、ほぼ無い**（がたは、刷って見る）
  - ベッドから剥がれにくく: 腕の底の縁を落とさない・胴の縁の落としを 0.15 → 0.10・蓋を板の真ん中に並べる・1 層目を遅く（tools/slice_cover_snap.py）
座標は CAD（基板の上面 = 0・x 右・y 奥）。左右は電池の中心 x = 122 で対称。**蓋は「かぎが縁に当たって座った位置」で書く**。寸法はこのファイルが持つ。
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

from build123d import Circle, Compound, Cylinder, Plane, Polygon, Pos, Rot, export_stl, extrude, mirror, offset  # noqa: E402

import click_case as C  # noqa: E402
import click_cover_slide as K  # noqa: E402  （読むだけ: vol・section・_place・_ccw）
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
DBACK = 2.0                   # **クリップと電池を奥へ動かす量（基板の提案）**。2.3 を超えると、電池の下の銅の逃げが、奥のビアの列（y = −29.1）と VBAT_SW の線に掛かる
(CX, _cy0), CELL_R = LAY.cell()
CY = _cy0 + DBACK             # 動かした電池の中心
CLIP_FRONT = LAY.clip_body()[1] + DBACK         # 動かしたクリップの板の、手前の端
PAD = tuple(v + (DBACK if i % 2 else 0.0) for i, v in enumerate(LAY.clip_pads()[0]))   # 動かした左のランド (x0, y0, x1, y1)
Y0 = LAY.frame[1]             # 枠の外面
REC = 0.15                    # 蓋の手前の面を、外面から引っ込める量
YF = Y0 + REC
CL = 0.15                     # 蓋と枠の隙（片側）
A0, A1 = 112.5, 2 * CX - 112.5          # 口の真ん中（上まで開いた溝。電池 φ16 の道 113.5〜130.5 ＋ 足）
YB = CLIP_FRONT - S.CLIP_TOL - 0.1      # 蓋の真ん中の塊の奥の面（クリップの板が公差の端まで手前に来ても 0.1 空く）
STRIP_Z = 3.6                 # 真ん中の塊の、電池の上に渡る帯の下面（電池の上面 3.2 の 0.4 上。刷るときは 7.7 mm を宙に渡る → 垂れの分）
POCKET_R = 7.5                # 電池を受けるくぼみの半径（電池 8.0 より小さい = 電池は、くぼみの左右の角 2 点で当たる）
CELL_GAP = 0.2                # くぼみの角と電池の、前後の隙（BACK_CL より大きい: 蓋を押し切っても、電池を押さない）
LIP_T = 1.6                   # 口の左右の縁（手前の壁の残り）の厚さ。この奥の面に、かぎが掛かる
LIP_S = 0.2                   # 縁の端の、まっすぐな所（奥の面から）。その手前 FLARE は 45° で外へ開く（腕の先が当たる面・外れたかぎが乗って、蓋を押し出す面）
FLARE = 1.0                   # 縁の端の 45° の面の長さ（前後）
SCOOP = 3.0                   # 縁の手前のくぼみの幅（縁の端から外へ。45° の面の先は、外面まで浅い斜め）= 指の先・爪の横の入り口。**枠の上面まで開いている**
YL = Y0 + LIP_T
XLIP = 106.9                  # 左の縁の端（まっすぐな所）。右は対称
XPK = 105.6                   # かぎの入る空洞の、外の壁（ねじ H14 の下穴の縁 104.8 から 0.8）
NECK = 0.2                    # 腕の外の面と、縁の端のまっすぐな所の隙（腕は 45° の面で当たるので、ここは当たらない）
XN = XLIP + NECK              # 腕の外の面（座った形。付け根から先までまっすぐ）
HOOK = 1.3                    # かぎの出のいちばん大きい値（腕の外の面から）。縁との掛かり = 出 − NECK。蓋ごとの値は VARIANTS の engage
HOOK_CH = 0.3                 # かぎの外の手前の角を 45° に落とす量（縁の当たる所を腕の芯へ寄せる = 腕の曲げを減らす。つまんで出た蓋は、これより多く出る）
HOOK_FLAT, HOOK_RAMP = 0.05, 1.3        # かぎの外の面の平らな所の長さ・斜めの所の長さ ÷ 出（入れるとき、縁に乗って腕を内へ押す）
HOOK_FILLET = 0.2             # かぎの付け根（掛かる面と腕の間）の角を埋める量
TAB_FLARE = 0.25              # 腕の先の 45° の面の長さ（前後）= 縁の 45° の面と重なる長さ。その手前は、まっすぐ = **つまむ面**（指で内へ押す）
TAB_Y = 1.9                   # つまみ（腕の先の、高くした所）の奥行き（蓋の手前の面から）
TAB_W = 1.6                   # つまみの内の面（腕の外の面から）= つまみの幅は、これ ＋ 外の面までの 0.45
TAB_TOP = TOP - 0.15          # つまみの上面（枠の上面の 0.15 下）
CAM_R = 3.0                   # 斜めの面の比: つまみが内へ 1 動くと、蓋が手前へ CAM_R 出る（面は、前後の向きから 18.4°）
CAM_I = 0.28                  # 斜めの面に乗ってから、つまみの角 K が内へ動く量
CAM_F = CAM_R * CAM_I         # そのとき、蓋が手前へ出る量（0.84）
TAB_TAPER = 0.6               # つまみの内の面を、手前へ向かって外へ逃がす量（つまむと腕の先ほど内へ傾くので、K がいちばん内の点であり続けるように）
CAM_M = 0.05                  # かぎがいちばん大きい蓋で、かぎが縁から外れてから、K が斜めの面に乗るまでの余裕
ENGAGE_MAX = 1.1              # いちばん大きい掛かり（枠の斜めの面の位置を、これで決める）
SEAT = 0.03                   # 立体どうしの重なりを見るとき、かぎを縁から離しておく量（計算上の接触を重なりに数えない）
ASM = 0.03                    # 同じく、腕の先を 45° の面から離しておく量
ZW = S.FRAME_UNDER            # 腕の通る窓の上の端 = 枠の屋根の下面（3.0）。その上は、枠の手前の壁を残す（まぐさ）
HS = ZW - 0.2                 # 蓋の、屋根の下に入る所の高さ
YR = -37.5                    # 腕の付け根
YJ = -36.25                   # 付け根の塊の、奥の面。案内の壁は、ここから 0.3 奥まで（右のコンデンサ C_BAT の手前のランド〔y ≥ −35.22〕から 0.4 以上）
ARM_L = YR - YF               # 腕の長さ
ROOT_R = 0.25                 # 腕の付け根の内の角の丸み
XSI = PAD[0] - S.PART_CLEAR   # 蓋の柱（ランドの脇を通る所）の、内の面 = ランドの外の縁の 0.4 外（109.5）
YWB = PAD[1] - 0.375          # ランドの手前で、蓋の胴が内へ広がれる所の、奥の端
XWI = LAY.clip_body()[0] - 0.2          # その内の端（クリップの板の端の 0.2 外）
T_MAX = 0.90                  # 腕の厚さ（胴の外の縁は、これで決める）
GAP_MIN = 0.40                # 腕と胴の間の、いちばん狭い隙（付け根の近く。線で埋まらない幅）
GUIDE_CL = 0.25               # 付け根の塊と、枠の案内の壁の隙（左右）の、いちばん緩い値 = 枠の壁の位置。蓋ごとの隙は VARIANTS の guide（蓋の側の当てで詰める）
BACK_CL = CL                  # 蓋を奥へ押し切れる量 = 口の真ん中の溝の奥の隙（屋根の縁で止まる。その先は、電池とクリップの止め）。**奥の壁は置かない**（B2 の薄い壁をやめた）
GUIDE_BACK = 0.3              # 案内の壁が、付け根の塊の奥の面より奥へ伸びる量
REL_CL = 0.05                 # 外すとき、かぎが縁の端から離れる隙
LEAD = 0.5                    # 入れるときの案内: 真ん中の塊の奥の角・付け根の塊の外の奥の角を、斜めに落とす量
BED = 0.10                    # ベッドの面（底）の縁を落とす量（1 層目の太り）。**胴だけ。腕は落とさない**（B3 は 0.15 を腕にも = 腕の 1 層目が 0.6 幅だった）
H15_NEW = (2 * CX - 104.0, -48.225)             # **動かした先のねじ H15**（H14 と対称 = 140.0）。いまの基板は (136.5, −48.225)
H15_OLD = next(c for n, c, _ in LAY.screws() if n == "H15")
PRINT_ERR = 0.15              # 刷りの誤差の見込み（片側）
MU = 0.3                      # PLA どうしの摩擦の見込み（座る力の、小さい側の見積もりに使う。仮定）
MARK = S.COVER_MARK           # 見分ける切り欠き（幅・深さ・間隔）
# 蓋 3 つ: **かぎの掛かり engage を振る**（まだ分からないのは「かぎが縁から外れ切る前に、斜めの面が蓋を押し始めないか」。掛かりが小さいほど、
# 外れてから押し始めるまでの余裕が大きい: 0.05／0.15／0.25。代わりに、掛かりが減る）。腕・予圧・つまみ・案内の隙（0.25 = 刷れて、入った蓋の値）は同じ
VARIANTS = {1: dict(t=0.90, pre=0.05, guide=0.25, engage=1.1),      # 掛かり 1.1（B3 と同じ）・余裕 0.05
            2: dict(t=0.90, pre=0.05, guide=0.25, engage=1.0),      # 掛かり 1.0・余裕 0.15
            3: dict(t=0.90, pre=0.05, guide=0.25, engage=0.9)}      # 掛かり 0.9・余裕 0.25
MAIN = 2
BOX = (100.5, LAY.frame[1], LAY.frame[2], S.COUPON_CORNER_BOX[1])        # 切り出す範囲（ねじ H14 の座まで入れる）
MOD = (XLIP - SCOOP - EPS, Y0 - 1.0, 2 * CX - (XLIP - SCOOP) + EPS, LAY.clip_body()[3] + S.PART_CLEAR + DBACK + EPS)   # B2 が本番の枠から変えた範囲（平面）
H15_MOD = (2 * CX - XPK - EPS, Y0 - 1.0, H15_NEW[0] + S.SCREW_BOSS_HALF + EPS, -46.0)             # ほかに、動かした H15 の座と下穴
GS = (100.0, 500.0, S.DROP_G)                                            # 電池の慣性を見る落下の加速度 [G]。**どれも仮定**
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


YS = YL + SEAT                                   # かぎの、掛かる面
A_HOOK = YR - (YS + HOOK_CH / 2)                 # 付け根から、かぎの掛かる所まで
YA = YL - LIP_S                                  # 腕の先の 45° の面の、奥の端 = 縁の 45° の面の奥の端（ここで腕は NECK だけ外へ段になる）
YG = YA - TAB_FLARE                              # 同じく、手前の端 = つまむ面の奥の端
GRIP = YG - YF                                   # つまむ面の奥行き
YT = YF + TAB_Y                                  # つまみの奥の面
YCUT = YT + 0.275                                # 枠の手前の壁の上（まぐさ）を、つまみの分だけ切る所の、奥の端
A_K = YR - YT                                    # 付け根から、つまみの内の奥の角 K まで
K_CLEAR = (ENGAGE_MAX + REL_CL) * shape(A_K) / shape(A_HOOK)      # かぎ（いちばん大きい掛かり）が縁から外れるときの、K の内への動き
XS0 = XN + TAB_W + K_CLEAR + CAM_M               # 枠の斜めの面の、奥の端の x（K が、ここで乗る）
D_MAX = (K_CLEAR + CAM_M + CAM_I) / shape(A_K)   # つまみ切ったときの、腕の先の動き（座った形から）
DTIP = D_MAX + 0.1                               # 腕の先が内へ動ける量（胴に当たって止まる = 行き過ぎの止め）


def lip_line(y):
    """左の縁の端の x（y の所）: 奥の面から LIP_S まではまっすぐ・その手前 FLARE は 45°・さらに手前は、外面で SCOOP まで開く浅い斜め。"""
    if y >= YA:
        return XLIP
    if y >= YA - FLARE:
        return XLIP - (YA - y)
    return (XLIP - FLARE) - (SCOOP - FLARE) * (YA - FLARE - y) / (YA - FLARE - Y0)


def cam_line(y):
    """左の、枠の手前の壁の上（まぐさ）の残りの、外の端の x（y の所）: つまみの奥の面 YT から手前へ CAM_F の間は斜め（K が乗る面）・その手前はまっすぐ。"""
    return XS0 + min(max(YT - y, 0.0), CAM_F) / CAM_R + (0.05 if YT - y > CAM_F + 1e-9 else 0.0)


def bend(pts, d):
    """左の腕の点を、先が d だけ内へ動く撓みの形に動かす（座った形から。d < 0 は外へ）。"""
    return [(x + d * shape(YR - y), y) for x, y in pts]


def body_edge(y):
    """左の胴の、外の縁の x（腕が DTIP 動いても当たらない線。付け根の近くは GAP_MIN。つまみの所は、つまみの内の面から）。"""
    x = XN + T_MAX + max(GAP_MIN, 0.1 + DTIP * shape(YR - y))
    return max(x, XN + TAB_W + 0.1 + DTIP * shape(YR - y)) if y <= YT + 0.3 else x


def release_tip(pre, engage=ENGAGE_MAX):
    """かぎが縁から外れるのに要る、腕の先の動き（刷った形から）: かぎの所で 予圧 ＋ 掛かり ＋ REL_CL 動かす。"""
    return (pre + engage + REL_CL) / shape(A_HOOK)


def _arm_pts(t, hook, chamfer=HOOK_CH):
    """左の腕の平面の形（座った形）。かぎは外（−x）へ出る。先は、45° の面 → まっすぐな爪の掛かる面。"""
    end = YS + chamfer + HOOK_FLAT + hook * HOOK_RAMP          # かぎの奥の端
    pts = [(XN, YR + 0.3), (XN, end)]
    if hook > 0:
        pts += [(XN - hook, YS + chamfer + HOOK_FLAT), (XN - hook, YS + chamfer), (XN - hook + chamfer, YS),
                (XN - HOOK_FILLET, YS), (XN, YS - HOOK_FILLET)]
    pts += _tab_outer() + [(XN + t, YF), (XN + t, YR + 0.3)]
    # 撓みの形を滑らかに出すために、長い辺を刻む
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        n = max(1, int(abs(y1 - y0) / 0.6))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    return out


def _tab_outer():
    """腕の先の、外の輪郭（45° の面 → つまむ面 → 手前の角）。"""
    xg = XLIP - TAB_FLARE
    return [(XN, YA), (XLIP, YA), (xg, YG), (xg, YF + 0.1), (xg + 0.1, YF)]


def _tab_pts():
    """つまみ（腕の先の、高くした所）の平面の形。内の奥の角 K = (XN + TAB_W, YT) が、枠の斜めの面に乗る。"""
    return [(XN, YT)] + _tab_outer() + [(XN + TAB_W - TAB_TAPER, YF), (XN + TAB_W, YT)]


def _poly(pts):
    return Polygon(*K._ccw(list(pts)), align=None)


def _side_pts(n=24):
    """左の胴（屋根の下に入る所）の平面の形: 外の縁（腕から離れた線）・ランドの脇の柱・ランドの手前の広い所。"""
    ys = [YF + (YR - YF) * i / n for i in range(n + 1)]
    return [(body_edge(y), y) for y in ys] + [(XSI, YR), (XSI, YWB), (XWI, YWB), (XWI, YF)]


def pocket_center():
    """電池を受けるくぼみの円の中心と、くぼみの角の x（中心から）。角（蓋の奥の面 YB の上）で、電池との前後の隙が CELL_GAP になる所に置く。"""
    dy = CY - YB - CELL_GAP
    hw = math.sqrt(CELL_R ** 2 - dy ** 2)
    return (CX, YB + math.sqrt(POCKET_R ** 2 - hw ** 2)), hw


@lru_cache(maxsize=None)
def cover(variant=MAIN, mark=True, dl=None, dr=None, t=None, hook=None, chamfer=HOOK_CH, root_r=None, tab=True):
    """B4 の蓋（座った位置）。dl・dr = 左・右の腕の先を、**座った形から**内へ動かした量（既定 = ASM）。**刷る形は dl = dr = −pre**（printed）。
    t・hook・chamfer・root_r を渡すと、その厚さの腕・その出のかぎ・その角・その付け根の丸み（検査を壊して見る形。hook = 0 で、かぎ無し）。tab=False = つまみを高くしない。"""
    v = VARIANTS[variant]
    t = v["t"] if t is None else t
    hook = v["engage"] + NECK if hook is None else hook
    dl = ASM if dl is None else dl
    dr = ASM if dr is None else dr
    xo = XN - (GUIDE_CL - v["guide"])                            # 付け根の塊の外の面（案内の隙を詰める蓋は、ここが外へ出る）
    root_r = ROOT_R if root_r is None else root_r

    def half(d):
        out = [_poly(_side_pts()),
               _poly([(xo, YR - EPS), (xo, YJ - LEAD), (xo + LEAD, YJ), (XSI, YJ), (XSI, YR - EPS)])]      # 付け根の塊（外の奥の角は、案内の壁へ入る案内）
        if root_r > 0:                                           # 腕の付け根の内の角の丸み: 腕と付け根の塊の間の角を、円弧で**埋める**
            xc, yc = XN + t + root_r, YR - root_r
            out.append(C._rect2d((XN + t - EPS, yc, xc, YR + EPS)) - Pos(xc, yc) * Circle(root_r))
        return out

    arms = _union([_poly(bend(_arm_pts(t, hook, chamfer), dl)), _mirror(_poly(bend(_arm_pts(t, hook, chamfer), dr)))])
    tabs = _union([_poly(bend(_tab_pts(), dl)), _mirror(_poly(bend(_tab_pts(), dr)))])
    low = _union(half(dl) + [_mirror(q) for q in half(dr)])
    xa, xb = A0 + CL, A1 - CL                                   # 真ん中の塊（奥の左右の角は、口の真ん中の溝へ入る案内）
    mid = _poly([(xa, YF), (xb, YF), (xb, YB - LEAD), (xb - LEAD, YB), (xa + LEAD, YB), (xa, YB - LEAD)])
    (px, py), _ = pocket_center()
    pocket = Pos(px, py, -1.0) * Cylinder(POCKET_R, STRIP_Z + 1.0, align=P.CEN_MIN)
    body = extrude(low, HS) + (extrude(mid, TOP) - pocket)
    limbs = extrude(arms, HS) + (extrude(tabs, TAB_TOP) if tab else extrude(tabs, HS))        # 腕とつまみ: 底の縁は落とさない（1 層目の幅を減らさない）
    plan = (low + mid) - Pos(px, py) * Circle(POCKET_R)
    if mark:
        mw, md, mp = MARK
        x1 = A1 - CL - 1.2
        cuts = [(x1 - i * mp - mw, YB - md, x1 - i * mp, YB + 1.0) for i in range(variant)]
        body = body - _union([_box(q, -1.0, TOP + 1.0) for q in cuts])
        plan = plan - _union([C._rect2d(q) for q in cuts])
    # ベッドの面（底）の縁を落とす: 下の 2 層を、平面の形を内へ寄せた段に置き換える
    body = body - _box((XPK - 2.0, Y0 - 1.0, mx(XPK) + 2.0, YJ + 2.0), -1.0, 0.2)
    body = body + extrude(offset(plan, -BED), 0.1 + EPS) + Pos(0, 0, 0.1) * extrude(offset(plan, -BED / 2), 0.1 + EPS)
    body = (body + limbs).clean()
    if len(body.solids()) != 1:
        raise RuntimeError(f"B4 の蓋が {len(body.solids())} 個の塊")
    return body


def printed(variant, mark=True):
    """刷る形（腕が予圧ぶん外へ開いた形）。"""
    pre = VARIANTS[variant]["pre"]
    return cover(variant, mark, -pre, -pre)


def posed(part, dx=0.0, dy=0.0, dz=0.0, rz=0.0, rx=0.0, pivot=None):
    """part を、pivot（既定は蓋の手前の真ん中）まわりに回して（度）から、平行に動かす。"""
    px, py, pz = pivot or (CX, YF, HS / 2)
    return Pos(px + dx, py + dy, pz + dz) * Rot(rx, 0, rz) * Pos(-px, -py, -pz) * part


# ---------------------------------------------------------------------------
# 枠（本番の枠の右手前の角 → 本番の口を埋める → B2 の形に掘る。クリップの空間を奥へ・H15 を動かす）
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def prod_corner():
    """本番の枠の右手前の角（BOX の範囲）＋ 切った左の端の壁（当て板に載せるため。本番には無い）。"""
    a = LAY.key_area
    part = C.frame_full() & _box(BOX, -1.0, TOP + 1.0)
    return part + _box((BOX[0], a[1] - EPS, BOX[0] + S.COUPON_CORNER_WALL, BOX[3]), 0.0, S.FRAME_UNDER + EPS)


@lru_cache(maxsize=None)
def frame(lips=True, standin=True, cam=True):
    """B4 の口を掘った枠の角。lips=False = 口の左右の縁なし・cam=False = まぐさの残り（つまみを押し出す斜めの面）なし（どちらも、検査を壊して見る形）。standin = **クリップの板の代わり**（試し刷りだけ。本番には無い）:
    屋根を、クリップの板の範囲（図面の外接の矩形。手前の端は、口の真ん中の溝の奥の縁まで = 公差の端より 0.05 奥）で、板の下面の高さまで厚くする → 蓋を外したときに電池がどれだけ見えるか・
    爪が届くかを、試し刷りで試せる。"""
    cv = LAY.cover()
    d, depth = LAY.pilot()
    wall_in = LAY.key_area[1]                                   # 手前の壁の内面
    boss_back = max(r[3] for n, r in C.lower_rects() if n == "boss" and r[0] < 104.0 < r[2] and r[1] < -40.0)   # 本番のねじの座の奥の面
    part = prod_corner()
    # 本番の口・溝・歯・溝の奥の壁と、クリップの空間の手前の端を埋める。いまの H15 の下穴も埋める
    part = part + _box((XSI, Y0, mx(XSI), cv["y_cheek"]), 0.0, TOP) \
        + Pos(H15_OLD[0], H15_OLD[1], 0.0) * Cylinder(d / 2 + EPS, depth + EPS, align=P.CEN_MIN)
    cuts = [
        _box((A0, Y0 - 1.0, A1, YB + CL), -1.0, TOP + 1.0),                                             # 口の真ん中（上まで）
        # クリップの空間（本番と同じ高さ・幅）を、DBACK 奥へ: 手前の端は、動かした板の 0.4 手前から・奥の端は、本番の端 ＋ DBACK
        _box((XSI, CLIP_FRONT - S.PART_CLEAR, mx(XSI), MOD[3] - EPS), -1.0, S.CLIP_ROOF_UNDER),
        _box((XSI, wall_in - EPS, mx(XSI), CLIP_FRONT - S.PART_CLEAR + EPS), -1.0, ZW),                 # その手前の、屋根の下（本番と同じ 3.0）
        _box((mx(XSI) - EPS, wall_in - EPS, mx(XPK), boss_back + 0.03), -1.0, ZW),                      # いまの H15 の座（壁の奥へ出た分）
    ]
    for side in (0, 1):
        f = (lambda x: x) if side == 0 else mx
        xa, xb = sorted((f(XLIP if lips else XPK), f(A0 + EPS)))
        cuts.append(_box((xa, Y0 - 1.0, xb, wall_in + EPS), -1.0, ZW))                                   # 腕の通る窓（屋根の下）
        xa, xb = sorted((f(XPK), f(XLIP + EPS)))
        cuts.append(_box((xa, YL, xb, boss_back + 0.03), -1.0, ZW))                                      # かぎの入る空洞（縁の裏）
        if lips:
            cut = [(f(XLIP + EPS), YA), (f(XLIP), YA), (f(XLIP - FLARE), YA - FLARE), (f(XLIP - SCOOP), Y0), (f(XLIP - SCOOP), Y0 - 0.3),
                   (f(XLIP + EPS), Y0 - 0.3)]
            cuts.append(Pos(0, 0, -1.0) * extrude(_poly(cut), TOP + 2.0))                                # 縁の端の 45° の面と、指の入るくぼみ（上まで）
        if not cam:                                              # 壊して見る形: まぐさの残り（斜めの面）が無い
            cuts.append(_box(tuple(sorted((f(XLIP), f(A0 + EPS)))[:1]) + (Y0 - 0.3,) + tuple(sorted((f(XLIP), f(A0 + EPS)))[1:]) + (YCUT,), ZW - EPS, TOP + 1.0))
        else:
            xl = XLIP if lips else XPK
            top = [(f(xl), Y0 - 0.3), (f(cam_line(Y0)), Y0 - 0.3), (f(cam_line(Y0)), YT - CAM_F), (f(XS0 + CAM_I), YT - CAM_F), (f(XS0), YT), (f(XS0), YCUT),
                   (f(xl), YCUT)]
            cuts.append(Pos(0, 0, ZW - EPS) * extrude(_poly(top), TOP - ZW + 1.0))                       # つまみの通る所（手前の壁の上を切る。内の端は斜めの面）
    part = part - _union(cuts)
    adds = [_box((mx(XPK), wall_in - EPS, H15_NEW[0] + S.SCREW_BOSS_HALF, boss_back), 0.0, ZW + EPS)]    # 動かした H15 の座
    for side in (0, 1):
        f = (lambda x: x) if side == 0 else mx
        xa, xb = sorted((f(XPK), f(XN - GUIDE_CL)))
        adds.append(_box((xa, YR - 1.2, xb, YJ + GUIDE_BACK), 0.0, ZW + EPS))                            # 案内の壁（付け根の塊の外。幅 1.25）
    if standin:
        body = LAY.clip_body()
        adds.append(_box((body[0], max(CLIP_FRONT - S.CLIP_TOL, YB + CL), body[2], CLIP_FRONT + 3.0), S.CLIP_H - S.CLIP_SHEET_T - S.CLIP_TOL, S.CLIP_ROOF_UNDER + EPS))
    part = part + _union(adds)
    part = part - Pos(H15_NEW[0], H15_NEW[1], -1.0) * Cylinder(d / 2, depth + 1.0, align=P.CEN_MIN)
    part = part.clean()
    if lips and len(part.solids()) != 1:
        raise RuntimeError(f"B4 の枠が {len(part.solids())} 個の塊")
    return part


def clip(dx=0.0, dy=0.0):
    """動かしたクリップの金属（図面から作った形 = click_case.clip_solid を DBACK 奥へ）。dx・dy = 公差を見るためにずらす量。"""
    return Pos(dx, DBACK + dy, 0.0) * C.clip_solid()


@lru_cache(maxsize=None)
def base():
    """当て板（基板の代わり・**クリップを DBACK 奥へ・H15 を動かし・H30 と H31 を消した基板**）: ねじ穴 H14・動かした H15・電池の奥の止め・
    クリップの脚の代わり（動かしたランドの上・電池の左右の案内も兼ねる）・左と奥の縁の当て・電池の代わりを裏から押す長い穴。
    **クリップの板（基板の 3.5〜4.1 上）の代わりは無い**。"""
    s = S
    p = LAY.pcb
    fit, fence = s.COUPON_FIT, 1.8
    plate = _box((BOX[0] - fit - fence, p[1], p[2], BOX[3] + fit + fence), -s.PCB_T, 0.0)
    at = [c for n, c, _ in LAY.screws() if n == "H14"] + [H15_NEW]
    holes = _union([Pos(c[0], c[1], -s.PCB_T - 1.0) * Cylinder(s.SCREW_HOLE_D / 2, s.PCB_T + 2.0, align=P.CEN_MIN) for c in at])
    parts = [plate - holes,
             _box((BOX[0] - fit - fence, p[1], BOX[0] - fit, BOX[3] + fit + fence), -EPS, 2.0),
             _box((BOX[0] - fit - fence, BOX[3] + fit, p[2], BOX[3] + fit + fence), -EPS, 2.0)]
    stop_y = s.CLIP_AT[1] + s.CLIP_STOP - s.CLIP_SHEET_T + DBACK
    parts.append(_box((CX - s.CLIP_STOP_W / 2, stop_y, CX + s.CLIP_STOP_W / 2, stop_y + 1.0), -EPS, 2.8))
    for f in ((lambda x: x), mx):
        xa, xb = sorted((f(PAD[0]), f(CX - CELL_R - fit)))
        parts.append(_box((xa, PAD[1], xb, PAD[3]), -EPS, LAY.z()["clip_top"]))
    pd, pw, pl = s.COUPON_PUSH
    push = _box((CX - pw / 2, CY - pl, CX + pw / 2, CY + pw / 2), -s.PCB_T - 1.0, 1.0)
    return (_union(parts) - push).clean()


@lru_cache(maxsize=None)
def cell():
    """電池の代わり（本番の試し刷りと同じ物を、DBACK 奥へ）。"""
    return Pos(0, DBACK, 0) * C.corner_coupon()["cell"]


# ---------------------------------------------------------------------------
# 動かして探す（検査と絵が使う）
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def obstacles(lips=True, with_cell=False, cam=True):
    """蓋が当たる相手 [立体]: 枠（口のまわりだけ切り出した物。クリップの板の代わりを含む）・当て板・クリップの金属（図面から作った形）・（電池の代わり）。"""
    near = frame(lips, True, cam) & _box((BOX[0], Y0 - 1.0, mx(BOX[0]), YJ + 4.0), -2.0, TOP + 1.0)
    return tuple([near, base(), clip()] + ([cell()] if with_cell else []))


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


def pinched(variant=MAIN, left=True, right=True, mark=False):
    """つまみ切った形の蓋（腕の先を、座った形から D_MAX 内へ）。left・right = どちらの腕をつまむか。"""
    return cover(variant, mark, D_MAX if left else None, D_MAX if right else None)


def one_arm_out(variant=MAIN, iters=120, side="left"):
    """**片方（左）の腕だけ**を、かぎが縁から外れる所まで内へ撓ませた蓋（右の腕は、座った形）で、蓋の手前の面の端が手前へ出られる量と姿勢
    （平面の中で、ずらす・回すを探す）。side = どちらの端の出を、いちばん大きくするか: "left" = つまんだ側（片方が出る量）・"right" = つまんでいない側
    （これが小さい = 蓋は、もう片方のかぎに掛かったまま = 片方だけでは出てこない）。"""
    a = arm_numbers(variant)
    one = cover(variant, False, a["release"] - a["pre"] + 0.05, None)
    x = XLIP - a["engage"] / 2
    return wiggle(one, obstacles(), lambda q: corner_out(q, x if side == "left" else mx(x)), iters=iters)


def push_out(part, obst, step=0.05, limit=3.0, tol=2e-3):
    """part が obst に重なっているとき、重ならなくなるまで手前へ動かす量（斜めの面に押し出される量）。重なっていなければ 0。"""
    n = 0
    while n * step <= limit and hit(posed(part, dy=-n * step), obst) > tol:
        n += 1
    return n * step


@lru_cache(maxsize=None)
def eject(variant=MAIN, cam=True, step=0.1, dstep=0.05):
    """**つまむだけで、蓋がどこまで出るか**を、立体を動かして解く（引く力は 0）。
      cam    両方の腕をつまみ切った形（D_MAX）は、座った位置では枠（斜めの面）に重なる → 重ならなくなるまで手前へ動かした量 = 斜めの面が押し出す量
      path   そこで指を離す: 蓋を step ずつ手前へ動かしながら、腕がどこまで外へ戻れるか（枠に重ならない、いちばん小さい撓み d）を探す [(出た量, d)]。
             d が減り続ける間は、腕のばねの力が、蓋を手前へ押している（腕のエネルギー ½ k d² が減る向き）
      rest   指を離した所から、d が減り続けている間だけ進んだ所 = 蓋が止まる位置（摩擦を見ない。途中に d の減らない所があれば、そこで止まると見る）。work = そこまでに腕 2 本が蓋にした仕事 [N·mm]・force = その平均の力 [N]
      back   cam の位置で指を離した形（path の最初の d）の蓋を、奥へ戻そうとして進める量（かぎが縁の手前に当たって、掛かり直せない = 小さい）
    cam=False = 枠の斜めの面が無いとき（検査を壊して見る形: つまんでも、蓋は押し出されない）。"""
    ob = obstacles(cam=cam)
    k = arm_numbers(variant)["k"]
    out = dict(cam=push_out(pinched(variant), ob))
    d, y, path = D_MAX, out["cam"], []
    while y <= 4.0:
        while d - dstep >= ASM - 1e-9 and hit(posed(cover(variant, False, round(d - dstep, 3), round(d - dstep, 3)), dy=-y), ob) < 2e-3:
            d = round(d - dstep, 3)
        path.append((round(y, 3), d))
        if d <= ASM + dstep or (len(path) > 3 and path[-3][1] == d):
            break
        y += step
    out["path"] = path
    rest = out["cam"]                                           # 指を離した所から、腕が戻り続ける間だけ進む（戻らない所があれば、そこで止まる）
    d_rest = path[0][1]
    for (y0, d0), (y1, d1) in zip(path, path[1:]):
        if d1 >= d0:
            break
        rest, d_rest = y1, d1
    pre = VARIANTS[variant]["pre"]
    work = 2 * 0.5 * k * ((path[0][1] + pre) ** 2 - (d_rest + pre) ** 2)
    out.update(rest=rest, work=work, force=work / max(rest - out["cam"], 1e-9),
               back=travel(posed(cover(variant, False, path[0][1], path[0][1]), dy=-out["cam"]), ob, (0, 1, 0), limit=2.0, pivot=(CX, YF, HS / 2)))
    return out


def engagement(variant=MAIN, dx=0.0, hook=None):
    """かぎと縁の掛かり（左, 右）[mm]: かぎを、角の斜めの分 ＋ 0.1 手前へ動かしたとき、縁のまっすぐな所と重なる所の左右の幅（立体から測る）。dx = 蓋を横へずらした量。"""
    out = []
    cv = posed(cover(variant, False, hook=hook), dx=dx, dy=-(HOOK_CH + 0.1))
    fr = obstacles()[0]
    for f in ((lambda x: x), mx):
        xa, xb = sorted((f(XPK - 0.5), f(XLIP + 0.05)))
        c = (cv & _box((xa, YL - LIP_S + 0.02, xb, YL + 0.3), 0.3, HS - 0.3)) & fr
        try:
            out.append(c.bounding_box().size.X if c is not None and c.volume > 1e-6 else 0.0)
        except (AttributeError, ValueError):
            out.append(0.0)
    return tuple(out)


def measure_moves(variant=MAIN):
    """絵と文書に載せる「動ける量」（検査と同じ探し方）: forward・up = 座った蓋が進める量・side・back = 胴が左右・奥へ動ける量（腕を 0.3 内へ逃がした蓋で）・
    cell = 電池の代わりが手前へ進める量・one_arm = 片方の腕だけをつまみ切ったとき、その側のかぎの所が手前へ出る量と姿勢・eject = つまむだけで出る量（蓋ごと）。"""
    cv, ob = cover(variant, False), obstacles()
    slack = cover(variant, False, 0.3, 0.3)
    return dict(forward=travel(cv, ob, (0, -1, 0)), up=travel(cv, ob, (0, 0, 1), limit=1.0),
                side=max(travel(slack, ob, (-1, 0, 0), limit=1.0), travel(slack, ob, (1, 0, 0), limit=1.0)),
                back=travel(slack, obstacles(with_cell=True), (0, 1, 0), limit=1.0),
                cell=travel(cell(), (ob[0], ob[1], cv), (0, -1, 0), pivot=(0.0, 0.0, 0.0)),
                one_arm=one_arm_out(variant), one_arm_other=one_arm_out(variant, side="right")[0], eject={n: eject(n) for n in sorted(VARIANTS)})


# ---------------------------------------------------------------------------
# 数（材料の値は TDS = spec.PLA_*・断面は立体から測るか、名目）
# ---------------------------------------------------------------------------

def arm_numbers(variant=MAIN):
    """腕（片持ち梁・先に力）。
      release           かぎが縁から外れるときの、先の動き（刷った形から）・pinch_max  つまみ切ったとき（斜めの面の端まで）・insert  入れるとき・stop  胴に当たって止まるとき
      strain_*          そのときの付け根のひずみ [%]（上限は strain_use = spec.PLA_STRAIN_USE × PLA_BEND / PLA_E）
      pinch             つまみ切るときに、1 本の腕の先（つまみ）を押す力 [N]（腕のばねだけ。斜めの面が蓋を押す分は、蓋が自由なので、ほぼ 0）
      insert_force      押し込むときに要る力 [N]・腕 2 本（かぎの斜めの面が縁に乗って、腕を撓ませる。摩擦 MU を入れた大きい側）
      cam_margin        かぎが縁から外れてから、つまみの角 K が斜めの面に乗るまでの、K の動きの余裕（0 より小さいと、外れる前に押し始めて、噛む）
      seat_y            腕 2 本が 45° の面を押して、蓋を手前へ押す力 [N]（摩擦を引いた値, 引かない値）。**予圧が小さいので、ほぼ無い**
      engage_worst      掛かりのいちばん小さい見込み: 縁とかぎが誤差ぶん短く刷れる・縁の厚さの誤差で腕が内へ寄る
      one_arm_calc      片方だけつまんだとき、その側のかぎが手前へ出る量の見積もり = 案内の隙 ÷（かぎから案内までの奥行き）×（左右のかぎの間）
      drop              自分の重さで、DROP_G（半波 DROP_MS）の衝撃を横に受けたときの、かぎの所の揺れ [mm]（外れるのは 予圧 ＋ 掛かり）"""
    v = VARIANTS[variant]
    t, pre, eng = v["t"], v["pre"], v["engage"]
    e = S.PLA_E
    inertia = HS * t ** 3 / 12
    k = 3 * e * inertia / ARM_L ** 3
    strain = lambda d: 1.5 * t * d / ARM_L ** 2 * 100          # noqa: E731
    rel = release_tip(pre, eng)
    ins = (pre + eng) / shape(A_HOOK)
    stop = pre + DTIP
    pmax = pre + D_MAX
    k_hook = 3 * e * inertia / A_HOOK ** 3
    th = math.atan(1.0 / HOOK_RAMP)                             # かぎの斜めの面の、前後の向きからの角度
    wedge_in = (math.sin(th) + MU * math.cos(th)) / (math.cos(th) - MU * math.sin(th))
    acc = S.DROP_G * 9.80665
    wl = C.PLA_DENSITY * HS * t * acc * 1e-3
    static = wl * ARM_L ** 4 / (8 * e * inertia)
    freq = 1.875104 ** 2 / (2 * math.pi) * math.sqrt(e * inertia / (C.PLA_DENSITY * HS * t * ARM_L ** 4) * 1e6)
    gain = C.shock_gain(freq, S.DROP_MS)
    wedge = (1 - MU) / (1 + MU)
    return dict(t=t, pre=pre, hook=eng + NECK, length=ARM_L, k=k, release=rel, pinch_max=pmax, insert=ins, stop=stop,
                strain_release=strain(rel), strain_pinch=strain(pmax), strain_insert=strain(ins), strain_stop=strain(stop),
                strain_use=S.PLA_STRAIN_USE * S.PLA_BEND / e * 100, strain_limit=S.PLA_BEND / e * 100,
                pinch=k * pmax, insert_force=2 * k_hook * (pre + eng) * wedge_in, seat_y=(2 * k * pre * wedge, 2 * k * pre),
                cam_margin=XS0 - (XN + TAB_W) - (eng + REL_CL) * shape(A_K) / shape(A_HOOK),
                engage=eng, engage_flat=eng - HOOK_CH, engage_worst=eng - 3 * PRINT_ERR, guide=v["guide"],
                one_arm_calc=v["guide"] / (YR - YL) * (mx(XLIP) - XLIP),
                freq=freq, gain=gain, drop=static * gain * shape(A_HOOK), drop_margin=(pre + eng) / (static * gain * shape(A_HOOK)),
                front_gap=body_edge(YF) - (XN + TAB_W))


@lru_cache(maxsize=None)
def plate_sections(variant=MAIN, step=0.1):
    """蓋の真ん中の板の断面（くぼみの左右の角の間の 5 か所）を、立体から測る [(x, 断面)]。"""
    (px, py), hw = pocket_center()
    cv = cover(variant, False)
    xs = [CX - (hw - 0.05) * k for k in (1.0, 0.5, 0.0, -0.5, -1.0)]
    return [(x, K.section(cv, x, step=step, y0=YF, y1=YB, z0=0.0, z1=TOP)) for x in xs]


def stresses(variant=MAIN, force=PUSH, center=True):
    """電池が蓋を手前へ force [N] で押すときの、力の道の応力 [MPa]。**力は、左右のかぎを通る**（手前から入れる蓋なので、電池の押す向き = 抜ける向き）。
    center=True = 電池が、くぼみの**真ん中**で当たる（いちばん悪い当たり方。刷りの誤差で、角の隙と真ん中の隙の差が無くなったとき）・False = 設計どおり左右の角。
      plate   蓋の真ん中の板（左右のかぎで受ける梁）。断面は立体から測る（click_cover_slide.section）。tension = 手前の縁・compression = 奥の縁
      arm     腕（かぎ〜付け根を押し縮める柱。かぎは腕の芯から外れているので、曲げも受ける）: stress・buckle = 座屈する力（付け根は固定・先は縁が横を支える）
      stem    ランドの脇の柱（腕の押す力を、引っ張りで胴へ返す。腕との間が離れているので、曲げも受ける）: いちばん細い所（ランドの手前の角）。
              **腕と柱の間の偶力を、全部柱が受けると見た上側の見積もり**
      hook    かぎの付け根のせん断・lip 縁の面圧（かぎの平らな所だけで受けると見て）"""
    v = VARIANTS[variant]
    t, hook = v["t"], v["engage"] + NECK
    p = force / 2
    (px, py), hw = pocket_center()
    x_hook = (XN - hook + HOOK_CH + XLIP) / 2                   # かぎの平らな所と、縁の重なりの真ん中
    out = dict(force=force)
    worst = None
    m = p * ((CX if center else CX - hw) - x_hook)
    for x, sc in plate_sections(variant):
        ten, cmp_ = m * sc["front"] / sc["inertia"], m * sc["rear"] / sc["inertia"]
        if worst is None or max(ten, cmp_) > max(worst["tension"], worst["compression"]):
            worst = dict(x=x, moment=m, tension=ten, compression=cmp_, **sc)
    out["plate"] = worst
    area, inertia = t * HS, HS * t ** 3 / 12
    ecc = (XN + t / 2) - x_hook
    buckle = 2.046 * math.pi ** 2 * S.PLA_E * inertia / A_HOOK ** 2
    amp = 1.0 / (1.0 - p / buckle) if p < buckle else float("inf")
    out["arm"] = dict(load=p, ecc=ecc, moment=p * ecc, buckle=buckle, stress=p / area + p * ecc * (t / 2) / inertia * amp)
    ws = XSI - body_edge(YWB)
    dist = (XSI - ws / 2) - (XN + t / 2)
    ms = p * dist + 0.5 * p * ecc
    out["stem"] = dict(width=ws, dist=dist, moment=ms, stress=p / (ws * HS) + ms * (ws / 2) / (HS * ws ** 3 / 12))
    out["hook"] = p / ((HOOK_CH + HOOK_FLAT + hook * HOOK_RAMP) * HS)
    out["lip"] = p / ((v["engage"] - HOOK_CH) * HS)
    return out


def strength_forces(variant=MAIN, center=True):
    """それぞれの所が TDS の強さに届く、電池の押す力 [N]: 板の引っ張り（PLA_TENSILE）・板の圧縮・柱・腕（PLA_BEND）・腕の座屈・かぎのせん断
    （PLA_TENSILE ÷ √3）・縁の面圧（PLA_BEND）。腕は力に比例しない（座屈に近づくと増える）ので、二分法で探す。"""
    one = stresses(variant, 1.0, center)
    out = dict(plate_tension=S.PLA_TENSILE / one["plate"]["tension"], plate_compression=S.PLA_BEND / one["plate"]["compression"],
               stem=S.PLA_BEND / one["stem"]["stress"], buckle=2 * one["arm"]["buckle"],
               hook=S.PLA_TENSILE / math.sqrt(3) / one["hook"], lip=S.PLA_BEND / one["lip"])
    lo, hi = 0.0, 2 * one["arm"]["buckle"]
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if stresses(variant, mid, center)["arm"]["stress"] < S.PLA_BEND else (lo, mid)
    out["arm"] = lo
    return out


def lintel():
    """腕の通る窓の上に残る、手前の壁（まぐさ）を、縁の付け根から口の真ん中の溝まで張り出した片持ち梁と見たとき（奥の屋根とのつながりは数えない = 弱い側）、
    先を上から 10 N で押したときの、先の下がり [mm] と、付け根の応力 [MPa]。下がりが蓋との隙（ZW − HS）より小さければ、蓋に載らない。"""
    length = A0 - cam_line(Y0)                                  # B4: つまみの通る所を切ったので、残りは、斜めの面の端から口の真ん中の溝まで
    b, h = LAY.key_area[1] - Y0, TOP - ZW                      # 奥行き（壁の厚さ）・高さ
    inertia = b * h ** 3 / 12
    return dict(length=length, section=(b, h), drop=10.0 * length ** 3 / (3 * S.PLA_E * inertia), stress=10.0 * length * (h / 2) / inertia, gap=ZW - HS)


def footprint(variant=MAIN):
    """刷る形の蓋の、1 層目（底から 0.05）でベッドに着く面積 [mm2]。"""
    cv = printed(variant, False) & _box((XPK - 3.0, Y0 - 1.0, mx(XPK) + 3.0, YJ + 2.0), 0.02, 0.07)
    return cv.volume / 0.05


def cell_access():
    """蓋を外したときに、電池に指・爪が届く所（クリップと電池を DBACK 動かした形で）。口の真ん中は、手前と上の両方へ開いた箱。
      well      その箱（幅, 奥行き, 深さ = 枠の上面から基板まで）
      top       上から見える電池の上面: 電池の手前の縁から、クリップの板の手前の端（公差の端まで手前に来たとき）まで（奥行き）と、その奥の端での幅
      front     手前から見える電池の側面: 高さ（電池の厚さ）と、外面からの奥行き
    押す向き: 見えている上面と手前の縁を、爪か指の先で**下へ押しながら手前へ**引く（本番の蓋と同じ動き。電池が出てくるほど、押せる面が増える）。"""
    front = CY - CELL_R
    edge = min(YB + CL, CLIP_FRONT - S.CLIP_TOL)
    depth = edge - front
    return dict(well=(A1 - A0, YB + CL - Y0, TOP), top=(depth, 2 * math.sqrt(CELL_R ** 2 - (CY - edge) ** 2)), front=(S.CELL_T, front - Y0),
                top_nominal=min(YB + CL, CLIP_FRONT) - front, top_production=LAY.clip_body()[1] - (LAY.cell()[0][1] - CELL_R))


def numbers():
    """文書と絵に載せる数。"""
    mass = cover(MAIN, False).volume * C.PLA_DENSITY
    (px, py), hw = pocket_center()
    acc = 9.80665e-3
    st = {True: stresses(MAIN, PUSH, True), False: stresses(MAIN, PUSH, False)}
    sf = strength_forces(MAIN, True)
    weakest = min(sf, key=sf.get)
    cavity_back = MOD[3]
    return dict(arms={n: arm_numbers(n) for n in VARIANTS}, mass=mass, stress=st, strength=sf, weakest=(weakest, sf[weakest]),
                weakest_g=sf[weakest] / (S.CELL_MASS * acc), loads={g: S.CELL_MASS * g * acc for g in GS},
                pocket=dict(center=(px, py), corner=hw, center_gap=(CY - CELL_R) - (py - POCKET_R), plate_t=(py - POCKET_R) - YF),
                h14_wall=XPK - (104.0 + S.SCREW_PILOT_D / 2), h15_wall=(H15_NEW[0] - S.SCREW_PILOT_D / 2) - mx(XPK),
                h15_move=H15_NEW[0] - H15_OLD[0], lip=LIP_T, window=(A0 - XLIP, ZW), hook_span=mx(XLIP - ENGAGE_MAX / 2) - (XLIP - ENGAGE_MAX / 2),
                target=dict(face=(GRIP, TAB_TOP), top=(TAB_W + XN - (XLIP - TAB_FLARE), TAB_Y), scoop=(SCOOP, YA - Y0), travel=D_MAX * shape(YR - YF)),
                cam=dict(ratio=CAM_R, inward=CAM_I, out=CAM_F, x0=XS0, d_max=D_MAX, footprint=footprint()),
                seat_face=TAB_FLARE * math.sqrt(2.0), lintel=lintel(), cavity_back=cavity_back, dback=DBACK, cell_access=cell_access())


# ---------------------------------------------------------------------------
# 刷る板
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def pieces():
    """{名前: 立体}（組んだ向き。蓋は**刷る形** = 腕が予圧ぶん外へ開いた形）。"""
    out = {"frame": frame(), "base": base(), "cell": cell()}
    for n in sorted(VARIANTS):
        out[f"cover{n}"] = printed(n)
    return out


def plate_layout(gap=4.0):
    """1 枚に並べた刷る物 [(名前, 置いた立体, 組んだ座標 → 板の座標)]: 手前から 当て板・電池の代わりと蓋 3 つ（**底をベッドに・板の真ん中**）・枠（上面をベッドに）。
    蓋は小さくて剥がれやすいので、ベッドの真ん中に来る列に置く（B3 は、いちばん手前の列だった）。"""
    pc = pieces()
    out, y = [], 0.0
    part, fn, size = K._place(pc["base"], 0.0, y, False)
    out.append(("base", part, fn))
    y += size.Y + gap
    x, row = 0.0, 0.0
    for name in ["cell"] + [n for n in sorted(pc) if n.startswith("cover")]:
        part, fn, size = K._place(pc[name], x, y, False)
        if x and x + size.X > 60.0:
            x, y, row = 0.0, y + row + gap, 0.0
            part, fn, size = K._place(pc[name], x, y, False)
        out.append((name, part, fn))
        x += size.X + gap
        row = max(row, size.Y)
    y += row + gap
    part, fn, size = K._place(pc["frame"], 0.0, y, True)
    out.append(("frame", part, fn))
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
