"""CCKB の基板・プレート・ケースの境界（決定記録 projects/cckb/docs/decisions/2026-09-24-interface.md）。

**外の事実と、生成した物そのもの**に突き合わせる:
  - XIAO の寸法 ↔ Seeed 公式の STEP（lib/xiao.3dshapes・無改変）
  - 取付・支え ↔ foundry.pcb が**いま生成した**基板（KiCad の Python で世界座標に解いたパッド・
    コートヤード。projects/cckb/tools/board_geometry.py）
  - プレートの分割 ↔ foundry.plate が生成した立体の外接箱
  - 幾何の小道具 ↔ build123d のオフセット
各検査の下に「故意に壊すと落ちる」検査を置く（CLAUDE.md 検証の作法 2）。
"""

import json
import math
import re
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT, require
from foundry import paths
from foundry.project import load

sys.path.insert(0, str(ROOT / "projects" / "cckb"))
import interface as I  # noqa: E402


def ifc_with(**over):
    """spec の値を差し替えた Interface（故意に壊す検査用）。load() は毎回新しい spec を作る。"""
    p = load("cckb")
    for k, v in over.items():
        setattr(p.spec, k, v)
    return I.Interface(p)


@pytest.fixture(scope="module")
def ifc():
    return I.Interface()


# ---------------------------------------------------------------------------
# 幾何の小道具（自分の関数を外の実装と突き合わせる）
# ---------------------------------------------------------------------------

def test_poly_offset_matches_build123d():
    """poly_offset_axis がスタビの輪郭を build123d の INTERSECTION オフセットと同じに広げる。
    （初版は符号が逆で**縮めていた**——取付の探索がスタビの逃げを実際より小さく見た）。
    V1 の輪郭（凸でない 8 点）と V2 のプレートの開口（凸でない 8 点）の両方で見る"""
    from build123d import BuildLine, BuildSketch, Kind, Polyline, make_face, offset

    from foundry.mech import CHOC_STAB_OUTLINE, CHOC_V2_STAB_PLATE

    # V2 の開口には幅 0.495 の切り欠き（羽の付け根の角）があり、0.5 広げると閉じる（軸ごとの広げ方は閉じた
    # 切り欠きを扱えない）。プレートで使う STAB_KERF 0.15 だけで見る
    for outline, d in [(CHOC_STAB_OUTLINE, 0.15), (CHOC_STAB_OUTLINE, 0.5), (CHOC_V2_STAB_PLATE, 0.15)]:
        with BuildSketch() as sk:
            with BuildLine():
                Polyline(*outline, close=True)
            make_face()
            offset(amount=d, kind=Kind.INTERSECTION)
        bb = sk.sketch.bounding_box()
        mine = I.poly_box(I.poly_offset_axis(list(outline), d))
        assert all(abs(a - b) < 1e-6 for a, b in
                   zip(mine, (bb.min.X, bb.min.Y, bb.max.X, bb.max.Y))), (d, mine, bb)
        area = sk.sketch.area
        poly = I.poly_offset_axis(list(outline), d)
        shoelace = abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                           - poly[(i + 1) % len(poly)][0] * poly[i][1]
                           for i in range(len(poly)))) / 2
        assert abs(area - shoelace) < 1e-6


# ---------------------------------------------------------------------------
# 外の事実: XIAO の寸法を Seeed 公式の STEP から測る
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def xiao_step():
    from build123d import import_step

    return import_step(str(paths.LIB / "xiao.3dshapes" / "XIAO_nRF52840.step"))


def _usb_shell(step):
    """USB シェルの立体。**寸法で特定する**（HHKB で bbox の端から推測して 180° 逆に置いた）。"""
    hits = [s for s in step.solids()
            if abs(sorted([s.bounding_box().size.X, s.bounding_box().size.Y,
                           s.bounding_box().size.Z])[-1] - 8.94) < 0.02
            and abs(sorted([s.bounding_box().size.X, s.bounding_box().size.Y,
                            s.bounding_box().size.Z])[1] - 7.3) < 0.02]
    assert len(hits) == 1, len(hits)
    return hits[0]


def test_the_xiao_numbers_are_the_official_step(xiao_step):
    s = load("cckb").spec
    board = max(xiao_step.solids(), key=lambda so: so.bounding_box().size.X
                * so.bounding_box().size.Z)
    bb = board.bounding_box()
    assert abs(bb.size.X - s.XIAO_L) < 0.01 and abs(bb.size.Z - s.XIAO_W) < 0.01
    shell = _usb_shell(xiao_step)
    sh = shell.bounding_box()
    assert abs((sh.max.X - bb.max.X) - s.XIAO_USB_OVERHANG) < 0.01
    assert abs(sh.size.Z - s.XIAO_USB_W) < 0.01
    assert abs(xiao_step.bounding_box().max.Y - bb.min.Y - s.XIAO_H) < 0.01
    # 口の外形の中心の高さ（断面で測る。STEP の座標の Y が上）
    from build123d import Vector

    ys = [sh.min.Y + i * 0.02 for i in range(0, int(sh.size.Y / 0.02) + 1)]
    zc = (sh.min.Z + sh.max.Z) / 2            # 幅の中央: 上下の壁の外面が口の外形
    solid = [shell.is_inside(Vector(sh.max.X - 0.1, y, zc)) for y in ys]
    lo = ys[solid.index(True)]
    hi = ys[len(solid) - 1 - solid[::-1].index(True)]
    assert abs((lo + hi) / 2 - bb.min.Y - s.XIAO_USB_Z) < 0.03, ((lo + hi) / 2 - bb.min.Y)
    assert abs((hi - lo) - s.XIAO_USB_H) < 0.05
    # アンテナのチップ（1.6×3.2×0.5）: USB と反対の端からの範囲
    chip = [so for so in xiao_step.solids()
            if abs(so.bounding_box().size.X - 1.6) < 0.01
            and abs(so.bounding_box().size.Z - 3.2) < 0.01]
    assert len(chip) == 1
    cb = chip[0].bounding_box()
    a0, a1 = s.XIAO_ANT_FROM_EDGE
    assert abs(cb.min.X - bb.min.X - a0) < 0.01 and abs(cb.max.X - bb.min.X - a1) < 0.01


