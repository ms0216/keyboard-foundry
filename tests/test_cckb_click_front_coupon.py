"""cckb-click の「手前の縁を細くする」試し刷り（projects/cckb-click/click_coupon_front.py・docs/coupon-front.md）。

**生成した立体そのもの**を重ねる・動かす・切って見る。各検査に「故意に壊すと落ちる」を入れる。
外の事実: 本番の枠の立体（切れ端はそこから切る）・基板の厚さの公差（JLCPCB ±10 %）・スライスした G-code（Bambu Studio）。
本番の枠を作るので（約 40 秒）、ほとんどが slow。**本番の枠・基板を変えていないこと**は、既存の検査（test_cckb_click_case・_board）がそのまま通ることで見る。
"""

import math
import sys

import pytest
from build123d import Pos, export_stl

from conftest import ROOT, require

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
sys.path.insert(0, str(ROOT / "projects" / "cckb-click" / "tools"))
import click_case as C  # noqa: E402
import click_coupon_front as K  # noqa: E402
import click_coupon_v2 as V  # noqa: E402

LAY, S = C.LAY, C.S
TOL = 1e-3
vol = K.vol
pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# 形: 本番の枠の切れ端か・手前の縁の数
# ---------------------------------------------------------------------------

def test_the_strip_is_the_production_frame_from_the_hole_edge_to_the_back_rib():
    """穴の手前の縁から、奥のリブの手前（奥の厚い壁の手前）までは、本番の枠と同じ立体（穴・くぼみ・面取り・継ぎ目の溝・柱）。"""
    box = C._box((K.X0, K.HOLE_Y, K.X1, K.YC - LAY.rib() / 2 - 0.01), -3.0, 6.0)
    real = C.frame_full() & box
    assert [k.w for k in K.KS] == [1.0, 1.5, 2.25] and K.X1 - K.X0 == pytest.approx(4.75 * 19.05 + LAY.rib())
    for m in K.MARGINS:
        mine = K.frame(m) & box
        assert mine.volume == pytest.approx(real.volume, abs=0.01) and vol(mine, real) == pytest.approx(real.volume, abs=0.01)
        assert len(K.frame(m).solids()) == 1
    # 壊す: 1 mm ずれた枠なら同じにならない
    assert vol(Pos(1.0, 0, 0) * (K.frame(0.8) & box), real) < real.volume - 5.0


def test_the_front_margin_is_0_8_and_0_4_and_the_pocket_skin_is_what_is_left():
    """キャップから枠の外面まで 2.0 / 1.6（いまは 4.2）。くぼみは穴の縁から 0.6 外まで → 外の皮は 1.2 / 0.8。**立体に点を打って測る。**"""
    assert K.MARGINS == (0.8, 0.4) and K.HOLE_Y - K.POCKET_Y == pytest.approx(S.TAB_REACH + S.POCKET_CLEAR) == pytest.approx(0.6)
    assert K.HOLE_Y + S.CAP_CLEAR - LAY.frame[1] == pytest.approx(4.2)
    k = K.KS[-1]
    xt = LAY.hole(k)[0] + 1.5                                           # つばのくぼみの真ん中
    for m, face, skin in zip(K.MARGINS, (2.0, 1.6), (1.2, 0.8)):
        fr, g = K.frame(m), K.geom(m)
        assert fr.bounding_box().min.Y == pytest.approx(K.A1 - m, abs=1e-4) and g["cap_to_face"] == pytest.approx(face)
        z = S.FRAME_UNDER + 0.5
        assert fr.is_inside((xt, g["yo"] + 0.03, z)) and fr.is_inside((xt, K.POCKET_Y - 0.03, z))
        assert not fr.is_inside((xt, K.POCKET_Y + 0.03, z)) and not fr.is_inside((xt, g["yo"] - 0.03, z))
        assert g["skin"] == pytest.approx(skin) and K.POCKET_Y - g["yo"] == pytest.approx(skin)
        # 基板の手前の縁: いまの基板から 2.85（0.8）・3.25（0.4）引っ込める
        assert g["yb"] - LAY.pcb[1] == pytest.approx(3.0 - m + 0.65) and g["yb"] - g["yi"] == pytest.approx(K.GAP)


