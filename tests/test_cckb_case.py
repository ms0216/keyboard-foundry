"""CCKB のケース・キーキャップ・組み立て（projects/cckb/{case,keycaps,coupons,assembly}.py）。

**生成した立体そのもの**と、外の事実（基板はいま KiCad で生成した物・スイッチは Kailh 図面・
印刷機は A1 mini の実効 168.4）に突き合わせる。各検査の下に「故意に壊すと落ちる」検査を置く
（CLAUDE.md 検証の作法 2）。壊す検査は、壊した値で立体を作り直して同じ関数に通す。
"""

import math
import re
import sys
import types

import pytest

from conftest import ROOT, require
from foundry import paths, tags
from foundry.project import load

sys.path.insert(0, str(ROOT / "projects" / "cckb"))
import assembly as A  # noqa: E402
import case as C  # noqa: E402
import case_spec as CS  # noqa: E402
import coupons  # noqa: E402
import interface as I  # noqa: E402
import keycaps as KC  # noqa: E402

LIMIT = load("cckb").spec.PRINT_MAX


def ifc_with(**over):
    p = load("cckb")
    for k, v in over.items():
        setattr(p.spec, k, v)
    return I.Interface(p)


def cs_with(**over):
    ns = {k: getattr(CS, k) for k in dir(CS) if k.isupper()}
    ns.update(over)
    return types.SimpleNamespace(**ns)


@pytest.fixture(scope="module")
def geo():
    require(paths.KICAD_PYTHON, "基板の生成")
    return A.board_geometry()


@pytest.fixture(scope="module")
def asm(geo):
    return A.Assembly(geo)


@pytest.fixture(scope="module")
def g(asm):
    return asm.groups()


def slim(asm, names, pressed=False):
    """組み立ての一部だけ（壊す検査を速くする）。"""
    out = {}
    printed = None
    for n in names:
        if n in ("tray_L", "tray_R", "lid_L", "lid_R"):
            printed = printed or asm.printed()
            out[n] = printed[n]
        elif n in ("plate_L", "plate_R"):
            out[n] = asm.plates()[n]
        elif n == "keycaps":
            out[n] = A.Compound(asm.keycap_solids(pressed))
        elif n == "switches":
            out[n] = A.Compound(asm.switch_solids(pressed))
        else:
            v = getattr(asm, {"stabs": "stab_solids", "nuts": "nuts", "screws": "screws",
                              "inserts": "inserts", "pads": "pads"}.get(n, n))()
            out[n] = A.Compound(v) if isinstance(v, list) else v
    return out


# ---------------------------------------------------------------------------
# 値の約束
# ---------------------------------------------------------------------------

def test_case_provisional_values_are_listed_with_the_same_numbers():
    bad = tags.provisional_mismatches(ROOT / "projects/cckb/case_spec.py",
                                      ROOT / "projects/cckb/docs/provisional-values-case.md")
    assert not bad, "\n".join(bad)


def test_every_case_constant_is_read():
    """読まれていない定数は効いていると思い込ませる（test_meta と同じ約束をケースの値にも）。"""
    path = ROOT / "projects/cckb/case_spec.py"
    readers = [p for p in (ROOT / "projects/cckb").glob("*.py") if p != path] + [ROOT / "tests/test_cckb_case.py"]
    reads = set().union(*(tags.names_read(p) for p in readers))
    silent = [n for n in tags.module_constants(path) if n not in reads]
    assert not silent, silent


# ---------------------------------------------------------------------------
# 印刷: A1 mini に入るか・1 つの水密な立体か
# ---------------------------------------------------------------------------

def all_printed(asm):
    parts = dict(asm.printed())
    parts.update(asm.plates())
    parts.update(KC.print_parts(asm.i))
    parts.update(coupons.parts(asm.i))
    return parts


@pytest.fixture(scope="module")
def printed_all(asm):
    return all_printed(asm)


def test_every_printed_part_fits_the_a1_mini(asm, printed_all):
    sizes = A.print_sizes(printed_all, LIMIT)
    assert len(sizes) == 17, sorted(sizes)          # トレイ 2・ふた 2・プレート 2・キャップ 4＋並べた 2・小片 5
    bad = {n: v for n, v in sizes.items() if not v[2]}
    assert not bad, bad


def test_the_size_check_notices_a_long_tray(geo):
    a = A.Assembly(geo, ifc_with(CASE_SEAM=(40.0, 40.0)))
    sizes = A.print_sizes(a.case.tray_halves(), LIMIT)
    assert not sizes["tray_L"][2], sizes


def test_case_parts_and_keycaps_are_single_watertight_solids(printed_all):
    for name, part in printed_all.items():
        if name.startswith(("tray_", "lid_", "keycap_", "plate_")):   # keycaps_set_* は並べた Compound
            assert len(part.solids()) == 1, name
        assert A.mesh_of(part).is_watertight, name


# ---------------------------------------------------------------------------
# 干渉（B-rep の総当たり）
# ---------------------------------------------------------------------------