def test_the_xiao_check_notices_a_wrong_length(xiao_step, monkeypatch):
    real = load

    def fake(name):
        p = real(name)
        p.spec.XIAO_L = 21.5
        return p
    monkeypatch.setattr(sys.modules[__name__], "load", fake)
    with pytest.raises(AssertionError):
        test_the_xiao_numbers_are_the_official_step(xiao_step)


# ---------------------------------------------------------------------------
# 角: 部品が角に入り、壁・隣のキー・基板の縁から離れていること
# ---------------------------------------------------------------------------

COPPER_EDGE = 0.3            # 銅と外形（pcb_rules.JLC["edge_clearance"]）


def corner_problems(ifc):
    s, z = ifc.s, ifc.z()
    out = []
    copper = I.grow(ifc.pcb, -COPPER_EDGE)
    corners = ifc.corners()
    # --- 左: XIAO ---
    xiao, pads = ifc.xiao(), ifc.xiao_pads_extent()
    if not I.inside(copper, (pads[0], pads[1], pads[2], pads[3])):
        out.append("XIAO のパッドが基板の銅の範囲の外")
    cav = ifc.cover_cavity("left")
    cav = (cav[0], cav[1], cav[2], math.inf)      # 奥は垂れ壁が無い（プレートの開口で見る・下）
    if not I.inside(cav, xiao, 0.2):
        out.append(f"XIAO がふたの下の空間に 0.2 の隙で入らない {xiao} / {cav}")
    lc = corners["left"]
    if xiao[3] > lc[3] - 0.2 or pads[3] > lc[3]:
        out.append("XIAO がプレートの開口（角のセル）の外に出る")
    if z["xiao_top"] > z["lid_bottom"] - 0.3:
        out.append("XIAO の頭がふたに当たる")
    face = ifc.usb_shell()[0]
    recess = face - ifc.case_outer[0]
    if not (0.0 <= recess <= s.USB_SHELL_EXPOSED - 0.2 - 0.2):
        out.append(f"USB の口が外面から {recess:.2f}（0〜{s.USB_SHELL_EXPOSED - 0.4:.2f}）")
    if xiao[0] < ifc.wall_inner[0] + 0.2:
        out.append("XIAO の基板が壁に食い込む")
    body_bottom = z["usb_center"] - s.USB_PLUG_BODY_H / 2
    if body_bottom < 0.5:
        out.append(f"プラグの樹脂が机に当たる（下端 {body_bottom:.2f}）")
    # --- 右: ホルダ・電池・ふた・電源スイッチ ---
    cav = ifc.cover_cavity("right")
    for pad in ifc.holder_pads():
        if not I.inside(copper, pad):
            out.append("ホルダのパッドが銅の範囲の外")
    if not I.inside(cav, ifc.holder_body(), 0.2):
        out.append("ホルダがふたの下の空間に入らない")
    (cx, cy), cr = ifc.cell()
    if not I.inside(cav, (cx - cr, cy - cr, cx + cr, cy + cr), 0.2):
        out.append("電池がふたの下の空間に入らない")
    if z["holder_top"] > z["lid_bottom"] - 0.3:
        out.append("ホルダの頭がふたに当たる")
    (px, py), pr = ifc.lid_pillar()
    if I.circle_rect_gap((px, py), pr, ifc.holder_body()) < 3.0:
        out.append("ふたの柱が電池を取り出す指の場所を塞ぐ（ホルダから 3.0 未満）")
    if not I.inside(cav, (px - pr, py - pr, px + pr, py + pr), 0.2):
        out.append("ふたの柱がふたの下の空間の外")
    # 電源スイッチ（表・スルーホール・レバーが上。spec.PSW_*）
    body = ifc.psw_body()                          # 公差の最大
    for pad in ifc.psw_pads():
        if not I.inside(copper, pad):
            out.append("電源スイッチのランドが銅の範囲の外")
    if not I.inside(ifc.pcb, body):
        out.append("電源スイッチの本体が基板の外へ出る（基板を上から落とすときの壁との隙を食う）")
    if not I.inside(cav, body, 0.2):
        out.append("電源スイッチがふたの下の空間に入らない")
    for pad in ifc.holder_pads():
        if I.rect_gap(body, pad) < s.PSW_HOLDER_CLEAR - 1e-9:
            out.append(f"電源スイッチとホルダのパッドの間 {I.rect_gap(body, pad):.2f}"
                       f"（コートヤードが重ならない {s.PSW_HOLDER_CLEAR}）")
    if z["psw_top"] + s.PSW_H_TOL > z["lid_bottom"] - 0.3:
        out.append("電源スイッチの本体がふたに当たる")
    tip = ifc.psw_tip_range()
    if not (z["lid_bottom"] < tip[1] < z["rim"]):
        out.append(f"レバーの先（名目 {tip[1]:.2f}）がふたの穴の中（{z['lid_bottom']:.2f}〜{z['rim']:.2f}）にない"
                   "（上なら鞄の中で出る・下なら爪が届かない）")
    if s.PSW_PIN_TRIM > s.UNDER_PCB - 0.3:
        out.append("電源スイッチの切った足が床に 0.3 未満")
    pins = ifc.psw_pins()
    if abs(pins[0][1] - pins[1][1] - s.PSW_PIN_PITCH) > 1e-9 or pins[1] != tuple(s.PSW_AT):
        out.append("電源スイッチの足の並び")
    # --- 角のふたと隣のキャップ ---
    for side in ("left", "right"):
        cov = ifc.cover(side)
        for (x, y), k in zip(ifc.positions, ifc.keys):
            cap = (x - k.w_mm / 2 + s.KEYCAP_GAP, y - 9.525 + s.KEYCAP_GAP,
                   x + k.w_mm / 2 - s.KEYCAP_GAP, y + 9.525 - s.KEYCAP_GAP)
            if I.rect_gap(cov, cap) < 1.0:
                out.append(f"{side} のふたが {k.label} のキャップに 1.0 未満")
    return out


def test_the_corner_parts_fit_their_corners(ifc):
    assert corner_problems(ifc) == []


