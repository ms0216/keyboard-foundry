"""CCKB の**配線して塗った板**（projects/cckb/pcb/cckb_main.kicad_pcb・発注に使う板）の検査。

相手にするのは KiCad が読んだ板そのもの（projects/cckb/tools/board_facts.py が pcbnew で書き出す）と、
外の事実（回路の宣言 circuit.py・ファームの overlay・ZMK の gpio_595 のビット順・データシートの
パッド・公式 STEP・kicad-cli の DRC）。**生成器の意図とは比べない。**

各検査の下に「故意に壊すと落ちる」検査を置く（CLAUDE.md 検証の作法 2）。壊すのは事実の JSON の
写し（板は触らない）か、板の写し（DRC）。
"""

import copy
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
import circuit  # noqa: E402
import interface as I  # noqa: E402

BOARD = paths.PROJECTS / "cckb" / "pcb" / "cckb_main.kicad_pcb"
OVERLAY = paths.ROOT / "config" / "boards" / "shields" / "cckb" / "cckb.overlay"
SPEC = load("cckb").spec


@pytest.fixture(scope="module")
def ifc():
    return I.Interface()


def _control_rect(ifc):
    """禁止域と同じ大きさで、ベタのあるはずの所（キー領域の中・Alt の手前）へ 20mm ずらした矩形。
    **検査器が銅を数えられることを確かめる対照**（0 しか返さない検査器は禁止域の 0 を証明しない）。"""
    x0, y0, x1, y1 = ifc.antenna_keepout()
    return (x0 + 20.0, y0, x1 + 20.0, y1)


