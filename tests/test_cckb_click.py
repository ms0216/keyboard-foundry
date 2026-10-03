"""cckb-click（タクトスイッチ＋枠の下から入れるキャップ）の試し刷り。projects/cckb-click/{spec,click_parts,click_coupons}.py。

**生成した立体そのもの**を切る・動かす・重ねて見る（式どうしを比べない）。各検査の下に「故意に壊すと落ちる」検査を置く
（CLAUDE.md 検証の作法 2）。壊す検査は、壊した値で立体を作り直して同じ関数に通す。

外の事実: スイッチは Alps SKRAAWE010 の製品仕様書（spec.py の各行に項目）、平面と高さは販売者の公開 STEP の実測
（決定記録 2026-10-03-structure）。印刷機は A1 mini の実効 168.4（docs/knowledge/case-and-print.md）。
"""

import json
import math
import re
import sys
import types
from dataclasses import replace

import pytest
import trimesh
from build123d import Box, GeomType, Plane, Pos, Rot, Vector

from conftest import ROOT
from foundry import gate
from foundry.layout import UNIT
from foundry.project import load
from foundry.verify import intersection_volume

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
import click_coupons as CC  # noqa: E402
import click_parts as P  # noqa: E402

S = P.S
PROJECT = ROOT / "projects" / "cckb-click"
TOL = 1e-4          # mm3。面が触れているだけの組の丸め
MIN_SKIN = 0.6      # くぼみの上に残す枠の皮の厚さ（0.4 未満は「無い」のと同じ: case-and-print.md。穴を広げた列でも残るように 0.6）


def spec_with(**over):
    ns = {k: getattr(S, k) for k in dir(S) if k.isupper()}
    ns.update(over)
    return types.SimpleNamespace(**ns)


def key(s=S, **kw):
    """1 マスの組（枠・板・キャップ）。板はスイッチの代わりの台を載せない（台は固い。押し切りでは別に見る）。"""
    c = P.Cell(0.0, 0.0, kw.pop("hole", s.HOLE_B), **kw)
    return c, P.frame([c], s), P.base([c], s), P.cap(c, s)


# ---------------------------------------------------------------------------
# 積み上げ（R1・R3）
# ---------------------------------------------------------------------------

def stack_problems(s=S):
    lv = P.levels(s)
    out = []
    if lv["preload_max"] > 1e-9:
        out.append(f"ステムが一番高い {lv['stem_max']:.2f} と押す面 {lv['pad']:.2f}: {lv['preload_max']:.2f} 押しっぱなし（R1）")
    if lv["pad_lowest"] < s.SW_BODY_H - 1e-9:
        out.append(f"押し切りで押す面 {lv['pad_lowest']:.2f} がスイッチの本体 {s.SW_BODY_H} に当たる（R3）")
    if lv["cap_top"] - lv["descent_max"] < lv["frame_top"] - 1e-9:
        out.append(f"押し切りでキャップの上面 {lv['cap_top'] - lv['descent_max']:.2f} が枠の上面 {lv['frame_top']} より沈む（指が枠に当たって押し切れない）")
    return out


def test_the_stack_never_preloads_the_switch_and_never_bottoms_on_it():
    assert stack_problems() == []
    lv = P.levels()
    # 記録にある数（docs/decisions/2026-10-03-structure.md）と同じか。変えたら記録も直す
    assert (lv["pad"], lv["cap_top"], lv["float_nominal"], lv["float_max"]) == pytest.approx((3.6, 6.0, 0.2, 0.4))
    assert 0.5 + S.PCB_T + lv["cap_top"] == pytest.approx(8.1)          # 底のシート 0.5 ＋ 基板 ＋ キャップの上面 = 目標の厚さ


@pytest.mark.parametrize("over, word", [
    (dict(TAB_T=0.6), "R1"),                      # つばを厚くすると押す面が 3.4 に下がり、ステム 3.6 で 0.2 押しっぱなし
    (dict(SW_OVERTRAVEL=0.3), "R3"),              # 底を突くまでが長ければ本体に当たる
    (dict(POCKET_DEPTH=1.2), "押し切れない"),      # 押す面を上げると浮きが増え、押し切りでキャップが枠より沈む
])
def test_the_stack_check_notices_a_broken_stack(over, word):
    assert any(word in p for p in stack_problems(spec_with(**over)))


def test_the_switch_numbers_match_the_datasheet_and_the_standin_is_built_from_them():
    """SKRAAWE010 PRODUCT SPECIFICATIONS の数（外形図・7.2・C11・C12）。**ここは仕様書から打ち直した 2 つ目の写し**——
    spec.py を 1 か所ずらすと落ちる。スイッチの代わりの台は、その数で作られているかを立体で測る。"""
    assert (S.SW_BODY, S.SW_BODY_H, S.SW_STEM_D, S.SW_STEM_TOP, S.SW_STEM_TOP_TOL) == (6.2, 2.5, 2.0, 3.4, 0.2)
    assert (S.SW_TRAVEL, S.SW_TRAVEL_TOL, S.SW_ACTUATOR_D, S.SW_PUSH_ANGLE_MAX) == (0.3, 0.2, 3.0, 3.0)
    st = P.standin(P.Cell(0.0, 0.0, S.HOLE_B, standin=3.4))
    bb = st.bounding_box()
    assert (bb.size.X, bb.size.Y, bb.max.Z, bb.min.Z) == pytest.approx((6.2, 6.2, 3.4, 0.0), abs=1e-3)
    stem = [f.bounding_box() for f in section_faces(st, 3.0)]
    assert len(stem) == 1 and stem[0].size.X == pytest.approx(2.0, abs=1e-3)