@pytest.mark.parametrize("over, expect", [
    (dict(XIAO_AT=(-131.67, -38.1)), "USB の口"),                 # 1mm 奥へ引っ込めた
    (dict(CASE_WALL=2.4), "USB の口"),         # 壁を厚くした（XIAO が同じ所なら口が 1.1 引っ込む）
    (dict(XIAO_AT=(-133.47, -38.1)), "XIAO の基板が壁"),         # XIAO を壁へ 0.8 寄せた
    (dict(XIAO_AT=(-132.67, -37.5)), "プレートの開口"),
    (dict(HOLDER_AT=(129.5, -38.6)), "ホルダのパッドが銅"),
    (dict(HOLDER_H=6.2), "ホルダの頭"),
    (dict(PSW_AT=(141.625, -38.6)), "本体が基板の外"),          # 右へ 0.4（縁に揃えた位置から）
    (dict(HOLDER_AT=(125.2, -38.6)), "ホルダのパッドの間"),       # ホルダを 0.5 戻す（コートヤードが重なる）
    (dict(PSW_AT=(141.225, -45.0)), "ふたの下の空間"),            # 手前へ（本体が壁の内面を越える）
    (dict(PSW_TAB=0.6), "レバーの先"),                           # 爪が 0.2 長い → 先がふたの上面を越える
    (dict(PSW_LEVER_H=1.5), "レバーの先"),                       # 短いレバー → 爪が届かない
    (dict(PSW_PIN_TRIM=1.7), "切った足"),
    (dict(LID_PILLAR_AT=(111.0, -38.6)), "指の場所"),
    (dict(CASE_KEY_GAP=0.2), "キャップ"),
    (dict(RIM_ABOVE_PCB=6.5), "ホルダの頭"),
])
def test_the_corner_check_notices_a_break(over, expect):
    bad = corner_problems(ifc_with(**over))
    assert any(expect in b for b in bad), bad


def test_the_psw_tip_worst_case_includes_pcb_thickness_tolerance(ifc):
    """重要 1（監査 audit-psw.md）: 基板は床のボスに**下面**で載り、ふた（rim）は名目の積み上げで
    刷った固定の立体。基板が厚いほど、その分だけレバーの先はふたに対して相対的に上がる。
    最悪値は本体 ±PSW_H_TOL・レバー ±PSW_LEVER_H_TOL に基板の厚さ ±PCB_T_TOL_ABS（JLC 1.6mm ±10% = 0.16）
    を足した +0.36（ふたの上面から出る）。"""
    s = ifc.s
    z = ifc.z()
    lo, nom, hi = ifc.psw_tip_range()
    assert hi == pytest.approx(z["rim"] + 0.36, abs=1e-9)
    assert s.PCB_T_TOL_ABS == pytest.approx(0.16, abs=1e-9)


def test_the_psw_tip_worst_case_check_notices_a_missing_pcb_term():
    """基板の厚さの項を抜くと、最悪値が小さくなりすぎる（重要 1 の直しが効いていることの確認）。"""
    ifc = ifc_with()
    z = ifc.z()
    lo, nom, hi = ifc.psw_tip_range()
    d_without_pcb = ifc.s.PSW_H_TOL + ifc.s.PSW_LEVER_H_TOL
    hi_without_pcb = z["psw_tip"] + d_without_pcb
    assert hi > hi_without_pcb  # 直した版は必ずより出っ張る側に出る
    assert hi - hi_without_pcb == pytest.approx(ifc.s.PCB_T_TOL_ABS, abs=1e-9)


def test_the_left_cover_screw_keeps_5mm_from_the_antenna(ifc):
    """H3（左のふたのネジ）の鋼のネジとアンテナのチップの間（HHKB の要件 5mm・rf-antenna.md）。"""
    chip = ifc.antenna_chip()
    h3 = [m for m in ifc.mounts() if ifc.in_corner(m)]
    assert len(h3) == 1
    assert I.circle_rect_gap(h3[0], I.HOLE_D / 2 - 0.1, chip) >= 5.0


# ---------------------------------------------------------------------------
# 高さ
# ---------------------------------------------------------------------------

