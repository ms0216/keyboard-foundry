"""cckb-click の試し刷り v2（ねじの下穴 3 通り・つまみの位置 2 つ）。projects/cckb-click/click_coupon_v2.py。
（同じ板で刷った差し込み式の蓋 3 つは使えなかった。蓋はねじで留める形に変え、3 つの形と検査は消した: tests/test_cckb_click_case.py の蓋の章）

**生成した立体そのもの**を重ねる・動かす・切って見る。各検査に「故意に壊すと落ちる」を入れる。
外の事実: M2 並目の寸法（ISO 724: 外径 2.0・めねじの内径 1.567）・本番の枠の立体（切れ端はそこから切る）。
本番の枠を作る検査（25 秒）は slow。
"""

import math
import sys

import pytest
from build123d import Pos

from conftest import ROOT

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
import click_case as C  # noqa: E402
import click_coupon_v2 as V  # noqa: E402

LAY, S = C.LAY, C.S
TOL = 1e-3
vol = V.vol


def overhangs(part):
    out = []
    for f in part.faces():
        try:
            nz = f.normal_at().Z
        except Exception:
            continue
        if nz < -0.72 and f.center().Z > 1e-3:
            out.append((round(f.center().Z, 2), round(f.area, 3)))
    return out


# ---------------------------------------------------------------------------
# つまみ（式から作った壁の切れ端）
# ---------------------------------------------------------------------------

def test_the_two_switch_positions_are_the_previous_one_and_the_production_one_0_75_further_out():
    """利用者が刷った 2 つの位置: (i) 前の位置（本体は基板の縁から 2.5）・(ii) 0.75 外。**(ii) を利用者が選び、本番の位置になった**
    （2026-10-04）。試し刷りは、本番の位置から測って同じ 2 つを出し続ける。"""
    f2, p2 = LAY.frame[2], LAY.pcb[2]
    assert V.KNOB_VARIANTS == ((-S.COUPON_V2_PSW_SHIFT, 1), (0.0, 2)) and S.COUPON_V2_PSW_SHIFT == 0.75
    for (dx, _), (tip_board, tip_frame, body, origin) in zip(V.KNOB_VARIANTS, ((1.05, 1.35, 2.5, 141.125), (0.30, 0.60, 1.75, 141.875))):
        lay = V.shifted(dx)
        k = lay.psw_knob(1)
        assert (p2 - k[2], f2 - k[2], p2 - lay.psw_body()[2], lay.s.PSW_AT[0]) == pytest.approx((tip_board, tip_frame, body, origin))
    assert V.shifted(0.0) is LAY and S.PSW_AT == (141.875, -38.1)                         # (ii) = 本番
    assert p2 - LAY.psw_body()[2] == pytest.approx(S.PSW_BODY_TO_EDGE)


