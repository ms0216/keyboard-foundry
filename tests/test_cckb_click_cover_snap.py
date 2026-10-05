"""cckb-click の蓋の別案 B（左右のばねの腕で掛ける蓋）の試し刷り（projects/cckb-click/click_cover_snap.py・docs/coupon-cover-snap.md）。

**生成した立体そのもの**を重ねる・動かす・切って見る。各検査に「故意に壊すと落ちる」を入れる。
外の事実: 本番の枠の立体（B の枠は、その角から作る）・クリップの図面から作った立体（click_case.clip_solid）・配線済みの基板のファイル（H15 を動かす先に
線が無いこと）・TDS の材料の値（spec.PLA_*）・スライスした G-code（tools/slice_cover_snap.py が見る）。
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


def released(n=B.MAIN, left=True, right=True):
    """腕を「外す」所まで動かした蓋。"""
    rel = B.arm_numbers(n)["release"]
    return B.cover(n, False, rel if left else None, rel if right else None)


# ---------------------------------------------------------------------------
# 形: 本番の枠の角か・変えたのは口のまわりと H15 だけか
# ---------------------------------------------------------------------------

def test_the_frame_is_the_production_corner_outside_the_mouth_and_h15():
    """口のまわり（MOD）と H15 の座（H15_MOD）の外は、本番の枠の角と同じ立体。手前の壁は、腕の通る窓の上に 2.0 残る（外形は変えない）。
    H15 の下穴は動かした先にあり、いまの位置は埋まっている。H14 の下穴と、かぎの空洞の間に壁がある。"""
    prod, mine = B.prod_corner(), B.frame()
    box = C._box(B.MOD, -3.0, 8.0) + C._box(B.H15_MOD, -3.0, 8.0)
    a, b = prod - box, mine - box
    assert a.volume == pytest.approx(b.volume, abs=0.01) and vol(a, b) == pytest.approx(a.volume, abs=0.01)
    pb, mb = prod.bounding_box(), mine.bounding_box()
    for q in ("min", "max"):
        for ax in "XYZ":
            assert getattr(getattr(mb, q), ax) == pytest.approx(getattr(getattr(pb, q), ax), abs=1e-4)
    assert len(mine.solids()) == 1
    for f in ((lambda x: x), B.mx):                                         # 窓の上の壁（まぐさ）: 外面から 3.0 まで樹脂
        assert all(mine.is_inside((f(B.XLIP + 1.0), B.Y0 + d, B.ZW + 1.0)) for d in (0.05, 1.5, 2.9))
        assert all(mine.is_inside((f(B.A0 - 1.0), B.Y0 + d, B.ZW + 1.0)) for d in (0.05, 1.5, 2.4))      # クリップの空間に面した所は、奥行き 2.45（本番と同じ）
        assert not mine.is_inside((f((B.XLIP + B.A0) / 2), B.Y0 + 1.5, B.ZW - 0.5))      # 窓
        assert mine.is_inside((f(B.XPK + 0.4), B.Y0 + B.LIP_T - 0.3, 1.5))               # 口の縁
        assert not mine.is_inside((f(B.XPK + 0.4), B.YL + 0.6, 1.5))                     # 縁の裏の空洞
    assert not mine.is_inside((B.H15_NEW[0], B.H15_NEW[1], 1.0)) and mine.is_inside((B.H15_NEW[0], B.H15_NEW[1], 3.5))
    assert prod.is_inside((B.H15_NEW[0], B.H15_NEW[1], 1.0)) and not prod.is_inside((B.H15_OLD[0], B.H15_OLD[1], 1.0))
    assert not mine.is_inside((104.0, -48.225, 1.0)) and mine.is_inside((B.XPK - 0.4, -48.225, 1.5))    # H14 と、その壁
    n = B.numbers()
    assert n["h14_wall"] == pytest.approx(0.8, abs=1e-6) and n["h15_wall"] == pytest.approx(0.8, abs=1e-6)
    notch = LAY.psw_notch()                                                 # つまみの切り欠きは、変えた範囲の外
    assert min(p[0] for p in notch) > B.H15_MOD[2]
    assert vol(Pos(0.5, 0, 0) * a, b) < a.volume - 3.0                      # 壊す: 0.5 ずれた枠なら同じにならない


def test_the_board_is_not_changed_and_the_new_h15_place_has_no_track():
    """基板は変えていない（H15 は、いまも 136.5）。**提案の先（140.0）に、配線済みの基板の線が無い**（穴の縁 ＋ 0.5 以内）。ビアは 1 つだけ掛かる
    （縫い付けのビア。動かすときに外す）。いまの H15 は、右の腕の通り道の中にある = B は、いまの基板のままでは作れない。"""
    assert dict((n, c) for n, c, _ in LAY.screws())["H15"] == (136.5, -48.225) and B.H15_NEW == (140.0, -48.225)
    text = (ROOT / "projects" / "cckb-click" / "pcb" / "cckb-click_main.kicad_pcb").read_text()
    cx, cy, keep = 150.0 + B.H15_NEW[0], 100.0 - B.H15_NEW[1], S.SCREW_HOLE_D / 2 + 0.5

    def seg_near(px, py):
        out = 0
        for m in re.finditer(r'\(segment\s*\(start ([\d.-]+) ([\d.-]+)\)\s*\(end ([\d.-]+) ([\d.-]+)\)\s*\(width ([\d.]+)\)', text):
            x1, y1, x2, y2, w = map(float, m.groups())
            dx, dy = x2 - x1, y2 - y1
            n2 = dx * dx + dy * dy
            k = 0.0 if n2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / n2))
            out += math.hypot(px - x1 - k * dx, py - y1 - k * dy) - w / 2 < keep
        return out

    assert len(re.findall(r"\(segment", text)) > 500                          # 読めている
    assert seg_near(cx, cy) == 0
    first = re.search(r'\(segment\s*\(start ([\d.-]+) ([\d.-]+)\)', text)
    assert seg_near(float(first.group(1)), float(first.group(2))) > 0          # 壊す: 線のある所では数える
    vias = [m for m in re.finditer(r'\(via\s*\(at ([\d.-]+) ([\d.-]+)\)\s*\(size ([\d.]+)\)', text)
            if math.hypot(cx - float(m.group(1)), cy - float(m.group(2))) - float(m.group(3)) / 2 < keep]
    assert len(vias) == 1
    lane = (B.mx(B.XLIP + B.T_MAX + 0.1), B.mx(B.XLIP))                       # 右の腕の通り道（窓の、縁の側）
    assert lane[0] < B.H15_OLD[0] + S.SCREW_PILOT_D / 2 and B.H15_OLD[0] - S.SCREW_PILOT_D / 2 < lane[1]


def test_nothing_overlaps_at_rest_and_nothing_sticks_out():
    """掛けた位置で、蓋 3 つとも、枠・当て板・クリップ・電池・電源スイッチ・コンデンサと重ならない。枠も同じ。
    蓋の真ん中は枠の上面と面一・手前の面は、かぎが縁に当たるまで寄っても外面の 0.1 内。"""
    fr, base, cell, clip = B.frame(), B.base(), B.cell(), C.clip_solid()
    parts = C.board_parts()
    others = (base, clip, parts["SW_PWR"], parts["C_BAT"])
    for other in others + (cell,):
        assert vol(fr, other) < TOL
    for n in B.VARIANTS:
        cv = B.cover(n, True)
        for other in (fr,) + others:
            assert vol(cv, other) < TOL, n
        assert vol(cv, cell) < TOL, n
        bb = cv.bounding_box()
        assert bb.max.Z == pytest.approx(B.TOP, abs=1e-4) and bb.min.Z == pytest.approx(0.0, abs=1e-4)
        assert bb.min.Y - B.SEAT >= B.Y0 + 0.1 - 1e-6
        assert B.XPK < bb.min.X and bb.max.X < B.mx(B.XPK)
        assert len(cv.solids()) == 1
    assert vol(B.posed(B.cover(B.MAIN, True), dz=0.4), fr) > 0.05              # 壊す: 0.4 持ち上げると枠に重なる


# ---------------------------------------------------------------------------
# 掛けた蓋は動かない・電池は出ない
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", sorted(B.VARIANTS))
def test_the_engaged_cover_cannot_move(n):
    """左右のかぎが掛かった蓋は、手前へ 0.1・上へ 0.25・奥へ 0.2 より動けない（0.05 ずつ動かして、枠・当て板・クリップに当たるまで）。
    左右は、腕の先が縁に触れている（腕は撓む）ので、腕を 0.3 内へ逃がした蓋で胴の遊びを測る: 0.1〜0.2（奥の案内と、口の真ん中の溝）。
    内へ倒れない（手前の下の縁を軸に ±3° 回すと当たる）。"""
    cv, ob = B.cover(n, False), B.obstacles()
    assert B.hit(cv, ob) < TOL
    assert B.travel(cv, ob, (0, -1, 0)) <= 0.1 + 1e-9
    assert B.travel(cv, ob, (0, 0, 1), limit=1.0) <= 0.25 + 1e-9
    pre = B.VARIANTS[n]["pre"]
    slack = B.cover(n, False, pre + 0.3, pre + 0.3)
    for sx in (-1, 1):
        assert 0.1 - 1e-9 <= B.travel(slack, ob, (sx, 0, 0), limit=1.0) <= 0.2 + 1e-9
    assert B.travel(cv, B.obstacles(with_cell=True), (0, 1, 0), limit=1.0) <= 0.2 + 1e-9
    for rx in (3.0, -3.0):
        assert B.hit(B.posed(cv, rx=rx, pivot=(B.CX, B.YF, 0.0)), ob) > TOL


def test_breaking_the_catch_lets_the_cover_out():
    """壊す: 口の縁の無い枠・かぎの無い蓋なら、手前へ 2 以上進める（上の検査が、掛かりを見ている）。"""
    cv = B.cover(B.MAIN, False)
    assert B.travel(cv, B.obstacles(lips=False), (0, -1, 0)) >= 2.0
    assert B.travel(B.cover(B.MAIN, False, hook=0.0), B.obstacles(), (0, -1, 0)) >= 2.0


def test_the_cell_cannot_get_out():
    """蓋を掛けたら、電池の代わりは手前へ 0.3 より進めない（斜め手前も）。蓋を外せば、手前へ 15 以上、何にも当たらない。"""
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


def test_engagement_is_one_mm_and_survives_tolerance():
    """かぎと縁の掛かり（立体から測る）: 3 つとも 1.0 以上。蓋が案内の隙ぶん横へ寄っても（腕が追わないと見て）0.85 以上。
    誤差と遊びを全部悪い側に取った見込み（計算）が 0.6 以上。壊す: かぎの出 0.3 の蓋は 0.4 に届かない。"""
    for n, v in B.VARIANTS.items():
        e = B.engagement(n)
        assert min(e) >= 1.0 and max(e) <= v["hook"] + 1e-6, (n, e)
        assert min(B.engagement(n, B.GUIDE_CL)) >= 0.85
        a = B.arm_numbers(n)
        assert a["engage"] >= 1.0 and a["engage_worst"] >= 0.6 - 1e-9, (n, a["engage_worst"])
    assert 0.1 < max(B.engagement(B.MAIN, hook=0.3)) < 0.4


# ---------------------------------------------------------------------------
# 外す・入れる
# ---------------------------------------------------------------------------

def test_release_needs_both_arms():
    """両方の腕をつまめば、蓋は手前へ 15 以上まっすぐ抜ける（枠・当て板・クリップ・電池に当たらない）。
    **片方だけ**では: まっすぐは 0.1 まで。平面の中で動かして探しても（ずらす・回す）、つまんだ側が手前へ出るのは 1.0 まで。
    その姿勢でも、電池の代わりは 1.0 より手前へ進めない。壊す: 両方をつまんだ蓋なら、同じ探し方が 60 歩で 1.5 以上出す（探し方が、出る道を見つけられる）。"""
    obc = B.obstacles(with_cell=True)
    assert B.travel(released(), obc, (0, -1, 0), step=0.5, limit=16.0) >= 15.0
    ob = B.obstacles()
    for left in (True, False):
        one = released(left=left, right=not left)
        assert B.travel(one, ob, (0, -1, 0)) <= 0.1 + 1e-9
    one = released(left=True, right=False)
    out, pose = B.wiggle(one, ob, lambda p: B.corner_out(p, B.XLIP + 1.0))
    assert 0.2 < out <= 1.0, out
    cell = B.cell()
    blk = (ob[0], ob[1], B.posed(one, **pose))
    assert B.travel(cell, blk, (0, -1, 0), pivot=(0.0, 0.0, 0.0)) <= 1.0
    loose, _ = B.wiggle(released(), ob, lambda p: B.corner_out(p, B.XLIP + 1.0), iters=60)
    assert loose >= 1.5, loose


def test_insert_path_needs_the_arms_to_give_and_no_more_than_release():
    """入れる道: 手前 14 から掛けた位置まで、腕を「外す」所まで内へ動かせば、どこでも枠・当て板・クリップ・電池に当たらない。
    かぎが縁の中にいる間（手前へ 0.5〜1.5）は、腕が掛けた形のままでは通れない = 腕が撓んで入る（カチッ）。最後は、掛けた形で収まる。"""
    obc = B.obstacles(with_cell=True)
    rel, asm = released(), B.cover(B.MAIN, False)
    for k in range(29):
        dy = -14.0 + 0.5 * k
        assert B.hit(B.posed(rel, dy=dy), obc) < TOL, dy
    for dy in (-1.5, -1.0, -0.5):
        assert B.hit(B.posed(asm, dy=dy), obc) > TOL, dy
    assert B.hit(asm, obc) < TOL


# ---------------------------------------------------------------------------
# 数
# ---------------------------------------------------------------------------

def test_arm_strain_and_force():
    """腕: 外すとき・入れるときの付け根のひずみが、この機種の上限（spec.PLA_STRAIN_USE × PLA_BEND / PLA_E = 1.52 %）以内。胴に当たって止まるときも、
    曲げ強さのひずみ（2.76 %）の 0.7 倍以内。線 2 本（0.84）以上の厚さ。つまむ力 0.8〜3 N。掛けた後も縁を押している。落下で、かぎが自分の重さで
    外れるまで 2 倍以上。胴は、外す所より先で腕を止める。壊す: 厚さ 1.2 の腕で同じかぎなら、上限を超える。"""
    for n, v in B.VARIANTS.items():
        a = B.arm_numbers(n)
        assert a["strain_use"] == pytest.approx(S.PLA_STRAIN_USE * S.PLA_BEND / S.PLA_E * 100)
        assert a["strain_insert"] < a["strain_release"] <= a["strain_use"], (n, a["strain_release"])
        assert a["strain_stop"] <= 0.7 * a["strain_limit"]
        assert v["t"] >= 0.84 and 0.8 <= a["pinch"] <= 3.0 and a["hold"] > 0.05
        assert a["drop_margin"] >= 2.0
        assert a["stop"] >= a["release"] + 0.05 and a["length"] == pytest.approx(B.YR - B.YF)
        assert 1.5 * 1.2 * a["release"] / a["length"] ** 2 * 100 > a["strain_use"]
    # 腕の長さの根拠: 線 2 本の腕（0.85）で掛かり 1.0 を外すのに要る長さは、ランドの手前の奥行き（外面から 6.5 ほど）より長い
    need = math.sqrt(1.5 * 0.85 * (1.0 + 0.15) / (S.PLA_STRAIN_USE * S.PLA_BEND / S.PLA_E))
    room = LAY.clip_pads()[0][1] - S.PART_CLEAR - B.YF
    assert need > 9.5 and room < 7.0 and B.ARM_L > need


def test_stresses_are_reported_honestly():
    """電池が押す力は、かぎと腕と、蓋の真ん中の板を通る。指で強く押す 20 N（仮定）で、板の手前の縁の引っ張りが TDS の引っ張り強さ以内・
    板の奥の縁・柱・腕が曲げ強さ以内・腕の座屈の 1/3 以内。**余裕は小さい**: 強さに届く力は 15〜30 N の間・1500 G（仮定）では板が強さを超える。
    **本番の蓋（A）より苦しい**: 同じ力で比べて、板の引っ張りが A の 1.5 倍以上。断面は立体から測った物（名目の計算と 5 % 以内で合う）。"""
    n = B.numbers()
    st = B.stresses(B.MAIN, B.PUSH)
    assert st["plate"]["tension"] < S.PLA_TENSILE and st["plate"]["compression"] < S.PLA_BEND
    assert st["stem"]["stress"] < S.PLA_BEND and st["arm"]["stress"] < S.PLA_BEND and st["arm"]["load"] < st["arm"]["buckle"] / 3
    assert st["plate_center_hit"]["tension"] > st["plate"]["tension"]
    assert 15.0 < n["force_at_strength"] < 30.0
    big = B.stresses(B.MAIN, S.CELL_MASS * S.DROP_G * 9.80665e-3)
    assert big["plate"]["tension"] > S.PLA_TENSILE
    half = B.stresses(B.MAIN, B.PUSH / 2)
    assert half["plate"]["tension"] == pytest.approx(st["plate"]["tension"] / 2)
    a = C.cover_beam()
    a_force = C.cover_numbers()["cell_force"]
    assert st["plate"]["tension"] / B.PUSH > 1.5 * a["tension"] / a_force
    mid = dict(B.plate_sections(B.MAIN))[B.CX]
    pk = n["pocket"]
    assert mid["area"] == pytest.approx(pk["plate_t"] * B.STRIP_Z + (B.YB - B.YF) * (B.TOP - B.STRIP_Z), rel=0.05)
    assert pk["center_gap"] > B.CELL_GAP + 0.05                                # 電池は、真ん中でなく角で当たる
    assert n["hook_span"] > 30.0                                               # かぎの間（A の耳の間は 20 ほど）


# ---------------------------------------------------------------------------
# 刷れるか・見分け
# ---------------------------------------------------------------------------

def test_printable_without_support():
    """蓋（底をベッドに）: 下に何も無い所は、電池の上に渡る帯（くぼみの上・左右の足の間の橋）だけ。枠（上面をベッドに）: 上を向いた面の高さが、
    本番の角に無い物を足していない（B は、屋根から下がる壁と、切り欠きしか足していない）。板は A1 mini に載る・6 個。"""
    cv = B.cover(B.MAIN, True, 0.0, 0.0)
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
