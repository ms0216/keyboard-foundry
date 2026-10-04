"""cckb-click の蓋の別案 S（横ずらしで掛ける蓋）の試し刷り（projects/cckb-click/click_cover_slide.py・docs/coupon-cover-slide.md）。

**生成した立体そのもの**を重ねる・動かす・切って見る。各検査に「故意に壊すと落ちる」を入れる。
外の事実: 本番の枠の立体（S の枠は、その角の切れ端から作る）・クリップの図面から作った立体（click_case.clip_solid）・当て板と電池の代わり
（本番の蓋の試し刷りと同じ物）・TDS の材料の値（spec.PLA_*）・スライスした G-code（tools/slice_cover_slide.py が見る）。
本番の枠を作るので（約 40 秒）、全部 slow。**本番の蓋・枠・基板を変えていないこと**は、既存の検査（test_cckb_click_case・_board）がそのまま通ることで見る。
"""

import math
import sys

import pytest
from build123d import Pos, Rot, export_stl

from conftest import ROOT

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
import click_case as C  # noqa: E402
import click_cover_slide as K  # noqa: E402

LAY, S = C.LAY, C.S
vol = K.vol
TOL = 2e-3
pytestmark = pytest.mark.slow

MOD = (K.FILL[0], K.Y0 - 1.0, K.XTIP + K.LEAF_L + 0.3, K.FILL[3])          # S が本番の枠から変えた範囲（平面）


def cc():
    return C.corner_coupon()


# ---------------------------------------------------------------------------
# 形: 本番の枠の角か・変えたのは口のまわりだけか
# ---------------------------------------------------------------------------

def test_the_frame_is_the_production_corner_outside_the_mouth():
    """口のまわり（MOD）の外は、本番の枠の角の切れ端と同じ立体（つまみの切り欠き・ねじ穴 H15 の下穴・外形）。枠の外へ出る物が無い・手前の壁は 3.0 のまま。"""
    prod, mine = cc()["frame"], K.frame()
    box = C._box(MOD, -3.0, 8.0)
    a, b = prod - box, mine - box
    assert a.volume == pytest.approx(b.volume, abs=0.01) and vol(a, b) == pytest.approx(a.volume, abs=0.01)
    pb, mb = prod.bounding_box(), mine.bounding_box()
    for q in ("min", "max"):
        for ax in "XYZ":
            assert getattr(getattr(mb, q), ax) == pytest.approx(getattr(getattr(pb, q), ax), abs=1e-4)
    assert len(mine.solids()) == 1
    # 手前の壁（口の外）: 外面から 3.0 の所までが樹脂・その奥（キーの領域）は本番と同じ
    assert LAY.key_area[1] - LAY.frame[1] == pytest.approx(3.0) == pytest.approx(S.PLATE_MARGIN_Y)
    for x in (K.FILL[0] + 0.5, K.CAV[0] - 0.4):
        assert all(mine.is_inside((x, K.Y0 + d, 1.5)) for d in (0.05, 1.5, 2.9))
    # つまみの切り欠きは MOD の外（x は板ばねの付け根より右・y は埋め直した範囲より奥）
    notch = LAY.psw_notch()
    assert min(p[0] for p in notch) > K.XTIP + K.LEAF_L + 0.3 and min(p[1] for p in notch) > K.FILL[3] - 1e-6
    # 壊す: 0.5 ずれた枠なら同じにならない
    assert vol(Pos(0.5, 0, 0) * a, b) < a.volume - 3.0