def test_the_knob_coupon_has_both_positions_with_captive_sliding_stand_ins_and_nothing_sticks_out():
    kn = V.knob_v2()
    assert set(kn) == {"frame", "base", "knob_1", "knob_2"}
    frame, base = kn["frame"], kn["base"]
    assert len(frame.solids()) == 1 and len(base.solids()) == 1 and vol(frame, base) < TOL
    f2, pitch = LAY.frame[2], V.knob_pitch()
    assert frame.bounding_box().max.X == pytest.approx(f2) and base.bounding_box().max.X == pytest.approx(LAY.pcb[2])
    assert (base.bounding_box().min.Z, frame.bounding_box().max.Z) == pytest.approx((-S.PCB_T, 5.0))
    for i, (dx, dots) in enumerate(V.KNOB_VARIANTS):
        lay = V.shifted(dx)
        up = Pos(0, i * pitch, 0)
        for pos in (1, -1):
            k = up * C.knob_standin(pos, lay)
            assert vol(k, base) < TOL and vol(k, frame) < TOL and k.bounding_box().max.X < f2 - 0.5        # 当たらない・枠の外へ出ない
            assert vol(Pos(0, pos * 0.4, 0) * k, base) > 0.01                                               # 行程の端で止まる
            assert vol(Pos(0, 0, 0.8) * k, frame) > 0.01                                                    # 上へは抜けない（厚い屋根）
        a, b = C.knob_standin(1, lay).bounding_box(), C.knob_standin(-1, lay).bounding_box()
        assert a.min.Y - b.min.Y == pytest.approx(S.PSW_TRAVEL)                                             # 行程 1.6
        assert vol(up * C.knob_standin(1, lay), kn[f"knob_{i + 1}"]) == pytest.approx(kn[f"knob_{i + 1}"].volume)
        # 切り欠き: 内側の幅 10・外面で 14.8。つまみの上は枠が無い
        k = lay.psw_knob(1)
        assert not frame.is_inside((k[2] - 0.2, S.PSW_AT[1] + i * pitch, 4.9))
        n = lay.psw_notch()
        assert n[-1][1] - n[0][1] == pytest.approx(S.PSW_NOTCH[0]) and n[-2][1] - n[1][1] == pytest.approx(14.8)
        # 内側の面の上の縁は斜めに落ちている（scoop 2.0）・その下は厚い屋根が 1.2 残る
        x0, y = n[0][0], S.PSW_AT[1] + i * pitch
        assert not frame.is_inside((x0 - 0.5, y, 4.9)) and frame.is_inside((x0 - 0.5, y, 3.2)) and frame.is_inside((x0 - 2.5, y, 4.9))
        assert frame.is_inside((x0 - 0.1, y, C.psw_ceiling(lay) + 0.1)) and not frame.is_inside((x0 - 0.1, y, C.psw_ceiling(lay) - 0.1))
    # 見分ける点: (i) 1 個・(ii) 2 個（上面）
    x = V.knob_box()[0] + 3.0
    assert not frame.is_inside((x, S.PSW_AT[1], 4.9)) and frame.is_inside((x, S.PSW_AT[1] + 0.8, 4.9))
    assert not frame.is_inside((x, S.PSW_AT[1] + pitch + 0.8, 4.9)) and frame.is_inside((x, S.PSW_AT[1] + pitch, 4.9))
    assert overhangs(C.P.flip_to_bed(frame)) == [] or all(z < 0.5 for z, _ in overhangs(C.P.flip_to_bed(frame)))


@pytest.mark.slow
def test_the_fingertip_reaches_past_the_knob_tip_only_at_the_outer_position():
    """指先 = 半径 7.5 の硬い球（仮定）。机に置いたまま: (i) 前の位置は、切り欠きを広げても先まで届かない（基板の縁と机が先に当たる）。
    (ii) 0.75 外（= 本番）なら 0.16 届く。（v1 の切り欠き〔外面で 12.0〕と前の位置では −0.22 だった: 2026-10-04 に測った数。その形はもう作らない。）"""
    inner, out = (V.finger_reach(dx) for dx, _ in V.KNOB_VARIANTS)
    assert (inner["tip_in"], inner["open"], out["open"], out["tip_in"]) == pytest.approx((1.35, 14.8, 14.8, 0.6))
    assert inner["bite"] == pytest.approx(-0.03, abs=0.03) and out["bite"] == pytest.approx(0.16, abs=0.03)
    assert inner["bite"] < 0 < out["bite"]
    assert V.finger_reach(-S.COUPON_V2_PSW_SHIFT, r=2.0)["bite"] > 0.5                    # 検査器が生きている: 細い物（爪）なら (i) でも届く


# ---------------------------------------------------------------------------
# 本番の枠から切る物（slow）
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_the_knob_stub_formula_reproduces_the_real_frame_around_the_notch():
    """式から作った切れ端（本番の位置 = (ii)・足なし・入の印つき）が、本番の枠の立体と同じ（つまみのまわり）
    = **利用者が (ii) で触った切り欠きが、そのまま本番の枠に入っている**。"""
    box = V.knob_box()
    region = C._box((137.5, -46.0, box[2], -30.2), -1.0, 6.0)
    real, stub = C.frame_full() & region, V.knob_stub(0.0, 0, False, True) & region
    assert (real - stub).volume < TOL and (stub - real).volume < TOL and real.volume > 150
    # 検査器が生きている: (i) の位置の切れ端は違う形・入の印が無い切れ端も違う（印の体積ぶん）
    assert ((V.knob_stub(-S.COUPON_V2_PSW_SHIFT, 0, False, True) & region) - real).volume > 5.0
    mark = math.pi * (S.ON_MARK[0] / 2) ** 2 * S.ON_MARK[1]
    assert ((V.knob_stub(0.0, 0, False) & region) - real).volume == pytest.approx(mark, rel=0.05)