@pytest.fixture(scope="module")
def facts(tmp_path_factory, ifc):
    require(paths.KICAD_PYTHON, "板の事実の書き出し")
    out = tmp_path_factory.mktemp("cckbpcb") / "facts.json"
    rects = [ifc.antenna_keepout(), _control_rect(ifc)]
    r = subprocess.run([paths.KICAD_PYTHON, str(ROOT / "projects/cckb/tools/board_facts.py"),
                        str(BOARD), str(out)] + [",".join(str(v) for v in b) for b in rects],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
    return json.loads(out.read_text())


# ---------------------------------------------------------------------------
# (a) 結線: 宣言 → パッド → 塗った板のネット。**物の数で**数える
# ---------------------------------------------------------------------------

def netlist_problems(facts):
    want = circuit.expected_pad_nets()
    mech = circuit.mechanical_refs()
    out = []
    refs = [f["ref"] for f in facts["footprints"]]
    if len(refs) != len(set(refs)):
        out.append("同じ参照名が 2 つ")
    for r in sorted(set(refs) - set(want) - mech):
        out.append(f"{r}: 回路にも機械部品の一覧にも無い")
    for r in sorted((set(want) | mech) - set(refs)):
        out.append(f"{r}: 板に無い")
    seen = {}
    for p in facts["pads"]:
        if p["npth"] or not p["num"]:
            if p["net"]:
                out.append(f"{p['ref']} の穴にネット {p['net']}")
            continue
        if p["ref"] in mech:
            out.append(f"{p['ref']}（穴）に銅のパッド {p['num']}")
            continue
        decl = want.get(p["ref"], {})
        if p["num"] not in decl:
            out.append(f"{p['ref']}.{p['num']}: 宣言に無いパッド")
            continue
        if p["net"] != decl[p["num"]]:
            out.append(f"{p['ref']}.{p['num']}: 板 {p['net'] or '（無し）'} / 宣言 {decl[p['num']] or 'NC'}")
        seen.setdefault(p["ref"], set()).add(p["num"])
    for r, d in want.items():
        missing = set(d) - seen.get(r, set())
        if r in refs and missing:
            out.append(f"{r}: 宣言したパッド {sorted(missing)} が板に無い")
    return out


def test_every_pad_carries_the_declared_net(facts):
    assert netlist_problems(facts) == []
    # 母数（物の数）: キー 62 × (スイッチ + ダイオード) ＋ 電子部品 10 ＋ 穴 11
    assert len(facts["footprints"]) == 62 * 2 + len(circuit.electronics()) + 11
    assert len(circuit.electronics()) == 10
    copper = [p for p in facts["pads"] if not p["npth"] and p["num"]]
    # スイッチ 2・ダイオード 2・XIAO 14+7（D0〜D6 のパッド内ビア）・595 16×2・C 2×2・R 2×2・
    # D_PWR 2・ホルダ 2・電源スイッチ 7
    assert len(copper) == 62 * 4 + 21 + 32 + 4 + 4 + 2 + 2 + 7
    nc = sorted(f"{p['ref']}.{p['num']}" for p in copper if not p["net"])
    # ネットの無いパッドは**宣言した NC だけ**（XIAO 5V・D1×2・D9、595 U2 の QH と QH'、
    # 電源スイッチの ① と耳 4 つ）
    assert nc == sorted(["U_MCU.5V", "U_MCU.D1", "U_MCU.D1", "U_MCU.D9", "U2.7", "U2.9",
                         "SW_PWR.1", "SW_PWR.4", "SW_PWR.5", "SW_PWR.6", "SW_PWR.7"]), nc


@pytest.mark.parametrize("ref, num, net", [
    ("U1", "14", "SPI_SCK"),          # DS に SCK
    ("D_PWR", "1", ""),               # カソードが外れた
    ("SW30", "1", "COL1"),            # Ctrl の列を 1 つずらした
])
def test_the_netlist_check_notices_a_wrong_pad(facts, ref, num, net):
    f = copy.deepcopy(facts)
    hit = [p for p in f["pads"] if p["ref"] == ref and p["num"] == num]
    assert hit
    for p in hit:
        p["net"] = net
    assert netlist_problems(f)


def test_the_netlist_check_notices_an_undeclared_part(facts):
    f = copy.deepcopy(facts)
    f["footprints"].append(dict(f["footprints"][0], ref="D_PWR2"))
    assert any("D_PWR2" in b for b in netlist_problems(f))


# ---------------------------------------------------------------------------
# (b) DRC: 違反 0・未配線 0。**警告は種類ごとに数えて記録する**（隠さない）
# ---------------------------------------------------------------------------

# 知っている警告と、なぜ直さないか（数は記録 projects/cckb/pcb/cckb_main.drc.json）
KNOWN_WARNINGS = {
    "npth_inside_courtyard",    # 電源スイッチの位置決めの穴がホルダの下（spec.DRC_SEVERITY の理由）
    "silk_edge_clearance",      # シルクが外形・逃げ穴に近い（刷れずに欠けるだけ）
    "silk_overlap",             # シルクどうしの重なり（読みにくいだけ）
    "silk_over_copper",
}


@pytest.fixture(scope="module")
def drc_record():
    from foundry import drc

    require(paths.KICAD_CLI, "DRC")
    return drc.run(BOARD)


def test_the_routed_board_has_no_drc_violation_and_nothing_unrouted(drc_record, facts):
    r = drc_record
    print("DRC 警告の内訳:", r["warning_kinds"])
    assert r["violations"] == 0, r["details"]
    assert r["unconnected"] == 0
    assert facts["unconnected"] == 0            # KiCad の連結（pcbnew）でも 0
    assert set(r["warning_kinds"]) <= KNOWN_WARNINGS, r["warning_kinds"]
    assert r["warning_kinds"].get("npth_inside_courtyard", 0) == 2


def test_the_npth_warning_is_only_the_switch_pegs_under_the_holder():
    """下げた重大度（npth_inside_courtyard）に**ほかの物が紛れていない**こと。"""
    require(paths.KICAD_CLI, "DRC")
    out = BOARD.parent / "_npth.json"
    subprocess.run([paths.KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all",
                    "-o", str(out), str(BOARD)], capture_output=True, text=True)
    d = json.loads(out.read_text())
    out.unlink()
    items = [v for v in d["violations"] if v["type"] == "npth_inside_courtyard"]
    assert len(items) == 2
    for v in items:
        desc = " ".join(i["description"] for i in v["items"])
        assert "SW_PWR" in desc and "BT1" in desc, desc


def test_the_drc_check_notices_a_short(tmp_path):
    """**検査器が壊れていないか。**板の写しで列の線 1 本を幅 2mm に太らせると違反が出る。

    （ネット名を書き換えても壊れない: KiCad 10 は読み込むときに線のネットを繋がりから
    付け直した。2026-09-24 に確かめた——ROW0 と書いた線が COL3 として読まれた）"""
    from foundry import drc

    require(paths.KICAD_CLI, "DRC")
    d = tmp_path / "b"
    d.mkdir()
    for suf in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(BOARD.with_suffix(suf), d / ("x" + suf))
    t = (d / "x.kicad_pcb").read_text()
    m = re.search(r'\(segment\s*\(start [^)]*\)\s*\(end [^)]*\)\s*\(width [^)]*\)\s*'
                  r'\(layer "F\.Cu"\)\s*\(net "COL3"\)', t)
    assert m, "COL3 の表の線が見つからない（書式が変わった？）"
    t = t[:m.start()] + re.sub(r"\(width [^)]*\)", "(width 2)", m.group(0)) + t[m.end():]
    (d / "x.kicad_pcb").write_text(t)
    r = drc.run(d / "x.kicad_pcb")
    assert r["violations"] > 0 or r["unconnected"] > 0


# ---------------------------------------------------------------------------
# (c) 実装面: JLC が実装する物は全部裏（パッドの層で見る）。表は XIAO とホルダ（とスイッチの足）
# ---------------------------------------------------------------------------

JLC_REFS = re.compile(r"D\d+|U[12]|C_U[12]|R_(HI|LO)|D_PWR|SW_PWR")


def side_problems(facts):
    out = []
    pads = {}
    for p in facts["pads"]:
        pads.setdefault(p["ref"], []).append(p)
    jlc = [f for f in facts["footprints"] if JLC_REFS.fullmatch(f["ref"])]
    if len(jlc) != 62 + 8:
        out.append(f"JLC が実装する部品が {len(jlc)} 個（62 + 8 のはず）")
    for f in jlc:
        smd = [p for p in pads[f["ref"]] if p["smd"]]
        if not smd or any(p["front"] or not p["back"] for p in smd):
            out.append(f"{f['ref']}: パッドが裏だけでない")
        if f["exclude_bom"] or f["exclude_pos"]:
            out.append(f"{f['ref']}: BOM/CPL から外れている")
    for f in facts["footprints"]:
        front_smd = [p for p in pads.get(f["ref"], []) if p["smd"] and p["front"]]
        if front_smd and f["ref"] not in ("U_MCU", "BT1"):
            out.append(f"{f['ref']}: 表に SMD のパッド（表は XIAO とホルダだけ・D8）")
        if f["ref"] in ("U_MCU", "BT1") and not (f["exclude_bom"] and f["exclude_pos"]):
            out.append(f"{f['ref']}: 利用者が手はんだする物が BOM/CPL に載る")
        if re.fullmatch(r"SW\d+", f["ref"]) and not (f["exclude_bom"] and f["exclude_pos"]):
            out.append(f"{f['ref']}: 利用者が手はんだするスイッチが BOM/CPL に載る")
    return out


def test_jlc_parts_are_all_on_the_bottom(facts):
    assert side_problems(facts) == []


def test_the_side_check_notices_a_part_on_top(facts):
    f = copy.deepcopy(facts)
    for p in f["pads"]:
        if p["ref"] == "C_U1":
            p["front"], p["back"] = True, False
    assert any("C_U1" in b for b in side_problems(f))


# ---------------------------------------------------------------------------
# (d) ファーム ↔ 基板: overlay が名指しする XIAO のピン・595 の出力に、その行・列が来ている
# ---------------------------------------------------------------------------

# xiao_ble（Zephyr のボード定義）の xiao_spi: SCK = D8・MOSI = D10・MISO = D9
# （docs/knowledge/zmk-and-xiao.md「XIAO のピン」）。ZMK gpio_595: &shifter n は鎖の先頭
# （MOSI に繋がる 595）から数えて n//8 個目の 595 の Q(n%8)（QA = 0）。同上「キーマップ・行列」
XIAO_SPI = {"SCK": "D8", "MOSI": "D10"}


def overlay_facts(text):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", " ", text, flags=re.S)
    rows = [int(n) for n in re.findall(
        r"<&xiao_d (\d+)", re.search(r"row-gpios\s*=(.*?);", text, re.S).group(1))]
    cols = [int(n) for n in re.findall(
        r"<&shifter (\d+)", re.search(r"col-gpios\s*=(.*?);", text, re.S).group(1))]
    cs = int(re.search(r"cs-gpios\s*=\s*<&xiao_d (\d+)", text).group(1))
    adc = int(re.search(r"io-channels\s*=\s*<&adc (\d+)>", text).group(1))
    return rows, cols, cs, adc


def firmware_problems(facts, overlay_text):
    from foundry import pinmap

    rows, cols, cs, adc = overlay_facts(overlay_text)
    net = {(p["ref"], p["num"]): p["net"] for p in facts["pads"] if p["num"]}
    out = []
    for i, d in enumerate(rows):                          # kscan の行 i = row-gpios の i 番目
        if net.get(("U_MCU", f"D{d}")) != f"ROW{i}":
            out.append(f"行 {i}: overlay は D{d}、板の D{d} は {net.get(('U_MCU', f'D{d}'))}")
    for i, n in enumerate(cols):                          # kscan の列 i = &shifter n
        chip = ["U1", "U2"][n // 8]
        pad = pinmap.resolve("74LVC595", f"Q{n % 8}")
        if net.get((chip, pad)) != f"COL{i}":
            out.append(f"列 {i}: &shifter {n} = {chip} の Q{n % 8}（{pad} 番）が "
                       f"{net.get((chip, pad))}")
    # 鎖: U1 の DS = MOSI（D10）、U1 の Q7S = U2 の DS、SCK・ラッチは両方に
    ds1 = net.get(("U1", pinmap.resolve("74LVC595", "DS")))
    if ds1 != net.get(("U_MCU", XIAO_SPI["MOSI"])) or not ds1:
        out.append(f"U1 の DS {ds1} が XIAO の MOSI（{XIAO_SPI['MOSI']}）でない")
    q7s = net.get(("U1", pinmap.resolve("74LVC595", "Q7S")))
    if not q7s or q7s != net.get(("U2", pinmap.resolve("74LVC595", "DS"))):
        out.append("U1 の Q7S が U2 の DS に繋がっていない")
    for chip in ("U1", "U2"):
        if net.get((chip, pinmap.resolve("74LVC595", "SH_CP"))) != \
                net.get(("U_MCU", XIAO_SPI["SCK"])):
            out.append(f"{chip} の SH_CP が XIAO の SCK でない")
        if net.get((chip, pinmap.resolve("74LVC595", "ST_CP"))) != net.get(("U_MCU", f"D{cs}")):
            out.append(f"{chip} の ST_CP が overlay の CS（D{cs}）でない")
    # 電池の電圧: adc 0 = AIN0 = P0.02 = D0（zmk-and-xiao.md「ADC は D0〜D5 だけ（P0.02/03/28/29/04/05）」）
    ain = {0: "D0", 1: "D1", 4: "D2", 5: "D3", 7: "D4", 2: "D5"}.get(adc)
    if adc != 0 or net.get(("U_MCU", ain)) != "VBAT_SENSE":
        out.append(f"電池の電圧 adc {adc} → {ain} が VBAT_SENSE でない")
    return out


def test_the_board_matches_the_firmware_pin_map(facts):
    assert firmware_problems(facts, OVERLAY.read_text()) == []


@pytest.mark.parametrize("old, new", [
    ("<&xiao_d 2 (GPIO", "<&xiao_d 9 (GPIO"),                       # 行 0 のピンを取り違えた
    ("<&shifter 8 GPIO_ACTIVE_HIGH>, <&shifter 9", "<&shifter 9 GPIO_ACTIVE_HIGH>, <&shifter 8"),
    ("cs-gpios = <&xiao_d 7", "cs-gpios = <&xiao_d 1"),
])
def test_the_firmware_check_notices_a_changed_overlay(facts, old, new):
    text = OVERLAY.read_text()
    assert old in text
    assert firmware_problems(facts, text.replace(old, new, 1))


def test_the_routed_board_wires_every_key_as_the_transform_says():
    """行列の transform（ファーム）と、**配線した板**の各スイッチの COL・ダイオードの ROW。"""
    from test_cckb import TRANSFORM, board_matrix_mismatches

    assert board_matrix_mismatches(BOARD.read_text(), TRANSFORM.read_text()) == []


# ---------------------------------------------------------------------------
# (e) アンテナの禁止域: **塗った後**の銅が 0。禁止域は本物の位置にある
# ---------------------------------------------------------------------------

def test_the_antenna_keepout_has_no_copper_after_the_fill(facts, ifc):
    keep, ctrl = facts["copper_in"]
    assert keep["rect"] == list(ifc.antenna_keepout())
    assert keep["area"] == {"F.Cu": 0.0, "B.Cu": 0.0}, keep
    # 対照: 同じ大きさをベタのある所へずらすと銅が数えられる（0 しか返さない検査器ではない）
    assert ctrl["area"]["F.Cu"] > 10 and ctrl["area"]["B.Cu"] > 10, ctrl


def test_the_keepout_rule_area_is_where_the_antenna_is(facts, ifc):
    z = [z for z in facts["zones"] if z["name"] == "ANTENNA_KEEPOUT"]
    assert len(z) == 1 and z[0]["rule"] and sorted(z[0]["layers"]) == ["B.Cu", "F.Cu"]
    assert z[0]["no_tracks"] and z[0]["no_vias"] and z[0]["no_fill"]
    assert all(abs(a - b) < 0.01 for a, b in zip(z[0]["outline"], ifc.antenna_keepout()))
    chip = ifc.antenna_chip()               # 公式 STEP のチップ（test_cckb_interface が測る）
    k = ifc.antenna_keepout()
    assert k[0] <= chip[0] and k[1] <= chip[1] and k[2] >= chip[2] and k[3] >= chip[3]


def test_nothing_on_top_under_the_xiao(facts, ifc):
    """XIAO の裏の露出パッドの下に表の銅を置かない（XIAO_UNDERSIDE のルール領域が塗った板で効いている）。"""
    z = [z for z in facts["zones"] if z["name"] == "XIAO_UNDERSIDE"]
    assert len(z) == 1 and z[0]["layers"] == ["F.Cu"] and z[0]["no_vias"]
    x0, y0, x1, y1 = z[0]["outline"]
    for t in facts["tracks"]:
        if t["layer"] == "F.Cu":
            for p in (t["a"], t["b"]):
                assert not (x0 < p[0] < x1 and y0 < p[1] < y1), t
    for v in facts["vias"]:
        assert not (x0 - 0.3 < v["pos"][0] < x1 + 0.3 and y0 - 0.3 < v["pos"][1] < y1 + 0.3), v


# ---------------------------------------------------------------------------
# GND ベタ: 両面に塗られ、面積で健全（島は消した分を記録）
# ---------------------------------------------------------------------------

def test_both_layers_are_poured_with_ground_and_measured_by_area(facts, ifc):
    board_area = (ifc.pcb[2] - ifc.pcb[0]) * (ifc.pcb[3] - ifc.pcb[1])
    gz = [z for z in facts["zones"] if not z["rule"] and z["net"] == "GND"]
    assert sorted(z["layers"][0] for z in gz) == ["B.Cu", "F.Cu"]
    for z in gz:
        (lay, area), = z["area"].items()
        print(f"{lay}: {area:.0f} mm²（板 {board_area:.0f} mm² の {area / board_area:.0%}）"
              f" / 島 {z['outlines'][lay]}")
        assert area > 0.6 * board_area, (lay, area)
    rec = json.loads((BOARD.parent / "route.json").read_text())
    assert rec["unconnected"] == 0
    print("消した浮き島:", rec["islands_removed"], "個", rec["islands_removed_mm2"], "mm²")


def test_every_gnd_smd_pad_has_its_own_stub_and_via(facts):
    """GND の SMD パッドは**同じ層のスタブ → ビア**で繋ぐ（ベタが偶然被っているだけに頼らない）。"""
    vias = [v["pos"] for v in facts["vias"] if v["net"] == "GND"]
    pads = [p for p in facts["pads"] if p["net"] == "GND" and p["smd"]]
    assert len(pads) == 9                    # 595 ×2 × (GND・OE)・C ×2・R_LO・ホルダ −・XIAO GND
    for p in pads:
        lay = "F.Cu" if p["front"] else "B.Cu"
        b = p["box"]
        stubs = [t for t in facts["tracks"] if t["net"] == "GND" and t["layer"] == lay and any(
            b[0] - 1e-3 <= q[0] <= b[2] + 1e-3 and b[1] - 1e-3 <= q[1] <= b[3] + 1e-3
            for q in (t["a"], t["b"]))]
        ends = [q for t in stubs for q in (t["a"], t["b"])]
        assert any(math.hypot(q[0] - v[0], q[1] - v[1]) < 1e-3 for q in ends for v in vias), \
            f"{p['ref']}.{p['num']}"


# ---------------------------------------------------------------------------
# (f) 取付・支え・逃げ穴（段階 1 の検査は未配線の板で続く。ここは配線した板の外形）
# ---------------------------------------------------------------------------

def test_the_stab_reliefs_are_cut_in_the_routed_board(facts, ifc):
    segs = {(tuple(e["a"]), tuple(e["b"])) for e in facts["edge"] if e["shape"] == "Line"}
    n = 0
    for poly in ifc.stab_reliefs():
        for a, b in zip(poly, poly[1:] + poly[:1]):
            hit = any(math.hypot(a[0] - p[0], a[1] - p[1]) < 1e-3 and
                      math.hypot(b[0] - q[0], b[1] - q[1]) < 1e-3 for p, q in segs)
            assert hit, (a, b)
            n += 1
    assert n == 8 * 8


def test_no_copper_under_a_support_post_or_boss_on_the_bottom_parts(facts, ifc):
    """裏の部品（パッド）が支えの柱・取付のボスに当たらない（配線はマスク越しなので当たってよい）。"""
    for p in facts["pads"]:
        if not p["back"] or p["npth"] or re.fullmatch(r"SW\d+", p["ref"]):
            continue
        for s in SPEC.SUPPORTS:
            assert I.circle_rect_gap(s, SPEC.SUPPORT_D / 2, p["box"]) >= 0.3, (p["ref"], s)
        for m in ifc.mounts():
            assert I.circle_rect_gap(m, SPEC.MOUNT_BOSS_D / 2, p["box"]) >= 0.3, (p["ref"], m)


# ---------------------------------------------------------------------------
# (g) 電源の経路と極性
# ---------------------------------------------------------------------------

def power_problems(facts):
    from foundry import pinmap

    net = {(p["ref"], p["num"]): p["net"] for p in facts["pads"] if p["num"]}
    out = []
    k, a = pinmap.resolve("schottky", "K"), pinmap.resolve("schottky", "A")
    if net.get(("D_PWR", k)) != net.get(("U_MCU", "3V3")) or net.get(("D_PWR", k)) != "V3V3":
        out.append("B5819W のカソードが XIAO の 3V3 でない")
    if net.get(("D_PWR", a)) != "VBAT_SW":
        out.append("B5819W のアノードがスイッチの後ろ（VBAT_SW）でない")
    plus = pinmap.resolve("coin_holder_bs16", "+")
    if net.get(("BT1", plus)) != net.get(("SW_PWR", "2")) or not net.get(("BT1", plus)):
        out.append("ホルダの＋がスイッチの共通（②）に来ていない")
    if net.get(("BT1", pinmap.resolve("coin_holder_bs16", "-"))) != "GND":
        out.append("ホルダの−が GND でない")
    if net.get(("SW_PWR", "3")) != "VBAT_SW":
        out.append("スイッチの ③ が VBAT_SW でない")
    # 分圧はスイッチの後ろ・ショットキーの手前
    if (net.get(("R_HI", "1")), net.get(("R_HI", "2")), net.get(("R_LO", "1")),
            net.get(("R_LO", "2"))) != ("VBAT_SW", "VBAT_SENSE", "VBAT_SENSE", "GND"):
        out.append("分圧の結線")
    # XIAO に電池が行くのは 3V3（ショットキーの後ろ）と D0（分圧）だけ。BAT のパッドは無い
    for (r, n), v in net.items():
        if r == "U_MCU" and v.startswith("VBAT") and not (n == "D0" and v == "VBAT_SENSE"):
            out.append(f"XIAO の {n} に {v}")
    if any(r == "U_MCU" and n == "BAT" for r, n in net):
        out.append("XIAO の BAT にパッドがある")
    return out


def test_the_power_path_has_the_right_polarity(facts):
    assert power_problems(facts) == []


def test_the_power_check_notices_a_reversed_schottky(facts):
    f = copy.deepcopy(facts)
    for p in f["pads"]:
        if p["ref"] == "D_PWR":
            p["net"] = {"V3V3": "VBAT_SW", "VBAT_SW": "V3V3"}[p["net"]]
    assert any("カソード" in b for b in power_problems(f))


# ---------------------------------------------------------------------------
# 部品の形 ↔ データシート・公式 STEP（取り込んだフットプリントを板の上の位置で見る）
# ---------------------------------------------------------------------------

def _pads_of(facts, ref):
    return {p["num"]: p for p in facts["pads"] if p["ref"] == ref and p["num"]}


def test_the_power_switch_pads_hold_the_terminals_of_the_drawing(facts, ifc):
    """MK-12C02-G025 の図面（上面図）: 端子 ①②③ は本体の縁から 1.0 出て、間隔 3.0・1.5
    （② は中心から 0.75）。耳は本体の四隅から幅 0.4 の金具が 3.3〜3.925。これらが板の上の
    パッドの中にあり、パッドの外形が interface の psw_land と一致すること。"""
    s = SPEC
    ps = _pads_of(facts, "SW_PWR")
    x, y = s.PSW_AT
    body_in = x - s.PSW_BODY[1] / 2                        # 本体の内側の縁（端子の出る側）
    # 端子（足）: 縁から 1.0、幅 0.4。**板の向き**で: 縁に沿う y、奥行 x
    tips = {}
    for n, p in (("1", ps["1"]), ("2", ps["2"]), ("3", ps["3"])):
        b = p["box"]
        assert b[0] <= body_in - 1.0 and b[2] >= body_in, (n, b)
        tips[n] = (b[1] + b[3]) / 2 - y
    d = sorted(tips.values())
    assert abs((d[1] - d[0]) - 1.5) < 0.01 and abs((d[2] - d[1]) - 3.0) < 0.01 or \
        abs((d[1] - d[0]) - 3.0) < 0.01 and abs((d[2] - d[1]) - 1.5) < 0.01, tips
    assert abs(abs(tips["2"]) - 0.75) < 0.01
    # 耳: 金具（縁に沿って 3.3〜3.925・奥行 ±(0.9〜1.3)）がパッドの中
    for n in "4567":
        b = ps[n]["box"]
        dy = (b[1] + b[3]) / 2 - y
        tab_y = (y + math.copysign(3.3, dy), y + math.copysign(3.925, dy))
        dx = (b[0] + b[2]) / 2 - x
        tab_x = (x + math.copysign(0.9, dx), x + math.copysign(1.3, dx))
        assert b[1] <= min(tab_y) and b[3] >= max(tab_y), (n, b, tab_y)
        assert b[0] <= min(tab_x) and b[2] >= max(tab_x), (n, b, tab_x)
    # パッドの外形 = interface の psw_land（spec の PSW_* から作る。2 つの出どころが一致）
    allb = [p["box"] for p in ps.values()]
    ext = (min(b[0] for b in allb), min(b[1] for b in allb), max(b[2] for b in allb),
           max(b[3] for b in allb))
    assert all(abs(a - b) < 0.02 for a, b in zip(ext, ifc.psw_land())), (ext, ifc.psw_land())
    # 穴: φ0.9 を間隔 3.0（図面 2-Ø0.9・3±0.1）
    holes = [p for p in facts["pads"] if p["ref"] == "SW_PWR" and p["npth"]]
    assert len(holes) == 2 and all(abs(h["drill"] - 0.9) < 1e-3 for h in holes)
    assert abs(abs(holes[0]["pos"][1] - holes[1]["pos"][1]) - 3.0) < 1e-3


def test_the_holder_pads_are_the_drawing_land(facts, ifc):
    """BS-16-B4AK003 図面 MY-CP-0085 の PCB Layout: 3.75 × 4.5 を外外 28.0。＋は外側（基板の縁）。"""
    ps = _pads_of(facts, "BT1")
    for p, want in zip((ps["1"], ps["2"]), ifc.holder_pads()[::-1]):
        assert all(abs(a - b) < 0.01 for a, b in zip(p["box"], want)), (p["box"], want)
    assert ps["1"]["pos"][0] > ps["2"]["pos"][0]            # ＋（1）が +x（外側）


def test_the_xiao_pads_cover_the_castellations_of_the_official_step(facts, xiao_castellations):
    """公式 STEP のキャステレーション 14 個（XIAO の裏のパッド 1.524 幅・縁から 2.73）が、板の上の
    XIAO のパッドの中にあること。**STEP を毎回測る**（lib/xiao.3dshapes・無改変）。"""
    assert castellation_misses(facts, xiao_castellations) == []


def castellation_misses(facts, cast):
    """パッドの中に無いキャステレーション、または XIAO の縁からパッドの外端までが
    XIAO_PAD_EXT（0.6 ± 0.05）でないもの。"""
    ps = [p for p in facts["pads"] if p["ref"] == "U_MCU" and p["smd"]]
    assert len(ps) == 14 and len(cast) == 14
    y0 = SPEC.XIAO_AT[1]
    out = []
    for c in cast:
        hit = [p for p in ps if p["box"][0] <= c[0] and p["box"][2] >= c[2]
               and p["box"][1] <= c[1] and p["box"][3] >= c[3]]
        if len(hit) != 1:
            out.append(c)
            continue
        b = hit[0]["box"]
        # 縁の側（XIAO の中心から遠い方）で、パッドの外端 − XIAO の縁
        ext = (b[3] - c[3]) if c[3] > y0 else (c[1] - b[1])
        if abs(ext - SPEC.XIAO_PAD_EXT) > 0.05:
            out.append((c, round(ext, 3)))
    return out


@pytest.mark.parametrize("dx, dy", [(0.2, 0.0), (0.0, 0.2), (0.0, -0.2)])
def test_the_xiao_check_notices_a_shifted_xiao(facts, xiao_castellations, dx, dy):
    """**検査器が壊れていないか。**XIAO が 0.2 ずれた（ピンの並びの中心と本体の中心の取り違え
    0.064 の 3 倍）ら、キャステレーションがパッドから外れて落ちること。"""
    moved = [(a + dx, b + dy, c + dx, d + dy) for a, b, c, d in xiao_castellations]
    assert castellation_misses(facts, moved)


@pytest.fixture(scope="module")
def xiao_castellations():
    """公式 STEP から XIAO の裏のパッド（1.524 幅・縁から内へ）を測り、板の上の位置（CAD）に置く。

    STEP の座標: 長手 X（USB が +X）、幅 Z、厚さ Y（下面 −0.25）。板の上では USB が −x なので
    x = XIAO_AT.x − (X − X の中心)、幅方向は Z の向きを D0〜D6 の列（手前 −y）で決める。
    """
    from build123d import GeomType, import_step

    step = import_step(str(paths.LIB / "xiao.3dshapes" / "XIAO_nRF52840.step"))
    board = max(step.solids(), key=lambda so: so.bounding_box().size.X * so.bounding_box().size.Z)
    bb = board.bounding_box()
    cx, cz = (bb.min.X + bb.max.X) / 2, (bb.min.Z + bb.max.Z) / 2
    pads = []
    for f in board.faces():
        b = f.bounding_box()
        if f.geom_type == GeomType.PLANE and abs(b.max.Y - b.min.Y) < 1e-3 and \
                abs(b.min.Y + 0.24) < 0.02 and abs(b.size.X - 1.524) < 0.01 and \
                (abs(b.min.Z - bb.min.Z) < 0.01 or abs(b.max.Z - bb.max.Z) < 0.01):
            pads.append(b)
    assert len(pads) == 14
    # 幅の向き: アンテナのチップ（1.6×3.2）は D0〜D6 の側（spec.XIAO_ANT_SIDE・段階 1 で解いた）
    chip = [so for so in step.solids() if abs(so.bounding_box().size.X - 1.6) < 0.01
            and abs(so.bounding_box().size.Z - 3.2) < 0.01][0].bounding_box()
    front = 1 if (chip.min.Z + chip.max.Z) / 2 > cz else -1     # 手前（D0〜D6）が +Z か −Z か
    x0, y0 = SPEC.XIAO_AT
    out = []
    for b in pads:
        xs = sorted([x0 - (b.min.X - cx), x0 - (b.max.X - cx)])
        ys = sorted([y0 - front * (b.min.Z - cz), y0 - front * (b.max.Z - cz)])
        # 丸い内端（半径 0.762）は矩形の外。矩形の部分（縁から 2.032）だけを当てる
        out.append((xs[0], ys[0], xs[1], ys[1]))
    return out


# ---------------------------------------------------------------------------
# 鮮度: 配線した板は**いまの配置**から作られた（配置を変えて配線し直さない、を捕まえる）
# ---------------------------------------------------------------------------

UNROUTED = paths.PROJECTS / "cckb" / "pcb" / "unrouted" / "cckb_main.kicad_pcb"


def test_the_committed_unrouted_board_is_what_the_generator_makes_now(tmp_path):
    from foundry.boardhash import fingerprint

    require(paths.KICAD_PYTHON, "基板の生成")
    d = tmp_path / "cckb"
    shutil.copytree(paths.PROJECTS / "cckb", d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(d)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert fingerprint(d / "pcb/unrouted/cckb_main.kicad_pcb") == fingerprint(UNROUTED), \
        "tools/kb cckb pcb で作り直し、route_pcb.py で配線し直すこと"


def route_is_fresh(record, unrouted):
    from foundry.boardhash import fingerprint

    return record["unrouted_fingerprint"] == fingerprint(unrouted)


def test_the_routed_board_was_made_from_the_current_placement():
    rec = json.loads((BOARD.parent / "route.json").read_text())
    assert route_is_fresh(rec, UNROUTED)


def test_the_freshness_check_notices_a_moved_part(tmp_path):
    """**検査器が壊れていないか。**未配線の板で U1 を 1mm 動かした写しでは鮮度が落ちる。"""
    rec = json.loads((BOARD.parent / "route.json").read_text())
    t = UNROUTED.read_text()
    i = t.index('(property "Reference" "U1"')
    blk_start = t.rfind("(footprint", 0, i)
    at = re.search(r"\(at (-?[\d.]+) (-?[\d.]+)", t[blk_start:])
    x = float(at.group(1))
    s = blk_start + at.start()
    moved = t[:s] + t[s:].replace(at.group(0), f"(at {x + 1.0:.4f} {at.group(2)}", 1)
    f = tmp_path / "u.kicad_pcb"
    f.write_text(moved)
    assert not route_is_fresh(rec, f)


# ---------------------------------------------------------------------------
# 上の検査それぞれを、事実の写しを壊して走らせ、**落ちること**を確かめる
# ---------------------------------------------------------------------------

def _near(pos, ref_pos, r):
    return math.hypot(pos[0] - ref_pos[0], pos[1] - ref_pos[1]) < r


def _break_gnd_via(f):
    u = next(p for p in f["pads"] if p["ref"] == "U1" and p["num"] == "8")
    f["vias"] = [v for v in f["vias"] if not (v["net"] == "GND" and _near(v["pos"], u["pos"], 6))]


def _break_relief(f):
    f["edge"] = [e for e in f["edge"] if e["shape"] != "Line" or not _near(e["a"], (121.444, 0), 16)]


def _break_support(f):
    s = SPEC.SUPPORTS[0]
    p = next(p for p in f["pads"] if p["ref"] == "D1" and p["num"] == "1")
    p["box"] = [s[0] - 0.4, s[1] - 0.4, s[0] + 0.4, s[1] + 0.4]


def _break_holder(f):
    a, b = [p for p in f["pads"] if p["ref"] == "BT1"]
    a["box"], b["box"], a["pos"], b["pos"] = b["box"], a["box"], b["pos"], a["pos"]


def _break_switch(f):
    p = next(p for p in f["pads"] if p["ref"] == "SW_PWR" and p["num"] == "2")
    p["box"] = [p["box"][0], p["box"][1] + 0.5, p["box"][2], p["box"][3] + 0.5]


def _break_under_xiao(f):
    x, y = SPEC.XIAO_AT
    f["tracks"].append(dict(net="SPI_SCK", layer="F.Cu", a=[x, y], b=[x + 1, y], w=0.2))


def _break_keepout_place(f):
    z = next(z for z in f["zones"] if z["name"] == "ANTENNA_KEEPOUT")
    z["outline"] = [v + 3.9 if i % 2 == 0 else v for i, v in enumerate(z["outline"])]


def _break_pour_area(f):
    """KiCad が島を黙って消すと多角形の数は同じまま面積だけ減る（pcb.md）。面積で気づくか。"""
    z = next(z for z in f["zones"] if z["name"] == "GND_B")
    z["area"]["B.Cu"] = z["area"]["B.Cu"] / 2


@pytest.mark.parametrize("check, breaker", [
    ("test_both_layers_are_poured_with_ground_and_measured_by_area", _break_pour_area),
    ("test_every_gnd_smd_pad_has_its_own_stub_and_via", _break_gnd_via),
    ("test_the_stab_reliefs_are_cut_in_the_routed_board", _break_relief),
    ("test_no_copper_under_a_support_post_or_boss_on_the_bottom_parts", _break_support),
    ("test_the_holder_pads_are_the_drawing_land", _break_holder),
    ("test_the_power_switch_pads_hold_the_terminals_of_the_drawing", _break_switch),
    ("test_nothing_on_top_under_the_xiao", _break_under_xiao),
    ("test_the_keepout_rule_area_is_where_the_antenna_is", _break_keepout_place),
])
def test_each_board_check_notices_a_break(facts, ifc, check, breaker):
    import inspect

    f = copy.deepcopy(facts)
    breaker(f)
    fn = globals()[check]
    args = {"facts": f, "ifc": ifc}
    with pytest.raises(AssertionError):
        fn(**{k: args[k] for k in inspect.signature(fn).parameters})