def test_nothing_overlaps_at_rest_and_nothing_sticks_out():
    """掛けた位置で、蓋 3 つとも、枠（筋なし）・当て板・クリップ・電池・電源スイッチと重ならない。枠も、当て板・クリップ・電池と重ならない。
    蓋は枠の上面と面一・手前の面は、蓋が手前へ寄り切っても外面の内。"""
    fr = K.frame(False)
    base, cell, clip = cc()["base"], cc()["cell"], C.clip_solid()
    psw = C.board_parts()["SW_PWR"]
    for other in (base, cell, clip, psw):
        assert vol(K.frame(), other) < TOL
    for n in K.VARIANTS:
        cv = K.cover(n, True)
        for other in (fr, base, cell, clip, psw):
            assert vol(cv, other) < TOL, n
        bb = cv.bounding_box()
        assert bb.max.Z == pytest.approx(K.TOP, abs=1e-4) and bb.min.Z == pytest.approx(0.0, abs=1e-4)      # 面一・足は基板に着く
        assert bb.min.Y - K.CL >= K.Y0 + 0.09                                                             # 手前へ CL 寄っても、外面の 0.1 内
        assert K.FILL[0] < bb.min.X and bb.max.X < K.XTIP                                                  # 左右は枠の中・板ばねの先より左
    # クリップの板の上（図面の名目 4.0 ＋ 0.1）との隙。**公差の端（4.35）では、上の板の下面 4.3 に当たる = 本番の蓋と同じ未解決**
    assert K.TOP - S.COVER_TOP_T - LAY.z()["clip_top"] == pytest.approx(0.2)
    # 壊す: 蓋を 0.3 右へ・0.3 奥へ・0.3 上へ動かすと、枠に当たる
    cv = K.cover(2, False)
    assert vol(K.posed(cv, dx=0.4), K.frame(False)) > 0.02 and vol(K.posed(cv, dy=0.3), fr) > 0.1 and vol(K.posed(cv, dz=0.3), fr) > 0.1


def test_the_cover_parts_behind_the_feet_stay_clear_of_the_clip_plate_all_the_way():
    """耳の奥の面（YB = クリップの板の端の 0.2 手前）より奥にある蓋の部分（出っ張り）は、落とす位置から掛けた位置まで、ずっとクリップの板の外
    （x ≤ CLIP_L か x ≥ CLIP_R）。上の板（板より上）は除く。"""
    assert K.YB == pytest.approx(LAY.clip_body()[1] - 0.2) and (K.CLIP_L, K.CLIP_R) == pytest.approx((113.35, 130.65))
    cv = K.cover(2, False)
    behind = cv & C._box((100.0, K.YB + 0.01, 150.0, K.YT + 1.0), -1.0, K.TOP - S.COVER_TOP_T - 0.01)
    spans = sorted((q.bounding_box().min.X, q.bounding_box().max.X) for q in behind.solids())
    assert len(spans) == 2
    (l0, l1), (r0, r1) = spans
    assert l1 + K.SLIDE <= K.CLIP_L + 1e-6 and r0 >= K.CLIP_R - 1e-6                    # 左は落とす位置（右へ SLIDE）で・右は掛けた位置で、いちばん近い
    clip = C.clip_solid()
    for i in range(17):
        assert vol(K.posed(cv, dx=K.SLIDE * i / 16), clip) < TOL
    # 壊す: 出っ張りを板の下まで伸ばした蓋（左へ SLIDE より多くずらしたのと同じ）は、落とす位置で板の下に入る = 上から落とせない
    assert vol(K.posed(cv, dx=K.SLIDE + 1.0, dz=1.0), clip) > 0.05


# ---------------------------------------------------------------------------
# 電池は、蓋を掛けたらどの向きにも出ない・蓋を外せば出せる
# ---------------------------------------------------------------------------

DIRS = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) != (0, 0, 0)]


def _travel(cell, obst, d, far=3.0, step=0.1):
    """電池の代わりを向き d へ step ずつ動かして、当たらずに進める距離。"""
    n = math.sqrt(sum(q * q for q in d))
    k = 0
    while k * step < far:
        t = (k + 1) * step
        if K.hit(Pos(d[0] * t / n, d[1] * t / n, d[2] * t / n) * cell, obst) > TOL:
            break
        k += 1
    return k * step


def test_the_cell_cannot_leave_in_any_direction_with_the_cover_locked():
    """蓋を掛けると、電池の代わりは 26 の向きのどれへも 1.0 より進めない（蓋が手前へ寄り切っていても）。手前へは 0.2〜0.4（蓋の手前の塊の丸い面に当たる）。"""
    cell = cc()["cell"]
    worst = {}
    # クリップの立体は、止めを公差ぶん厚く作ってある（止めに当てた電池と重なる）ので、電池の上に来る板の所だけを相手にする。奥の止めは、当て板の止めが受ける
    near, base, clip = K.obstacles(0.0)
    plate = clip & C._box((100.0, -60.0, 150.0, -20.0), S.CELL_T + 0.05, 9.0)
    assert vol(cell, plate) < TOL and vol(cell, base) < TOL and plate.volume > 30.0
    for dy in (0.0, -K.CL):
        obst = [near, base, plate, K.posed(K.cover(2, False), dy=dy)]
        for d in DIRS:
            worst[d] = max(worst.get(d, 0.0), _travel(cell, obst, d))
    assert max(worst.values()) <= 1.0, {d: v for d, v in worst.items() if v > 1.0}
    assert 0.15 <= worst[(0, -1, 0)] <= 0.45
    # 壊す ＝ 蓋を外せば、電池はまっすぐ手前へ 22 mm 何にも当たらずに出る（枠の縁の間 = 電池 ＋ 左右 1.0 以上）
    assert _travel(cell, [near, base, plate], (0, -1, 0), far=22.0, step=0.5) >= 22.0
    (cx, _), r = LAY.cell()
    assert K.A0 <= cx - r - 1.0 and K.A1 >= cx + r + 1.0