def z_problems(ifc):
    s, z = ifc.s, ifc.z()
    out = []
    # 基板の下へ出る物の最悪（基板が −10%・長さは公差の上限）。**床の止まり穴の上の物は穴の底と比べる**
    thin = z["pcb_bottom"] + s.PCB_T * (1 - s.PCB_T_TOL)           # 最悪の基板の上面
    worst_tip = thin - (s.SWITCH_PIN_L + s.SWITCH_PIN_TOL)
    # 足（端子 2・位置決め 1）の下にも止まり穴がある（2026-09-26。穴が板の足の穴の下にあることは
    # test_the_floor_pockets_sit_under_every_hole_of_the_switches が見る）
    if worst_tip < z["pocket_floor"] + 0.1:
        out.append(f"足の先（最悪 {worst_tip:.2f}）が床の穴の底 {z['pocket_floor']:.2f} に 0.1 未満")
    stud = thin - (s.SWITCH_STUD_L + s.SWITCH_STUD_TOL)
    if stud < z["pocket_floor"] + 0.1:
        out.append(f"中心の突起（最悪 {stud:.2f}）が床の穴の底 {z['pocket_floor']:.2f} に 0.1 未満")
    box = thin - s.STAB_BOX_L
    if box < z["pocket_floor"] + 0.1:
        out.append(f"スタビの箱（最悪 {box:.2f}）が床の穴の底 {z['pocket_floor']:.2f} に 0.1 未満")
    # スタビのねじの頭（基板の下面に着く。φ3.7 × 1.5・[暫定]）の下にも止まり穴（2026-09-26・監査 E 重要 2）
    if z["stab_screw_head"] < z["pocket_floor"] + 0.1:
        out.append(f"スタビのねじの頭（{z['stab_screw_head']:.2f}）が床の穴の底 {z['pocket_floor']:.2f} に 0.1 未満")
    if z["pocket_floor"] < 0.8 - 1e-9:
        out.append(f"床の穴の底の肉 {z['pocket_floor']:.2f} が 0.8（0.2 層で 4 層）未満")
    for name, h in (("BAT46W", 1.25), ("TSSOP-16", 1.2), ("裏の部品の包絡", s.BOTTOM_PART_H),
                    ("電源スイッチの切った足", s.PSW_PIN_TRIM),
                    ("スタビの爪", s.STAB_CLAW_L - s.PCB_T * (1 - s.PCB_T_TOL))):
        if h > s.UNDER_PCB - 0.3:
            out.append(f"{name} が床に 0.3 未満")
    if abs(z["plate_top"] - z["plate_bottom"] - ifc.sw.plate_t) > 1e-9 or \
            z["plate_bottom"] - z["pcb_top"] < 0.9:
        out.append("プレートと基板の隙間")
    if z["rim"] < z["keycap_bottomed"]:
        out.append("縁が押し切ったキャップより低い")
    # 下からのネジ: 先端がナットを抜け、プレートの上面を越えない
    tip = z["screw_head"] + s.SCREW_L
    if not (z["pcb_top"] + s.NUT_T <= tip + 1e-9 and tip <= z["plate_top"] - 0.1 + 1e-9):
        out.append(f"ネジの先 {tip:.2f}（ナット上面 {z['pcb_top'] + s.NUT_T:.2f}〜"
                   f"プレート上面 {z['plate_top']:.2f}）")
    # 皿の頭: 机から 0.5 以上沈み、頭の上（ボスの中）に 1.2 残る。頭の座は床 1.2 より上まで来るが、
    # 取付のボス φ5.6（床から基板の下面まで中身が詰まった柱）の中に入る（断面 section_mount_h0）
    if z["screw_head"] < 0.5 - 1e-9 or z["screw_head"] + s.SCREW_HEAD_H > z["pcb_bottom"] - 1.2 + 1e-9:
        out.append("皿の座ぐりの深さ")
    if s.CASE_FLOOR < 1.2 - 1e-9 or z["island_top"] - s.ANTISLIP_RECESS < 1.2 - 1e-9 \
            or s.ANTISLIP_SHEET_T <= s.ANTISLIP_RECESS:
        out.append("滑り止め（床・島の残りか、シートが接地しない）")
    # 全体の厚さ: V1 で利用者が決めた 13.8（O10）に、V2 の +0.6（ステム 8.0 → 8.6）を足した 14.4。
    # 2026-09-25 利用者の決定（基板の下の空きは 1.8 のまま・床に止まり穴。決定記録 2026-09-25-choc-v2 §4-2 の案 2）
    if z["keycap_top"] > 14.4 + 1e-9:
        out.append(f"全体の厚さ {z['keycap_top']:.2f} が利用者の決めた 14.4 を超える（O10 ＋ V2）")
    return out


def test_the_z_stack_holds(ifc):
    assert z_problems(ifc) == []


@pytest.mark.parametrize("over, expect", [
    (dict(UNDER_PCB=1.4), "足の先"),
    (dict(BOTTOM_PART_H=1.7), "裏の部品の包絡"),
    (dict(PSW_PIN_TRIM=1.7), "電源スイッチの切った足"),
    (dict(STAB_BOX_L=3.6), "スタビの箱"),
    (dict(SWITCH_STUD_L=3.6), "中心の突起"),
    (dict(FLOOR_POCKET_DEPTH=0.2), "中心の突起"),          # 穴が浅い
    (dict(FLOOR_POCKET_DEPTH=0.6), "床の穴の底の肉"),
    (dict(STAB_CLAW_L=3.2), "スタビの爪"),
    (dict(STAB_SCREW_HEAD_H=2.2), "スタビのねじの頭"),
    (dict(SCREW_L=8), "皿の座ぐり"),          # 頭の沈めは先から導くので、長いネジは頭が机の下へ出る
    (dict(SCREW_L=5), "皿の座ぐり"),          # 短いネジは頭がボスの上の肉を食う
    (dict(SCREW_PAST_NUT=-0.2), "ネジの先"),
    (dict(SCREW_PAST_NUT=0.8), "ネジの先"),
    (dict(SCREW_PAST_NUT=0.2), "皿の座ぐり"),
    (dict(CASE_FLOOR=1.0), "滑り止め"),
    (dict(CASE_FLOOR=1.6), "全体の厚さ"),
    (dict(SWITCH_STEM_ABOVE_PCB=8.7), "全体の厚さ"),
    (dict(ANTISLIP_SHEET_T=0.4), "滑り止め"),
    (dict(RIM_ABOVE_PCB=5.5), "縁"),
])
def test_the_z_check_notices_a_break(over, expect):
    bad = z_problems(ifc_with(**over))
    assert any(expect in b for b in bad), bad


def stiffness_margins(ifc):
    """基板が下へたわんだとき、裏に出る物の先と、その下の床（止まり穴の底・床の上面）の最悪の隙 {物: 隙}。"""
    s, z = ifc.s, ifc.z()
    thin = z["pcb_bottom"] + s.PCB_T * (1 - s.PCB_T_TOL)
    return {"足": thin - (s.SWITCH_PIN_L + s.SWITCH_PIN_TOL) - z["pocket_floor"],
            "中心の突起": thin - (s.SWITCH_STUD_L + s.SWITCH_STUD_TOL) - z["pocket_floor"],
            "スタビの箱": thin - s.STAB_BOX_L - z["pocket_floor"],
            "スタビのねじの頭": z["stab_screw_head"] - z["pocket_floor"],
            "裏の部品": z["pcb_bottom"] - s.BOTTOM_PART_H - s.CASE_FLOOR}


def test_the_pcb_thickness_is_stiff_enough(ifc):
    """O3。キーの中心から最寄りの支え（柱・取付）までの最大距離 d で、両端支持の梁
    （幅 1u・スパン 2d）に中央 10N（手のひら）をかけたたわみ。裏に出る物の最悪の余裕
    （V2 では中心の突起と止まり穴の底の 0.24）より小さいこと。FR4 の曲げ弾性率は保守側 18.6GPa。"""
    s = ifc.s
    sup = list(s.SUPPORTS) + ifc.mounts()
    d = max(min(math.hypot(x - a, y - b) for a, b in sup) for x, y in ifc.positions)
    L, b, E, F = 2 * d, 19.05, 18600.0, 10.0
    defl = lambda t: F * L ** 3 / (48 * E * b * t ** 3 / 12)
    m = stiffness_margins(ifc)
    margin = min(m.values())
    print(f"d={d:.1f} L={L:.1f} 1.6: {defl(1.6):.3f} 1.2: {defl(1.2):.3f} 余裕 {m}")
    assert s.PCB_T == 1.6 and defl(s.PCB_T) < margin


