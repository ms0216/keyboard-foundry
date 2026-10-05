"""cckb-click の蓋の別案 B2（左右のばねの腕で掛ける蓋）の試し刷り（projects/cckb-click/click_cover_snap.py・docs/coupon-cover-snap.md）。

**生成した立体そのもの**を重ねる・動かす・切って見る。各検査に「故意に壊すと落ちる」を入れる。
外の事実: 本番の枠の立体（B2 の枠は、その角から作る）・クリップの図面から作った立体（click_case.clip_solid）・**配線済みの基板のファイル**（クリップと H15 を
動かす先に何があるか）・TDS の材料の値（spec.PLA_*）・スライスした G-code（tools/slice_cover_snap.py が見る）。
本番の枠を作るので、全部 slow。**本番の蓋・枠・基板を変えていないこと**は、既存の検査（test_cckb_click_case・_board）がそのまま通ることで見る。
"""

import math
import re
import sys

import pytest
from build123d import Pos

from conftest import ROOT

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
import click_case as C  # noqa: E402
import click_cover_snap as B  # noqa: E402

LAY, S = C.LAY, C.S
vol = B.vol
TOL = 2e-3
pytestmark = pytest.mark.slow
GAP_VIAS = [(108.375, -42.625), (109.375, -48.625)]                 # 手前の面の左右の隙間の床に見える、基板のビア（配線済みの基板から数えた物）
BOARD = ROOT / "projects" / "cckb-click" / "pcb" / "cckb-click_main.kicad_pcb"


def released(n=B.MAIN, left=True, right=True):
    """腕を「外す」所まで内へ撓ませた蓋（座った形から）。"""
    rel = B.arm_numbers(n)["release"] - B.VARIANTS[n]["pre"]
    return B.cover(n, False, rel if left else None, rel if right else None)


def board_vias():
    """配線済みの基板のビア [(x, y, 径)]（CAD の座標）。"""
    text = BOARD.read_text()
    out = [(float(m.group(1)) - 150.0, 100.0 - float(m.group(2)), float(m.group(3)))
           for m in re.finditer(r'\(via\s*\(at ([\d.-]+) ([\d.-]+)\)\s*\(size ([\d.]+)\)', text)]
    assert len(out) > 500
    return out


def board_segments():
    """配線済みの基板の線 [(x1, y1, x2, y2, 幅)]（CAD の座標）。"""
    text = BOARD.read_text()
    out = [(float(a) - 150.0, 100.0 - float(b), float(c) - 150.0, 100.0 - float(d), float(w)) for a, b, c, d, w in
           re.findall(r'\(segment\s*\(start ([\d.-]+) ([\d.-]+)\)\s*\(end ([\d.-]+) ([\d.-]+)\)\s*\(width ([\d.]+)\)', text)]
    assert len(out) > 500
    return out


def seg_gap(seg, px, py):
    """点から、線の縁までの距離。"""
    x1, y1, x2, y2, w = seg
    dx, dy = x2 - x1, y2 - y1
    n2 = dx * dx + dy * dy
    k = 0.0 if n2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / n2))
    return math.hypot(px - x1 - k * dx, py - y1 - k * dy) - w / 2


def rect_gap(r, x, y):
    """点から、矩形 (x0, y0, x1, y1) までの距離（中なら 0）。"""
    return math.hypot(max(r[0] - x, 0.0, x - r[2]), max(r[1] - y, 0.0, y - r[3]))


# ---------------------------------------------------------------------------
# 形: 本番の枠の角か・変えたのは口のまわりと H15 だけか
# ---------------------------------------------------------------------------