# ---------------------------------------------------------------------------
# 掛けた蓋は、上がらない・傾かない（6 つの向きに動かして探す）
# ---------------------------------------------------------------------------

LOOSE = max(K.VARIANTS.values()) + K.PRINT_ERR        # いちばん緩い蓋が、さらに刷りの誤差ぶん緩く出たときの、斜面の隙


def test_the_locked_cover_cannot_rise_or_tilt_out():
    """**つぶれる筋が無い・いちばん緩い蓋が誤差ぶん緩い**（斜面の隙 0.40）形で、板ばねは上がったまま、蓋を 6 つの向きに動かして探す。
    上面の四隅のどれも 0.75 より上がらない（まっすぐ上へは 斜面の隙 ＋ 前後の遊び = 0.55）。左右に傾くのは 2.5° まで。"""
    cv = K.cover(3, False, LOOSE)
    obst = K.obstacles(0.0)
    assert LOOSE + K.CL == pytest.approx(0.55)
    rises = [K.wiggle(cv, obst, seed=s)[0] for s in (1, 2, 3)]
    assert 0.3 < max(rises) <= 0.75, rises
    tilt = max(K.wiggle(cv, obst, objective=lambda p: abs(p.get("ry", 0.0)), seed=s)[0] for s in (1, 2))
    assert tilt <= 2.5, tilt
    # 名目の蓋（蓋 2・筋なし）は 0.45 まで
    assert K.wiggle(K.cover(2, False), obst)[0] <= 0.45
    # 壊す: 屋根と出っ張りの無い枠なら、同じ探し方で蓋は 2 mm 以上上がる（= 探し方が、上へ抜ける道を見つけられる）
    assert K.wiggle(cv, K.obstacles(0.0, False, False))[0] > 2.0


def test_pressing_the_leaf_alone_or_sliding_part_way_does_not_free_the_cover():
    """板ばねを押し切っても（＝板ばねが折れて無くなっても）、蓋を右へずらさない限り、上がらない。ずらす量を決めて探すと、1.4 までは 0.45 以下・
    1.5 から抜ける（掛かり 1.45）。板ばねが上がったままなら、蓋は右へ TIP_CL より動けない。"""
    cv = K.cover(2, False)
    gone = K.obstacles(None)
    rise = {dx: K.wiggle(cv, gone, fixed=dict(dx=dx), iters=200)[0] for dx in (0.0, 0.8, 1.2, 1.4, 1.5, K.SLIDE)}
    assert all(rise[dx] <= 0.45 for dx in (0.0, 0.8, 1.2, 1.4)), rise
    assert rise[1.5] > 2.0 and rise[K.SLIDE] > 2.0, rise
    assert K.numbers()["engage"]["left"] == pytest.approx(1.45) == pytest.approx(K.numbers()["engage"]["right"])
    # 板ばねが上がったまま: 右へは TIP_CL（0.25）まで。0.4 では当たる。板ばねを release だけ押すと、通れる
    up = K.obstacles(0.0)
    assert K.hit(K.posed(cv, dx=K.TIP_CL - 0.03), up) < TOL and K.hit(K.posed(cv, dx=0.4), up) > 0.02
    ln = K.leaf_numbers()
    assert K.hit(K.posed(cv, dx=0.8), K.obstacles(round(ln["release"], 3))) < TOL
    assert K.hit(K.posed(cv, dx=0.8), K.obstacles(round(ln["release"] - 0.2, 3))) > 0.01
    # 蓋が手前へ座っているとき（ふだん）は、押し込みが CL ぶん少なくて済む
    assert K.hit(K.posed(cv, dx=0.8, dy=-K.CL), K.obstacles(round(ln["release_seated"], 3))) < TOL