def test_caps_move_freely_in_both_strips_and_a_wall_that_reached_into_the_pockets_would_be_noticed():
    """キャップ 3 個を、掛かった位置・押し切り・四方へ傾けて押し切った姿で、枠と重ねる（本番の検査と同じ姿）。"""
    for m in K.MARGINS:
        fr = K.frame(m)
        for k in K.KS:
            for mode in ("latched",) + C.POSES:
                assert vol(C.cap_pose(k, mode), fr) < TOL, (m, k.w, mode)
    # 壊す: 壁の内面が 0.7 内へ入った枠（くぼみを越えて穴の中へ出る）は、押し切ったキャップに当たる
    bad = K.frame(0.4, 0.7)
    assert min(vol(C.cap_pose(k, "pressed"), bad) for k in K.KS) > 0.01


# ---------------------------------------------------------------------------
# 爪: 掛かり・公差・持ち上げたとき
# ---------------------------------------------------------------------------

def test_the_lip_reaches_0_45_under_the_board_and_the_numbers_at_the_tolerance_ends_are_stated():
    for m in K.MARGINS:
        fr, b = K.frame(m), K.board_in(m, S.PCB_T, False)
        low = fr & C._box((K.X0, K.A1 - 5.0, K.X1, K.HOLE_Y), -5.0, K.LIP_Z0 - 0.3)        # 爪の先のあたり
        assert low.bounding_box().max.Y - b.bounding_box().min.Y == pytest.approx(K.LIP_REACH - K.GAP, abs=1e-3) == pytest.approx(0.45, abs=1e-3)
        assert vol(fr, b) < TOL                                                             # 名目では当たらない
    tol = K.tolerances()
    assert (tol["print"]["engage_min"], tol["print"]["engage_max"]) == pytest.approx((0.30, 0.60))
    assert (tol["all"]["engage_min"], tol["all"]["gap_min"]) == pytest.approx((0.10, -0.20))         # 基板の外形 ±0.2 も足すと、隙は負 = 当たる
    assert (tol["print"]["play_min"], tol["print"]["play_max"]) == pytest.approx((-0.04, 0.453), abs=2e-3)
    assert K.play_calc(1.76, K.GAP) == pytest.approx(0.047, abs=1e-3) and K.play_calc(1.44, K.GAP) == pytest.approx(0.367, abs=1e-3)


@pytest.mark.parametrize("m", K.MARGINS)
def test_lifting_the_front_is_stopped_by_the_lip_after_the_stated_play(m):
    """枠の立体を持ち上げて、基板の代わりに当たるまでの量を測る。式（play_calc）と合うこと。爪の無い枠は止まらない。"""
    for t, want in zip(K.BOARD_TS, (0.407, 0.207, 0.007)):
        got = K.lift_play(m, t)
        assert got is not None and got == pytest.approx(want, abs=0.011) and K.play_calc(t) == pytest.approx(want, abs=1e-3)
    # 刷りの誤差の端（壁と爪が 0.15 基板の側・反対の側）
    assert K.lift_play(m, S.PCB_T, 0.15) == pytest.approx(K.play_calc(S.PCB_T, 0.0), abs=0.011)
    assert K.lift_play(m, S.PCB_T, -0.15) == pytest.approx(K.play_calc(S.PCB_T, 0.30), abs=0.011)
    # きつい端: 厚さ 1.76 で壁が 0.15 寄ると、組んだ位置で 0.04 食い込む（立体でも重なる）
    assert K.play_calc(1.76, 0.0) == pytest.approx(-0.04, abs=1e-3)
    assert vol(K.frame(m, 0.15), K.board_in(m, 1.76, False)) > TOL
    # 壊す: 爪の無い枠は、どこまで上げても当たらない
    no_lip = K.frame(m, 0.0, False) & C._box((K.X0 - 1, K.A1 - 5, K.X1 + 1, K.HOLE_Y + 1), -5, 1)
    b = K.board_in(m, S.PCB_T, False)
    assert all(vol(Pos(0, 0, dz) * no_lip, b) < TOL for dz in (0.0, 0.3, 1.0, 2.0))