def test_the_frame_is_the_production_corner_outside_the_mouth_and_h15():
    """口のまわり（MOD）と H15 の座（H15_MOD）の外は、本番の枠の角と同じ立体。手前の壁は、腕の通る窓の上に 高さ 2.0 × 奥行き 3.0 残る（外形は変えない）。
    クリップの空間は DBACK 奥へ伸びる（その奥の屋根は、試し刷りの範囲の端まで詰まっている）。H15 の下穴は動かした先にある。H14 の下穴と、かぎの空洞の間に壁。"""
    prod, mine = B.prod_corner(), B.frame()
    box = C._box(B.MOD, -3.0, 8.0) + C._box(B.H15_MOD, -3.0, 8.0)
    a, b = prod - box, mine - box
    assert a.volume == pytest.approx(b.volume, abs=0.01) and vol(a, b) == pytest.approx(a.volume, abs=0.01)
    pb, mb = prod.bounding_box(), mine.bounding_box()
    for q in ("min", "max"):
        for ax in "XYZ":
            assert getattr(getattr(mb, q), ax) == pytest.approx(getattr(getattr(pb, q), ax), abs=1e-4)
    assert len(mine.solids()) == 1
    for f in ((lambda x: x), B.mx):
        for x in (B.XLIP + 1.0, B.A0 - 1.0):                                    # 窓の上の壁（まぐさ）: 外面から 3.0 まで樹脂
            assert all(mine.is_inside((f(x), B.Y0 + d, B.ZW + 1.0)) for d in (0.05, 1.5, 2.9))
            assert not mine.is_inside((f(x), B.Y0 + 1.5, B.ZW - 0.5))           # 窓
        assert mine.is_inside((f(B.XPK + 0.4), B.Y0 + B.LIP_T - 0.3, 1.5))      # 口の縁
        assert not mine.is_inside((f(B.XPK + 0.4), B.YL + 0.6, 1.5))            # 縁の裏の空洞
        assert not mine.is_inside((f(B.XLIP - 0.5), B.Y0 + 0.2, 1.5))           # 縁の端の 45° の面（爪の入る所）
    back = B.MOD[3]
    for x in (B.CX - 9.0, B.CX, B.CX + 9.0):                                    # クリップの空間の奥の端と、その奥の屋根
        assert not mine.is_inside((x, back - 0.3, 3.5)) and prod.is_inside((x, back - 0.3, 3.5))
        assert all(mine.is_inside((x, y, 3.5)) for y in (back + 0.2, back + 0.9, B.BOX[3] - 0.15))
    assert back == pytest.approx(LAY.clip_body()[3] + S.PART_CLEAR + B.DBACK, abs=0.02) and B.BOX[3] - back > 1.6
    assert not mine.is_inside((B.H15_NEW[0], B.H15_NEW[1], 1.0)) and mine.is_inside((B.H15_NEW[0], B.H15_NEW[1], 3.5))
    assert prod.is_inside((B.H15_NEW[0], B.H15_NEW[1], 1.0)) and not prod.is_inside((B.H15_OLD[0], B.H15_OLD[1], 1.0))
    assert not mine.is_inside((104.0, -48.225, 1.0)) and mine.is_inside((B.XPK - 0.4, -48.225, 1.5))    # H14 と、その壁
    n = B.numbers()
    assert n["h14_wall"] == pytest.approx(0.8, abs=1e-6) and n["h15_wall"] == pytest.approx(0.8, abs=1e-6)
    notch = LAY.psw_notch()                                                     # つまみの切り欠きは、変えた範囲の外
    assert min(p[0] for p in notch) > B.H15_MOD[2]
    assert vol(Pos(0.5, 0, 0) * a, b) < a.volume - 3.0                          # 壊す: 0.5 ずれた枠なら同じにならない