def test_the_overhangs_and_lips_still_hold_at_the_tolerance_extremes():
    """掛かりを**立体で測る**: 蓋を持ち上げた形と枠の重なりの、左右への長さ。蓋が右へ寄り切り（TIP_CL）、屋根と出っ張りが誤差ぶん短く刷れても
    （両側 × PRINT_ERR）、上への掛かりは 0.9 以上・縁の裏の掛かりは 1.2 以上。板ばねの鼻と当ての重なりは 0.35 以上。"""
    fr = K.frame_body(False)
    out = {}
    for name, dx in (("nominal", 0.0), ("right", K.TIP_CL)):
        up = K.posed(K.cover(2, False), dx=dx, dz=0.8) & fr                         # 屋根・出っ張りの下に入っている所
        xs = sorted((q.bounding_box().min.X, q.bounding_box().size.X) for q in up.solids())
        slab = C._box((100.0, -60.0, 150.0, -40.0), K.EAR_LIFT + 0.1, K.RIB_Z - 0.1)  # 当て（右の耳の先の縦の板）より下の高さで測る
        fwd = K.posed(K.cover(2, False), dx=dx, dy=-0.6) & fr & slab                # 縁の裏に入っている所
        ls = sorted((q.bounding_box().min.X, q.bounding_box().size.X) for q in fwd.solids())
        out[name] = ([w for _, w in xs], [w for _, w in ls])
    assert out["nominal"][0] == pytest.approx([1.45, 1.25], abs=0.02)               # 右は、出っ張り（枠）の幅 1.25 ぶん
    assert out["nominal"][1] == pytest.approx([2.2, 1.5], abs=0.02)
    assert min(out["right"][0]) - 2 * K.PRINT_ERR >= 0.9 - 1e-6 and min(out["right"][1]) - 2 * K.PRINT_ERR >= 1.2, out
    # 板ばねの鼻と当ての端面: 前後の重なり（名目 0.65・蓋が手前へ座ると 0.5・さらに誤差で 0.35）・上下に、斜めに落としていない所が 0.4
    both = K.posed(K.cover(2, False), dx=0.5) & K.leaf(0.0)
    bb = both.bounding_box()
    assert bb.size.Y == pytest.approx(K.NOSE[1], abs=0.01) and bb.size.Y - K.CL - K.PRINT_ERR >= 0.35 - 1e-6
    assert (K.TOP - K.CAM[0]) - (K.RIB_Z + K.CAM[1]) == pytest.approx(0.4)
    # 壊す: 蓋を SLIDE 右へ戻すと、上への掛かりは無い
    assert vol(K.posed(K.cover(2, False), dx=K.SLIDE, dz=0.8), fr) < TOL


# ---------------------------------------------------------------------------
# 入れ方・外し方（1 歩ずつ）
# ---------------------------------------------------------------------------

def test_the_cover_goes_in_from_above_then_slides_and_the_leaf_snaps_back():
    """入れる: 掛ける位置より SLIDE 右で、上から基板まで落とす（電池とクリップは付いたまま）→ 左へ SLIDE ずらす → 板ばねが戻る。外すのは、この逆。
    板ばねは、蓋の当てに押しのけられている間だけ撓む（先が 0.8 まで = 奥の空き）。"""
    cv = K.cover(2, False)
    ln = K.leaf_numbers()
    pushed = K.obstacles(round(ln["insert"], 3), False, True, True)                 # 板ばねを押しのけた形・電池つき
    rest = K.obstacles(0.0, False, True, True)
    assert ln["insert"] <= K.LEAF_ROOM + 1e-9
    for i in range(25):                                                             # 上から落とす
        dz = 6.0 * (24 - i) / 24
        assert K.hit(K.posed(cv, dx=K.SLIDE, dz=dz), pushed) < TOL, dz
    for i in range(17):                                                             # 左へずらす
        dx = K.SLIDE * (16 - i) / 16
        assert K.hit(K.posed(cv, dx=dx), pushed if dx > 0.01 else rest) < TOL, dx
    assert K.hit(cv, rest) < TOL                                                    # 掛けた位置で、板ばねは戻っている
    # 板ばねを押しのけないと、落とせない（当ての下の縁と鼻の上の縁の斜面が、押しのける）。斜面の和 > 重なり ＋ 遊び
    assert K.hit(K.posed(cv, dx=K.SLIDE), rest) > 0.05 and K.hit(K.posed(cv, dx=K.SLIDE, dz=K.TOP - K.RIB_Z + 0.05), rest) < TOL
    assert sum(K.CAM) >= K.NOSE[1] + K.CL + 0.1
    # 途中まで戻した蓋は、板ばねが戻れない（当てが鼻の手前にいる）= カチッと言うのは、最後まで左へ寄せたときだけ
    assert all(K.hit(K.posed(cv, dx=dx), rest) > 0.01 for dx in (0.4, 0.8, 1.2))
    # 掛ける位置では、上から落とせない（屋根と出っ張りに当たる）
    assert K.hit(K.posed(cv, dz=1.0), rest) > 0.3
    # つぶれる筋は、ずらす動きの最後の 0.9 で当たり始める（それまでは軽く動く）
    ridged = K.obstacles(None, True)
    assert K.hit(K.posed(cv, dx=1.0), ridged) < TOL and K.hit(K.posed(cv, dx=0.3), ridged) > 1e-3
    # 壊す: 板ばねの奥の空きより多く押しのけた形は、枠に食い込む（= 行き過ぎの止めが効く）
    emb = vol(K.leaf(0.0), K.frame_body(False))
    assert vol(K.leaf(K.LEAF_ROOM - 0.05), K.frame_body(False)) < emb + 0.01 < vol(K.leaf(K.LEAF_ROOM + 0.3), K.frame_body(False))


