"""CCKB のケース・キーキャップ・組み立て（projects/cckb/{case,keycaps,coupons,assembly}.py）。

**生成した立体そのもの**と、外の事実（基板は発注する配線済みの板を KiCad で読んだ物・スイッチは Kailh 図面・
印刷機は A1 mini の実効 168.4）に突き合わせる。各検査の下に「故意に壊すと落ちる」検査を置く
（CLAUDE.md 検証の作法 2）。壊す検査は、壊した値で立体を作り直して同じ関数に通す。
"""

import copy
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


def geo_with(geo, ref, dx=0.0, dy=0.0, **fields):
    """板の写しで、フットプリント ref（とそのパッド）を (dx, dy) 動かし、fields を書き換えた物。
    **板の上の実物が動いた**ことにする（ケースは境界の決定のまま）。"""
    g = copy.deepcopy(geo)
    for f in g["footprints"]:
        if f["ref"] == ref:
            f["x"] += dx
            f["y"] += dy
            f.update(fields)
    for p in g["pads"]:
        if p["ref"] == ref:
            p["x"] += dx
            p["y"] += dy
            b = p["box"]
            p["box"] = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]
    return g


@pytest.fixture(scope="module")
def geo():
    # 発注する板の形のコミットした写し（板の sha256 で突き合わせる）。KiCad が要らないので CI でも
    # 走る。写しが KiCad の読みと同じかは test_cckb_interface が見る（最終レビュー I5）
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
    """読まれていない定数は効いていると思い込ませる（test_meta と同じ約束をケースの値にも）。
    **検査だけが読む定数は数えない**（検査が読んでも形は変わらない。最終レビュー M9）。"""
    path = ROOT / "projects/cckb/case_spec.py"
    readers = [p for p in (ROOT / "projects/cckb").rglob("*.py") if p != path and "__pycache__" not in p.parts]
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


@pytest.mark.slow
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


def test_the_assembly_models_the_routed_board(asm, geo):
    """組み立ての基板は**発注する配線済みの板**（pcb/cckb_main.kicad_pcb）で、裏の部品を物の数で数える。

    - 外形と逃げ穴は板の Edge.Cuts（穴 = スタビ 8）
    - 板で裏返した部品 69 = JLC の CPL 69 行（fab-checklist）。どれも箱で置く。**穴（H_LID）を部品に数えない**
      （統合で起きた赤）。電源スイッチは 2026-09-24 から表（スルーホール）で、図面の形で別に置く
    - XIAO・ホルダ・電源スイッチは板のフットプリントの位置に置く
    """
    assert A.ROUTED_BOARD.name == "cckb_main.kicad_pcb" and A.ROUTED_BOARD.parent.name == "pcb"
    assert len(geo["outline"]["holes"]) == 8
    flipped = [f["ref"] for f in geo["footprints"] if f["back"]]
    assert len(flipped) == 69 and "SW_PWR" not in flipped
    refs = asm.bottom_refs()
    assert len(refs) == 69 and "H_LID" not in refs
    assert sorted(refs) == sorted(flipped)
    copper = {p["ref"] for p in geo["pads"] if not p["npth"]}
    assert all(r in copper for r in refs)                      # 穴だけのフットプリントは部品ではない
    fps = {f["ref"]: f for f in geo["footprints"]}
    assert asm.r.s.PSW_AT == (fps["SW_PWR"]["x"], fps["SW_PWR"]["y"])
    assert asm.r.s.HOLDER_AT == (fps["BT1"]["x"], fps["BT1"]["y"])
    assert abs(asm.r.s.XIAO_AT[0] + asm.s.XIAO_PIN_SHIFT - fps["U_MCU"]["x"]) < 1e-9


def test_the_placement_check_notices_a_rotated_part(geo):
    """形の向きは決め打ちなので、板で回っていたら組み立てを作らせない。"""
    with pytest.raises(AssertionError):
        A.Assembly(geo_with(geo, "U_MCU", deg=0.0))


def test_the_interference_check_notices_a_power_switch_moved_on_the_board(geo):
    """板の電源スイッチを 0.6 外へ（本体の最大の右の縁 143.175 → 143.775 が壁の内面 143.675 を越える。
    レバーもふたの穴の縁 142.425 を越える）。"""
    a = A.Assembly(geo_with(geo, "SW_PWR", dx=0.6))
    bad = A.interference(slim(a, ["psw", "tray_R", "lid_R"]))
    assert ("psw", "tray_R") in bad and ("psw", "lid_R") in bad, bad