def test_the_board_proposal_against_the_routed_board():
    """基板は変えていない（H15 は 136.5・クリップは CLIP_AT）。**提案の先に、配線済みの基板の何があるか**を、ファイルから数える（文書の表の根拠）:
      H15 → (140.0, −48.225): 穴の縁 ＋ 0.5 以内に線は無い・ビアが 1 つ掛かる。右の壁のつまみの切り欠きと、電源スイッチのランドから 3 以上
      クリップを奥へ DBACK: 電池の下の銅の逃げの奥の端が −31.665 → −29.665 になる。その間（x 113.5〜130.5）にビアが 3 つ（y = −30.625）。
        その奥のビアの列（y = −29.1）と VBAT_SW の線（y = −28.35）には掛からない（0.2・1.0 以上）。2.3 を超えて動かすと、ビアの列に掛かる
      動かした＋のランドと、まわりのビアの隙は 0.2 以上
    いまの H15 は、右の腕の通り道の中にある = B2 は、いまの基板のままでは作れない。"""
    assert dict((n, c) for n, c, _ in LAY.screws())["H15"] == (136.5, -48.225) and B.H15_NEW == (140.0, -48.225)
    assert S.CLIP_AT == (122.0, -41.425) and B.DBACK == 2.0
    vias, segs = board_vias(), board_segments()
    hx, hy = B.H15_NEW
    keep = S.SCREW_HOLE_D / 2 + 0.5
    assert min(seg_gap(s, hx, hy) for s in segs) > keep
    assert min(seg_gap(s, segs[0][0], segs[0][1]) for s in segs) < 0.0           # 壊す: 線のある所では数える
    assert [v for v in vias if math.hypot(v[0] - hx, v[1] - hy) - v[2] / 2 < keep] == [(pytest.approx(139.375), pytest.approx(-48.625), 0.6)]
    assert min(math.hypot(p[0] - hx, p[1] - hy) for p in LAY.psw_notch()) - S.SCREW_HOLE_D / 2 > 3.0
    assert rect_gap(LAY.psw_pads(), hx, hy) - S.SCREW_HOLE_D / 2 > 3.0
    lane = (B.mx(B.XN + B.T_MAX), B.mx(B.XLIP))                                  # 右の腕の通り道（窓の、縁の側）
    assert lane[0] < B.H15_OLD[0] + S.SCREW_PILOT_D / 2 and B.H15_OLD[0] - S.SCREW_PILOT_D / 2 < lane[1]
    ko = LAY.cell_keepout()                                                      # (x0, y0, x1, y1)
    new_back = ko[3] + B.DBACK
    inside = sorted((round(v[0], 3), round(v[1], 3)) for v in vias if ko[0] < v[0] < ko[2] and ko[3] - v[2] / 2 < v[1] < new_back + v[2] / 2)
    assert inside == [(115.375, -30.625), (121.375, -30.625), (127.375, -30.625)]
    row = [v for v in vias if ko[0] < v[0] < ko[2] and abs(v[1] + 29.1) < 0.01]
    assert len(row) == 3 and all(v[1] - v[2] / 2 - new_back > 0.2 for v in row) and row[0][1] - row[0][2] / 2 - (ko[3] + 2.3) < 0.2
    trunk = [s for s in segs if abs(s[1] + 28.35) < 0.01 and abs(s[3] + 28.35) < 0.01 and min(s[0], s[2]) < ko[0] and max(s[0], s[2]) > ko[2]]
    assert len(trunk) == 1 and (-28.35 - trunk[0][4] / 2) - new_back > 1.0
    for pad in (B.PAD, (B.mx(B.PAD[2]), B.PAD[1], B.mx(B.PAD[0]), B.PAD[3])):
        assert min(rect_gap(pad, v[0], v[1]) - v[2] / 2 for v in vias) > 0.2