def test_a_thing_in_the_nail_slot_can_only_push_the_cover_shut():
    """爪を入れる所（板ばねの手前の溝）は、蓋の右の外（枠）。そこに面している蓋の面は、当ての端面（右向き）だけ = 溝の中の物が蓋を押せる向きは左（閉まる向き）。"""
    cv = K.cover(2, False)
    slot = C._box((K.XRE + K.SLIDE - 0.3, K.TRENCH[0], K.XLANE, K.LEAF_Y[0]), K.TRENCH_Z, K.TOP + 1.0)
    part = cv & slot
    assert part.bounding_box().max.X == pytest.approx(K.XRE + K.SLIDE, abs=1e-4) and part.volume < 0.3 * (K.RIB_Y[1] - K.RIB_Y[0]) * (K.TOP - K.RIB_Z) + 1e-3
    assert K.XTIP - (K.XRE + K.SLIDE) == pytest.approx(K.TIP_CL)
    fr = K.frame()
    xm, ym = K.XTIP + K.NOSE[0] + 1.0, (K.TRENCH[0] + K.LEAF_Y[0]) / 2
    assert not fr.is_inside((xm, ym, K.TOP - 0.5)) and fr.is_inside((xm, K.TRENCH[0] - 0.2, K.TOP - 0.5)) and fr.is_inside((xm, K.LEAF_Y[0] + 0.3, K.TOP - 0.5))
    assert K.LEAF_Y[0] - K.TRENCH[0] == pytest.approx(1.0) and K.XLANE - K.XTIP - K.NOSE[0] >= 2.5       # 幅 1.0・鼻の右に 2.5 以上


# ---------------------------------------------------------------------------
# 枠の肉・力の道
# ---------------------------------------------------------------------------

def test_the_wall_to_screw_h15_and_the_skin_over_its_pilot_remain():
    """右の空洞の端から、ねじ H15 の下穴の縁まで 1.45。板ばねの溝の底は、下穴の上の端の 0.5 上（**立体に点を打つ**）。"""
    fr = K.frame()
    hx, hy = next(c for n, c, _ in LAY.screws() if n == "H15")
    r = S.SCREW_PILOT_D / 2
    n = K.numbers()
    assert n["h15_wall"] == pytest.approx(1.45) and n["h15_cap"] == pytest.approx(0.5)
    assert all(fr.is_inside((K.CAV[1] + d, hy, 1.5)) for d in (0.05, 0.7, 1.4)) and not fr.is_inside((K.CAV[1] - 0.05, hy, 1.5))
    assert not fr.is_inside((hx, hy, 1.5)) and not fr.is_inside((hx - r + 0.05, hy, 1.5))
    top = LAY.pilot()[1]
    assert fr.is_inside((hx, hy, top + 0.05)) and fr.is_inside((hx, hy, K.TRENCH_Z - 0.05)) and not fr.is_inside((hx, hy + 0.9, K.TRENCH_Z + 0.1))
    # 板ばねの溝の手前に残る壁（外面から 0.9）
    assert all(fr.is_inside((hx, K.Y0 + d, K.TOP - 0.5)) for d in (0.05, 0.8)) and not fr.is_inside((hx, K.TRENCH[0] + 0.1, K.TOP - 0.5))
    assert K.TRENCH[0] - K.Y0 == pytest.approx(0.9)


