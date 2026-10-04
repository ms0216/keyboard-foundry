"""cckb-click の試し刷り v2（ねじの下穴 3 通り・つまみの位置 2 つ・蓋の留め方 3 通り）。projects/cckb-click/click_coupon_v2.py。

**生成した立体そのもの**を重ねる・動かす・切って見る。各検査に「故意に壊すと落ちる」を入れる。
外の事実: M2 並目の寸法（ISO 724: 外径 2.0・めねじの内径 1.567）・片持ち梁の式（骨組みの解き方の物差し）・
本番の枠の立体（切れ端はそこから切る）・利用者が刷った v1 の結果（蓋が留まらない = 掛かり 0.25 では足りない）。
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


# ---------------------------------------------------------------------------
# 蓋のばね（計算）と蓋の立体
# ---------------------------------------------------------------------------

def test_the_frame_solver_agrees_with_the_cantilever_formula():
    """骨組みの解き方の物差し: 片持ち梁を先で δ 押したときのひずみ 1.5·t·δ/a²・力 E·b·t³·δ/(4·a³)（click_case.cover_spring と同じ式）。"""
    a, t, b = 5.5, 0.7, 1.2
    u, strain = V.frame_fe([(0.0, 0.0), (a, 0.0)], [(0, 1, t)], 0, 1, b)
    per_n = -u[1][1]
    assert strain[0] * (0.25 / per_n) == pytest.approx(1.5 * t * 0.25 / a ** 2, rel=1e-6)
    assert 0.25 / per_n == pytest.approx(C.PLA_E * b * t ** 3 * 0.25 / (4 * a ** 3), rel=1e-6)
    # v1 の並び（まっすぐな腕 2 本・太さ 0.7・効く長さ 5.5）で掛かりを 0.6 にすると 2.1 %: 許容を超える = 掛かりを増やすには形を変えるしかない
    assert strain[0] * (0.6 / per_n) > 2 * S.PLA_STRAIN_LIMIT


@pytest.mark.parametrize("n, hook, strain, hold", [(1, 0.6, 0.0071, 1.2), (2, 0.45, 0.0084, 0.58)])
def test_the_cover_springs_stay_under_the_strain_limit_with_a_bigger_hook_than_v1(n, hook, strain, hold):
    sp = V.spring(n)
    assert sp["delta"] == hook and hook > 1.7 * S.COVER_BUMP[0]                        # v1 の掛かり 0.25 より大きい
    assert sp["strain"] == pytest.approx(strain, abs=2e-4) and sp["strain"] <= S.PLA_STRAIN_LIMIT
    assert V.spring(n, 0.06)["strain"] <= S.PLA_STRAIN_LIMIT                           # 刷り上がりの太り 0.06 でも
    assert sp["hold"] == pytest.approx(hold, abs=0.05)
    g = V._geom(n)
    gap = (g["sag"] if n == 1 else g["arm"][2])
    assert sp["sag"] <= gap - 0.1                                                       # 腕の先の下がりが、下の隙間に収まる
    relief = g.get("relief", 0.0)
    assert sp["lean"] <= relief + S.COVER_CLEAR - 0.05                                  # 山が外へ倒れても口の壁に当たらない


def test_the_spring_check_notices_a_thicker_arm_and_a_bigger_hook(monkeypatch):
    covers = {k: dict(v) for k, v in S.COUPON_V2_COVERS.items()}
    covers[1]["hook"], covers[2]["arm"] = 0.9, (7.0, 0.7, 0.75)
    monkeypatch.setattr(S, "COUPON_V2_COVERS", covers)
    assert V.spring(1)["strain"] > S.PLA_STRAIN_LIMIT and V.spring(2)["strain"] > S.PLA_STRAIN_LIMIT


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


@pytest.mark.parametrize("n", [1, 2, 3])
def test_each_cover_is_one_solid_with_the_v1_outline_and_prints_front_face_down(n):
    cover = V.cover_v2(n)
    assert len(cover.solids()) == 1 and cover.is_valid
    b, old = cover.bounding_box(), C.cover_solid().bounding_box()
    rib = S.COUPON_V2_COVERS[3]["rib"][0] if n == 3 else 0.0
    assert (b.min.X, b.max.X) == pytest.approx((old.min.X - rib, old.max.X + rib), abs=1e-6)
    assert (b.min.Y, b.max.Y, b.min.Z, b.max.Z) == pytest.approx((old.min.Y, old.max.Y, old.min.Z, old.max.Z), abs=1e-6)
    pr = V.cover_print(n)
    assert pr.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
    # 45° より寝た下向きの面: 見分ける点（上の板の横穴・直径 1.0）の天井だけ
    assert all(a < 0.5 for _, a in overhangs(pr)), overhangs(pr)
    assert len(V.cover_v2(n, hooks=False).solids()) == 1


def test_the_hairpin_and_the_thin_arms_are_where_the_spring_model_says():
    """ばねの骨組み（spring）と立体が同じ寸法か: 腕の中は詰まり、隙間は空いている。"""
    cv = LAY.cover()
    y = (cv["y0"] + cv["y_front"]) / 2
    g = V._geom(1)
    cover = V.cover_v2(1)
    for sg in (-1, 1):
        x = lambda u: g["xm"] + sg * u                                                    # noqa: E731
        um = (g["u_u0"] + g["u_riser"]) / 2
        assert cover.is_inside((x(um), y, sum(g["z1"]) / 2)) and cover.is_inside((x(um), y, sum(g["z2"]) / 2))
        assert not cover.is_inside((x(um), y, (g["z2"][1] + g["z1"][0]) / 2)) and not cover.is_inside((x(um), y, g["z2"][0] - 0.2))
        assert cover.is_inside((x(um), y, g["z1"][1] - 0.05)) and not cover.is_inside((x(um), y, g["z1"][0] - 0.05))       # 太さ 0.7
        assert g["z1"][1] - g["z1"][0] == pytest.approx(0.7) and g["z2"][1] - g["z2"][0] == pytest.approx(0.7)
        assert cover.is_inside((x((g["u_u1"] + g["u_u0"]) / 2), y, g["z1"][0] - 0.2))                                     # 折り返し
        assert not cover.is_inside((x((g["u_post"] + g["u_u1"]) / 2), y, g["z1"][0] - 0.2))                               # 柱との隙間
        assert cover.is_inside((x((g["u_neck"] + g["u_leg1"]) / 2), y, g["z_arm"] + 0.2))                                 # 付け根（上の板へ）
        assert not cover.is_inside((x(g["u_neck"] - 0.5), y, g["z_arm"] + 0.2))
        assert cover.is_inside((x(sum(g["hook_u"]) / 2), cv["y0"] + 1.3, g["z_arm"] + g["h"] - 0.05))                     # 山の頂
        assert not cover.is_inside((x(g["half"] - 0.2), y, sum(g["z2"]) / 2))                                             # 端の逃げ
        assert cover.is_inside((x(g["half"] - 0.2), y, g["z_slab"] - 0.2))                                                # 下の板は端まで
    g = V._geom(2)
    cover = V.cover_v2(2)
    um = (g["u_post"] + g["hook_u"][0]) / 2
    assert cover.is_inside((g["xm"] + um, y, sum(g["z1"]) / 2)) and not cover.is_inside((g["xm"] + um, y, g["z1"][0] - 0.2))
    assert g["z1"][1] - g["z1"][0] == pytest.approx(0.45) and g["hook_u"][0] - g["u_post"] == pytest.approx(V.spring(2)["lever"])


# ---------------------------------------------------------------------------
# つまみ（式から作った壁の切れ端）
# ---------------------------------------------------------------------------

def test_the_two_switch_positions_are_the_current_one_and_one_0_75_further_out():
    f2, p2 = LAY.frame[2], LAY.pcb[2]
    for dx, tip_board, tip_frame, body in ((0.0, 1.05, 1.35, 2.5), (S.COUPON_V2_PSW_SHIFT, 0.30, 0.60, 1.75)):
        lay = V.shifted(dx)
        k = lay.psw_knob(1)
        assert (p2 - k[2], f2 - k[2], p2 - lay.psw_body()[2]) == pytest.approx((tip_board, tip_frame, body))
    assert V.shifted(0.0) is LAY and S.PSW_AT == (141.125, -38.1)                         # 本番の値は動かしていない
    assert p2 - V.shifted(S.COUPON_V2_PSW_SHIFT).psw_body()[2] < S.PSW_EDGE_MIN           # (ii) は JLC の「2.5 以上」を割る


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
        n = V.notch_v2(lay)
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
    """指先 = 半径 7.5 の硬い球（仮定）。机に置いたまま: いまの位置は、切り欠きを広げても先まで届かない（基板の縁と机が先に当たる）。
    0.75 外なら 0.16 届く。v1 の切り欠きでは 0.22 足りない（利用者の「奥に入りすぎ」と同じ向き）。"""
    old, new, out = V.finger_reach(0.0, "v1"), V.finger_reach(0.0, "v2"), V.finger_reach(S.COUPON_V2_PSW_SHIFT, "v2")
    assert (old["tip_in"], old["open"], new["open"], out["tip_in"]) == pytest.approx((1.35, 12.0, 14.8, 0.6))
    assert old["bite"] == pytest.approx(-0.22, abs=0.03) and new["bite"] == pytest.approx(-0.03, abs=0.03) and out["bite"] == pytest.approx(0.16, abs=0.03)
    assert old["bite"] < new["bite"] < 0 < out["bite"]
    assert V.finger_reach(0.0, "v2", r=2.0)["bite"] > 0.5                                 # 検査器が生きている: 細い物（爪）なら届く


# ---------------------------------------------------------------------------
# 本番の枠から切る物（slow）
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_the_knob_stub_formula_reproduces_the_real_frame_around_the_notch():
    """式から作った切れ端（v1 の切り欠き・足なし）が、本番の枠の立体と同じ（つまみのまわり）。"""
    box = V.knob_box()
    region = C._box((137.5, -46.0, box[2], -30.2), -1.0, 6.0)
    real, stub = C.frame_full() & region, V.knob_stub(0.0, "v1", 0, False) & region
    assert (real - stub).volume < TOL and (stub - real).volume < TOL and real.volume > 150
    assert (real - (V.knob_stub(0.0, "v2", 0, False) & region)).volume > 5.0              # 検査器が生きている: 新しい切り欠きは違う形


@pytest.mark.slow
def test_the_screw_pieces_are_the_real_walls_with_three_pilot_sizes():
    sc = V.screw_v2()
    full = C.frame_full()
    boxes = C.screw_coupon_boxes()
    old, depth = LAY.pilot()
    assert S.COUPON_V2_PILOTS == (1.5, 1.6, 1.7) and old == 1.8
    for name, want in (("back", (0.87, 0.81, 0.77)), ("side", (0.65, 0.59, 0.55))):
        piece = sc[f"frame_{name}"]
        holes = sc["holes"][name]
        assert [d for _, d in holes] == list(S.COUPON_V2_PILOTS) and len(piece.solids()) == 1
        box, screws, _ = boxes[name]
        real = full & C._box(box, -1.0, 6.0)
        if name == "back":
            # 違いは、下穴を埋めて開け直した輪（3 つ）と、見分ける溝 1 ＋ 2 ＋ 3 本だけ
            ring = sum(math.pi * (old ** 2 - d ** 2) / 4 * depth for d in S.COUPON_V2_PILOTS)
            w, dp = S.COUPON_V2_MARK[:2]
            assert (piece - real).volume == pytest.approx(ring, rel=0.05) and (real - piece).volume == pytest.approx(6 * w * dp * 5.0, rel=0.1)
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


def hook_only(n, sg):
    g = V._geom(n)
    xa, xb = sorted((g["xm"] + sg * g["hook_u"][0], g["xm"] + sg * (g["half"] + 0.1)))
    return V.cover_v2(n) & C._box((xa - 0.01, -60, xb, -40), g["z_arm"] - 1.0, 6.0)


@pytest.mark.slow
def test_the_cover_stub_is_the_real_mouth_with_a_deeper_groove_and_all_three_covers_fit_it():
    stub, plain_stub = V.cover_stub(), V.cover_stub(False)
    box = V.cover_box()
    real = C.frame_full() & C._box(box, -1.0, 6.0)
    assert (real - plain_stub).volume < TOL and (plain_stub - real).volume == pytest.approx(18.375, abs=0.1)    # 足したのは奥の両端の足（1.5 角・屋根の下まで）だけ
    cut = plain_stub - stub
    assert 3.0 < cut.volume < 6.0 and len(stub.solids()) == 1
    cv = LAY.cover()
    for x in (cv["x0"] + 0.9, cv["x1"] - 0.9):
        assert stub.is_inside((x, cv["y0"] + 0.2, cv["z_slot"] + 0.3))                         # 手前の肉 0.4
        assert not stub.is_inside((x, cv["y0"] + 0.6, cv["z_slot"] + 0.6)) and stub.is_inside((x, cv["y0"] + 0.6, cv["z_slot"] + 0.8))   # 溝の深さ 0.7
    parts = C.board_parts()
    others = {"電池": C.cell_solid(), "クリップ": parts["BT1"], "基板": C.pcb_solid()}
    for n, want in ((1, 0.6), (2, 0.45)):
        cover = V.cover_v2(n)
        assert vol(stub, cover) < TOL and all(vol(v, cover) < TOL for v in others.values()), n
        d = V.detent(stub, cover)
        assert d["left"][0] == pytest.approx(want, abs=0.01) and d["right"][0] == pytest.approx(want, abs=0.01)   # 掛かり = ばねの計算のたわみ
        assert V.spring(n)["delta"] == want
        # 蓋が基板まで 0.1 下がっても掛かりは残る（v1 は 0.15 しか残らなかった）。0.1 浮いても山は溝の天井に当たらない
        # （ひさしまでの 0.15 いっぱいに浮くと、蓋 1 の山の頂が溝の天井を 0.05 押す = 腕が 0.05 たわむだけ）
        low = V.detent(stub, Pos(0, 0, -0.1) * cover)
        assert low["left"][0] == pytest.approx(want - 0.1, abs=0.01) and vol(stub, Pos(0, 0, 0.1) * cover) < TOL
        # v1 の浅い溝のままの枠には入らない（山が口の上の壁に当たる）= 枠も刷り直す
        assert vol(plain_stub, cover) > 0.05
        # 入れる・外す間、山が電池に当たらない: 手前へ s 引いた所で、山は「枠との重なりの高さ」だけ下がる
        for sg in (-1, 1):
            hook = hook_only(n, sg)
            for i in range(0, 45):
                s = 0.05 * i
                moved = Pos(0, -s, 0) * hook
                hit = stub & moved
                dz = 0.0 if hit is None or not hit.solids() else max(q.bounding_box().size.Z for q in hit.solids())
                assert vol(others["電池"], Pos(0, 0, -dz) * moved) < TOL, (n, s, dz)
    # 山・筋の無い形は、手前へまっすぐ抜ける（枠・電池・クリップ・基板に当たらない）。面一
    for n in (1, 2, 3):
        plain = V.cover_v2(n, hooks=False)
        for i in range(0, 28):
            moved = Pos(0, -0.25 * i, 0) * plain
            assert vol(stub, moved) < TOL and all(vol(v, moved) < TOL for v in others.values()), (n, i)
        b = V.cover_v2(n).bounding_box()
        assert (b.max.Z, b.min.Y) == pytest.approx((5.0, LAY.frame[1]), abs=1e-6)
        for d in ((0, 0, 0.35), (0, 0.3, 0), (0.4, 0, 0), (-0.4, 0, 0)):                       # 上（ひさし）・奥・左右は枠が止める
            assert vol(stub, Pos(*d) * plain) > 0.01, (n, d)
    # 蓋 3: 筋だけが枠に食い込む（片側 0.10・4 本）
    c3 = V.cover_v2(3)
    hit = stub & c3
    assert 0.03 < hit.volume < 0.15 and len(hit.solids()) == 4 and all(vol(v, c3) < TOL for v in others.values())
    assert max(q.bounding_box().size.X for q in hit.solids()) == pytest.approx(S.COUPON_V2_COVERS[3]["rib"][0] - S.COVER_CLEAR, abs=0.01)
    # 蓋が無くても電池は出し入れできる（溝を深くした枠で）
    (cx, cy), r = LAY.cell()
    path = C._union([Pos(0, -0.5 * i, 0) * C.cell_solid() for i in range(0, 40)])
    assert vol(stub, path) < TOL


@pytest.mark.slow
def test_v1_cover_diagnosis_the_bump_is_small_and_the_cover_floats():
    """利用者が刷った v1 の蓋は留まらなかった。立体から: 掛かり 0.25・蓋は下へ 0.1 上へ 0.15 動ける。"""
    stub = V.cover_stub(False)
    cover, plain = C.cover_solid(), C.cover_solid(False)
    assert V.detent(stub, cover)["left"][0] == pytest.approx(0.25, abs=0.01)
    assert V.detent(stub, Pos(0, 0, -0.1) * cover)["left"][0] == pytest.approx(0.15, abs=0.01)
    assert vol(stub, Pos(0, 0, 0.15) * plain) < TOL and vol(stub, Pos(0, 0, 0.25) * plain) > 0.05
    assert cover.bounding_box().min.Z == pytest.approx(0.1)


@pytest.mark.slow
def test_everything_is_on_one_plate_that_fits_the_a1_mini():
    layout = V.plate_layout()
    assert [t for t, _, _ in layout] == ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4", "C5"]
    plate = V.plate()
    size = plate.bounding_box().size
    assert len(plate.solids()) == 13 and max(size.X, size.Y) <= S.PRINT_MAX and plate.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
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