def test_the_print_limit_and_the_strip_length_come_from_outside():
    from foundry.layout import bounds_mm
    from foundry.slice_check import PRINTERS

    assert S.PRINT_MAX == load("cckb").spec.PRINT_MAX == 168.4 < PRINTERS["a1mini"]["bed"][0]      # CLI の自動配置の実効（case-and-print.md）
    x0, _, x1, _ = bounds_mm(load("cckb-click").keys())
    assert S.COUPON_STRIP_U * UNIT == pytest.approx((x1 - x0) / 2)                                  # 配列の幅の半分


def skin_above_pocket(s=S, n=200):
    """くぼみの上に残る枠の皮の厚さ（穴の縁のすぐ外・**枠の立体の中の点を縦に数える**）。穴の上の縁の面取りが削る。"""
    c = P.Cell(0.0, 0.0, s.HOLE_B)
    fr = P.frame([c], s)
    x = P.hole_size(c)[0] / 2 + 0.02
    y = -P.hole_size(c)[1] / 2 + s.TAB_LEN - 0.5
    z0 = s.FRAME_UNDER
    return sum(fr.is_inside(Vector(x, y, z0 + s.FRAME_T * (k + 0.5) / n)) for k in range(n)) * s.FRAME_T / n


def test_the_skin_above_the_pocket_is_thick_enough_to_print():
    assert skin_above_pocket() >= MIN_SKIN - 0.02
    assert skin_above_pocket(spec_with(HOLE_CHAMFER=0.6)) < MIN_SKIN - 0.02       # 面取りを大きくすると皮が薄くなる


# ---------------------------------------------------------------------------
# 刷る向きで、機能する面がきれいに出るか（R4）
# ---------------------------------------------------------------------------

def horizontal_faces(part):
    """水平な平面 [(z, 上向きか, 面積)]。"""
    out = []
    for f in part.faces():
        if f.geom_type == GeomType.PLANE and abs(abs(f.normal_at().Z) - 1) < 1e-6:
            out.append((round(f.center().Z, 6), f.normal_at().Z > 0, f.area))
    return out


def print_problems(c, s=S, dots=0):
    """刷る向きのキャップ: 水平な面が層の倍数にあるか・宙に張り出す平らな面（下向きでベッドの上に無い面）が無いか。"""
    part = P.cap_print_pose(c, P.cap(c, s, dots=dots), s)
    out = []
    for z, up, area in horizontal_faces(part):
        if not P.on_layer(z, s):
            out.append(f"高さ {z:.3f} の面が層の倍数でない")
        if not up and z > 1e-6:
            out.append(f"高さ {z:.3f} に下向きの平らな面 {area:.2f} mm2（支え無しで宙に張り出す）")
    return out


def test_the_production_cap_prints_with_its_working_faces_clean():
    c = P.Cell(0.0, 0.0, S.HOLE_B)
    assert print_problems(c) == []
    part = P.cap_print_pose(c, P.cap(c))
    faces = horizontal_faces(part)
    lv = P.levels()
    # 押す面 = ベッドの面（下面の全部）。ステムの当て面 φ3 が、キャップが横にずれ切っても入る
    bed = [a for z, up, a in faces if abs(z) < 1e-6 and not up]
    side = max(P.side_gap(replace(c, step=max(S.COUPON_HOLE_STEPS))))
    assert len(bed) == 1 and bed[0] > math.pi * (S.SW_ACTUATOR_D / 2 + side) ** 2
    # 掛かる面 = つばの上面（上向き・TAB_T の高さ・4 枚）
    latch = [a for z, up, a in faces if abs(z - S.TAB_T) < 1e-6 and up]
    assert len(latch) == 4 and min(latch) > 1.0
    assert part.bounding_box().max.Z == pytest.approx(lv["cap_top"] - lv["pad"])


def test_every_height_in_print_orientation_is_a_multiple_of_the_layer():
    for latch, tab in CC.LATCH_VARIANTS:
        bad = {k: v for k, v in P.print_heights(S, latch, tab).items() if not P.on_layer(v)}
        assert not bad, (latch, tab, bad)
    frame = P.flip_to_bed(key(dots=3)[1])
    assert all(P.on_layer(z) for z, _, _ in horizontal_faces(frame))
    # 枠の、宙に張り出す平らな面は見分ける点の天井だけ（点の数だけ・点の大きさ）
    hang = [a for z, up, a in horizontal_faces(frame) if not up and z > 1e-6]
    assert len(hang) == 3 and max(hang) < math.pi * (S.COUPON_DOT[0] / 2) ** 2 + 1e-6


def test_the_print_check_notices_an_off_layer_height_and_an_unsupported_face():
    c = P.Cell(0.0, 0.0, S.HOLE_B)
    assert any("層の倍数でない" in p for p in print_problems(c, spec_with(TAB_T=0.45)))
    assert not P.on_layer(P.print_heights(spec_with(POCKET_DEPTH=0.95))["くぼみの底"])
    # 層を 0.2 に戻すと、つば 0.5 は層の境目に乗らない。1 層目より低い面も乗らない（1 層目の中に面は作れない）
    assert any("層の倍数でない" in p for p in print_problems(c, spec_with(TAB_T=0.5, PRINT_LAYER=0.2)))
    assert P.on_layer(0.0) and not P.on_layer(0.1) and P.on_layer(0.1, first=0.1) and P.on_layer(S.PRINT_FIRST_LAYER)
    # 販売者と同じ平らな足（S）は掛かる面が宙に張り出す。**検査がそれを見つける**こと（C の 45° は見つからないこと）
    assert any("宙に張り出す" in p for p in print_problems(replace(c, latch="S", tab=0.6)))
    assert print_problems(replace(c, latch="C", tab=0.6)) == []