def test_the_lip_only_holds_while_the_back_screws_keep_the_board_from_sliding_back():
    """留めているのは奥のねじ: ねじを外して基板の代わりを奥へ 0.5 引くと、爪は掛からない（外せる）。引かなければ、持ち上げると当たる。"""
    for m in K.MARGINS:
        hook = K._hook(m)
        b = K.board_in(m, S.PCB_T, False)
        assert vol(Pos(0, 0, 1.0) * hook, b) > TOL
        assert all(vol(Pos(0, 0, dz) * hook, Pos(0, 0.5, 0) * b) < TOL for dz in (0.0, 0.5, 1.0, 3.0))
        assert K.LIP_REACH - K.GAP < 0.5


# ---------------------------------------------------------------------------
# 入れられるか・外せるか（立体を段ごとに動かす）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("m", K.MARGINS)
def test_every_board_can_be_tilted_in_and_swung_down_and_taken_out_the_same_way(m):
    for t in K.BOARD_TS:
        for th in (0.0, 10.0, 20.0):
            path = K.insert_path(m, t, th)
            assert path is not None and path[0][0] == th and path[-1] == (0.0, 0.0), (t, th)
            assert all(abs(b[1] - a[1]) <= 0.101 for a, b in zip(path, path[1:]))          # 段の間で飛ばない
    # 道の各段で、スイッチの代わりの付いた板の全部を、枠の全部と、掛かった位置のキャップに重ねる
    fr, caps = K.frame(m), K.caps()
    for t in (S.PCB_T, K.BOARD_TS[-1]):
        b = K.board_in(m, t)
        for th, dy in K.insert_path(m, t, 10.0):
            p = K.posed(b, m, th, dy)
            assert vol(fr, p) < TOL and all(vol(c, p) < TOL for c in caps), (t, th, dy)
    # 10° で差すには、奥へ 0.15（厚さ 1.6）〜0.25（1.8）引いた所から
    assert K.insert_path(m, S.PCB_T, 10.0)[0][1] == pytest.approx(0.15) and K.insert_path(m, 1.8, 10.0)[0][1] == pytest.approx(0.25)


def test_the_insertion_check_notices_a_lip_that_is_too_long_and_a_board_that_is_too_thick():
    """壊す: 手前の縁が 0.3 長い板は、組んだ位置で壁に食い込む = 道が無い。厚さ 2.4 の板は、爪の先と載る面の間（2.07）を通らない。"""
    m = K.MARGINS[0]
    assert K.insert_path(m, S.PCB_T, 10.0, edge=0.3) is None and K.insert_path(m, S.PCB_T, 10.0, edge=0.1) is not None
    assert K.insert_path(m, 2.4, 10.0) is None and K.insert_path(m, 2.4, 0.0) is None
    assert 0.0 - K.geom(m)["tip_z"] == pytest.approx(2.066, abs=1e-3)


# ---------------------------------------------------------------------------
# 下へ出る物・奥のねじ・刷る向き
# ---------------------------------------------------------------------------

def test_only_the_front_wall_and_lip_go_below_the_board_top_and_the_lip_ends_0_1_below_the_sheet():
    for m in K.MARGINS:
        fr, g = K.frame(m), K.geom(m)
        bb = fr.bounding_box()
        assert bb.min.Z == pytest.approx(K.LIP_BOTTOM) == pytest.approx(-2.2)
        assert -S.PCB_T - bb.min.Z == pytest.approx(0.6)                                    # 基板の下面（名目）から 0.6 下
        below_sheet = -S.PCB_T - S.BOTTOM_SHEET_T - bb.min.Z
        assert below_sheet == pytest.approx(0.1) == pytest.approx(S.SCREW_HEAD_H - S.BOTTOM_SHEET_T)   # 底のシート 0.5 では隠れない。ねじの頭と同じ
        assert vol(fr, C._box((K.X0 - 1, g["tip_y"] + 0.01, K.X1 + 1, 0.0), -5.0, -0.02)) < TOL        # 爪の先より奥には、基板の上面より下の物が無い
        assert vol(fr, C._box((K.X0 - 1, g["yo"] - 1, K.X1 + 1, g["tip_y"]), -5.0, -0.02)) > 50.0