def test_nothing_overlaps_at_rest_and_nothing_sticks_out():
    """座った位置で、蓋 3 つとも、枠・当て板・クリップ・電池・電源スイッチ・コンデンサと重ならない。枠も同じ。
    蓋の真ん中は枠の上面と面一・手前の面は外面の 0.1 以上 内。**クリップが公差の端（± CLIP_TOL）へずれても、蓋と枠に当たらない**・
    蓋は、クリップの板の上に掛からない（クリップの上面が公差の端 4.35 でも、蓋とは関係が無い）。"""
    fr, base, cell, clip = B.frame(), B.base(), B.cell(), B.clip()
    parts = C.board_parts()
    others = (base, clip, parts["SW_PWR"], parts["C_BAT"])
    for other in others + (cell,):
        assert vol(fr, other) < TOL
    shifted = [B.clip(dx, dy) for dx in (-S.CLIP_TOL, S.CLIP_TOL) for dy in (-S.CLIP_TOL, S.CLIP_TOL)]
    assert all(vol(fr, c) < TOL for c in shifted)
    body = LAY.clip_body()
    over_clip = C._box((body[0], B.CLIP_FRONT - S.CLIP_TOL, body[2], body[3] + B.DBACK), S.CELL_T + 0.05, 9.0)
    for n in B.VARIANTS:
        cv = B.cover(n, True)
        for other in (fr, cell) + others + tuple(shifted):
            assert vol(cv, other) < TOL, n
        assert vol(cv, over_clip) < 1e-6
        bb = cv.bounding_box()
        assert bb.max.Z == pytest.approx(B.TOP, abs=1e-4) and bb.min.Z == pytest.approx(0.0, abs=1e-4)
        assert bb.min.Y >= B.Y0 + 0.1 - 1e-6
        assert B.XPK < bb.min.X and bb.max.X < B.mx(B.XPK)
        assert len(cv.solids()) == 1 and len(B.printed(n).solids()) == 1
    assert vol(B.posed(B.cover(B.MAIN, True), dz=0.4), fr) > 0.05              # 壊す: 0.4 持ち上げると枠に重なる
    assert vol(B.cover(B.MAIN, True), B.clip(0.0, -0.6)) > 1e-3                # 壊す: クリップが 0.6 手前なら、蓋に当たる


# ---------------------------------------------------------------------------
# 座った蓋は動かない・電池は出ない
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", sorted(B.VARIANTS))
def test_the_seated_cover_cannot_move(n):
    """左右のかぎが掛かった蓋は、手前へ 0.1・上へ 0.25 より動けない（0.05 ずつ動かして、枠・当て板・クリップに当たるまで）。
    奥へは、腕が 45° の面に乗って撓む分だけ押し込める: 腕を 0.3 内へ逃がした蓋で 0.1〜0.2・そのとき電池に当たらない。
    左右は、同じ蓋で胴の遊びを測る: 0.05〜0.15。内へ倒れない（手前の下の縁を軸に ±3° 回すと当たる）。"""
    cv, ob = B.cover(n, False), B.obstacles()
    assert B.hit(cv, ob) < TOL
    assert B.travel(cv, ob, (0, -1, 0)) <= 0.1 + 1e-9
    assert B.travel(cv, ob, (0, 0, 1), limit=1.0) <= 0.25 + 1e-9
    assert B.travel(cv, ob, (0, 1, 0), limit=1.0) <= 0.05 + 1e-9             # 座った形のままでは、奥へも進めない（腕の先が 45° の面に乗る）
    slack = B.cover(n, False, 0.3, 0.3)
    assert 0.1 - 1e-9 <= B.travel(slack, B.obstacles(with_cell=True), (0, 1, 0), limit=1.0) <= 0.2 + 1e-9
    for sx in (-1, 1):
        assert 0.05 - 1e-9 <= B.travel(slack, ob, (sx, 0, 0), limit=1.0) <= 0.15 + 1e-9
    for rx in (3.0, -3.0):
        assert B.hit(B.posed(cv, rx=rx, pivot=(B.CX, B.YF, 0.0)), ob) > TOL


def test_breaking_the_catch_lets_the_cover_out():
    """壊す: 口の縁の無い枠・かぎの無い蓋なら、手前へ 2 以上進める（上の検査が、掛かりを見ている）。"""
    cv = B.cover(B.MAIN, False)
    assert B.travel(cv, B.obstacles(lips=False), (0, -1, 0)) >= 2.0
    assert B.travel(B.cover(B.MAIN, False, hook=0.0), B.obstacles(), (0, -1, 0)) >= 2.0