# ---------------------------------------------------------------------------
# 下から入り、上へ抜けない（R2）。隙
# ---------------------------------------------------------------------------

def section_faces(part, z):
    """立体を高さ z で切った面。"""
    r = part.intersect(Plane.XY.offset(z))
    return list(r.faces()) if hasattr(r, "faces") else [f for x in r for f in x.faces()]


def insert_problems(s=S, **kw):
    c, fr, _, cp = key(s, **kw)
    lv = P.levels(s, c.latch, c.tab)
    out = []
    # 下から掛かった位置まで（枠だけ。板は入れるときには無い）
    for k in range(0, 13):
        dz = -6.0 + 0.5 * k
        v = intersection_volume(fr, Pos(0, 0, dz) * cp)
        if v > TOL:
            out.append(f"下から入れる途中（掛かった位置から {dz:+.1f}）で枠に {v:.3f} mm3 当たる")
    v = intersection_volume(fr, Pos(0, 0, -lv["descent_max"]) * cp)
    if v > TOL:
        out.append(f"押し切りで枠に {v:.3f} mm3 当たる")
    up = intersection_volume(fr, Pos(0, 0, 0.2) * cp)
    if up < 0.05:
        out.append(f"掛かった位置から 0.2 上げても枠に当たらない（{up:.3f} mm3）: 上へ抜ける")
    gx, gy = P.side_gap(c, s)
    worst = P.latch_overlap(c, s, dx=gx, dy=gy)
    if worst < 0.5:
        out.append(f"横にずれ切ると掛かりが {worst:.2f} mm2 しか残らない")
    return out


@pytest.mark.parametrize("latch, tab", CC.LATCH_VARIANTS)
def test_the_cap_goes_in_from_below_and_cannot_leave_upward(latch, tab):
    assert insert_problems(latch=latch, tab=tab) == []


@pytest.mark.parametrize("hole", ["HOLE_A", "HOLE_B"])
@pytest.mark.parametrize("step", S.COUPON_HOLE_STEPS)
def test_the_swept_holes_still_latch_and_leave_the_declared_gap(hole, step):
    assert insert_problems(hole=getattr(S, hole), step=step) == []
    # 隙を**立体の断面**から測る（穴の内法とキャップの胴の外法。枠の厚さの真ん中）
    c, fr, _, cp = key(hole=getattr(S, hole), step=step)
    z = S.FRAME_UNDER + S.POCKET_DEPTH + 0.3
    holes = [w.bounding_box() for f in section_faces(fr, z) for w in f.inner_wires()]
    body = [f.bounding_box() for f in section_faces(cp, z)]
    assert len(holes) == 1 and len(body) == 1
    assert (holes[0].size.X - body[0].size.X) / 2 == pytest.approx(S.CAP_CLEAR + step / 2, abs=1e-3)
    # y は手前の側で測る（奥の壁には継ぎ目の溝があり、穴の外接が溝の深さだけ伸びる）
    assert body[0].min.Y - holes[0].min.Y == pytest.approx(S.CAP_CLEAR + step / 2, abs=1e-3)
    assert holes[0].size.Y - S.SEAM_NOTCH[1] == pytest.approx(getattr(S, hole)[1] + step, abs=1e-3)
    assert holes[0].size.X == pytest.approx(getattr(S, hole)[0] + step, abs=1e-3)


@pytest.mark.parametrize("over, kw, word", [
    (dict(TAB_REACH=0.0, TAB_R=2.25), {}, "上へ抜ける"),        # つばが穴と同じ形: 掛からない
    (dict(CAP_CLEAR=-0.05), {}, "当たる"),
    (dict(POCKET_CLEAR=-0.1), {}, "当たる"),                     # くぼみがつばより狭い
    # つばの角を穴の角と同じ丸み（一様に広げた形）にすると、穴を 0.1 広げた列で斜めにずれ切ったとき角が外れる（0.06 mm2）
    (dict(TAB_R=2.6), dict(step=0.1), "掛かりが"),
])
def test_the_insert_check_notices_a_cap_that_falls_through_or_binds(over, kw, word):
    assert any(word in p for p in insert_problems(spec_with(**over), **kw))


def pocket_wall(s=S, step=0.0, n=400):
    """隣り合う穴のくぼみの間に残る壁の厚さ（**枠の立体の中の点を数える**。つばを通る線・くぼみの高さの真ん中）。"""
    cells = [P.Cell(0.0, 0.0, s.HOLE_B, step=step), P.Cell(UNIT, 0.0, s.HOLE_B, step=step)]
    fr = P.frame(cells, s)
    y = -P.hole_size(cells[0])[1] / 2 + s.TAB_LEN - 0.5       # くぼみの、辺に沿ったまっすぐな所
    z = s.FRAME_UNDER + s.POCKET_DEPTH / 2
    xs = [UNIT / 2 - 2.0 + 4.0 * k / n for k in range(n + 1)]
    return sum(fr.is_inside(Vector(x, y, z)) for x in xs) * 4.0 / n


def test_the_wall_between_neighbouring_pockets_is_printable():
    """0.4 未満の肉は「無い」のと同じ（case-and-print.md）。基準の穴で外周 2 本（0.8）、穴を一番広げた列でも 1 本より太く残る。"""
    assert pocket_wall() == pytest.approx(UNIT - S.HOLE_B[0] - 2 * (S.TAB_REACH + S.POCKET_CLEAR), abs=0.03)
    assert pocket_wall() >= 0.8 - 0.03 and pocket_wall(step=max(S.COUPON_HOLE_STEPS)) >= 0.6 - 0.03
    assert pocket_wall(spec_with(POCKET_CLEAR=0.6)) < 0.4          # 壊すと気づく