def test_the_back_wall_is_fastened_like_the_production_perimeter_and_one_board_fits_both_strips():
    d, depth = LAY.pilot()
    assert (d, depth, S.SCREW_L) == (1.6, 2.8, 4.0)
    real = V.flesh(C.frame_full(), -19.05, 48.225, d)[0]                                    # 本番の奥の壁のねじ（キーの辺の真ん中）
    for m in K.MARGINS:
        fr, b = K.frame(m), K.board_in(m)
        for x, y in K.pilots(m):
            assert K.back_face(m) - y == pytest.approx(S.SCREW_FROM_EDGE)
            assert not fr.is_inside((x, y, depth - 0.1)) and fr.is_inside((x, y, depth + 0.1))
            assert not b.is_inside((x, y, -0.5)) and b.is_inside((x + S.SCREW_HOLE_D / 2 + 0.05, y, -0.5))    # 板の穴は下穴の真上
            assert V.flesh(fr, x, y, d)[0] >= real - 0.03
        assert vol(K.screws(m), b) < TOL and vol(K.screws(m), fr) > 0.5                     # ねじは板の穴を通り、枠に食い込む
        assert K.back_face(m) - b.bounding_box().max.Y == pytest.approx(S.PCB_INSET_Y)
    assert V.flesh(K.frame(0.8), *K.pilots(0.8)[0], d)[0] == pytest.approx(real, abs=0.03)
    # スイッチの代わりは、どちらの枠でもキーの中心から 0.2 以内
    for m in K.MARGINS:
        assert abs(K.standin_dy() + K.geom(m)["off"]) == pytest.approx(0.2)


def test_printed_top_down_the_only_overhangs_are_the_lip_slope_and_the_three_seam_notch_roofs():
    """枠は上面をベッドに刷る。宙へ張り出す面は、爪の掛かる面（水平から 30° = 1 層 0.17）と、奥の厚い壁が継ぎ目の溝をまたぐ所 3 つ（本番の奥の壁と同じ）だけ。"""
    assert K.LIP_SLOPE == 30.0
    step = S.PRINT_LAYER / math.tan(math.radians(K.LIP_SLOPE))
    assert step == pytest.approx(0.173, abs=1e-3) and step < 0.5 * 0.42
    for m in K.MARGINS:
        part = K.P.flip_to_bed(K.frame(m))
        assert part.bounding_box().size.Z == pytest.approx(7.2) and K.P.on_layer(7.2)
        down = []
        for f in part.faces():
            try:
                nz = f.normal_at().Z
            except Exception:
                continue
            if nz < -0.72 and f.center().Z > 1e-3:
                down.append((round(f.center().Z, 2), round(f.area, 2), round(nz, 3)))
        slope = [q for q in down if q[2] > -0.99]
        flat = [q for q in down if q[2] <= -0.99]
        assert len(slope) == 1 and slope[0][2] == pytest.approx(-math.cos(math.radians(30)), abs=1e-3)
        assert slope[0][1] == pytest.approx((K.X1 - K.X0) * K.LIP_REACH / math.cos(math.radians(30)), rel=0.01)
        assert len(flat) == 3 and all(z == pytest.approx(2.0, abs=0.02) and a == pytest.approx(S.SEAM_NOTCH[0] * S.SEAM_NOTCH[1], abs=0.02) for z, a, _ in flat), flat


def test_the_plate_fits_the_a1_mini_and_the_point_mapping_lands_where_the_solids_are():
    lay = K.plate_layout()
    assert [t for t, *_ in lay] == ["C1", "C2", "C3", "B1", "B2", "B3", "F08", "F04"]
    plate = K.plate()
    bb = plate.bounding_box()
    assert max(bb.size.X, bb.size.Y) <= S.PRINT_MAX and bb.min.Z == pytest.approx(0.0, abs=1e-6) and len(plate.solids()) == 8
    boxes = [p.bounding_box() for _, _, _, p, _ in lay]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert max(b.min.X - a.max.X, a.min.X - b.max.X, b.min.Y - a.max.Y, a.min.Y - b.max.Y) >= 3.99
    for m, tag in zip(K.MARGINS, ("F08", "F04")):
        part, fn = next((p, f) for t, _, _, p, f in lay if t == tag)
        (x, y), g = K.pilots(m)[0], K.geom(m)
        assert not part.is_inside(fn((x, y, 1.0))) and part.is_inside(fn((x + 1.2, y, 1.0)))
        assert part.is_inside(fn((x, g["yo"] + 0.4, -1.0))) and not part.is_inside(fn((x, g["yo"] + 1.0, -1.0)))
        assert fn((x, y, S.FRAME_UNDER + S.FRAME_T))[2] == pytest.approx(0.0, abs=1e-6)                # 上面がベッド
        assert fn((x, y, K.LIP_BOTTOM))[2] == pytest.approx(7.2, abs=1e-6)                             # 爪がいちばん上