def test_the_power_switch_pins_must_be_trimmed(asm, g):
    """電源スイッチの足を切らないと（図の最長 4.1・爪 0.4）床に当たる。切った足（PSW_PIN_TRIM）は当たらない。"""
    assert A.interference({"psw": g["psw"]}, {"tray_R": g["tray_R"]}) == {}
    bad = A.interference({"psw": asm.psw(trimmed=False)}, {"tray_R": g["tray_R"]})
    assert ("psw", "tray_R") in bad, bad


@pytest.mark.slow
def test_nothing_interferes(g):
    sl, failed = [], []
    bad = A.interference(g, skip=set(A.EXPECTED) | {("pads", "desk")}, slivers=sl, failures=failed)
    assert bad == {}, bad
    assert failed == [], failed          # 形状演算の失敗を「干渉 0」と数えない（最終レビュー I2）
    # 丸めの削りかす（厚さ < 0.001）は 0 に数える。**数を隠さない**: 増えたら中身を見る
    assert len(sl) <= 10 and sum(sl) < 0.02, sl


class _BrokenVolume:
    """OCC が壊れた立体を返したときの形（体積を聞くと例外）。"""

    @property
    def volume(self):
        raise ValueError("壊れた立体")


class _BreaksOnCommon:
    """共通部分が壊れた立体になる物（外接箱は本物の箱）。"""

    def __init__(self, solid):
        self.s = solid

    def __and__(self, other):
        return _BrokenVolume()

    def bounding_box(self):
        return self.s.bounding_box()


def test_the_interference_check_counts_a_failed_boolean_as_a_failure(monkeypatch):
    """**壊して落ちることを示す。**共通部分の体積が取れない組を 0 と数えず、failures に積む。
    failures を渡さなければ例外で止まる（ほかの呼び手も黙って 0 にしない）。KiCad は要らない。"""
    a, b = C.box(0, 0, 0, 2, 2, 2), C.box(1, 1, 1, 3, 3, 3)
    monkeypatch.setattr(A, "solids_of", lambda part: [_BreaksOnCommon(part)] if part is a else [part])
    failed = []
    assert A.interference({"a": a, "b": b}, failures=failed) == {}
    assert [pair for pair, _ in failed] == [("a", "b")], failed
    with pytest.raises(A.GeometryFailure):
        A.interference({"a": a, "b": b})
    with pytest.raises(A.GeometryFailure):
        A.common_volume(_BreaksOnCommon(a), b)


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


@pytest.mark.slow
def test_the_designed_overlap_check_notices_a_lost_captive_web(geo):
    a = A.Assembly(geo, cs=cs_with(CAPTIVE_HOLE_D=2.4))
    bad = A.expected_overlaps_ok(a, a.groups())
    assert any("screw_lid" in b for b in bad), bad


# ---------------------------------------------------------------------------
# 押し切ったキャップ
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_pressed_keycaps_hit_nothing(asm):
    gp = asm.groups(pressed=True)
    bad = A.interference({"keycaps": gp["keycaps"]}, {k: v for k, v in gp.items() if k != "keycaps"})
    assert bad == {}, bad


def test_the_pressed_check_notices_caps_over_the_wall(geo):
    a = A.Assembly(geo, ifc_with(KEYCAP_GAP=-0.8))            # キャップが壁の内面より 0.3 外へ
    gp = slim(a, ["keycaps", "tray_L", "tray_R"], pressed=True)
    bad = A.interference({"keycaps": gp["keycaps"]}, {k: gp[k] for k in ("tray_L", "tray_R")})
    assert bad, "壁がキャップの下に入っても落ちない"


@pytest.mark.slow
def test_the_pressed_check_notices_a_long_skirt(geo):
    a = A.Assembly(geo, cs=cs_with(KEYCAP_SKIRT_H=3.5))      # 押し切った下端 6.5 < プレートの上面 7.2
    gp = slim(a, ["keycaps", "switches", "plate_L", "plate_R"], pressed=True)
    bad = A.interference({"keycaps": gp["keycaps"]}, {k: v for k, v in gp.items() if k != "keycaps"})
    assert ("keycaps", "plate_L") in bad, bad


# ---------------------------------------------------------------------------
# 入れられるか・外せるか・留まるか
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_every_part_can_be_put_in_and_taken_out(asm, g):
    assert A.path_problems(asm, g) == {}