def guide_problems(s=S):
    """横の動きを胴（穴）で受けているか。くぼみの隙が胴の隙より狭いと、つば（ベッド側で太る・薄い）が先に当たる。
    **立体の断面から測る**: くぼみの高さで切った穴の内法 − つばの高さで切ったキャップの外法。"""
    out = []
    for step in s.COUPON_HOLE_STEPS:
        c, fr, _, cp = key(s, step=step)
        lv = P.levels(s)
        pocket = [w.bounding_box() for f in section_faces(fr, lv["latch"] - 0.1) for w in f.inner_wires()]
        tab = [f.bounding_box() for f in section_faces(cp, lv["latch"] - 0.05)]
        gap = (pocket[0].size.X - tab[0].size.X) / 2
        body = P.side_gap(c, s)[0]
        if gap < body - 1e-6:
            out.append(f"穴 +{step}: つばとくぼみの隙 {gap:.2f} が胴と穴の隙 {body:.2f} より狭い")
    return out


def test_sideways_play_is_taken_by_the_body_not_by_the_thin_tabs():
    assert guide_problems() == []
    assert any("より狭い" in p for p in guide_problems(spec_with(POCKET_CLEAR=0.2)))      # 0.2 だと穴を広げた列でつばが先に当たる


# ---------------------------------------------------------------------------
# 幅の広いキーの端を押す
# ---------------------------------------------------------------------------

def end_press_problems(w_u, s=S):
    """端を押して中心が ON の最大まで沈んだ姿を**立体で回して**、枠・基板の上の物に当たらないか。傾きがスイッチの許す範囲か。"""
    c = P.Cell(0.0, 0.0, s.HOLE_B, w_u=w_u)
    fr, cp = P.frame([c], s), P.cap(c, s)
    lv = P.levels(s)
    ep = P.end_press(c, s)
    px, pz = -ep["pivot"], lv["latch"]
    tilted = Pos(px, 0, pz) * Rot(0, ep["angle"], 0) * Pos(-px, 0, -pz) * cp
    bb = tilted.bounding_box()
    out = []
    if not (bb.max.X > cp.bounding_box().max.X - 0.2 and bb.min.Z < lv["pad"] - 0.5 * ep["near_drop"]):
        out.append("回した向きが違う（押した側が下がっていない）")
    v = intersection_volume(fr, tilted)
    if v > TOL:
        out.append(f"{w_u}u: 傾いたキャップが枠に {v:.4f} mm3 当たる（遠い側が穴に擦る・近い側が柱に着く）")
    half = w_u * UNIT / 2
    keepout = Pos(0, 0, 0) * Box(2 * half, UNIT, s.SW_BODY_H, align=P.CEN_MIN)
    v = intersection_volume(keepout, tilted)
    if v > TOL:
        out.append(f"{w_u}u: 押した側の縁が、基板の上の物の高さ {s.SW_BODY_H} まで下がる（{v:.4f} mm3）")
    if ep["angle"] > s.SW_PUSH_ANGLE_MAX:
        out.append(f"{w_u}u: 傾き {ep['angle']:.2f}° がスイッチの許す {s.SW_PUSH_ANGLE_MAX}° を超える")
    return out


def test_every_wide_key_in_the_layout_survives_an_end_press():
    widths = sorted({k.w_u for k in load("cckb-click").keys()} - {1.0})
    assert widths == sorted(S.COUPON_WIDE) and len(load("cckb-click").keys()) == 62      # 試し刷りは配列の広いキーを全部含む
    for w in widths:
        assert end_press_problems(w) == []


def test_the_1u_end_press_exceeds_the_push_angle_and_is_recorded():
    """1u の縁を押して遠い側のつばだけで回ると 3° を少し超える（販売者の 1u も同じ形）。**設計では消していない**ので
    open-gaps に載っていること。形を変えて 3° に収まったら、この検査と記録を一緒に直す。"""
    ep = P.end_press(P.Cell(0.0, 0.0, S.HOLE_B))
    assert 3.0 < ep["angle"] < 3.5
    assert f"{ep['angle']:.1f}°" in (PROJECT / "docs" / "open-gaps.md").read_text()


@pytest.mark.parametrize("over, word", [
    (dict(CAP_CLEAR=0.005), "枠に"),                # 隙が傾きの横の動きより小さいと擦る
    (dict(SW_TRAVEL_TOL=1.2), "基板の上の物"),       # 沈みが大きいと押した側が下に着く
    (dict(SW_PUSH_ANGLE_MAX=1.0), "超える"),
])
def test_the_end_press_check_notices_rubbing_landing_and_tilt(over, word):
    assert any(word in p for p in end_press_problems(2.25, spec_with(**over)))


# ---------------------------------------------------------------------------
# 小片の一式（遅い: 全部を作る）
# ---------------------------------------------------------------------------

EXPECTED_STLS = {"coupon_min_frame", "coupon_min_base", "coupon_min_caps", "coupon_min_plate", "coupon_a_frame", "coupon_a_caps", "coupon_ab_base", "coupon_b_frame", "coupon_b_caps",
                 "coupon_standin_frame", "coupon_standin_base", "coupon_latch_frame", "coupon_latch_base", "coupon_latch_caps",
                 "coupon_wide_frame", "coupon_wide_base", "coupon_wide_caps", "coupon_strip_frame"}