def test_the_cell_cannot_get_out_and_cannot_touch_copper():
    """蓋を掛けたら、電池の代わりは手前へ 0.3 より進めない（斜め手前も）。蓋を外せば、手前へ 15 以上、何にも当たらない。
    裸の銅: −のランド（φ7・クリップの中心）は電池の真下で、電池の縁から 3.9 以上 内。手前の面の左右の隙間（腕と胴の間）は、付け根の塊で行き止まり。
    その床に見える基板のビアは 2 つ（どちらも GND の縫い付け）。＋のランドは、蓋の柱の内側（隙間からは、柱の向こう）。"""
    fr, base = B.obstacles()[0], B.base()
    cell = B.cell()
    blk = (fr, base, B.cover(B.MAIN, False))
    assert B.hit(cell, blk) < TOL
    kw = dict(pivot=(0.0, 0.0, 0.0))
    fwd = B.travel(cell, blk, (0, -1, 0), **kw)
    assert 0.15 <= fwd <= 0.3
    for sx in (-1, 1):
        assert B.travel(cell, blk, (0.5 * sx, -1, 0), **kw) <= 0.45
    assert B.travel(cell, (fr, base), (0, -1, 0), step=0.5, limit=16.0, **kw) >= 15.0
    assert B.travel(cell, blk, (0, 0, 1), limit=2.0, **kw) <= 1.2            # 上は、蓋の帯（当て板にクリップの板の代わりは無い）
    neg = (S.CLIP_AT[0], S.CLIP_AT[1] + B.DBACK, 3.5)                        # 動かした −のランド（中心, 半径。基板の BT1 の 2 番: φ7）
    assert B.CELL_R - (math.hypot(neg[0] - B.CX, neg[1] - B.CY) + neg[2]) > 3.9
    cv = B.cover(B.MAIN, False)
    t = B.VARIANTS[B.MAIN]["t"]
    for y in (B.YF + 1.0, -45.0, B.YWB, B.YR - 1.0):                         # 隙間の中は空・その内側は柱（蓋）
        xm = (B.XN + t + B.body_edge(y)) / 2
        assert not cv.is_inside((xm, y, 1.4)) and cv.is_inside((B.body_edge(y) + 0.3, y, 1.4))
    assert cv.is_inside(((B.XN + B.XSI) / 2, (B.YR + B.YJ) / 2, 1.4))        # 行き止まり（付け根の塊）
    assert B.PAD[0] - B.XSI == pytest.approx(S.PART_CLEAR)                   # ＋のランドは、柱の内の面の 0.4 内
    in_gap = sorted((round(v[0], 3), round(v[1], 3)) for v in board_vias() for f in ((lambda x: x), B.mx)
                    if B.YF < v[1] < B.YR and B.XN + t - v[2] / 2 < f(v[0]) < B.body_edge(v[1]) + v[2] / 2)
    assert in_gap == GAP_VIAS, in_gap


def test_engagement_is_one_mm_and_survives_tolerance():
    """かぎと縁の掛かり（立体から測る）: 3 つとも 1.0 以上。誤差を全部悪い側に取った見込み（計算）が 0.6 以上。
    壊す: かぎの出 0.5 の蓋は 0.4 に届かない。"""
    for n in B.VARIANTS:
        e = B.engagement(n)
        assert min(e) >= 1.0 and max(e) <= B.ENGAGE + 1e-6, (n, e)
        a = B.arm_numbers(n)
        assert a["engage"] >= 1.0 and a["engage_worst"] >= 0.6 - 1e-9 and a["engage_flat"] >= 0.6
    assert 0.1 < max(B.engagement(B.MAIN, hook=0.5)) < 0.4


# ---------------------------------------------------------------------------
# 外す・入れる
# ---------------------------------------------------------------------------