@pytest.mark.slow
@pytest.mark.parametrize("move,cs_over,path", [
    (("U_MCU", 1.5, 0.0), {}, "usb_plug"),                      # 板の XIAO が 1.5 奥 → プラグの樹脂が壁に入り込む
    (("BT1", 0.0, 2.6), {}, "cell"),                            # 板のホルダが奥 → 電池がプレートの下
    (None, {"PSW_SLOT_CLEAR": -0.3}, "lid_R"),                  # レバーの穴が狭い（ふたが外れない）
    (None, {"DRIVER_D": 5.0}, "screws"),                        # ドライバーが座ぐりに入らない
])
def test_the_path_check_notices_a_blocked_path(geo, move, cs_over, path):
    a = A.Assembly(geo_with(geo, *move) if move else geo, None, cs_with(**cs_over) if cs_over else CS)
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
    # 公差を積んだレバーの先とふたの上面の差（正なら下）。**最高では出る**（open-gaps O13 で利用者が決める）
    worst, nominal, lowest = A.psw_tip_margin(asm)
    print(f"レバーの先はふたの上面から: 名目 {nominal:+.2f}・公差の最高 {worst:+.2f}・最低 {lowest:+.2f}")
    assert nominal > 0


@pytest.mark.parametrize("cs_over, ifc_over", [
    ({"PSW_SLOT_NAIL": 0.3}, {}),                 # 穴の端に爪の場所が無い
    ({}, {"PSW_TAB": 0.7}),                       # 爪で浮く量が大きい → 先がふたの上面を越える
])
def test_the_nail_check_notices_a_blocked_or_protruding_lever(geo, cs_over, ifc_over):
    a = A.Assembly(geo, ifc_with(**ifc_over) if ifc_over else None, cs_with(**cs_over) if cs_over else CS)
    assert A.nail_problems(a, slim(a, ["tray_R", "lid_R", "psw"]))


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


@pytest.mark.slow
def test_every_wall_is_thick_enough(asm):
    parts = dict(asm.printed())
    parts.update(asm.plates())
    assert _thin(asm, parts) == []


def test_the_wall_probes_were_measured(asm):
    """測り所が材料に当たっているか（0 のまま通っていないか）と、数。"""
    meshes = {k: A.mesh_of(v) for k, v in asm.printed().items()}
    res = A.measure_probes(asm, meshes)
    assert len(res) == 22 and all(t > 0.3 for _, _, t, _, _ in res), res


@pytest.mark.slow
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


# ---------------------------------------------------------------------------
# 床 1.2 と滑り止めの島（2026-09-24 利用者の決定・O10。決定記録 2026-09-24-interface.md §2-5）
# ---------------------------------------------------------------------------

OLD_CORNER_PADS = ((-133.975, 41.725), (-133.975, -41.725), (133.975, 41.725), (133.975, -41.725))


def floor_runs(asm, tray_l):
    """左のトレイの床を下から刺して測る {所: 材料の厚さ}（最初の材料）。"""
    m = A.mesh_of(tray_l)
    isl = I.grow(asm.case.antislip_pads()[0], asm.c.ANTISLIP_ISLAND)     # 島を消した形でも同じ所を刺す
    pad = asm.case.antislip_pads()[0]
    pts = {"床": (-60.3, 30.3), "くぼみ": ((pad[0] + pad[2]) / 2, (pad[1] + pad[3]) / 2),
           "島の縁": ((pad[0] + isl[0]) / 2, (pad[1] + pad[3]) / 2)}
    out = {}
    for k, (x, y) in pts.items():
        r = A.material_runs(m, (x, y, -5), (0, 0, 1))
        out[k] = round(r[0][1] - r[0][0], 4) if r else 0.0
    return out


def test_the_floor_is_1_2_with_1_6_islands_at_the_pads(asm):
    """床 1.2・島の縁 1.6（島の上面）・くぼみの下 1.2。**生成した立体を刺して**測る。"""
    z = asm.z
    got = floor_runs(asm, asm.printed()["tray_L"])
    assert abs(z["floor_top"] - 1.2) < 1e-9 and abs(z["island_top"] - 1.6) < 1e-9
    assert got == {"床": 1.2, "くぼみ": 1.2, "島の縁": 1.6}, got
    assert len(asm.case.antislip_islands()) == 4


def test_the_floor_check_notices_missing_islands(geo):
    """島を消すと、くぼみの下が 1.2 − 0.4 = 0.8 になって落ちる。"""
    a = A.Assembly(geo)
    a.case.antislip_islands = lambda: []
    got = floor_runs(a, a.printed()["tray_L"])
    assert abs(got["くぼみ"] - 0.8) < 1e-3 and got["島の縁"] < 1.6 - 1e-3, got