def test_every_part_declares_how_it_is_held(g):
    assert set(g) == set(A.HELD_BY), (set(g) ^ set(A.HELD_BY))


def test_the_switches_on_the_board_sit_under_the_layout_keys(asm, geo):
    """キャップ（配列から置く）とスイッチ（基板から置く）が同じ位置か。"""
    sw = sorted((f["x"], f["y"]) for f in geo["footprints"] if re.fullmatch(r"SW\d+", f["ref"]))
    lay = sorted(asm.i.positions)
    assert len(sw) == len(lay) == 62
    assert all(math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-3 for a, b in zip(sw, lay))


def test_nothing_interferes(g):
    sl = []
    bad = A.interference(g, skip=set(A.EXPECTED) | {("pads", "desk")}, slivers=sl)
    assert bad == {}, bad
    # 丸めの削りかす（厚さ < 0.001）は 0 に数える。**数を隠さない**: 増えたら中身を見る
    assert len(sl) <= 10 and sum(sl) < 0.02, sl


def test_the_interference_check_notices_a_bigger_cell(asm, geo):
    """電池を 1mm 大きくする（設計書 §11 の壊し方）。"""
    a = A.Assembly(geo, cs=cs_with(CELL_REAL_D=CS.CELL_REAL_D + 1.0))
    bad = A.interference(slim(a, ["cell", "holder", "lid_R", "tray_R"]))
    assert ("cell", "holder") in bad, bad


def test_the_interference_check_notices_a_low_lid(asm, geo):
    a = A.Assembly(geo, ifc_with(RIM_ABOVE_PCB=6.4))       # ふたの下面 10.2 < ホルダ 10.5
    bad = A.interference(slim(a, ["holder", "lid_R"]))
    assert ("holder", "lid_R") in bad, bad


def test_designed_overlaps_are_only_what_the_reason_says(asm, g):
    assert A.expected_overlaps_ok(asm, g) == []


def test_the_designed_overlap_check_notices_a_lost_captive_web(geo):
    a = A.Assembly(geo, cs=cs_with(CAPTIVE_HOLE_D=2.4))
    bad = A.expected_overlaps_ok(a, a.groups())
    assert any("screw_lid" in b for b in bad), bad


# ---------------------------------------------------------------------------
# 押し切ったキャップ
# ---------------------------------------------------------------------------

def test_pressed_keycaps_hit_nothing(asm):
    gp = asm.groups(pressed=True)
    bad = A.interference({"keycaps": gp["keycaps"]}, {k: v for k, v in gp.items() if k != "keycaps"})
    assert bad == {}, bad


def test_the_pressed_check_notices_caps_over_the_wall(geo):
    a = A.Assembly(geo, ifc_with(KEYCAP_GAP=-0.8))            # キャップが壁の内面より 0.3 外へ
    gp = slim(a, ["keycaps", "tray_L", "tray_R"], pressed=True)
    bad = A.interference({"keycaps": gp["keycaps"]}, {k: gp[k] for k in ("tray_L", "tray_R")})
    assert bad, "壁がキャップの下に入っても落ちない"


def test_the_pressed_check_notices_a_long_skirt(geo):
    a = A.Assembly(geo, cs=cs_with(KEYCAP_SKIRT_H=3.5))      # 押し切った下端 6.5 < プレートの上面 7.2
    gp = slim(a, ["keycaps", "switches", "plate_L", "plate_R"], pressed=True)
    bad = A.interference({"keycaps": gp["keycaps"]}, {k: v for k, v in gp.items() if k != "keycaps"})
    assert ("keycaps", "plate_L") in bad, bad


# ---------------------------------------------------------------------------
# 入れられるか・外せるか・留まるか
# ---------------------------------------------------------------------------

def test_every_part_can_be_put_in_and_taken_out(asm, g):
    assert A.path_problems(asm, g) == {}


@pytest.mark.parametrize("over,cs_over,path", [
    ({"XIAO_AT": (-131.17, -38.1)}, {}, "usb_plug"),            # メスが 1.5 奥 → 樹脂が壁に入り込む
    ({"HOLDER_AT": (128.5, -36.0)}, {}, "cell"),               # 電池がプレートの下
    ({}, {"PSW_SLOT_CLEAR": -1.0}, "board"),                    # つまみの切り欠きが狭い
    ({}, {"DRIVER_D": 5.0}, "screws"),                          # ドライバーが座ぐりに入らない
])
def test_the_path_check_notices_a_blocked_path(geo, over, cs_over, path):
    a = A.Assembly(geo, ifc_with(**over) if over else None, cs_with(**cs_over) if cs_over else CS)
    bad = A.path_problems(a, a.groups())
    assert path in bad, bad


def test_the_parts_are_held(asm, g):
    assert A.retention_problems(asm, g) == []


@pytest.mark.parametrize("over", [{"RIM_ABOVE_PCB": 9.0}, {"SCREW_L": 4}])
def test_the_retention_check_notices_a_loose_part(geo, over):
    a = A.Assembly(geo, ifc_with(**over))
    assert A.retention_problems(a, slim(a, ["cell", "lid_R", "screw_lid"]))