def test_release_needs_both_arms_and_one_arm_springs_back():
    """両方の腕をつまめば、蓋は手前へ 15 以上まっすぐ抜ける。**片方だけ**（腕を、外す所まで実際に撓ませた形）では: まっすぐは 0.1 まで。
    平面の中で、ずらす・回すを探しても、つまんだ側のかぎの所が手前へ出るのは、**かぎの角の斜め（HOOK_CH）より 0.05 以上 小さい** =
    手を離すと、かぎは斜めの面で縁の角に乗り、腕のばねが蓋を引き戻す（外れたままにならない）。
    その姿勢で、手を離した形（座った腕）は縁に重なる = そこでは止まれない。電池の代わりは 1.0 より手前へ進めない。
    壊す: 両方をつまんだ蓋なら、同じ探し方が 60 歩で 1.5 以上出す・角の斜めが 0.1 しか無ければ、出る量の方が大きい。"""
    obc = B.obstacles(with_cell=True)
    assert B.travel(released(), obc, (0, -1, 0), step=0.5, limit=16.0) >= 15.0
    ob = B.obstacles()
    for left in (True, False):
        assert B.travel(released(left=left, right=not left), ob, (0, -1, 0)) <= 0.1 + 1e-9
    found = B.one_arm_out(B.MAIN)
    worst = max(v[0] for v in found.values())
    assert 0.05 < worst <= B.HOOK_CH - 0.05, worst
    assert worst > 0.1                                                           # 壊す: 角の斜めが 0.1 なら足りない
    out, pose = found[0.0]
    assert B.hit(B.posed(B.cover(B.MAIN, False), **pose), ob) > TOL
    blk = (ob[0], ob[1], B.posed(released(left=True, right=False), **pose))
    assert B.travel(B.cell(), blk, (0, -1, 0), pivot=(0.0, 0.0, 0.0)) <= 1.0
    loose, _ = B.wiggle(released(), ob, lambda p: B.corner_out(p, B.XLIP + 1.0), iters=60)
    assert loose >= 1.5, loose


def test_insert_path_self_aligns_and_needs_the_arms_to_give():
    """入れる道: 手前 14 から座った位置まで、腕を「外す」所まで内へ動かせば、どこでも枠・当て板・クリップ・電池に当たらない。
    かぎが縁の中にいる間（手前へ 0.5〜1.5）は、腕が座った形のままでは通れない = 腕が撓んで入る（カチッ）。最後は、座った形で収まる。
    **自分で真ん中に寄る**: 横へ 0.3 ずれていても、真ん中の塊の奥の角が口に入り始める所で当たらない（角を LEAD 落としてある）。
    壊す: その先（斜めを過ぎた所）では、0.3 ずれたままだと当たる。"""
    obc = B.obstacles(with_cell=True)
    rel, asm = released(), B.cover(B.MAIN, False)
    for k in range(29):
        dy = -14.0 + 0.5 * k
        assert B.hit(B.posed(rel, dy=dy), obc) < TOL, dy
    for dy in (-1.5, -1.0, -0.5):
        assert B.hit(B.posed(asm, dy=dy), obc) > TOL, dy
    assert B.hit(asm, obc) < TOL
    enter_block = -(B.YB - B.Y0) + 0.15                    # 真ん中の塊の奥の面が、枠の外面を 0.15 過ぎた所
    for sx in (-1, 1):
        assert B.hit(B.posed(rel, dx=0.3 * sx, dy=enter_block), obc) < TOL
        assert B.hit(B.posed(rel, dx=0.3 * sx, dy=enter_block + B.LEAD + 0.3), obc) > TOL


# ---------------------------------------------------------------------------
# 数
# ---------------------------------------------------------------------------