def test_the_antislip_islands_keep_clear_of_the_back_of_the_board(asm):
    """島（上面 1.6）の上に、基板の裏に出る物（足の先の最悪 1.34・裏の部品・電源スイッチの切った足）が来ない。平面で 0.5 以上。"""
    assert A.island_problems(asm) == []


def test_the_island_check_notices_the_old_corner_pads(geo):
    """前の四隅（外面から 3.0・16 × 10）に戻すと、Esc / BS の足と電源スイッチの足の下に島が入る。"""
    a = A.Assembly(geo, cs=cs_with(ANTISLIP_AT=OLD_CORNER_PADS, ANTISLIP_PAD=(16.0, 10.0)))
    names = {n for _, n, _ in A.island_problems(a)}
    assert {"SW1 のパッド", "SW15 のパッド", "SW_PWR のパッド"} <= names, names


@pytest.mark.slow
def test_the_interference_check_notices_an_island_under_the_pins(geo):
    """同じ壊し方で、組み立ての干渉（隙 0）も島とスイッチの足を捕まえる。電源スイッチの足は切って
    島の上面から 0.4 上に止まるので干渉にはならない（平面の余裕は上の island_problems が見る）。"""
    a = A.Assembly(geo, cs=cs_with(ANTISLIP_AT=OLD_CORNER_PADS, ANTISLIP_PAD=(16.0, 10.0)))
    bad = A.interference(slim(a, ["tray_L", "tray_R", "switches", "psw"]))
    assert ("tray_L", "switches") in bad and ("tray_R", "switches") in bad and ("tray_R", "psw") not in bad, bad


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


# ---------------------------------------------------------------------------
# 基板の面に当たる金属: interface.metal_on_pcb（禁止域の元）と組み立てモデルの金属の立体が同じか
# （2 回目の監査 S1。禁止域は interface の判定で置くので、判定がモデルとずれたら禁止域もずれる）
# ---------------------------------------------------------------------------

def metal_contacts_in_model(g, z):
    """組み立てモデルの金属（ナット・ネジ・インサート）のうち、下端が基板の上面・上端が基板の下面に
    ある立体。{(層, x, y): 外接の半径}。"""
    out = {}
    for name in ("nuts", "screws", "screw_lid", "inserts"):
        for s in A.solids_of(g[name]):
            b = s.bounding_box()
            c = (round((b.min.X + b.max.X) / 2, 2), round((b.min.Y + b.max.Y) / 2, 2))
            r = max(math.hypot(v.X - c[0], v.Y - c[1]) for v in s.vertices())   # 形の外接円
            if abs(b.min.Z - z["pcb_top"]) < 0.01:
                out[("F.Cu",) + c] = r
            if abs(b.max.Z - z["pcb_bottom"]) < 0.01:
                out[("B.Cu",) + c] = r
    return out


def test_the_metal_on_the_board_is_what_the_assembly_model_holds(g):
    ifc = I.Interface()
    model = metal_contacts_in_model(g, ifc.z())
    judged = {(m["side"], round(m["pos"][0], 2), round(m["pos"][1], 2)): m["r"]
              for m in ifc.metal_on_pcb() if m["side"]}
    assert set(model) == set(judged), (sorted(model), sorted(judged))
    # モデルの立体（ナットは向きを 1 つに決めた六角柱）が、判定の円（回りうる範囲）の中に入る
    for k, r in model.items():
        assert r <= judged[k] + 1e-6, (k, r, judged[k])
    assert len(judged) == 10


def test_the_metal_model_check_notices_a_nut_under_the_board(g):
    """ナットを 1 個、基板の下面に当てた形にずらすと、判定と合わなくなる。"""
    ifc = I.Interface()
    z = ifc.z()
    g2 = dict(g)
    nuts = A.solids_of(g["nuts"])
    dz = z["pcb_bottom"] - z["pcb_top"] - load("cckb").spec.NUT_T
    moved = nuts[0].moved(A.Pos(0, 0, dz))
    g2["nuts"] = A.Compound([moved] + nuts[1:])
    model = metal_contacts_in_model(g2, z)
    judged = {(m["side"], round(m["pos"][0], 2), round(m["pos"][1], 2))
              for m in ifc.metal_on_pcb() if m["side"]}
    assert set(model) != judged