def test_the_load_path_stresses_have_margin_and_the_section_meter_agrees_with_the_production_one():
    """電池が 1500 G で押す 26.5 N を、蓋の真ん中で受ける（左右の足では受けられない: 下の検査）。**断面は立体から測る。**
    蓋の胴: 曲げ 134 N·mm・手前の縁の引っ張りは引っ張り強さの 1/1.4 以下・奥の縁（上の板の端）の圧縮は曲げ強さの 1/1.35 以下
    （**本番の蓋より悪い**: 引っ張りは同じくらい・圧縮は 1.6 倍）。耳の首と枠の縁の曲げは引っ張り強さの 1/1.8 以下。"""
    st = K.stresses()
    assert st["force"] == pytest.approx(26.48, abs=0.01) and sum(st["react"]) == pytest.approx(st["force"])
    assert st["body"]["moment"] == pytest.approx(134.5, abs=1.0) and st["body"]["x"] == pytest.approx(LAY.cell()[0][0])
    assert st["body"]["tension"] <= S.PLA_TENSILE / 1.4 and st["body"]["compression"] <= S.PLA_BEND / 1.35
    for k in ("neck_left", "neck_right", "neck_right_root", "lip_left", "lip_right"):
        assert st[k]["stress"] <= S.PLA_TENSILE / 1.8, (k, st[k])
    assert max(st["ear_bearing"]) < 3.0
    prod = C.cover_beam()
    assert prod["tension"] == pytest.approx(23.7, abs=0.2) and prod["compression"] == pytest.approx(34.1, abs=0.2)
    assert 0.95 < st["body"]["tension"] / prod["tension"] < 1.1 and 1.5 < st["body"]["compression"] / prod["compression"] < 1.7
    # 測り方の突き合わせ: 同じ section() で本番の蓋の真ん中を測ると、click_case.cover_beam（別の実装）の断面と合う
    cv = LAY.cover()
    bands = [cv["band"]["A"], cv["band"]["B"]]
    skip = lambda y, z: y < cv["yf"] + cv["t"] + 0.01 and any(z0 - 0.01 <= z <= z1 + 0.01 for z0, z1 in bands)      # noqa: E731
    sc = K.section(C.cover_solid(None, 0.0, False, False), (cv["x0"] + cv["x1"]) / 2, y0=cv["yf"], y1=cv["y1"], z1=cv["z_top"], skip=skip)
    assert sc["area"] == pytest.approx(prod["area"], rel=0.01) and sc["inertia"] == pytest.approx(prod["inertia"], rel=0.01)
    # 壊す: 上の板を取った蓋（上面の 0.7 を削る）なら、断面二次モーメントは半分以下
    thin = K.cover(2, False) - C._box((K.XL + 0.5, K.YF + 1.3, K.XR - 0.5, K.YT + 1.0), K.TOP - S.COVER_TOP_T - 0.01, K.TOP + 1.0)
    x = st["body"]["x"]
    a, b = K.section(K.cover(2, False), x), K.section(thin, x)
    assert b["inertia"] < a["inertia"] / 2


def test_side_feet_like_the_production_cover_would_land_on_the_cell():
    """**左右の足で電池を受ける形（本番の蓋）は、S では作れない。**蓋を SLIDE 右で落とすと、左の足（電池の円 ＋ 0.2 まで詰めた塊）が電池の上に載る。
    S の蓋は、落とす位置から掛ける位置まで、電池（止めに当てた位置）と CELL_PASS = 0.1 の隙を保つ・掛けた位置では、真ん中で 0.2。"""
    (cx, cy), r = LAY.cell()
    cell = cc()["cell"]
    keep = Pos(cx, cy, -1.0) * C.Cylinder(r + S.COVER_CELL_CLEAR, 9.0, align=C.CEN_MIN)
    foot = C._box((K.XL, K.YF, cx - 4.0, K.YB), 0.0, 4.3) - keep                       # 本番の蓋と同じ作り方の、左の足
    assert vol(foot, cell) < TOL and vol(Pos(K.SLIDE, 0, 0.5) * foot, cell) > 0.5
    cv = K.cover(2, False)
    for i in range(17):
        dx = K.SLIDE * i / 16
        assert vol(K.posed(cv, dx=dx), cell) < TOL
        assert vol(K.posed(cv, dx=dx), Pos(0, -(K.CELL_PASS - 0.02), 0) * cell) < TOL, dx       # 電池が 0.08 手前にいても当たらない
    # 掛けた位置: 電池が手前へ 0.2 動くと、真ん中で当たる（当たる所の図心が、電池の真ん中の ± 1.5）
    assert vol(cv, Pos(0, -0.19, 0) * cell) < TOL
    touch = cv & (Pos(0, -0.3, 0) * cell)
    assert touch.volume > 0.5 and abs(touch.center().X - cx) < 1.5