# STL の名前 → その中の立体の数（キャップはマスの数。数えて確かめる）
BODIES = {"coupon_min_caps": 4, "coupon_min_plate": 6, "coupon_a_caps": 9, "coupon_b_caps": 9, "coupon_latch_caps": 6, "coupon_wide_caps": 3}


@pytest.fixture(scope="module")
def built():
    return {name: (cp, CC.build(cp)) for name, cp in CC.coupons().items()}


def assembly_problems(cp, parts, s=S):
    """置いた状態と押し切りで、枠・板・キャップが重ならないか。返り値 (問題, 承知して外した組の数)。
    外すのは「台が押す面より高い」マスのキャップ×台だけ（押し込みを触るための台。実物では枠が浮く）。"""
    out, skipped = [], 0
    fr = parts["frame"]
    if "base" in parts:
        v = intersection_volume(fr, parts["base"])
        if v > TOL:
            out.append(f"枠×板 {v:.3f} mm3")
    bare = P.base([replace(c, standin=None) for c in cp.cells], s, extra_u=cp.extra_u) if cp.has_base else None
    for c, part in parts.get("caps", []):
        lv = P.levels(s, c.latch, c.tab)
        v = intersection_volume(fr, part)
        if v > TOL:
            out.append(f"枠×キャップ({c.cx:.0f},{c.cy:.0f}) {v:.3f} mm3")
        if c.standin is not None and c.standin > lv["pad"] + 1e-9:
            skipped += 1
        else:
            v = intersection_volume(P.standin(c, s), part)
            if v > TOL:
                out.append(f"台×キャップ({c.cx:.0f},{c.cy:.0f}) {v:.3f} mm3")
        low = Pos(c.cx, c.cy, -lv["descent_max"]) * P.cap(c, s)
        body = Pos(c.cx, c.cy, 0) * Box(s.SW_BODY, s.SW_BODY, s.SW_BODY_H, align=P.CEN_MIN)
        for other, label in ((fr, "枠（柱・壁）"), (bare, "板"), (body, "スイッチの本体")):
            v = intersection_volume(other, low)
            if v > TOL:
                out.append(f"押し切りで{label}×キャップ({c.cx:.0f},{c.cy:.0f}) {v:.3f} mm3")
    return out, skipped


@pytest.mark.slow
def test_nothing_in_any_coupon_interferes_at_rest_or_fully_pressed(built):
    assert set(built) == {"min", "a", "b", "standin", "latch", "wide", "strip"}
    total_caps = total_skipped = 0
    for name, (cp, parts) in built.items():
        bad, skipped = assembly_problems(cp, parts)
        assert not bad, f"{name}: {bad}"
        total_caps += len(parts.get("caps", []))
        total_skipped += skipped
    # 母数: キャップ 3 + 9 + 9 + 6 + 6 + 3 個。外したのは台 3.7（押す面 3.6 より高い）の 1 組だけ
    assert (total_caps, total_skipped) == (36, 1)


@pytest.mark.slow
def test_the_assembly_check_notices_a_post_under_the_cap_and_a_tight_lip():
    cp = CC.coupons()["b"]
    for over, word in ((dict(SW_BODY_H=2.8), "スイッチの本体"), (dict(COUPON_LIP=(-0.2, 1.6, 2.0)), "枠×板"),
                       (dict(FOOT_H=3.5), None)):
        s = spec_with(**over)
        target = CC.coupons(s)["latch"] if word is None else CC.coupons(s)["b"]
        bad, _ = assembly_problems(target, CC.build(target, s), s)
        assert any((word or "押し切りで板") in p for p in bad), (over, bad)
    assert cp.cells[0].standin == S.SW_STEM_TOP


def test_a_post_wider_than_the_rib_is_trimmed_and_never_sits_under_a_hole():
    """柱を太くしても、穴の下へは出ない（穴は柱ごと下まで抜く）。押し切りで胴が枠の下面より下へ出ても柱に当たらない保証。"""
    s = spec_with(POST_W=3.0)
    cells = [P.Cell(0.0, 0.0, s.HOLE_B), P.Cell(UNIT, 0.0, s.HOLE_B)]
    fr = P.frame(cells, s, wall=False, posts=[(UNIT / 2, 0.0, s.POST_W, s.POST_L)])
    post = [f.bounding_box() for f in section_faces(fr, 1.5)]
    assert len(post) == 1 and post[0].size.X == pytest.approx(UNIT - S.HOLE_B[0], abs=1e-3)
    low = Pos(0, 0, -P.levels(s)["descent_max"]) * P.cap(cells[0], s)
    assert intersection_volume(fr, low) < TOL


@pytest.mark.slow
def test_the_exported_coupons_are_the_declared_set_watertight_and_fit_the_a1_mini(tmp_path):
    (tmp_path / "coupon_old_leftover.stl").write_text("solid x\nendsolid x\n")       # 前の版の残骸は消える（lessons D）
    made, style = CC.export(out=tmp_path)
    stls = {p.stem for p in tmp_path.glob("coupon_*.stl")}
    assert stls == set(made) == EXPECTED_STLS
    for stem in sorted(stls):
        mesh = trimesh.load(str(tmp_path / f"{stem}.stl"))
        bodies = mesh.split(only_watertight=False)
        assert all(b.is_watertight for b in bodies), stem
        assert max(mesh.extents[:2]) <= S.PRINT_MAX and abs(mesh.bounds[0][2]) < 1e-6, stem
        assert len(bodies) == BODIES.get(stem, 1), (stem, len(bodies))     # 立体の数を数える
    assert len(style) == 19 and len(list((tmp_path / "assembly").glob("*.stl"))) == 19
    # 帯は 15u の半分の長さ ＋ 両側の縁
    assert made["coupon_strip_frame"][0] == pytest.approx(S.COUPON_STRIP_U * UNIT + 2 * S.COUPON_MARGIN)


