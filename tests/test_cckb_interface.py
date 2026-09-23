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
    （初版は符号が逆で**縮めていた**——取付の探索がスタビの逃げを実際より小さく見た）"""
    from build123d import BuildLine, BuildSketch, Kind, Polyline, make_face, offset

    from foundry.mech import CHOC_STAB_OUTLINE

    for d in (0.15, 0.5):
        with BuildSketch() as sk:
            with BuildLine():
                Polyline(*CHOC_STAB_OUTLINE, close=True)
            make_face()
            offset(amount=d, kind=Kind.INTERSECTION)
        bb = sk.sketch.bounding_box()
        mine = I.poly_box(I.poly_offset_axis(list(CHOC_STAB_OUTLINE), d))
        assert all(abs(a - b) < 1e-6 for a, b in
                   zip(mine, (bb.min.X, bb.min.Y, bb.max.X, bb.max.Y))), (d, mine, bb)
        area = sk.sketch.area
        poly = I.poly_offset_axis(list(CHOC_STAB_OUTLINE), d)
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
    land = ifc.psw_land()
    if not I.inside(copper, land):
        out.append("電源スイッチのランドが銅の範囲の外")
    if s.PSW_H > s.UNDER_PCB - 0.3:
        out.append("電源スイッチが床に近すぎる")
    tip = ifc.psw_knob()[2]
    o = ifc.case_outer[2]
    if not (o - s.PSW_SCOOP + 0.5 <= tip <= o + 0.5):
        out.append(f"つまみの先 {tip - o:+.2f}（外面から −{s.PSW_SCOOP - 0.5:.1f}〜+0.5）")
    for (qx, qy), qr in ifc.psw_pegs():
        for pad in ifc.holder_pads():
            if I.circle_rect_gap((qx, qy), qr, pad) < 0.5:
                out.append("スイッチの位置決めの穴がホルダのパッドに近い")
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
    (dict(PSW_KNOB_L=1.5), "つまみの先"),
    (dict(PSW_AT=(141.275, -42.4)), "位置決めの穴"),
    (dict(LID_PILLAR_AT=(111.0, -38.6)), "指の場所"),
    (dict(CASE_KEY_GAP=0.2), "キャップ"),
    (dict(RIM_ABOVE_PCB=6.5), "ホルダの頭"),
])
def test_the_corner_check_notices_a_break(over, expect):
    bad = corner_problems(ifc_with(**over))
    assert any(expect in b for b in bad), bad


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
    # 最悪の足: 基板が −10%・足が +0.1
    worst_tip = z["pcb_bottom"] + s.PCB_T * (1 - s.PCB_T_TOL) - (s.SWITCH_PIN_L + s.SWITCH_PIN_TOL)
    if worst_tip < s.CASE_FLOOR + 0.1:
        out.append(f"足の先（最悪 {worst_tip:.2f}）が床 {s.CASE_FLOOR} に 0.1 未満")
    for name, h in (("BAT46W", 1.25), ("TSSOP-16", 1.2), ("電源スイッチ", s.PSW_H)):
        if h > s.UNDER_PCB - 0.3:
            out.append(f"{name} が床に 0.3 未満")
    if z["stab_bottom"] < s.CASE_FLOOR + 0.5:
        out.append(f"スタビの下端 {z['stab_bottom']:.2f} が床に 0.5 未満")
    if abs(z["plate_top"] - z["plate_bottom"] - ifc.sw.plate_t) > 1e-9 or \
            z["plate_bottom"] - z["pcb_top"] < 0.9:
        out.append("プレートと基板の隙間")
    if z["rim"] < z["keycap_bottomed"]:
        out.append("縁が押し切ったキャップより低い")
    # 下からのネジ: 先端がナットを抜け、プレートの上面を越えない
    tip = s.SCREW_SINK + s.SCREW_L
    if not (z["pcb_top"] + s.NUT_T <= tip <= z["plate_top"] - 0.1):
        out.append(f"ネジの先 {tip:.2f}（ナット上面 {z['pcb_top'] + s.NUT_T:.2f}〜"
                   f"プレート上面 {z['plate_top']:.2f}）")
    if s.SCREW_SINK < 0.5 or s.SCREW_SINK + s.SCREW_HEAD_H > z["pcb_bottom"] - 1.2:
        out.append("皿の座ぐりの深さ")
    if s.CASE_FLOOR - s.ANTISLIP_RECESS < 1.2 or s.ANTISLIP_SHEET_T <= s.ANTISLIP_RECESS:
        out.append("滑り止め（床の残りか、シートが接地しない）")
    return out


def test_the_z_stack_holds(ifc):
    assert z_problems(ifc) == []


@pytest.mark.parametrize("over, expect", [
    (dict(UNDER_PCB=1.5), "足の先"),
    (dict(PSW_H=1.7), "電源スイッチ"),
    (dict(STAB_HOUSING_H=5.9), "スタビ"),
    (dict(SCREW_L=8), "ネジの先"),
    (dict(SCREW_SINK=0.2), "ネジの先"),
    (dict(ANTISLIP_SHEET_T=0.4), "滑り止め"),
    (dict(RIM_ABOVE_PCB=5.5), "縁"),
])
def test_the_z_check_notices_a_break(over, expect):
    bad = z_problems(ifc_with(**over))
    assert any(expect in b for b in bad), bad


def test_the_pcb_thickness_is_stiff_enough(ifc):
    """O3。キーの中心から最寄りの支え（柱・取付）までの最大距離 d で、両端支持の梁
    （幅 1u・スパン 2d）に中央 10N（手のひら）をかけたたわみ。足の先の最悪の余裕
    （0.14）より小さいこと。FR4 の曲げ弾性率は保守側 18.6GPa。"""
    s = ifc.s
    sup = list(s.SUPPORTS) + ifc.mounts()
    d = max(min(math.hypot(x - a, y - b) for a, b in sup) for x, y in ifc.positions)
    L, b, E, F = 2 * d, 19.05, 18600.0, 10.0
    defl = lambda t: F * L ** 3 / (48 * E * b * t ** 3 / 12)
    z = ifc.z()
    margin = z["pcb_bottom"] + s.PCB_T * (1 - s.PCB_T_TOL) - (s.SWITCH_PIN_L + s.SWITCH_PIN_TOL) \
        - s.CASE_FLOOR
    print(f"d={d:.1f} L={L:.1f} 1.6: {defl(1.6):.3f} 1.2: {defl(1.2):.3f} 余裕 {margin:.2f}")
    assert s.PCB_T == 1.6 and defl(s.PCB_T) < margin


# ---------------------------------------------------------------------------
# スタビの逃げ穴（O2）
# ---------------------------------------------------------------------------

def stab_problems(ifc, geo=None):
    out = []
    reliefs, housings = ifc.stab_reliefs(), ifc.stab_housings()
    if len(reliefs) != 8 or len(housings) != 8:
        out.append(f"スタビが {len(reliefs)} 個（Enter・左 Shift・スペース 2 つで 8）")
    for rel, hou in zip(reliefs, housings):
        gap = min(I.seg_dist(p, rel[i], rel[(i + 1) % len(rel)])
                  for p in hou for i in range(len(rel)))
        if not all(I.point_in_poly(p, rel) for p in hou) or gap < 0.4:
            out.append(f"逃げ穴とハウジングの隙 {gap:.2f}（外形公差 0.2 ＋ 0.2）")
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


def test_the_stab_check_notices_a_thin_margin():
    assert any("隙" in b for b in stab_problems(ifc_with(STAB_RELIEF_MARGIN=0.1)))


# ---------------------------------------------------------------------------
# 印刷する部品は A1 mini（168.4 角）に入る。プレートの継ぎ目は開口を切らない
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plate_pieces():
    from foundry.plate import build_plate, split_plate

    p = load("cckb")
    whole, _, _ = build_plate(p.spec, p.keys(), "main")
    return whole, split_plate(p.spec, whole, "main")


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

@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    require(paths.KICAD_PYTHON, "基板の生成")
    d = tmp_path_factory.mktemp("cckbif") / "cckb"
    shutil.copytree(paths.PROJECTS / "cckb", d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(d)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = d / "geo.json"
    r = subprocess.run([paths.KICAD_PYTHON, str(ROOT / "projects/cckb/tools/board_geometry.py"),
                        str(d / "pcb/unrouted/cckb_main.kicad_pcb"), str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
    return json.loads(out.read_text())


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
    ((-116.18, 18.4), "配線"),                 # 行の配線の上
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


@pytest.mark.xfail(strict=True, reason="O7: スタビのキー 4 つのダイオード（x 7.6）が逃げ穴に"
                   "かかる。基板の段で動かす。直ったら XPASS で落ちるのでこの印を外す")
def test_the_stab_relief_clears_the_diodes(ifc, geo):
    bad = []
    for rel in ifc.stab_reliefs():
        for f in geo["footprints"]:
            if re.fullmatch(r"D\d+", f["ref"]) and "back" in f["courtyard"]:
                b = f["courtyard"]["back"]
                if any(I.point_in_poly(p, rel) for p in
                       ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3]))) or \
                        I.rect_gap(I.poly_box(rel), b) < 0:
                    bad.append(f["ref"])
    assert not bad, bad


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