def test_the_leaf_numbers():
    """板ばね: 開ける押し込みで、ひずみが上限（1.52 %）以下・行き過ぎの止めで 1.6 % 以下・押す力は 0.7〜1.0 N。
    落下 1500 G で自分の重さで揺れる量は、重なりの 1/4 以下。蓋が右へ押す力（蓋の重さ × 1500 G）で座屈しない（先が自由と見ても 2 倍）。"""
    ln, n = K.leaf_numbers(), K.numbers()
    assert ln["overlap"] == pytest.approx(0.65) and ln["overlap_seated"] == pytest.approx(0.5)
    assert ln["strain_release"] <= ln["strain_use"] == pytest.approx(1.52) and ln["strain_stop"] <= 1.6 < ln["strain_limit"]
    assert 0.7 <= ln["force_release_seated"] <= ln["force_release"] <= 1.0
    assert ln["drop"] <= ln["overlap_seated"] / 4 and 1.0 < ln["gain"] < 2.0
    assert 4.0 < n["cover_force"] < 4.5 and ln["buckle_free"] >= 2.0 * n["cover_force"] and ln["buckle_held"] >= 15 * n["cover_force"]
    # 式の突き合わせ: 厚さを 0.6・高さを 0.9 にした「上下に撓む舌」なら、先が自由の座屈は 2 N に届かない（= 捨てた理由）
    old = math.pi ** 2 * S.PLA_E * (0.9 * 0.6 ** 3 / 12) / (2 * 8.3) ** 2
    assert old < 2.0 < n["cover_force"]


def test_one_of_the_three_covers_is_snug_at_each_print_error():
    """がた取り: 枠の斜面の筋（高さ 0.30）に、蓋の斜面が食い込む量（蓋が座ったとき・斜面に垂直）。刷りの誤差 −0.15／0／+0.15 のどれでも、
    3 つのうち 1 つは「しめしろ 0〜0.2・筋の無い所は当たらない」。**立体でも見る**: 座った蓋は、筋のある枠とだけ重なる。"""
    fits = K.numbers()["fits"]
    assert [round(fits[n]["interference"], 3) for n in (1, 2, 3)] == [0.159, 0.088, 0.017]
    for err in (-K.PRINT_ERR, 0.0, K.PRINT_ERR):
        ok = [n for n in fits if 0.0 <= fits[n]["interference"] + err <= 0.2 and fits[n]["solid_seated"] - err > 0.05]
        assert ok, err
    # いちばんきつい蓋 1 が、誤差ぶんきつく刷れると、筋の無い所も当たる（= そのときは蓋 2・3 を使う）
    assert fits[1]["solid_tight"] < 0.0 < fits[2]["solid_tight"]
    for n in K.VARIANTS:
        seated = K.posed(K.cover(n, False), dy=-K.CL)
        assert vol(seated, K.frame_body(False)) < TOL
        both = seated & K.frame_body(True)
        assert both.volume > 1e-4, n
        assert all(q.bounding_box().size.Z < K.RIDGE[0] + 0.02 for q in both.solids())
    v = [vol(K.posed(K.cover(n, False), dy=-K.CL), K.frame_body(True)) for n in (1, 2, 3)]
    assert v[0] > v[1] > v[2]


# ---------------------------------------------------------------------------
# 刷れるか（向き・宙に浮く面）と、刷る板
# ---------------------------------------------------------------------------

def _down_faces(part, tmp_path, name, steep=45.5):
    """上面をベッドに置いた part の、宙へ張り出す面（水平から steep° より寝ている下向きの面）[(面積, 組んだ座標の図心)]。ベッドの面と、その上 0.25 は除く。"""
    import numpy as np
    import trimesh

    p = tmp_path / f"{name}.stl"
    export_stl(Rot(180, 0, 0) * part, str(p))
    m = trimesh.load(str(p))
    z0 = m.bounds[0][2]
    lim = -math.sin(math.radians(steep))
    out = []
    for nrm, cen, area in zip(m.face_normals, m.triangles_center, m.area_faces):
        if nrm[2] < lim and cen[2] - z0 > 0.25:
            out.append((float(area), (float(cen[0]), float(-cen[1]), float(-cen[2]))))
    return out, np