@pytest.mark.slow
def test_the_screw_pieces_are_the_real_walls_with_three_pilot_sizes():
    sc = V.screw_v2()
    full = C.frame_full()
    boxes = C.screw_coupon_boxes()
    old, depth = LAY.pilot()
    assert S.COUPON_V2_PILOTS == (1.5, 1.6, 1.7) and old == 1.6                           # 本番は、利用者が選んだ真ん中の径になった
    for name, want in (("back", (0.87, 0.81, 0.77)), ("side", (0.65, 0.59, 0.55))):
        piece = sc[f"frame_{name}"]
        holes = sc["holes"][name]
        assert [d for _, d in holes] == list(S.COUPON_V2_PILOTS) and len(piece.solids()) == 1
        box, screws, _ = boxes[name]
        real = full & C._box(box, -1.0, 6.0)
        if name == "back":
            # 違いは、下穴を開け直した輪（本番 φ1.6 より小さい φ1.5 は足す・大きい φ1.7 は削る）と、見分ける溝 1 ＋ 2 ＋ 3 本だけ
            added = sum(math.pi * max(0.0, old ** 2 - d ** 2) / 4 * depth for d in S.COUPON_V2_PILOTS)
            cut = sum(math.pi * max(0.0, d ** 2 - old ** 2) / 4 * depth for d in S.COUPON_V2_PILOTS)
            w, dp = S.COUPON_V2_MARK[:2]
            assert added > 0.3 and cut > 0.3
            assert (piece - real).volume == pytest.approx(added, rel=0.05) and (real - piece).volume == pytest.approx(6 * w * dp * 5.0 + cut, rel=0.1)
            assert [c for c, _ in holes] == screws
        else:
            assert piece.bounding_box().size.Y == pytest.approx(3 * V.UNIT) and holes[1][0] == screws[0]
        for ((x, y), d), m in zip(holes, want):
            assert not piece.is_inside((x + d / 2 - 0.03, y, 1.0)) and piece.is_inside((x + d / 2 + 0.03, y, 1.0))     # 径
            assert not piece.is_inside((x, y, depth - 0.1)) and piece.is_inside((x, y, depth + 0.2))                  # 深さは本番と同じ
            assert V.flesh(piece, x, y, d)[0] == pytest.approx(m, abs=0.03), (name, d)
            base = sc[f"base_{name}"]
            assert not base.is_inside((x, y, -0.8)) and base.is_inside((x + S.SCREW_HOLE_D / 2 + 0.2, y, -0.8))
        b = sc[f"base_{name}"].bounding_box()
        assert (b.min.Z, b.max.Z) == pytest.approx((-S.PCB_T, 0.0))
    # 掛かり（半径）: ISO 724 の M2。φ1.8 は山の高さの 46 %
    assert [round(V.thread_engagement(d)[0], 3) for d in (1.5, 1.6, 1.7, 1.8)] == [0.217, 0.2, 0.15, 0.1]
    assert V.thread_engagement(1.8)[1] == pytest.approx(0.46, abs=0.01) and S.M2_THREAD[1] == pytest.approx(2.0 - 1.0825 * 0.4)


@pytest.mark.slow
def test_everything_is_on_one_plate_that_fits_the_a1_mini():
    layout = V.plate_layout()
    assert [t for t, _, _ in layout] == ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"]
    plate = V.plate()
    size = plate.bounding_box().size
    assert len(plate.solids()) == 8 and max(size.X, size.Y) <= S.PRINT_MAX and plate.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
    boxes = [p.bounding_box() for _, _, p in layout]
    for i, a in enumerate(boxes):                                                              # 並べた物どうしは 3 以上離れている
        for b in boxes[i + 1:]:
            gap = max(a.min.X - b.max.X, b.min.X - a.max.X, a.min.Y - b.max.Y, b.min.Y - a.max.Y)
            assert gap >= 3.0
    holes = V.placed_holes()
    assert [d for _, d in holes["A1"]] == list(S.COUPON_V2_PILOTS) == [d for _, d in holes["A3"]]
    for tag in ("A1", "A3"):
        part = next(p for t, _, p in layout if t == tag)
        for (x, y), d in holes[tag]:
            assert not part.is_inside((x, y, 4.5)) and part.is_inside((x + d / 2 + 0.05, y, 4.5))