def test_the_stiffness_check_notices_a_shallow_pocket():
    """止まり穴を 0.2 に浅くすると、中心の突起の余裕が 0.04 になり、たわみ 0.136 に負ける。"""
    m = stiffness_margins(ifc_with(FLOOR_POCKET_DEPTH=0.2))
    assert min(m.values()) < 0.136


# ---------------------------------------------------------------------------
# スタビの逃げ穴（O2）
# ---------------------------------------------------------------------------

def stab_problems(ifc, geo=None):
    """スタビの箱の穴（Edge.Cuts）: 箱（図の 5.80 × 7.30・参照）を x 片側 0.1・y 片側 0.35 以上の隙で含む
    （x 6.0 は販売者の足跡〔実物の実測〕の値。外形の公差 ±0.2 できつければやすりで広げる・lessons K）。
    箱の穴とねじ・爪の丸穴の間の基板の橋が 0.7 以上（ねじ: 6.2 − 1.5 − 4.0）。"""
    out = []
    reliefs, housings = ifc.stab_reliefs(), ifc.stab_housings()
    if len(reliefs) != 8 or len(housings) != 8:
        out.append(f"スタビが {len(reliefs)} 個（Enter・左 Shift・スペース 2 つで 8）")
    for rel, hou in zip(reliefs, housings):
        r, h = I.poly_box(rel), I.poly_box(hou)
        gx, gy = min(h[0] - r[0], r[2] - h[2]), min(h[1] - r[1], r[3] - h[3])
        if gx < 0.1 - 1e-9 or gy < 0.35 - 1e-9:
            out.append(f"逃げ穴とハウジングの隙 x {gx:.2f}（0.1）・y {gy:.2f}（0.35）")
    holes = ifc.stab_holes()
    if len(holes) != 16:
        out.append(f"ねじ・爪の穴 {len(holes)}（16）")
    for kind, c, d in holes:
        web = min(I.circle_poly_gap(c, d / 2, rel) for rel in reliefs)
        if web < 0.7 - 1e-9:
            out.append(f"箱の穴と{kind}の穴の橋 {web:.2f}（0.7 未満）")
    if geo is not None:
        for rel in reliefs:
            for pad in geo["pads"]:
                if re.fullmatch(r"SW\d+", pad["ref"]):
                    b = pad["box"]
                    c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
                    if I.circle_poly_gap(c, (b[2] - b[0]) / 2, rel) < COPPER_EDGE:
                        out.append(f"逃げ穴が {pad['ref']} のパッドに近い")
    return out


def test_the_stab_relief_contains_the_housing(ifc):
    assert stab_problems(ifc) == []


def _holes_with(monkeypatch, **kw):
    H = dict(I.CHOC_V2_STAB_HOLES)
    H.update(kw)
    monkeypatch.setattr(I, "CHOC_V2_STAB_HOLES", H)
    return I.Interface()


def test_the_stab_check_notices_a_thin_margin(monkeypatch):
    assert any("隙" in b for b in stab_problems(_holes_with(monkeypatch, box=(-2.95, -4.0, 2.95, 4.0))))


def test_the_stab_check_notices_a_thin_web(monkeypatch):
    """1 回目の板の穴（y にも広げた）では、ねじの穴との橋が 0.2 になった。"""
    assert any("橋" in b for b in stab_problems(_holes_with(monkeypatch, box=(-3.0, -4.5, 3.0, 4.5))))


# ---------------------------------------------------------------------------
# 印刷する部品は A1 mini（168.4 角）に入る。プレートの継ぎ目は開口を切らない
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plate_pieces():
    from foundry.plate import build_plate, split_plate

    p = load("cckb")
    whole, _, _ = build_plate(p.spec, p.keys(), "main")
    return whole, split_plate(p.spec, whole, "main", p.keys())


def test_every_printed_part_fits_the_a1_mini(ifc, plate_pieces):
    whole, pieces = plate_pieces
    assert len(pieces) == 2
    vol = sum(pc.volume for _, pc in pieces)
    assert abs(vol - whole.volume) < 1e-3            # 分けて失った物が無い
    for name, pc in pieces:
        bb = pc.bounding_box().size
        assert max(bb.X, bb.Y) <= ifc.s.PRINT_MAX, (name, bb)
    for name, box in ifc.case_pieces().items():
        assert max(I.size(box)) <= ifc.s.PRINT_MAX, (name, I.size(box))


@pytest.mark.parametrize("over, msg", [
    ({"PLATE_SPLIT": {"main": (9.525, 0.0, 4.7625, -4.7625)}}, "キーの段は 5 段"),   # 段より 1 つ少ない
    ({"PLATE_MARGIN_Y": 2.0}, "段の高さ"),        # 外形から割り出す段の高さがキーの段とずれる
])
def test_the_plate_split_refuses_a_split_that_does_not_match_the_rows(plate_pieces, over, msg):
    """最終レビュー M1: 個数が段数と違う・外形から割り出した段の高さがキーと違うときは黙って
    別の所で切らずに落とす（外形は本物のまま、分け方の前提だけを壊す）。"""
    from foundry.plate import split_plate

    p = load("cckb")
    for k, v in over.items():
        setattr(p.spec, k, v)
    with pytest.raises(ValueError, match=msg):
        split_plate(p.spec, plate_pieces[0], "main", p.keys())


def test_the_print_check_notices_a_long_piece():
    ifc = ifc_with(CASE_SEAM=(30.0, 30.0))
    assert any(max(I.size(b)) > ifc.s.PRINT_MAX for b in ifc.case_pieces().values())


def seam_problems(ifc):
    out = []
    seam = ifc.plate_seam()
    segs = list(zip(seam, seam[1:]))
    web = 2.0                                            # 継ぎ目の両側に残す桟
    for b in ifc.switch_bodies():
        for a, c in segs:
            if min(I.seg_dist(p, a, c) for p in ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]),
                                                   (b[2], b[3]))) < web or \
                    (a[0] == c[0] and b[0] - web < a[0] < b[2] + web
                     and min(a[1], c[1]) < b[3] and max(a[1], c[1]) > b[1]):
                out.append(f"継ぎ目がスイッチの開口 {b} を切る")
    for poly in ifc.stab_plate_openings():
        for a, c in segs:
            if min(I.seg_dist(p, a, c) for p in poly) < web:
                out.append("継ぎ目がスタビの開口に近い")
    for m in ifc.mounts():
        if min(I.seg_dist(m, a, c) for a, c in segs) < I.hex_r(ifc.s.MOUNT_POCKET_AF) + web:
            out.append(f"継ぎ目が取付 {m} の穴に近い")
    return out