def test_the_power_switch_takes_a_fingernail(asm, g):
    assert A.nail_problems(asm, g) == []


def test_the_nail_check_notices_no_scoop(geo):
    a = A.Assembly(geo, ifc_with(PSW_SCOOP=0.0))
    assert A.nail_problems(a, slim(a, ["tray_R", "lid_R"]))


# ---------------------------------------------------------------------------
# 肉厚・継ぎ目・面の取り合い
# ---------------------------------------------------------------------------

def _thin(asm, parts):
    meshes = {k: A.mesh_of(v) for k, v in parts.items()}
    bad = [p for p in A.measure_probes(asm, meshes) if p[2] < p[3] - 0.01]
    bad += [p for p in A.keycap_probes(asm) if p[2] < p[3] - 0.01]
    for k, m in meshes.items():
        th = A.z_scan(m, 1.2, skip=A.z_scan_skips(asm, k))
        if th:
            bad.append((k, "縦", len(th), th[:3]))
    return bad


def test_every_wall_is_thick_enough(asm):
    parts = dict(asm.printed())
    parts.update(asm.plates())
    assert _thin(asm, parts) == []


def test_the_wall_probes_were_measured(asm):
    """測り所が材料に当たっているか（0 のまま通っていないか）と、数。"""
    meshes = {k: A.mesh_of(v) for k, v in asm.printed().items()}
    res = A.measure_probes(asm, meshes)
    assert len(res) == 23 and all(t > 0.3 for _, _, t, _, _ in res), res


@pytest.mark.parametrize("over", [{"CASE_WALL": 0.8}, {"LID_T": 0.8}])
def test_the_wall_check_notices_a_thin_wall(geo, over):
    a = A.Assembly(geo, ifc_with(**over))
    assert _thin(a, a.printed())


def test_the_seam_does_not_cut_a_post(asm, g):
    assert A.seam_problems(asm, {k: g[k] for k in ("tray_L", "tray_R")}) == []


def test_the_seam_check_notices_a_seam_through_a_post(geo):
    a = A.Assembly(geo, ifc_with(CASE_SEAM=(-19.18, 4.7625)))
    assert A.seam_problems(a, a.case.tray_halves())


def test_the_antislip_pads_keep_clear_of_the_screw_seats(asm):
    assert A.pad_problems(asm) == []


def test_the_pad_check_notices_a_pad_over_a_screw(geo):
    a = A.Assembly(geo, cs=cs_with(ANTISLIP_PAD=(40.0, 30.0)))
    assert A.pad_problems(a)


def test_the_stab_housing_stays_off_the_floor(asm):
    """O2: スタビのハウジングの下端は床の上に空きがある → 床に穴は要らない（厚くもしない）。"""
    z = asm.z
    assert z["stab_bottom"] - z["floor_top"] >= 0.5


def test_the_stab_check_notices_a_long_housing(geo):
    a = A.Assembly(geo, ifc_with(STAB_HOUSING_H=6.0))
    bad = A.interference(slim(a, ["stabs", "tray_L", "tray_R"]))
    assert bad and a.z["stab_bottom"] - a.z["floor_top"] < 0.5


# ---------------------------------------------------------------------------
# キーキャップ
# ---------------------------------------------------------------------------

def test_the_keycap_posts_follow_the_kailh_drawing(asm):
    """脚は図面の穴（1.20 × 3.00・中心間 5.70・X 方向に並ぶ）から STEM_POST_FIT 細い。2.25u はスタビにも。"""
    cap = KC.keycap(2.25, asm.s, asm.i.sw, asm.c)
    posts = [s for s in cap.solids()]
    assert len(posts) == 1
    bb = cap.bounding_box()
    assert abs(bb.max.Z - asm.s.KEYCAP_TOP_T) < 1e-6
    assert abs(bb.min.Z + CS.STEM_POST_L) < 1e-6
    # 脚の断面（z = −1 で切る）: 6 本、各 (1.2 − fit) × (3.0 − fit)、中心 x = ±12.0 ± 2.85 と ±2.85
    from build123d import Face, Plane
    sec = cap & (Plane.XY.offset(-CS.KEYCAP_SKIRT_H - 0.5) * Face.make_rect(100, 100))
    faces = sec.faces()
    xs = sorted(round(f.center().X, 3) for f in faces)
    assert xs == sorted(round(s + d, 3) for s in (-12.0, 0.0, 12.0) for d in (-2.85, 2.85)), xs
    for f in faces:
        b = f.bounding_box()
        assert abs(b.size.X - (1.2 - CS.STEM_POST_FIT)) < 1e-6 and abs(b.size.Y - (3.0 - CS.STEM_POST_FIT)) < 1e-6


def test_the_keycap_top_is_the_interface_height(asm, g):
    top = g["keycaps"].bounding_box().max.Z
    assert abs(top - asm.z["keycap_top"]) < 1e-6


def test_the_keycap_counts_match_the_layout(asm):
    assert KC.print_counts(asm.i.keys) == {1.0: 51, 1.5: 5, 1.75: 2, 2.25: 4}
