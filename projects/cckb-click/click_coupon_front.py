"""cckb-click の「手前の縁を細くする」試し刷り（**刷る物だけ。本番の枠・基板は変えない**）。docs/coupon-front.md。

    .venv/bin/python3 projects/cckb-click/click_coupon_front.py        # STL と絵を build/cckb-click/ に
    .venv/bin/python3 projects/cckb-click/tools/slice_front.py         # スライスして G-code を検査 → coupon_front_plate_n04.gcode.3mf

何を試すか（検討の絵 build/cckb-click/study/front_wall_*.png の「案 B」）: 手前の壁のねじをやめ、枠の手前の壁を基板の手前の縁の外へ
下ろして、先の小さな出っ張り（爪）を基板の下へ回す。基板は手前の縁を引っ掛けてから倒し、奥（と左右）をねじで留める。
手前の縁（キー領域の端から枠の外面まで）は 3.0 → 0.8 か 0.4 になる。**爪が刷れるか・基板を保てるかは、刷らないと分からない**
（この機種では、計算で成り立った留め方が 4 回、刷ると使えなかった）。だから基板を変える前に、これだけ刷る。

刷る物（1 枚）:
  枠の切れ端 2 つ   本番の枠（click_case.frame_full）の手前の段の Alt（1u）・Meta（1.5u）・Space（2.25u）を切り出し、手前の壁だけを作り替えた物。
                    手前の縁 0.8 と 0.4。奥は、本番の外周の壁と同じ断面の壁（試し刷りだけの物）に下穴 φ1.6 が 3 つ
  基板の代わり 3 枚  厚さ 1.4・1.6・1.8（基板の厚さの公差 1.44〜1.76 を、層の倍数で外から挟む）。手前の縁は案 B の位置。スイッチの代わり 3 つ付き。
                    **2 つの枠に同じ板が合う**（0.4 の枠は、奥のねじを 0.4 奥へ寄せてある）
  キャップ 3 個      本番の形（1u・1.5u・2.25u）

**寸法は、ここの定数（試し刷りだけの値）と spec.py。**本番に入れると決めたら spec.py へ移す。座標は本番と同じ（CAD・基板の上面 = 0）。
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

from build123d import Compound, Cylinder, Pos, Rot, export_stl  # noqa: E402

import click_case as C  # noqa: E402
import click_parts as P  # noqa: E402
from foundry.layout import UNIT  # noqa: E402

LAY, S = C.LAY, C.S
EPS = C.EPS
OUT = C.OUT
TOP = S.FRAME_UNDER + S.FRAME_T
_box, _union = C._box, C._union
TOL = 1e-3

# ---------------------------------------------------------------------------
# 試し刷りだけの値
# ---------------------------------------------------------------------------
MARGINS = (0.8, 0.4)         # 手前の縁（キー領域の端から枠の外面まで）。本番はいま 3.0（spec.PLATE_MARGIN_Y）
KEYS = (56, 57, 58)          # 切り出すキー（基板の SW 番号）: 左 Alt 1u・左 Meta 1.5u・左の Space 2.25u（幅 90.5 の細い手前の縁ができる）
WALL = 0.8                   # 基板の手前の縁の外を下りる壁の厚さ（0.4 ノズルの線 2 本）
GAP = 0.15                   # 壁の内面と基板の手前の縁の隙（名目）
LIP_REACH = 0.6              # 爪が壁の内面から基板の下へ入る量
LIP_SLOPE = 30.0             # 爪の掛かる面の傾き [度]（水平から）。枠は上面をベッドに刷る = 爪は刷る向きのいちばん上で、この面は宙へ張り出す。
#                              0.1 の層で 1 層あたり 0.17 ずつ（線の幅 0.42 の 41 %）外へ出る。水平な面にすると、0.6 の張り出しを支え無しで刷ることになる
LIP_Z0 = -1.72               # 掛かる面が壁の内面で始まる高さ。厚さ 1.8 の板（基板の厚い側 1.76 の外）が、名目の隙で当たらない所
LIP_BOTTOM = -2.2            # 爪の下面（刷る向きではいちばん上の面。ベッドから 7.2 = 層の境目）。基板の下面（名目 −1.6）から 0.6 下
BOARD_TS = (1.4, 1.6, 1.8)   # 基板の代わりの厚さ（1 層目 0.2 ＋ 0.1 の倍数）。切り欠きの数 1・2・3
PRINT_ERR = 0.15             # 刷った物の誤差の見込み（片側）
OUTLINE_TOL = 0.2            # 基板の外形の公差（JLCPCB の外形 ±0.2。spec.PCB_INSET_X の行と同じ値）
MARK = (0.8, 0.5, 1.6)       # 見分ける切り欠き: 幅・深さ・間隔

KS = [k for k in LAY.keys if k.i in KEYS]
A1 = LAY.key_area[1]                       # キー領域の手前の端（−47.625）
HOLE_Y = LAY.hole(KS[0])[1]                # 手前の段の穴の手前の縁（−46.625）
POCKET_Y = HOLE_Y - S.TAB_REACH - S.POCKET_CLEAR          # くぼみの手前の端（穴の縁から 0.6 外）
YC = KS[0].y + UNIT / 2              # 手前の段と、その奥の段の間のリブの中心（−28.575）
X0 = min(k.x0 for k in KS) - LAY.rib() / 2
X1 = max(k.x1 for k in KS) + LAY.rib() / 2
REF = MARGINS[0]                           # 基板の代わりの座標は、この縁の枠に組んだ位置で持つ


def vol(a, b):
    if a is None or b is None:
        return 0.0
    c = a & b
    try:
        return 0.0 if c is None else float(c.volume)
    except (AttributeError, ValueError):
        return 0.0


def geom(m, err=0.0):
    """縁 m の枠の、手前の壁の寸法。err = 壁の内面と爪が、基板の側へずれて刷れた量（＋ = きつい）。"""
    yo = A1 - m
    yi = yo + WALL + err
    drop = LIP_REACH * math.tan(math.radians(LIP_SLOPE))
    return dict(m=m, yo=yo, yi=yi, yb=yo + WALL + GAP, tip_y=yi + LIP_REACH, tip_z=LIP_Z0 - drop, off=REF - m,
                skin=POCKET_Y - yo, rail=HOLE_Y - yo, cap_to_face=HOLE_Y + S.CAP_CLEAR - yo)


def board_edge():
    """基板の代わりの (手前の縁, 奥の縁, ねじ穴の y)。縁 REF の枠に組んだ位置。奥の縁は、本番と同じに穴の中心から SCREW_FROM_EDGE − PCB_INSET_Y。"""
    yb = geom(REF)["yb"]
    pilot = YC + S.PLATE_MARGIN_Y - S.SCREW_FROM_EDGE          # 本番と同じ: キー領域の端（ここではリブの中心）の 0.6 外
    return yb, pilot + S.SCREW_FROM_EDGE - S.PCB_INSET_Y, pilot


def pilots(m):
    """縁 m の枠の、奥の壁の下穴の中心 [(x, y)]（キーの中心の x）。"""
    _, _, py = board_edge()
    return [(k.x, py + geom(m)["off"]) for k in KS]


def back_face(m):
    return pilots(m)[0][1] + S.SCREW_FROM_EDGE


# ---------------------------------------------------------------------------
# 枠の切れ端
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def frame(m, err=0.0, lip=True):
    """縁 m の枠の切れ端（組んだ向き・本番の座標）。
      本番から   click_case.frame_full のキー領域の手前の端〜奥のリブの中心（穴・くぼみ・面取り・継ぎ目の溝・柱）
      作り替え   手前: 上の板を外面まで・基板の縁の外を下りる壁（厚さ WALL）・爪。キーの辺の真ん中に、本番のねじの所と同じ形の「厚い壁」
                 （基板の上に載る所。下穴は無い。Meta の所は本番には無い）
      試し刷りだけ  奥: 本番の外周の壁と同じ断面の壁・キーの中心に下穴 3 つ・外面の縦の溝（0.4 の枠 = 1 本・0.8 = 2 本）"""
    g = geom(m, err)
    real = C.frame_full() & _box((X0, A1, X1, YC), -1.0, TOP + 1.0)
    yt, zt = g["tip_y"], g["tip_z"]
    if lip:
        prof = [(g["yo"], LIP_BOTTOM), (yt, LIP_BOTTOM), (yt, zt), (g["yi"], LIP_Z0), (g["yi"], S.FRAME_UNDER + EPS), (g["yo"], S.FRAME_UNDER + EPS)]
    else:
        prof = [(g["yo"], 0.0), (g["yi"], 0.0), (g["yi"], S.FRAME_UNDER + EPS), (g["yo"], S.FRAME_UNDER + EPS)]
    h = S.SCREW_BOSS_HALF
    parts = [real,
             _box((X0, g["yo"], X1, A1 + EPS), S.FRAME_UNDER, TOP),
             C._prism_x(prof, X0, X1)]
    parts += [_box((k.x - h, g["yo"] + EPS, k.x + h, HOLE_Y), 0.0, S.FRAME_UNDER + EPS) for k in KS]           # 手前の厚い壁（載る所）
    yback = back_face(m)
    parts.append(_box((X0, YC - EPS, X1, yback), 0.0, TOP))
    parts += [_box((k.x - h, YC - LAY.rib() / 2, k.x + h, YC + EPS), 0.0, S.FRAME_UNDER + EPS) for k in KS]    # 奥の厚い壁（本番と同じ: 穴の縁まで）
    d, depth = LAY.pilot()
    cuts = [Pos(x, y, -1.0) * Cylinder(d / 2, depth + 1.0, align=C.CEN_MIN) for x, y in pilots(m)]
    w, dp, pitch = MARK
    n = 1 + MARGINS[::-1].index(m) if m in MARGINS else 0
    cuts += [_box((X0 + 6.0 + i * pitch, yback - dp, X0 + 6.0 + i * pitch + w, yback + 1.0), -1.0, TOP + 1.0) for i in range(n)]
    part = (_union(parts) - _union(cuts)).clean()
    if len(part.solids()) != 1:
        raise RuntimeError(f"手前の縁の試し刷りの枠（{m}）が {len(part.solids())} 個の塊")
    return part


# ---------------------------------------------------------------------------
# 基板の代わり・キャップ
# ---------------------------------------------------------------------------

def standin_dy():
    """スイッチの代わりを、キーの中心からずらす量。板は 2 つの枠で共用で、0.4 の枠では板ごと 0.4 奥へ寄る → その真ん中に置く（どちらの枠でも ±0.2）。"""
    return -sum(geom(m)["off"] for m in MARGINS) / len(MARGINS)


@lru_cache(maxsize=None)
def board(t=S.PCB_T, standins=True, edge=0.0):
    """基板の代わり（厚さ t・上面 = 0・縁 REF の枠に組んだ位置）。手前の縁は案 B の位置、ねじ穴は基板と同じ径。奥の縁の切り欠きの数 = 厚さの順。
    edge = 手前の縁を手前へ出す量（外形の公差を見る検査のため）。"""
    yb, yback, py = board_edge()
    plate = _box((X0, yb - edge, X1, yback), -t, 0.0)
    cuts = [Pos(k.x, py, -t - 1.0) * Cylinder(S.SCREW_HOLE_D / 2, t + 2.0, align=C.CEN_MIN) for k in KS]
    w, dp, pitch = MARK
    n = 1 + BOARD_TS.index(t) if t in BOARD_TS else 0
    cuts += [_box((X1 - 8.0 - i * pitch - w, yback - dp, X1 - 8.0 - i * pitch, yback + 1.0), -t - 1.0, 1.0) for i in range(n)]
    parts = [plate - _union(cuts)]
    if standins:
        parts += [P.standin(P.Cell(k.x, k.y + standin_dy(), S.HOLE_B, standin=S.SW_STEM_TOP), S) for k in KS]
    return _union(parts).clean()


def board_in(m, t=S.PCB_T, standins=True, edge=0.0):
    """縁 m の枠に組んだ位置の、基板の代わり。"""
    return Pos(0, geom(m)["off"], 0) * board(t, standins, edge)


def caps(mode="latched"):
    """キャップ 3 個（本番の形・本番の位置）[立体]。"""
    return [C.cap_pose(k, mode) for k in KS]


def screws(m):
    return _union([Pos(x, y, 0) * v for (x, y) in pilots(m)
                   for v in [_union([Pos(0, 0, -S.PCB_T - S.SCREW_HEAD_H) * Cylinder(S.SCREW_HEAD_D / 2, S.SCREW_HEAD_H, align=C.CEN_MIN),
                                     Pos(0, 0, -S.PCB_T - EPS) * Cylinder(S.SCREW_D / 2, S.SCREW_L + EPS, align=C.CEN_MIN)])]])


# ---------------------------------------------------------------------------
# 入れられるか・外せるか・持ち上がるか（立体を動かして見る）
# ---------------------------------------------------------------------------

def posed(part, m, th, dy):
    """基板の代わりを、上の手前の角（組んだ位置）を軸に th [度] 倒し（奥が下がる）、奥へ dy 引いた姿。枠は動かさない。"""
    yb = geom(m)["yb"]
    return Pos(0, dy, 0) * Pos(0, yb, 0) * Rot(-th, 0, 0) * Pos(0, -yb, 0) * part


def _hook(m, err=0.0):
    """枠の手前の、基板の代わりと当たりうる所だけ（速くするため）。"""
    return frame(m, err) & _box((X0 - 1.0, A1 - 5.0, X1 + 1.0, HOLE_Y + 1.0), -5.0, 1.0)


def insert_path(m, t=S.PCB_T, th_in=10.0, err=0.0, edge=0.0, far=2.0, step=0.05, th_step=1.0):
    """基板の代わりを、th_in 倒したまま手前へ差し込み（奥へ far 引いた所から）、倒した角を戻しながら組んだ位置まで動かす道 [(角度, 奥へ引いた量)]。
    各段で立体が枠に当たらないことを見る。**当たらずに行ける道が無ければ None**（外すのは同じ道の逆）。
      1. 角度 th_in のまま、奥へ far 引いた所から、当たる手前まで差し込む
      2. 角度を th_step ずつ戻す。各角度で、いまの位置から手前へ寄せられるだけ寄せる（当たるなら、奥へ引いて当たらない所を探す）
      3. 角度 0 で、組んだ位置（引いた量 0）に着く"""
    hook = _hook(m, err)
    front = board_in(m, t, False, edge) & _box((X0 - 1.0, A1 - 5.0, X1 + 1.0, HOLE_Y + 6.0), -5.0, 1.0)
    free = lambda th, dy: vol(hook, posed(front, m, th, dy)) < TOL           # noqa: E731
    n = int(round(far / step))
    path, th, i = [], th_in, n
    if not free(th, far):
        return None
    while True:
        while i > 0 and free(th, (i - 1) * step):                        # 手前へ寄せられるだけ寄せる
            i -= 1
        path.append((th, round(i * step, 3)))
        if th <= 0:
            break
        th = max(0.0, th - th_step)
        while not free(th, i * step):                                    # 戻した角度で当たるなら、奥へ引く
            i += 1
            if i > n:
                return None
    return path if path[-1][1] == 0 else None


def lift_play(m, t=S.PCB_T, err=0.0, edge=0.0, step=0.01, limit=1.0):
    """枠の手前を持ち上げたとき、爪が基板の下の角に当たるまでに動く量（立体で測る）。当たらずに limit まで上がれば None = 掛かっていない。
    組んだ位置でもう当たっていれば 0（= 枠が座らない。負の量は play_calc）。"""
    fr = _hook(m, err)
    b = board_in(m, t, False, edge) & _box((X0 - 1.0, A1 - 5.0, X1 + 1.0, HOLE_Y + 6.0), -5.0, 1.0)
    for i in range(int(limit / step) + 1):
        if vol(Pos(0, 0, i * step) * fr, b) > TOL:
            return round(max(0, i - 1) * step, 3)
    return None


def play_calc(t, gap=GAP):
    """同じ量を式で（負 = 組んだ位置で食い込む量）: 爪の掛かる面は、壁の内面から gap 入った所で LIP_Z0 − gap × tan(傾き)。"""
    return -t - (LIP_Z0 - gap * math.tan(math.radians(LIP_SLOPE)))


def tolerances():
    """公差の端での、掛かり（爪が基板の下へ入っている量）と、持ち上がる量 [mm]。式（立体との突き合わせは tests）。
      print   基板の厚さ 1.44〜1.76 と、刷った物の誤差 ± PRINT_ERR だけ
      all     それに基板の外形の公差 ± OUTLINE_TOL を足した物（**試し刷りでは見られない**: 刷った板の縁は基板の縁ではない）"""
    lo, hi = S.PCB_T * 0.9, S.PCB_T * 1.1
    out = {"nominal": dict(engage=LIP_REACH - GAP, play=play_calc(S.PCB_T))}
    for name, e in (("print", PRINT_ERR), ("all", PRINT_ERR + OUTLINE_TOL)):
        out[name] = dict(engage_min=LIP_REACH - GAP - e, engage_max=LIP_REACH - GAP + e,
                         play_max=play_calc(lo, GAP + e), play_min=play_calc(hi, GAP - e), gap_min=GAP - e)
    return out


def rail_section(m, x=None, dy=0.05):
    """手前の縁の断面（Space の穴の、厚い壁とつばの間の x で切る）を**立体から測る**: 面積と、縦の軸まわりの断面二次モーメント（横へ押したときの曲げ）。"""
    k = KS[-1]
    x = k.x + 8.0 if x is None else x
    g = geom(m)
    fr = frame(m)
    n = int(round((HOLE_Y - g["yo"]) / dy))
    rows = []
    for i in range(n):
        y = g["yo"] + (i + 0.5) * dy
        rows.append((y, vol(fr, _box((x - 0.05, y - dy / 2, x + 0.05, y + dy / 2), LIP_BOTTOM - 1.0, TOP + 1.0)) / 0.1))    # 高さの合計 × dy
    area = sum(a for _, a in rows)
    cy = sum(y * a for y, a in rows) / area
    inertia = sum(a * dy * dy / 12 + a * (y - cy) ** 2 for y, a in rows)
    return area, inertia


def numbers():
    """文書と絵に載せる数（ここで測る・計算する）。"""
    out = {"tol": tolerances(), "m": {}}
    span = P.hole_size(C.cell(KS[-1]))[0]                           # Space の穴の幅 = 柱から柱までの、縁が渡る長さ
    for m in MARGINS:
        g = geom(m)
        area, inertia = rail_section(m)
        k = 192 * S.PLA_E * inertia / span ** 3                      # 両端を固めた梁の真ん中を押す固さ [N/mm]
        fr = frame(m)
        bb = fr.bounding_box()
        out["m"][m] = dict(cap_to_face=round(g["cap_to_face"], 3), skin=round(g["skin"], 3), rail=round(g["rail"], 3),
                           board_edge=round(g["yb"], 3), seat=round(HOLE_Y - g["yb"], 3), seat_tab=round(max(0.0, POCKET_Y - g["yb"]), 3),
                           below_board=round(-S.PCB_T - bb.min.Z, 3), below_sheet=round(-S.PCB_T - S.BOTTOM_SHEET_T - bb.min.Z, 3),
                           size=(round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)),
                           rail_area=round(area, 2), rail_k=round(k, 2), rail_push=round(k * GAP, 2), span=round(span, 2),
                           play={t: lift_play(m, t) for t in BOARD_TS},
                           path={t: insert_path(m, t) for t in BOARD_TS})
    return out


# ---------------------------------------------------------------------------
# 1 枚に並べる
# ---------------------------------------------------------------------------

def pieces():
    """[(記号, 名前, 種類, 組んだ向きの立体)]。記号は絵と docs/coupon-front.md と同じ。"""
    out = [(f"F{int(round(m * 10)):02d}", f"枠の切れ端・手前の縁 {m}", "frame", frame(m)) for m in MARGINS]
    out += [(f"B{i + 1}", f"基板の代わり・厚さ {t}", "board", board(t)) for i, t in enumerate(BOARD_TS)]
    out += [(f"C{i + 1}", f"キャップ {k.w:g}u", "cap", C.cap_shape(k.w)) for i, k in enumerate(KS)]
    return out


@lru_cache(maxsize=None)
def plate_layout(gap=4.0):
    """[(記号, 名前, 種類, 置いた立体, 写す関数)]。手前から キャップ 3 個・基板の代わり 3 枚・枠 2 つ（**枠は上面をベッドに** = 爪がいちばん上）。
    長い辺が X。写す関数は、組んだ向きの点 (x, y, z) を、板の上の点へ写す（スライスした線と突き合わせるため）。"""
    out, y, x, row = [], 0.0, 0.0, 0.0
    order = {"cap": 0, "board": 1, "frame": 2}
    for tag, name, kind, part in sorted(pieces(), key=lambda q: order[q[2]]):
        bb = part.bounding_box()
        if kind == "cap":                                                 # 1 列に左から
            placed = Pos(x - bb.min.X, -bb.min.Y, -bb.min.Z) * part
            fn = (lambda p, bb=bb, x=x: (p[0] - bb.min.X + x, p[1] - bb.min.Y, p[2] - bb.min.Z))
            x, row = x + bb.size.X + gap, max(row, bb.size.Y)
        else:
            if row:
                y, row = row + gap, 0.0
            if kind == "frame":                                           # 上面をベッドに（x はそのまま・y と z が裏返る）
                placed = Pos(0, y, 0) * P.flip_to_bed(part)
                fn = (lambda p, bb=bb, y=y: (p[0] - bb.min.X, bb.max.Y - p[1] + y, bb.max.Z - p[2]))
            else:
                placed = Pos(-bb.min.X, y - bb.min.Y, -bb.min.Z) * part
                fn = (lambda p, bb=bb, y=y: (p[0] - bb.min.X, p[1] - bb.min.Y + y, p[2] - bb.min.Z))
            y += bb.size.Y + gap
        out.append((tag, name, kind, placed, fn))
    return tuple(out)


def plate():
    return Compound([p for _, _, _, p, _ in plate_layout()])


def probes(m):
    """スライスした線を数える所（縁 m の枠・組んだ向きの座標）{名前: (x, y0, y1, z)}。x は Space の穴の、厚い壁とつばの間（wall・lip・rail）と、
    つばのくぼみの真ん中（skin）。y0〜y1 は、そこに樹脂があるはずの範囲。"""
    g = geom(m)
    k = KS[-1]
    xm = k.x + 8.0
    xt = LAY.hole(k)[0] + 1.5
    return {"wall": (xm, g["yo"], g["yi"], -1.0),                                # 基板の縁の外を下りる壁（厚さ WALL）
            "lip": (xm, g["yo"], g["tip_y"], LIP_BOTTOM + 0.05),                 # 爪のいちばん下の層（刷る向きではいちばん上）
            "skin": (xt, g["yo"], POCKET_Y, S.FRAME_UNDER + 0.5),                # くぼみの外の皮
            "rail": (xm, g["yo"], HOLE_Y, TOP - 1.0)}                            # 穴の手前の縁（上の板）


def export(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    part = plate()
    size = part.bounding_box().size
    assert max(size.X, size.Y) <= S.PRINT_MAX, f"coupon_front_plate: {size.X:.1f} × {size.Y:.1f} が A1 mini に置けない"
    export_stl(part, str(out / "coupon_front_plate.stl"))
    return {"coupon_front_plate": (size.X, size.Y, size.Z)}


def main():
    import click_coupon_front_figs as figs

    for stem, size in sorted(export().items()):
        print(f"OK {stem}.stl  {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}")
    num = numbers()
    print("公差", num["tol"])
    for m, row in num["m"].items():
        print("縁", m, row)
    for p in figs.render_all(OUT, num):
        print("絵", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