def test_the_cover_prints_top_down_without_overhangs_and_the_frame_adds_only_two_bridges(tmp_path):
    """蓋を上面をベッドに置くと、45° より寝た下向きの面が無い（出っ張りの斜面は 45°）。枠の、S が変えた範囲では、宙に浮く面は
    板ばねの溝の底（幅 2.2〜2.8 の橋）と右の空洞の底（1.6 × 2.9）の 2 つだけ（G-code では tools/slice_cover_slide.py が見る）。"""
    faces, _ = _down_faces(K.cover(2, True), tmp_path, "cover")
    assert sum(a for a, _ in faces) < 0.01, faces[:5]
    faces, _ = _down_faces(K.frame(), tmp_path, "frame")
    mine = [(a, c) for a, c in faces if MOD[0] <= c[0] <= MOD[2] and MOD[1] <= c[1] <= MOD[3]]
    trench = sum(a for a, c in mine if abs(c[2] - K.TRENCH_Z) < 0.01)
    floor = sum(a for a, c in mine if abs(c[2] - K.FLOOR_T) < 0.01)
    other = sum(a for a, c in mine if abs(c[2] - K.TRENCH_Z) >= 0.01 and abs(c[2] - K.FLOOR_T) >= 0.01)
    assert other < 0.01
    want = (K.XLANE - K.CAV[1]) * (K.TRENCH[1] - K.TRENCH[0]) + (K.XTIP + K.LEAF_L - K.XLANE) * (K.TRENCH[1] - K.LEAF_Y[0] + K.LEAF_SLIT)
    assert trench == pytest.approx(want, rel=0.02) and floor == pytest.approx((K.CAV[1] - K.XRE - K.CL) * (K.YC - K.YLR), rel=0.02)
    assert K.TRENCH[1] - K.TRENCH[0] == pytest.approx(2.8) and K.LEAF_Z - K.TRENCH_Z == pytest.approx(0.4) and K.RIB_Z - K.TRENCH_Z == pytest.approx(0.4)
    # 壊す: 蓋を下面をベッドに置くと、上の板の下が宙に浮く
    faces, _ = _down_faces(Rot(180, 0, 0) * K.cover(2, True), tmp_path, "cover_up")
    assert sum(a for a, _ in faces) > 20.0


def test_the_plate_has_six_pieces_that_fit_the_printer_and_the_covers_are_told_apart():
    """刷る板: 電池の代わり・蓋 3 つ・当て板・枠。A1 mini に置ける・重ならない・全部ベッドに着く。蓋は切り欠きの数（1・2・3）と、斜面の隙が違う。"""
    lay = K.plate_layout()
    assert [n for n, _, _ in lay] == ["cell", "cover1", "cover2", "cover3", "base", "frame"]
    bbs = [p.bounding_box() for _, p, _ in lay]
    assert all(abs(b.min.Z) < 1e-6 for b in bbs)
    size = K.plate().bounding_box().size
    assert max(size.X, size.Y) <= S.PRINT_MAX
    for i, a in enumerate(bbs):
        for b in bbs[i + 1:]:
            assert a.max.X + 3.0 <= b.min.X or b.max.X + 3.0 <= a.min.X or a.max.Y + 3.0 <= b.min.Y or b.max.Y + 3.0 <= a.min.Y
    plain = K.cover(2, False).volume
    mw, md, _ = K.MARK
    for n in K.VARIANTS:
        notch = K.cover(n, False).volume - K.cover(n, True).volume
        assert notch == pytest.approx(n * mw * md * S.COVER_TOP_T, rel=0.25), n
    assert K.cover(1, False).volume > plain > K.cover(3, False).volume
    # 当て板と電池の代わりは、本番の蓋の試し刷りと同じ物
    assert vol(dict((n, p) for n, p, _ in lay)["base"], lay[4][1]) == pytest.approx(cc()["base"].volume, abs=0.01)
    # 置いた先の座標を返す関数が、置いた立体と合う（スライスの検査が使う）
    name, part, fn = lay[-1]
    p = fn((K.XTIP + 2.0, (K.LEAF_Y[0] + K.LEAF_Y[1]) / 2, K.TOP - 0.5))
    q = fn((K.XTIP + 2.0, K.LEAF_Y[1] + 0.4, K.TOP - 0.5))
    assert part.is_inside(p) and not part.is_inside(q)