# ---------------------------------------------------------------------------
# スライスした線
# ---------------------------------------------------------------------------

def test_the_line_counter_counts_lines_and_notices_a_gap():
    import slice_front as SF

    layer = [dict(feat="Outer wall", pts=[(0, 0.2), (10, 0.2)], ws=[0.4]), dict(feat="Inner wall", pts=[(10, 0.6), (0, 0.6)], ws=[0.4]),
             dict(feat="Outer wall", pts=[(0, 5.0), (10, 5.0)], ws=[0.4])]
    r = SF.measure({1.0: layer}, 5.0, 0.0, 0.8, 0.95)
    assert (r["n"], r["span"], r["fill"], r["walls"], r["z"]) == (2, 0.8, 0.8, 2, 1.0)
    assert SF.measure({1.0: layer}, 5.0, 2.0, 3.0, 0.95)["n"] == 0                          # 線の無い所
    assert SF.measure({1.0: layer}, 11.0, 0.0, 0.8, 0.95)["n"] == 0                         # 線の端の外


def test_the_sliced_plate_has_the_thin_wall_and_lip_as_real_lines_without_supports(tmp_path, monkeypatch):
    """Bambu Studio で実際にスライスして、細い所の線の本数・覆う幅・爪の斜面の 1 層ごとの張り出し・下穴の径を G-code から測る。"""
    import slice_front as SF
    import slice_precise as SP

    require(SP.BAMBU, "Bambu Studio")
    stl = tmp_path / "coupon_front_plate.stl"
    export_stl(K.plate(), str(stl))
    rc = SP.recipe("n04", S, "bambu")
    gcode, log = SP.slice_stl(rc, stl, out=tmp_path / "s")
    assert gcode is not None, log[-500:]
    applied, n = SP.applied_problems(rc, SP.gcode_config(gcode.read_text(errors="replace")))
    assert not applied and n >= 20
    assert rc["process"]["enable_support"] in ("0", 0, False)
    problems, facts = SF.check(gcode, rc)
    assert problems == [], problems
    want = {"F08 wall": (2, 0.8), "F08 lip": (3, 1.4), "F08 skin": (3, 1.2), "F08 rail": (4, 1.8),
            "F04 wall": (2, 0.8), "F04 lip": (3, 1.4), "F04 skin": (2, 0.8), "F04 rail": (3, 1.4)}
    for name, (lines, width) in want.items():
        r = next(v for k, v in facts.items() if k.startswith(name + "（"))
        assert r["本数"] == lines and r["覆う幅"] == pytest.approx(width, abs=0.02), (name, r)
    for tag in ("F08", "F04"):
        r = facts[f"{tag} 爪の斜面"]
        assert r["張り出しの合計"] == pytest.approx(K.LIP_REACH, abs=0.05) and r["層ごとの最大"] < 0.21 and r["層の数"] >= 6
    other = [ln for ln in log.splitlines() if "error" in ln.lower() and SF.KNOWN not in ln]
    assert not other and sum(SF.KNOWN in ln for ln in log.splitlines()) <= SF.KNOWN_MAX
    # 壊す 1: 数える所を 1 mm ずらすと（樹脂の無い所を含む）、合わないと言う
    real = K.probes
    monkeypatch.setattr(K, "probes", lambda m: {k: (x, y0 - 1.0, y1, z) for k, (x, y0, y1, z) in real(m).items()})
    bad, _ = SF.check(gcode, rc)
    assert len(bad) >= 8
    monkeypatch.setattr(K, "probes", real)
    # 壊す 2: 爪の出が設計と違えば（0.9 のつもりで 0.6 が刷られる）気づく
    monkeypatch.setattr(K, "LIP_REACH", 0.9)
    bad, _ = SF.check(gcode, rc)
    assert any("爪の張り出し" in q for q in bad)