@pytest.mark.slow
def test_the_shared_base_and_caps_really_are_the_same_shape(built):
    """刷る時間を減らすために共用にした物: a と b の板・standin と b のキャップ。**同じ形だから共用できる**ことを立体で確かめる。"""
    a, b = built["a"][1]["base"], built["b"][1]["base"]
    assert a.volume == pytest.approx(b.volume, rel=1e-9) and intersection_volume(a, b) == pytest.approx(a.volume, rel=1e-6)
    cps = CC.coupons()
    assert (cps["a"].base_stl, cps["b"].base_stl, cps["standin"].caps_stl) == ("coupon_ab_base", "", "")
    one = lambda c: P.cap(replace(c, cx=0.0, cy=0.0, standin=None, step=0.0, dots=0, back=False))      # noqa: E731
    sc, bc = one(cps["standin"].cells[0]), one(cps["b"].cells[0])
    assert intersection_volume(sc, bc) == pytest.approx(bc.volume, rel=1e-6) and sc.volume == pytest.approx(bc.volume)
    assert len(cps["standin"].cells) <= len(cps["b"].cells)
    # 共用できない組は見分けがつく: 案 A のキャップは B と違う形
    ac = one(cps["a"].cells[0])
    assert abs(ac.volume - bc.volume) > 10