def test_the_plate_seam_runs_between_openings(ifc):
    assert seam_problems(ifc) == []


def test_the_seam_check_notices_a_seam_through_a_key():
    assert seam_problems(ifc_with(PLATE_SPLIT={"main": (0.0, 0.0, 4.7625, -4.7625, 4.7625)}))


# ---------------------------------------------------------------------------
# 取付・支え ↔ いま生成した基板
# ---------------------------------------------------------------------------

def _read_geometry(board, out):
    r = subprocess.run([paths.KICAD_PYTHON, str(ROOT / "projects/cckb/tools/board_geometry.py"),
                        str(board), str(out)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
    return json.loads(out.read_text())


def _shape(g):
    """板の形だけ（どの板から作ったかの印を除く）。部品・パッドは並びを問わない（生成し直すと
    KiCad の並びが変わる。中身は同じ）。"""
    out = {k: v for k, v in g.items() if k != "board_sha256"}
    for k in ("footprints", "pads"):
        out[k] = sorted(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in out[k])
    return out


@pytest.fixture(scope="module")
def geo():
    """発注する板の形（コミットした写し・板の sha256 で突き合わせる）。KiCad が要らないので CI でも
    走る（最終レビュー I5）。写しが**いま生成した基板**と同じ形であることは下の 2 つの検査が
    KiCad で見る（配線は形を変えない: パッド・コートヤード・外形は未配線の板と同じ）。"""
    return I.board_geometry()


@pytest.fixture(scope="module")
def generated_geo(tmp_path_factory):
    """foundry.pcb が**いま生成した**未配線の板の形（KiCad の Python）。"""
    require(paths.KICAD_PYTHON, "基板の生成")
    d = tmp_path_factory.mktemp("cckbif") / "cckb"
    shutil.copytree(paths.PROJECTS / "cckb", d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(d)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return _read_geometry(d / "pcb/unrouted/cckb_main.kicad_pcb", d / "geo.json")


def test_the_committed_geometry_is_what_kicad_reads_from_the_routed_board(tmp_path):
    """写しの中身 = KiCad がいま発注する板から読む物（sha256 が合っていても、手で直した写しを通さない）。"""
    require(paths.KICAD_PYTHON, "配線済みの板を読む")
    for suf in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(I.ROUTED_BOARD.with_suffix(suf), tmp_path / I.ROUTED_BOARD.with_suffix(suf).name)
    got = _read_geometry(tmp_path / I.ROUTED_BOARD.name, tmp_path / "geo.json")
    assert got == json.loads(I.BOARD_GEOMETRY.read_text())


def test_the_committed_geometry_is_what_the_generator_makes_now(geo, generated_geo):
    """取付・支えの検査は前は**いま生成した**板を読んでいた。写しに替えても同じ物を見ていること。"""
    assert _shape(geo) == _shape(generated_geo)


def test_the_geometry_check_notices_a_changed_board(tmp_path):
    """**検査器が壊れていないか。**板が 1 バイト変われば写しは古い（KiCad は要らない）。"""
    board = tmp_path / "b.kicad_pcb"
    board.write_bytes(I.ROUTED_BOARD.read_bytes() + b"\n")
    with pytest.raises(I.StaleGeometry):
        I.board_geometry(board)
    assert I.board_geometry()["board_sha256"]           # 本物は通る


def test_the_board_has_exactly_the_declared_mounts(ifc, geo):
    holes = sorted((f["x"], f["y"]) for f in geo["footprints"] if re.fullmatch(r"H\d+", f["ref"]))
    assert len(holes) == len(ifc.mounts()) == 10
    for (x, y), (mx, my) in zip(holes, sorted(ifc.mounts())):
        assert abs(x - mx) < 1e-3 and abs(y - my) < 1e-3
    # 母数: 相手にした部品の数（名前の数ではなく物の数）
    assert len([f for f in geo["footprints"] if re.fullmatch(r"(SW|D)\d+", f["ref"])]) == 124


def test_every_mount_meets_the_five_conditions(ifc, geo):
    bad = {m: I.mount_problems(ifc, geo, m, corner_ok=True) for m in ifc.mounts()}
    assert not any(bad.values()), {k: v for k, v in bad.items() if v}


@pytest.mark.parametrize("move, expect", [
    ((-133.35, 38.1), "スイッチの開口"),        # Esc の真ん中
    ((-120.99, 20.07), "裏のコートヤード"),     # Tab のダイオード（キー −128.59 + 7.6）の上
    ((-139.18, 46.5), "縁"),
    ((-57.24, -40.0), "スタビ"),
    ((-110.0, 15.7), "配線"),                  # 行 1 のバス（裏・キー中心の 3.35 下）の上
    ((0.0, 28.575), "段の境目"),
    ((4.7625, -43.0), "継ぎ目"),
    ((128.5, -38.6), "ホルダ"),
])
def test_the_mount_check_notices_a_bad_place(ifc, geo, move, expect):
    bad = I.mount_problems(ifc, geo, move)
    assert any(expect in b for b in bad), bad


def test_every_support_is_clear_of_the_bottom_parts(ifc, geo):
    bad = {p: I.support_problems(ifc, geo, p) for p in ifc.s.SUPPORTS}
    assert not any(bad.values()), {k: v for k, v in bad.items() if v}
    assert len(ifc.s.SUPPORTS) >= 30


def test_the_support_check_notices_a_post_on_a_diode(ifc, geo):
    d1 = next(f for f in geo["footprints"] if f["ref"] == "D1")
    assert I.support_problems(ifc, geo, (d1["x"], d1["y"]))


def test_the_stab_relief_clears_the_switch_pads(ifc, geo):
    assert stab_problems(ifc, geo) == []


def relief_diode_problems(ifc, geo, margin=0.3):
    """スタビの逃げ穴（Edge.Cuts）とダイオードのコートヤードの隙が margin 未満のもの（O7）。
    相手は**いま生成した基板**の裏のコートヤード（D\\d+ を fullmatch・母数 62）。"""
    diodes = [f for f in geo["footprints"] if re.fullmatch(r"D\d+", f["ref"])]
    assert len(diodes) == 62 and all("back" in f["courtyard"] for f in diodes)
    bad = []
    for rel in ifc.stab_reliefs():
        for f in diodes:
            b = f["courtyard"]["back"]
            corners = ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3]))
            inside = any(I.point_in_poly(p, rel) for p in corners) or \
                any(I.rect_gap(b, (p[0], p[1], p[0], p[1])) < 0 for p in rel)
            gap = min(_seg_rect_gap(rel[i], rel[(i + 1) % len(rel)], b) for i in range(len(rel)))
            if inside or gap < margin:
                bad.append((f["ref"], round(-1 if inside else gap, 3)))
    return bad