def test_arm_strain_force_and_seat():
    """腕: 外すとき・入れるときの付け根のひずみが、この機種の上限（spec.PLA_STRAIN_USE × PLA_BEND / PLA_E = 1.52 %）以内。胴に当たって止まるときも、
    曲げ強さのひずみ（2.76 %）の 0.7 倍以内。線 2 本（0.84）以上の厚さ。つまむ力 0.8〜3 N。
    **座りの力**（腕 2 本が 45° の面を押して、蓋をかぎの当たる向きへ押す）: 名目で 0.15 N 以上（摩擦を引いて）= 蓋の重さの 15 倍以上。
    予圧が誤差ぶん小さく刷れても、0 にならない。かぎの角の斜めは、縁とかぎの位置の誤差を引いても残る（押し切る手前から、ばねが引き込む = カチッと入る）。落下で、かぎが自分の重さで外れるまで 2 倍以上。
    壊す: 厚さ 1.2 の腕なら、ひずみが上限を超える。"""
    mass = B.numbers()["mass"]
    for n, v in B.VARIANTS.items():
        a = B.arm_numbers(n)
        assert a["strain_use"] == pytest.approx(S.PLA_STRAIN_USE * S.PLA_BEND / S.PLA_E * 100)
        assert a["strain_insert"] < a["strain_release"] <= a["strain_use"], (n, a["strain_release"])
        assert a["strain_stop"] <= 0.7 * a["strain_limit"]
        assert v["t"] >= 0.84 and 0.8 <= a["pinch"] <= 3.0
        assert a["seat_y"][0] >= 0.15 and a["seat_y"][0] / (mass * 9.80665e-3) >= 15.0
        assert a["seat_y_ends"][0][0] > 0.03 and v["pre"] - B.PRINT_ERR > 0.0
        assert a["click_margin"] >= 0.05 and B.CELL_GAP > B.BACK_CL
        assert a["drop_margin"] >= 2.0
        assert a["stop"] >= a["release"] + 0.05 and a["length"] == pytest.approx(B.YR - B.YF)
        assert 1.5 * 1.2 * a["release"] / a["length"] ** 2 * 100 > a["strain_use"]
    need = math.sqrt(1.5 * 0.85 * (1.0 + 0.15) / (S.PLA_STRAIN_USE * S.PLA_BEND / S.PLA_E))      # 腕の長さの根拠（B と同じ）
    room = LAY.clip_pads()[0][1] - S.PART_CLEAR - B.YF
    assert need > 9.5 and room < 7.0 and B.ARM_L > need
    n = B.numbers()
    assert n["grip"] >= 0.85 and n["grip_open"] >= 0.9                           # 爪の掛かる面の奥行き・手前の面での入り口の幅


def test_every_part_of_the_load_path_is_under_half_strength_at_20_n():
    """電池が**くぼみの真ん中**で当たる（いちばん悪い当たり方）ときに、指で強く押す 20 N（仮定）で: 板の手前の縁の引っ張りが TDS の引っ張り強さの半分以内・
    板の奥の縁・柱・腕が、曲げ強さの半分以内。強さに届く力は、どこも 35 N 以上（= 電池 1.8 g の慣性に直すと 1900 G 以上。**導いた値で、要求ではない**）。
    本番の蓋（A）と同じ力で比べて、板の引っ張りが A 以下。断面は立体から測った物（名目の計算と 5 % 以内で合う）。
    壊す: クリップを動かす前の板の厚さ（B の 1.27）なら、同じ式で 20 N の応力が強さの半分を超える。"""
    n = B.numbers()
    st = B.stresses(B.MAIN, B.PUSH, True)
    assert st["plate"]["tension"] <= 0.5 * S.PLA_TENSILE and st["plate"]["compression"] <= 0.5 * S.PLA_BEND
    assert st["stem"]["stress"] <= 0.5 * S.PLA_BEND and st["arm"]["stress"] <= 0.5 * S.PLA_BEND and st["arm"]["load"] < st["arm"]["buckle"] / 3
    assert st["hook"] < 0.1 * S.PLA_TENSILE and st["lip"] < 0.1 * S.PLA_BEND
    assert B.stresses(B.MAIN, B.PUSH, False)["plate"]["tension"] < st["plate"]["tension"]
    sf = n["strength"]
    assert min(sf.values()) >= 35.0 and n["weakest"][1] == pytest.approx(min(sf.values()))
    assert n["weakest_g"] == pytest.approx(min(sf.values()) / (S.CELL_MASS * 9.80665e-3)) and n["weakest_g"] > 1900.0
    for key in ("plate_tension", "plate_compression", "stem"):                  # 強さに届く力で計算し直すと、強さになる
        back = B.stresses(B.MAIN, sf[key], True)
        got = {"plate_tension": back["plate"]["tension"] / S.PLA_TENSILE, "plate_compression": back["plate"]["compression"] / S.PLA_BEND,
               "stem": back["stem"]["stress"] / S.PLA_BEND}[key]
        assert got == pytest.approx(1.0, rel=1e-6)
    assert B.stresses(B.MAIN, sf["arm"], True)["arm"]["stress"] == pytest.approx(S.PLA_BEND, rel=1e-3)
    a = C.cover_beam()
    assert st["plate"]["tension"] / B.PUSH <= a["tension"] / C.cover_numbers()["cell_force"]
    mid = dict(B.plate_sections(B.MAIN))[B.CX]
    pk = n["pocket"]
    assert mid["area"] == pytest.approx(pk["plate_t"] * B.STRIP_Z + (B.YB - B.YF) * (B.TOP - B.STRIP_Z), rel=0.05)
    assert pk["plate_t"] > 3.0 and pk["center_gap"] > B.CELL_GAP + 0.05
    thin = 1.27                                                                  # 壊す: B の板（帯なしの、いちばん甘い見積もりでも）
    assert st["plate"]["moment"] * (thin / 2) / (B.TOP * thin ** 3 / 12) > 0.5 * S.PLA_BEND