def test_the_standin_coupon_covers_the_stem_tolerance_and_one_step_beyond():
    hs = [c.standin for c in CC.coupons()["standin"].cells]
    lo, hi = S.SW_STEM_TOP - S.SW_STEM_TOP_TOL, S.SW_STEM_TOP + S.SW_STEM_TOP_TOL
    assert hs == sorted(hs) and hs[0] == pytest.approx(lo) and hs[-1] == pytest.approx(hi + 0.1)
    assert all(b - a == pytest.approx(0.1) for a, b in zip(hs, hs[1:]))
    # 台の番号（板の点）と枠の縁の点が同じ番号
    cp = CC.coupons()["standin"]
    assert [c.dots for c in cp.cells] == [cp.bumps[i] for i in range(len(cp.cells))] == [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# 最初に刷る最小の一式（min）と、測る所
# ---------------------------------------------------------------------------

def min_set_problems(s=S):
    """最小の一式を**作った立体から測る**: 穴 3 つが 0.1 刻み・点の数で見分けがつく・キャップ 3 個が同じ形・測る所が 10.00。"""
    cp = CC.coupons(s)["min"]
    parts = CC.build(cp, s)
    out = []
    z = s.FRAME_UNDER + s.POCKET_DEPTH + 0.3
    inner = sorted((w.bounding_box() for f in section_faces(parts["frame"], z) for w in f.inner_wires()), key=lambda b: b.min.X)
    widths = [round(b.size.X - s.HOLE_B[0], 3) for b in inner[:3]]
    if len(inner) != 4 or widths != [0.0, 0.1, 0.2]:
        out.append(f"枠の穴が「基準・+0.1・+0.2」の 3 つ ＋ 測る穴 1 つになっていない（{len(inner)} 個・{widths}）")
    else:
        slot = inner[3]
        if abs(slot.size.X - 10.0) > 1e-3 or abs(slot.size.Y - 10.0) > 1e-3:
            out.append(f"測る穴が 10.00 角でない（{slot.size.X:.3f} × {slot.size.Y:.3f}）")
        if slot.min.X - inner[2].max.X < 2.0:
            out.append(f"測る穴と穴 3 の間が {slot.min.X - inner[2].max.X:.2f} しかない")
    if [c.dots for c in cp.cells] != [1, 2, 3] or any(c.standin != s.SW_STEM_TOP for c in cp.cells):
        out.append("点の数が 1・2・3 でない／台が名目の高さでない")
    caps = [Pos(-c.cx, -c.cy, -CC.rest_dz(c, s)) * part for c, part in parts["caps"]]
    if len(caps) != 3 or any(abs(intersection_volume(caps[0], k) - caps[0].volume) > 1e-3 for k in caps[1:]):
        out.append("キャップ 3 個が同じ形でない（穴の大きさだけを変えた比べ方にならない）")
    block = P.gauge_block(s)
    mid = [f.bounding_box() for f in section_faces(block, 1.5)]
    if len(mid) != 1 or abs(mid[0].size.X - 10.0) > 1e-3 or abs(mid[0].size.Y - 10.0) > 1e-3:
        out.append("測る塊が、段より上で 10.00 角でない")
    ledge = [a for zz, up, a in horizontal_faces(block) if up and abs(zz - s.TAB_T) < 1e-6]
    if len(ledge) != 1 or ledge[0] < 20.0 or abs(block.bounding_box().max.Z - 3.0) > 1e-6:
        out.append("測る塊の段（つばと同じ厚さ）か、高さ 3.00 が無い")
    if any(not P.on_layer(zz, s) for zz, _, _ in horizontal_faces(block)):
        out.append("測る塊の面が層の境目に無い")
    return out


def test_the_minimal_set_sweeps_three_holes_with_identical_caps_and_carries_the_gauges():
    assert min_set_problems() == []
    # 記入表に書いた設計値（docs/coupon-test.md）と同じ数か
    sheet = (PROJECT / "docs" / "coupon-test.md").read_text()
    for word in ("10.00", "3.00", "0.40", "2.40", "16.65", "17.05", "17.15", "17.25"):
        assert word in sheet, word
    lv = P.levels()
    assert (lv["cap_top"] - lv["pad"], S.TAB_T, P.body_plan(P.Cell(0, 0, S.HOLE_B)).bounding_box().size.X) == pytest.approx((2.4, 0.4, 16.65))


@pytest.mark.parametrize("over, word", [
    (dict(COUPON_HOLE_STEPS=(0.0, 0.1, 0.1)), "3 つ"),
    (dict(COUPON_GAUGE=(9.9, 3.0, 4.0)), "測る穴が 10.00 角でない"),
    (dict(COUPON_GAUGE=(10.0, 3.0, 0.5)), "段"),
    (dict(COUPON_GAUGE_EXTRA_U=0.6), "測る穴と穴 3 の間"),
])
def test_the_minimal_set_check_notices_a_wrong_sweep_and_a_wrong_gauge(over, word):
    assert any(word in p for p in min_set_problems(spec_with(**over)))


def test_the_minimal_plate_holds_six_separate_bodies_in_print_orientation():
    cp = CC.coupons()["min"]
    parts = CC.print_parts("min", cp, CC.build(cp))
    placed = CC.plate_layout(parts, "min")
    boxes = [(k, p.bounding_box()) for k, p in placed]
    assert [k for k, _ in boxes] == ["caps", "frame", "base"]
    for (_, a), (_, b) in zip(boxes, boxes[1:]):
        assert b.min.Y - a.max.Y == pytest.approx(5.0) and abs(a.min.Z) < 1e-6 and abs(b.min.Z) < 1e-6
    plate = parts["coupon_min_plate"]
    assert len(plate.solids()) == 6 and max(plate.bounding_box().size.X, plate.bounding_box().size.Y) <= S.PRINT_MAX
    # 枠は上面が下: 柱の先（設計の z = 0）がいちばん上。キャップは押す面が下: つばがベッドに着いている
    frame = dict(placed)["frame"]
    assert frame.bounding_box().max.Z == pytest.approx(S.FRAME_UNDER + S.FRAME_T)
    caps = dict(placed)["caps"]
    assert sum(1 for z, up, a in horizontal_faces(caps) if up and abs(z - S.TAB_T) < 1e-6) == 3 * 4 + 1      # つば 4 枚 × 3 ＋ 測る塊の段


# ---------------------------------------------------------------------------
# 継ぎ目の溝（外周の継ぎ目を、滑る面から引っ込める）
# ---------------------------------------------------------------------------

def notch_problems(s=S, step=0.0, want=None):
    """キャップの胴と枠の穴に、継ぎ目の溝があるか。**断面の面積と外接から測る**: 溝は面積を w × d だけ変え、外接（滑る面の位置）は変えない。
    つば・くぼみのある角の範囲に掛からない。"""
    c, fr, _, cp = key(s, step=step)
    w, d = want or s.SEAM_NOTCH                       # want = あるはずの溝（溝を無くした spec を見るとき）
    out = []
    z = s.FRAME_UNDER + s.POCKET_DEPTH + 0.3
    body = section_faces(cp, z)
    plan = P.body_plan(c, s)
    if abs(sum(f.area for f in plan.faces()) - body[0].area - w * d) > 0.01:
        out.append("キャップの胴に継ぎ目の溝が無い（断面の面積が w × d 減っていない）")
    if abs(body[0].bounding_box().size.Y - plan.bounding_box().size.Y) > 1e-3:
        out.append("継ぎ目の溝がキャップの胴の外接（滑る面）を変えている")
    hole = [wr for f in section_faces(fr, z) for wr in f.inner_wires()][0]
    hplan = P.hole_plan(c, s)
    grown = hole.bounding_box().size.Y - hplan.bounding_box().size.Y
    if abs(grown - d) > 1e-3:
        out.append(f"枠の穴に深さ {d} の継ぎ目の溝が無い（外接の伸び {grown:.3f}）")
    if w / 2 > P.hole_size(c)[0] / 2 - s.TAB_LEN - s.POCKET_CLEAR - 1.0:
        out.append("継ぎ目の溝が、つば・くぼみのある角の範囲に近い")
    if UNIT - P.hole_size(c)[1] - d < 1.2:
        out.append(f"溝を掘った所のリブが {UNIT - P.hole_size(c)[1] - d:.2f} しか残らない")
    return out


def test_the_seam_notch_is_cut_mid_edge_and_leaves_the_sliding_faces_alone():
    for step in S.COUPON_HOLE_STEPS:
        assert notch_problems(step=step) == []
    gone = notch_problems(spec_with(SEAM_NOTCH=None), want=S.SEAM_NOTCH)
    assert any("キャップの胴に" in p for p in gone) and any("枠の穴に" in p for p in gone)
    assert any("角の範囲に近い" in p for p in notch_problems(spec_with(SEAM_NOTCH=(9.0, 0.5))))
    assert any("リブが" in p for p in notch_problems(spec_with(SEAM_NOTCH=(2.0, 1.0))))


# ---------------------------------------------------------------------------
# 刷り方（print/ のプリセット）
# ---------------------------------------------------------------------------

def preset_problems(preset, recipe, s=S):
    """プリセットが形の前提と合っているか: 層の厚さ・1 層目・機能する面が層の境目・縁を汚す設定（ブリム・象の足の補正）を使っていない。"""
    out = []
    layer, first = float(preset.get("layer_height", "nan")), float(preset.get("initial_layer_print_height", "nan"))
    if not layer == pytest.approx(s.PRINT_LAYER):
        out.append(f"層 {layer} が spec の PRINT_LAYER {s.PRINT_LAYER} と違う")
    if not first <= s.PRINT_FIRST_LAYER + 1e-9:
        out.append(f"1 層目 {first} が PRINT_FIRST_LAYER {s.PRINT_FIRST_LAYER} より厚い")
    heights = dict(P.print_heights(s), 測る塊=s.COUPON_GAUGE[1], 台=s.COUPON_BASE_T + s.SW_STEM_TOP)
    off = {k: v for k, v in heights.items() if not (v >= first - 1e-9 and abs((v - first) / layer - round((v - first) / layer)) < 1e-6)}
    if off:
        out.append(f"機能する面が層の境目に乗らない: {off}")
    want = dict(brim_type="no_brim", elefant_foot_compensation="0", xy_hole_compensation="0", xy_contour_compensation="0",
                enable_support="0", seam_position="aligned", wall_sequence="inner-outer-inner wall")
    for k, v in want.items():
        if preset.get(k) != v:
            out.append(f"{k} が {preset.get(k)}（決定は {v}）")
    if int(preset.get("wall_loops", "0")) < 3:
        out.append("内→外→内の順は外周 3 本以上が要る")
    if f"{recipe['nozzle']} nozzle" not in recipe["machine"] or preset.get("from") != "User" or not preset.get("inherits"):
        out.append("ノズルとプリンタの設定の名前が合わない／読み込める形（from = User・inherits）でない")
    return out


@pytest.mark.parametrize("variant", sorted(S.PRINT_RECIPES))
def test_the_print_presets_match_the_layer_the_geometry_was_built_for(variant):
    r = S.PRINT_RECIPES[variant]
    preset = json.loads((PROJECT / r["process"]).read_text())
    assert preset_problems(preset, r) == []
    assert preset["name"] in (PROJECT / "docs" / "coupon-test.md").read_text()
    for over, word in ((dict(layer_height="0.12"), "境目に乗らない"), (dict(initial_layer_print_height="0.3"), "より厚い"),
                       (dict(brim_type="auto_brim"), "brim_type"), (dict(wall_loops="2"), "3 本以上"),
                       (dict(seam_position="back"), "seam_position")):
        assert any(word in p for p in preset_problems(dict(preset, **over), r)), over


def test_the_two_nozzles_are_the_ones_with_installed_profiles():
    assert sorted(r["nozzle"] for r in S.PRINT_RECIPES.values()) == [0.2, 0.4]
    assert len({r["process"] for r in S.PRINT_RECIPES.values()}) == 2
    assert {p.name for p in (PROJECT / "print").glob("*.json")} == {r["process"].split("/")[1] for r in S.PRINT_RECIPES.values()}


@pytest.mark.slow
def test_the_sliced_minimal_plate_keeps_every_seam_off_the_sliding_faces(tmp_path):
    """**実際にスライスして G-code で数える**（OrcaSlicer が無い環境では飛ばす）。継ぎ目の溝を無くすと、継ぎ目が滑る面に出ることも確かめる。"""
    from build123d import export_stl
    from foundry import paths

    if not __import__("pathlib").Path(paths.ORCA).exists():
        pytest.skip("OrcaSlicer が無い")
    sys.path.insert(0, str(PROJECT / "tools"))
    import slice_precise as SP

    def sliced(s, name):
        cp = CC.coupons(s)["min"]
        stl = tmp_path / name / "coupon_min_plate.stl"
        stl.parent.mkdir()
        export_stl(CC.print_parts("min", cp, CC.build(cp, s), s)["coupon_min_plate"], str(stl))
        rc = SP.recipe("n04", s, "orca")
        gcode, log = SP.slice_stl(rc, stl, out=tmp_path / name)
        assert gcode is not None, log[-500:]
        applied, n = SP.applied_problems(rc, SP.gcode_config(gcode.read_text(errors="replace")))
        assert applied == [] and n >= 20
        return SP.analyse(gcode, rc, s)

    problems, facts, _ = sliced(S, "ok")
    assert problems == [], problems
    assert facts["継ぎ目 cap"]["全部"] >= 3 * 20 and facts["継ぎ目 hole"]["全部"] >= 3 * 15           # 数えた母数（キャップ 3 個・穴 3 つ × 層）
    bad, _, _ = sliced(spec_with(SEAM_NOTCH=None), "no_notch")
    assert any("滑る面にある" in p for p in bad), bad


# ---------------------------------------------------------------------------
# 記録・名前・門
# ---------------------------------------------------------------------------

BORROWED = re.compile(r"acc|acid|click ?board", re.I)


def test_no_part_is_named_after_the_sellers_products():
    """販売者の製品名（ACC / Acid Caps / ClickBoard）を自分たちの部品の名前に使わない（利用者の決定・LICENSE）。"""
    names = sorted(EXPECTED_STLS) + list(CC.coupons()) + [S.NAME.replace("cckb-click", "")]
    assert not [n for n in names if BORROWED.search(n)]
    assert BORROWED.search("coupon_acc_caps") and BORROWED.search("AcidCaps_1u")      # 検査器が生きている


def test_the_license_notice_names_the_source_the_terms_and_the_changes():
    text = (PROJECT / "LICENSE").read_text()
    for word in ("CC BY-NC 4.0", "Salicylic_acid3", "ACC_Keycaps", "Case_Data", "MIT", "PCB_Data", "KiCAD_FootPrint",
                 "変えた所", "非営利"):
        assert word in text, word


def test_the_test_sheet_covers_every_printed_file():
    sheet = (PROJECT / "docs" / "coupon-test.md").read_text()
    missing = [s for s in sorted(EXPECTED_STLS) if s not in sheet]
    assert not missing, missing


def test_the_order_gate_is_closed_until_the_board_exists():
    doc = (PROJECT / "docs" / "open-gaps.md").read_text()
    assert gate.blockers(doc) and not gate.is_gate_open(doc)