def _seg_rect_gap(a, b, box):
    """線分 ab と矩形の距離（交われば 0）。細かく刻んで測る（0.01 mm）。"""
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.01))
    return min(I.rect_gap(box, (x, y, x, y)) for x, y in
               ((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)))


def test_the_stab_relief_clears_the_diodes(ifc, geo):
    """O7: スタビのキー 4 つのダイオード（V2 はいつもの位置 mech.CHOC_V2.diode_offset）のコートヤードが、
    箱の穴から 0.3 以上（JLC の外形公差 ±0.2 に 0.1 残す）。"""
    assert relief_diode_problems(ifc, geo) == []


def test_the_relief_check_notices_the_old_diode_place(ifc, geo):
    """**検査器が壊れていないか。**V1 の置き場所（7.6, −1.0・縦）に戻したダイオードで落ちること。"""
    g = json.loads(json.dumps(geo))
    for f in g["footprints"]:
        if f["ref"] == "D42":                      # Enter（キー中心 121.444, 0）
            f["courtyard"]["back"] = [121.444 + 7.6 - 1.195, 1.0 - 2.395,
                                      121.444 + 7.6 + 1.195, 1.0 + 2.395]
    assert [r for r, _ in relief_diode_problems(ifc, g)] == ["D42"]


def floor_pocket_problems(ifc, geo):
    """床の止まり穴（interface.floor_pockets・ケースの段が読む）が、**発注する板の実物**の
    スイッチの中心穴（非めっき φ5.05・母数 62）・端子の穴（φ1.2・62 × 2）・位置決めの穴（φ2.1・62）と
    スタビの箱の穴（Edge.Cuts・4 キー × 2）に揃っているか。"""
    out = []
    pk = ifc.floor_pockets()
    studs = [p for p in pk if p["kind"] == "stud"]
    boxes = [p for p in pk if p["kind"] == "stab_box"]
    # 端子と位置決め: 板の穴ごとに、同じスイッチの穴で、中心が同じ・穴の外形 ＋ 片側 0.3 以上を含む物があるか
    # 足 = 端子（めっき）と位置決め（非めっき φ2.1。2026-09-26 に長円から丸に）。中心の穴 φ5.05 は除く
    feet = [p for p in geo["pads"] if re.fullmatch(r"SW\d+", p["ref"]) and p["drill"] > 0
            and not (p["npth"] and p["drill"] > 3)]
    if len(feet) != 62 * 3:
        out.append(f"板の足の穴 {len(feet)}（62 × 3 のはず）")
    for h in feet:
        cx, cy = h["x"], h["y"]
        need = I.grow((cx - (h["box"][2] - h["box"][0]) / 2, cy - (h["box"][3] - h["box"][1]) / 2,
                       cx + (h["box"][2] - h["box"][0]) / 2, cy + (h["box"][3] - h["box"][1]) / 2), 0.3) \
            if h["npth"] else I.rect(cx, cy, h["drill"] + 0.6, h["drill"] + 0.6)
        ok = False
        for p in pk:
            if p["ref"] != h["ref"] or p["kind"] not in ("pin", "locator"):
                continue
            if "d" in p and math.hypot(p["pos"][0] - cx, p["pos"][1] - cy) < 1e-3:
                ok = p["d"] >= h["drill"] + 0.6 - 1e-9
            elif "box" in p and I.inside(p["box"], need):
                ok = True
            if ok:
                break
        if not ok:
            out.append(f"{h['ref']} の足の穴 ({cx:.2f}, {cy:.2f}) の下に止まり穴が無い（か狭い）")
    holes = {p["ref"]: p for p in geo["pads"] if re.fullmatch(r"SW\d+", p["ref"]) and p["npth"]
             and p.get("round") and abs(p["drill"] - 5.05) < 1e-6}
    if len(studs) != 62 or len(holes) != 62:
        out.append(f"突起の穴 {len(studs)} / 板の中心穴 {len(holes)}（62 ずつ）")
    for st in studs:
        h = holes.get(st["ref"])
        if h is None or math.hypot(h["x"] - st["pos"][0], h["y"] - st["pos"][1]) > 1e-3:
            out.append(f"{st['ref']} の突起の穴が板の中心穴と違う所")
        elif st["d"] < ifc.s.SWITCH_STUD_D + 2 * 0.3:
            out.append(f"{st['ref']} の穴 φ{st['d']} が突起 φ{ifc.s.SWITCH_STUD_D} に狭い")
    rel = ifc.stab_reliefs()
    if len(boxes) != len(rel) or len(rel) != 8:
        out.append(f"スタビの箱の穴 {len(boxes)} / 基板の穴 {len(rel)}（8）")
    for b in boxes:
        for h in ifc.stab_housings():
            hb = I.poly_box(h)
            if I.rect_gap(b["box"], hb) < 0 and not I.inside(b["box"], hb, 0.3):
                out.append(f"{b['ref']} の穴が箱 {hb} を 0.3 以上の余裕で含まない")
    # スタビのねじの頭: 板のスタビ（ST\d+）の小さい方の穴（ねじ）の真下に、頭 φSTAB_SCREW_HEAD_D ＋ 片側 0.3 以上
    screws = []
    for ref in sorted({p["ref"] for p in geo["pads"] if re.fullmatch(r"ST\d+", p["ref"])}):
        hs = [p for p in geo["pads"] if p["ref"] == ref]
        small = min(p["drill"] for p in hs)
        screws += [p for p in hs if p["drill"] == small]
    heads = [p for p in pk if p["kind"] == "stab_screw"]
    if len(screws) != 8 or len(heads) != 8:
        out.append(f"ねじの穴 {len(screws)} / 頭の止まり穴 {len(heads)}（8）")
    for h in screws:
        if not any(math.hypot(p["pos"][0] - h["x"], p["pos"][1] - h["y"]) < 1e-3
                   and p["d"] >= ifc.s.STAB_SCREW_HEAD_D + 0.6 - 1e-9 for p in heads):
            out.append(f"{h['ref']} のねじ ({h['x']:.2f}, {h['y']:.2f}) の頭の下に止まり穴が無い（か狭い）")
    return out