def test_the_wall_left_over_the_side_windows_is_stiff_enough():
    """腕の通る窓の上に残る手前の壁（高さ 2.0 × 奥行き 3.0・張り出し 5.6）: 先を上から 10 N で押しても、下がりは蓋との隙（0.2）より小さく、
    付け根の応力は曲げ強さの半分以内（奥の屋根とのつながりを数えない、弱い側の計算）。壊す: 高さ 0.7（クリップの上の屋根と同じ）なら、蓋に載る。"""
    q = B.lintel()
    assert q["section"] == pytest.approx((3.0, 2.0)) and q["length"] == pytest.approx(B.A0 - B.XLIP)
    assert q["drop"] < q["gap"] and q["stress"] <= 0.5 * S.PLA_BEND
    assert 10.0 * q["length"] ** 3 / (3 * S.PLA_E * 3.0 * 0.7 ** 3 / 12) > q["gap"]


# ---------------------------------------------------------------------------
# 刷れるか・見分け
# ---------------------------------------------------------------------------

def test_printable_without_support():
    """蓋（底をベッドに・刷る形）: 下に何も無い所は、電池の上に渡る帯（くぼみの上・左右の足の間）だけ。枠（上面をベッドに）: 上を向いた面の高さが、
    本番の角に無い物を足していない。板は A1 mini に載る・6 個。"""
    cv = B.printed(B.MAIN)
    (px, py), hw = B.pocket_center()
    for z in (0.3, 1.0, 2.0, B.HS, B.STRIP_Z, 4.2):
        slab = cv & C._box((B.XPK - 1.0, B.Y0 - 1.0, B.mx(B.XPK) + 1.0, B.YJ + 1.0), z + 0.001, z + 0.099)
        hang = Pos(0, 0, -0.1) * slab - cv
        v = 0.0 if hang is None else hang.volume
        if z == B.STRIP_Z:
            bb = hang.bounding_box()
            assert v > 0.3 and bb.size.X <= 2 * hw + 0.3 and bb.min.Y >= py - B.POCKET_R - 0.05 and bb.max.Y <= B.YB + 0.01
        else:
            assert v < 1e-3, (z, v)

    def up_levels(part):
        out = set()
        for f in part.faces():
            try:
                if f.normal_at(f.center()).Z > 0.9:
                    out.add(round(f.center().Z, 2))
            except Exception:                                    # 曲面（穴の壁）は、上を向いた平らな面ではない
                pass
        return out

    assert up_levels(B.frame()) <= up_levels(B.prod_corner())
    size = B.plate().bounding_box().size
    assert max(size.X, size.Y) <= S.PRINT_MAX and len(B.plate_layout()) == 6


def test_covers_are_told_apart_by_notches():
    """蓋 n は、上の板の奥の縁に切り欠きが n つ。"""
    mw, md, mp = B.MARK
    x1 = B.A1 - B.CL - 1.2
    for n in B.VARIANTS:
        cv = B.cover(n, True)
        got = sum(not cv.is_inside((x1 - i * mp - mw / 2, B.YB - md / 2, 4.5)) for i in range(4))
        assert got == n