def test_the_floor_pockets_sit_under_every_hole_of_the_switches(ifc, geo):
    assert floor_pocket_problems(ifc, geo) == []


def test_the_pocket_check_notices_a_tight_pocket(geo):
    bad = floor_pocket_problems(ifc_with(FLOOR_POCKET_CLEAR=0.1), geo)
    assert any("突起" in b for b in bad) and any("箱" in b for b in bad) and any("足の穴" in b for b in bad) \
        and any("頭" in b for b in bad), bad


def test_the_pocket_check_notices_pins_without_pockets(ifc, geo):
    """足の止まり穴を外す（前の形）と、62 × 3 の足の穴が全部見つかる。"""
    i2 = ifc_with()
    base = i2.floor_pockets
    i2.floor_pockets = lambda: [p for p in base() if p["kind"] not in ("pin", "locator")]
    bad = [b for b in floor_pocket_problems(i2, geo) if "足の穴" in b]
    assert len(bad) == 62 * 3, len(bad)


def test_the_pocket_check_notices_a_moved_switch(ifc, geo):
    g = json.loads(json.dumps(geo))
    hole = next(p for p in g["pads"] if p["ref"] == "SW7" and p["npth"] and abs(p["drill"] - 5.05) < 1e-6)
    hole["x"] += 0.1
    assert floor_pocket_problems(ifc, g)


def test_the_board_outline_is_the_declared_pcb(ifc, geo):
    e = geo["edge"]
    assert all(abs(a - b) < 0.06 for a, b in zip(e, ifc.pcb)), (e, ifc.pcb)


def _plate_open_at_pockets(spec):
    from build123d import Vector

    from foundry.plate import build_plate

    p = load("cckb")
    part, _, _ = build_plate(spec, p.keys(), "main")
    t = part.bounding_box().size.Z / 2
    # 中心から x に 1.9: 二面幅 4.2 の六角（二面が ±x）なら穴の中、M2 のバカ穴 φ2.4 なら板の中
    return [not part.is_inside(Vector(m[0] + 1.9, m[1], t))
            for m in spec.MOUNTS["main"] if not I.Interface(p).in_corner(m)]


def test_the_plate_has_a_nut_pocket_at_every_key_mount():
    got = _plate_open_at_pockets(load("cckb").spec)
    assert len(got) == 9 and all(got), got


def test_the_pocket_check_notices_round_holes():
    s = load("cckb").spec
    del s.MOUNT_POCKET_AF                      # 核の既定（M2 のバカ穴）に戻す
    assert not any(_plate_open_at_pockets(s))


# ---------------------------------------------------------------------------
# 規則の値は pcb_rules から導く（最終レビュー I1）
# ---------------------------------------------------------------------------
# pcb_rules の値を変えてから機種のモジュールを読み、機種の値が**ついてくる**かを見る。
# 数字で写していれば古い値のまま残る（test_meta の写しの検査はコメントで見分けるので、
# コメントに規則を書かない写しはこちらが捕まえる）
_FOLLOW = r"""
import sys
sys.path[:0] = [{root!r}, {proj!r}]
from foundry import pcb_rules as R
R.TRACK_W, R.VIA_D, R.NPTH_EDGE_MIN = 0.25, 0.7, 1.3
R.JLC["edge_clearance"] = 0.4
import {mods}
got = dict({got})
want = dict({want})
bad = {{k: (got[k], want[k]) for k in want if abs(got[k] - want[k]) > 1e-12}}
print("OK" if not bad else "NG %r" % bad)
"""


def _follow(python, mods, got, want):
    src = _FOLLOW.format(root=str(ROOT), proj=str(ROOT / "projects/cckb"), mods=mods, got=got, want=want)
    r = subprocess.run([python, "-c", src], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() + r.stderr[-1500:]


def test_the_project_rule_values_follow_pcb_rules():
    out = _follow(sys.executable, "matrix_routes as M, interface as I",
                  "HALF_W=M.HALF_W, VIA_R=M.VIA_R, TRACK_CLEAR=M.TRACK_CLEAR, PAD_GAP=M.PAD_GAP, "
                  "HOLE_GAP=M.HOLE_GAP, EDGE_GAP=M.EDGE_GAP, EDGE_MIN=I.EDGE_MIN, "
                  "COPPER_GAP=I.COPPER_GAP, TRACK_HALF=I.TRACK_HALF",
                  "HALF_W=0.125, VIA_R=0.35, TRACK_CLEAR=0.5, PAD_GAP=0.3, HOLE_GAP=0.4, "
                  "EDGE_GAP=0.45, EDGE_MIN=1.3, COPPER_GAP=0.4, TRACK_HALF=0.125")
    assert out == "OK", out


def test_the_pcb_extra_rule_values_follow_pcb_rules():
    require(paths.KICAD_PYTHON, "pcb_extra を KiCad の Python で読む")
    out = _follow(paths.KICAD_PYTHON, "pcb_extra as P", "EDGE_BAND=P.EDGE_BAND", "EDGE_BAND=0.42")
    assert out == "OK", out


def test_the_follow_check_notices_a_copied_value():
    """**検査器が壊れていないか。**写した値（ついてこない値）を NG と言うこと。"""
    out = _follow(sys.executable, "matrix_routes as M", "HALF_W=0.1", "HALF_W=0.125")
    assert out.startswith("NG"), out
