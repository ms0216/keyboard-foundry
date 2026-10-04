"""cckb-click の基板: 足跡・回路・配置（未配線の板）。projects/cckb-click/{spec,click_layout,click_circuit,pcb_extra}.py。

相手にするのは外の事実（Alps の製品ページのランドの図・MYOUNG と SHOU HAN の図面・LCSC〔EasyEDA〕の部品データ・
販売者が JLC に実装させた基板の足跡）と、KiCad が読んだ板そのもの。**生成器の意図とは比べない。**
各検査の下に「故意に壊すと落ちる」検査を置く（CLAUDE.md 検証の作法 2）。
配線して塗った板の検査は tests/test_cckb_click_board.py。
"""

import copy
import json
import math
import re
import subprocess
import sys

import pytest

from conftest import ROOT, require
from foundry import mech, paths, pinmap
from foundry.layout import UNIT
from foundry.project import load

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
import click_circuit as circuit  # noqa: E402
import click_layout as L  # noqa: E402

PROJECT = load("cckb-click")
S = PROJECT.spec
LAY = L.Layout(PROJECT)
EE = json.loads((ROOT / "tests/fixtures/easyeda/footprints_click.json").read_text())["parts"]
EE_UNIT = 0.254
WIDE = {1.5: 5, 1.75: 2, 2.25: 4}          # HHKB 英語配列（スペースを 2.25 + 1.5 + 2.25 に分けた）の幅の広いキー


# ---------------------------------------------------------------------------
# 足跡を読む（.kicad_mod の pad の行。KiCad の座標 = y 下向き）
# ---------------------------------------------------------------------------

def fp_pads(lib, name):
    """[(番号, 種類, 形, x, y, 幅, 高さ, 層の並び)]"""
    text = (paths.LIB / lib / f"{name}.kicad_mod").read_text()
    out = []
    for m in re.finditer(r'\(pad "([^"]*)" (\w+) (\w+) \(at ([-\d.]+) ([-\d.]+)\) \(size ([-\d.]+) ([-\d.]+)\)(.*)', text):
        num, kind, shape, x, y, w, h, rest = m.groups()
        out.append((num, kind, shape, float(x), float(y), float(w), float(h), re.findall(r'"([^"]+)"', rest)))
    return out


def ee_pads(code):
    ox, oy = EE[code]["head"]
    return [(n, (x - ox) * EE_UNIT, (y - oy) * EE_UNIT, w * EE_UNIT, h * EE_UNIT) for n, x, y, w, h in EE[code]["pads"]]


# ---------------------------------------------------------------------------
# スイッチ（Alps の図: 外外 8.5 × 5.0・内内 3.0 × 3.0。奥の 2 つ・手前の 2 つがそれぞれ中でつながる）
# ---------------------------------------------------------------------------
# 外の事実を**ここに打ち直す**（mech.SKRA_LAND と同じ図から。写しどうしを比べない）
ALPS_LAND_OUTER = (8.5, 5.0)
ALPS_LAND_INNER = (3.0, 3.0)
# 販売者が JLC に実装させた基板（PCB_Data/ClickBoard Tenkey/Assemble Alps Silent/Assemble.kicad_pcb・MIT）の足跡 SKRACAE010_1u から
# 読んだパッド（2026-10-03）: 番号・中心・大きさ。奥（KiCad の −y）が 1・手前が 2
SELLER_PADS = {("1", -2.875, -2.0), ("1", 2.875, -2.0), ("2", -2.875, 2.0), ("2", 2.875, 2.0)}
SELLER_PAD_SIZE = (2.75, 1.0)


def switch_land_problems(pads):
    out = []
    if len(pads) != 4 or any(p[1] != "smd" or p[2] != "rect" for p in pads):
        return [f"パッドが 4 つの矩形でない: {pads}"]
    x0 = min(p[3] - p[5] / 2 for p in pads)
    x1 = max(p[3] + p[5] / 2 for p in pads)
    y0 = min(p[4] - p[6] / 2 for p in pads)
    y1 = max(p[4] + p[6] / 2 for p in pads)
    if abs(x1 - x0 - ALPS_LAND_OUTER[0]) > 0.01 or abs(y1 - y0 - ALPS_LAND_OUTER[1]) > 0.01:
        out.append(f"外外 {x1 - x0:.3f} × {y1 - y0:.3f}（図は {ALPS_LAND_OUTER}）")
    if abs(x0 + x1) > 0.01 or abs(y0 + y1) > 0.01:
        out.append(f"中心がずれている ({(x0 + x1) / 2:.3f}, {(y0 + y1) / 2:.3f})")
    gx = min(p[3] - p[5] / 2 for p in pads if p[3] > 0) - max(p[3] + p[5] / 2 for p in pads if p[3] < 0)
    gy = min(p[4] - p[6] / 2 for p in pads if p[4] > 0) - max(p[4] + p[6] / 2 for p in pads if p[4] < 0)
    if abs(gx - ALPS_LAND_INNER[0]) > 0.01 or abs(gy - ALPS_LAND_INNER[1]) > 0.01:
        out.append(f"内内 {gx:.3f} × {gy:.3f}（図は {ALPS_LAND_INNER}）")
    for p in pads:
        if (p[0], p[3], p[4]) not in SELLER_PADS or (p[5], p[6]) != SELLER_PAD_SIZE:
            out.append(f"販売者の足跡と違うパッド {p[:7]}")
        if (p[0] == "1") != (p[4] < 0):
            out.append(f"パッド {p[0]} が y {p[4]}（1 = 奥の 2 つ = Alps の端子 1・2、2 = 手前 = 端子 3・4）")
        if set(p[7]) != {"F.Cu", "F.Paste", "F.Mask"}:
            out.append(f"パッドの層 {p[7]}")
    return out


def test_the_switch_land_is_the_alps_drawing_and_the_sellers_assembled_footprint():
    pads = fp_pads("keyswitch.pretty", mech.SKRA_FP)
    assert switch_land_problems(pads) == []
    assert mech.SKRA_LAND == dict(outer=ALPS_LAND_OUTER, inner=ALPS_LAND_INNER)
    # LCSC の足跡（C202383）は同じ場所に小さめのパッド（2.1 × 1.2・中心 ±3.0, ±2.0）。端子の先 ±3.4 は両方のランドの中
    ee = ee_pads("C202383")
    assert sorted((round(abs(x), 3), round(abs(y), 3)) for _, x, y, _, _ in ee) == [(3.0, 2.0)] * 4
    for _, x, y, w, h in ee:
        mine = next(p for p in pads if (p[3] > 0) == (x > 0) and (p[4] > 0) == (y > 0))
        assert abs(mine[3] - x) <= 0.15 and abs(mine[4] - y) <= 0.01      # 中心の差 0.125（JLC の置く位置は足跡の原点 = 同じ中心）
    # 端子（外形図: 幅 6.8 の先・間隔 4 ± 0.2・幅 0.7）がランドに載る
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = next(p for p in pads if (p[3] > 0) == (sx > 0) and (p[4] > 0) == (sy > 0))
            assert p[3] - p[5] / 2 <= sx * 3.4 <= p[3] + p[5] / 2 and abs(p[4] - sy * 2.0) + 0.35 + 0.2 <= p[6] / 2 + 0.2 + 1e-9


@pytest.mark.parametrize("i, dx, dy, word", [(0, 0.1, 0.0, "内内"), (1, 0.0, -0.1, "外外"), (2, -0.1, 0.0, "外外"), (3, 0.0, -0.1, "内内")])
def test_the_switch_land_check_notices_a_pad_moved_by_a_tenth(i, dx, dy, word):
    pads = fp_pads("keyswitch.pretty", mech.SKRA_FP)
    p = list(pads[i])
    p[3], p[4] = p[3] + dx, p[4] + dy
    pads[i] = tuple(p)
    assert any(word in b for b in switch_land_problems(pads)), switch_land_problems(pads)


def test_the_switch_land_check_notices_swapped_pad_numbers():
    pads = [(("2" if p[0] == "1" else "1"),) + p[1:] for p in fp_pads("keyswitch.pretty", mech.SKRA_FP)]
    assert any("奥の 2 つ" in b for b in switch_land_problems(pads))


# ---------------------------------------------------------------------------
# 電池クリップ（図面 MY-CP-0247 の PCB Layout Diagram と LCSC の足跡）
# ---------------------------------------------------------------------------
CLIP_DRAWING = dict(pad=(4.15, 4.20), span=20.05, height=4.0, body_w=16.90, depth=15.10, total_w=23.2)


def clip_problems(pads):
    out = []
    plus = [p for p in pads if p[0] == "1"]
    minus = [p for p in pads if p[0] == "2" and p[1] != "thru_hole"]
    if len(plus) != 2 or len(minus) != 1:
        return [f"＋ {len(plus)} 個・− {len(minus)} 個"]
    xs = sorted(p[3] for p in plus)
    if abs(xs[1] - xs[0] - CLIP_DRAWING["span"]) > 0.01 or abs(xs[0] + xs[1]) > 0.01 or any(abs(p[4]) > 0.01 for p in plus):
        out.append(f"＋のランドの中心 {xs}（図は間 {CLIP_DRAWING['span']}）")
    if any((p[5], p[6]) != CLIP_DRAWING["pad"] for p in plus):
        out.append(f"＋のランドの大きさ {[(p[5], p[6]) for p in plus]}")
    m = minus[0]
    ee_minus = next(p for p in ee_pads("C20606805") if p[0] == "2")
    if (m[3], m[4]) != (0.0, 0.0) or abs(m[5] - ee_minus[3]) > 0.01 or m[2] != "circle":
        out.append(f"−の裸の銅 {m[:7]}（LCSC の足跡は中心に φ{ee_minus[3]:.2f}）")
    if "F.Paste" in m[7] or m[1] != "connect":
        out.append(f"−の裸の銅にはんだが載る・種類が {m[1]}（層 {m[7]}）")
    for p in plus:
        e = min(ee_pads("C20606805"), key=lambda q: math.hypot(q[1] - p[3], q[2] - p[4]))
        if e[0] != "1" or math.hypot(e[1] - p[3], e[2] - p[4]) > 0.05:
            out.append(f"＋のランド {p[3], p[4]} が LCSC の足跡のパッド {e[:3]} と違う")
    vias = [p for p in pads if p[0] == "2" and p[1] == "thru_hole"]
    if len(vias) < 2 or any(math.hypot(p[3], p[4]) + p[5] / 2 > m[5] / 2 for p in vias):
        out.append(f"−の裸の銅の中のビア {len(vias)} 個（裏の GND へ 2 個以上・銅の中）")
    return out


def test_the_clip_land_is_the_drawing_and_the_bare_pad_gets_no_solder():
    assert clip_problems(fp_pads("cckb-click.pretty", "BAT_MY-1632-03-R")) == []
    assert (S.CLIP_PAD, S.CLIP_PAD_SPAN, S.CLIP_H, S.CLIP_BODY_W) == (CLIP_DRAWING["pad"], CLIP_DRAWING["span"],
                                                                     CLIP_DRAWING["height"], CLIP_DRAWING["body_w"])
    assert S.CLIP_STOP + S.CLIP_MOUTH == pytest.approx(CLIP_DRAWING["depth"], abs=0.02)
    assert S.CLIP_PAD_SPAN + S.CLIP_PAD[0] > CLIP_DRAWING["total_w"] + 0.3            # 端子（23.2 ± 0.3）がランドの外外 24.2 の中
    minus = next(p for p in fp_pads("cckb-click.pretty", "BAT_MY-1632-03-R") if p[1] == "connect")
    assert minus[5] == S.CLIP_NEG_PAD_D < 12.0                                      # CR1632 の −の面（約 φ12）の中


@pytest.mark.parametrize("edit, word", [
    (lambda p: (p[0], p[1], p[2], p[3] + 0.1) + p[4:] if p[0] == "1" and p[3] > 0 else p, "＋のランドの中心"),
    (lambda p: p[:7] + (p[7] + ["F.Paste"],) if p[0] == "2" and p[1] == "connect" else p, "はんだが載る"),
    (lambda p: p[:5] + (6.0, 6.0) + p[7:] if p[0] == "2" and p[1] == "connect" else p, "裸の銅"),
])
def test_the_clip_check_notices_a_break(edit, word):
    pads = [edit(p) for p in fp_pads("cckb-click.pretty", "BAT_MY-1632-03-R")]
    assert any(word in b for b in clip_problems(pads)), clip_problems(pads)


# ---------------------------------------------------------------------------
# 電源スイッチ（承認書 2024-12-14 の外形図・安装参考图 と LCSC の足跡）
# ---------------------------------------------------------------------------
# 図の値。向きは LCSC の足跡に合わせた（端子が −y・つまみが +y。突起の穴の軸が y +0.55）
MSK_DRAWING = dict(body=(8.0, 2.8), height=1.4, knob=(1.3, 1.45), travel=1.6, peg_pitch=3.0, peg_d=0.75,
                   shell_pad=(1.05, 0.7), shell_outer=8.4, shell_pitch=2.2, pin_w=0.6, pin_from_axis=(1.3, 2.6),
                   pin_x={"1": -2.25, "2": 0.75, "3": 2.25})
MSK_AXIS = 0.55


def psw_problems(pads):
    out = []
    pins = {p[0]: p for p in pads if p[0] in "123" and p[0]}
    shell = [p for p in pads if p[0] == "4"]
    holes = [p for p in pads if p[1] == "np_thru_hole"]
    if set(pins) != {"1", "2", "3"} or len(shell) != 4 or len(holes) != 2:
        return [f"端子 {sorted(pins)}・枠 {len(shell)}・穴 {len(holes)}"]
    for n, p in pins.items():
        near, far = MSK_AXIS - (p[4] + p[6] / 2), MSK_AXIS - (p[4] - p[6] / 2)
        if abs(p[3] - MSK_DRAWING["pin_x"][n]) > 0.01 or p[5] != MSK_DRAWING["pin_w"]:
            out.append(f"端子 {n} の x {p[3]}・幅 {p[5]}")
        if near > MSK_DRAWING["pin_from_axis"][0] + 0.01 or far < MSK_DRAWING["pin_from_axis"][1] - 0.01:
            out.append(f"端子 {n} のランドが軸から {near:.2f}〜{far:.2f}（図の 1.3〜2.6 を含んでいない）")
    xs = sorted({round(abs(p[3]) + p[5] / 2, 3) for p in shell})
    ys = sorted({p[4] for p in shell})
    if xs != [MSK_DRAWING["shell_outer"] / 2] or len(ys) != 2 or abs(ys[1] - ys[0] - MSK_DRAWING["shell_pitch"]) > 0.01 \
            or abs((ys[0] + ys[1]) / 2 - MSK_AXIS) > 0.01 or any((p[5], p[6]) != MSK_DRAWING["shell_pad"] for p in shell):
        out.append(f"枠のランド 外外の半分 {xs}・y {ys}")
    hx = sorted(p[3] for p in holes)
    if abs(hx[1] - hx[0] - MSK_DRAWING["peg_pitch"]) > 0.01 or any(abs(p[4] - MSK_AXIS) > 0.01 for p in holes):
        out.append(f"突起の穴 {[(p[3], p[4]) for p in holes]}")
    d = holes[0][5]
    if not MSK_DRAWING["peg_d"] + 0.1 < d <= MSK_DRAWING["peg_d"] + 0.2:
        out.append(f"突起の穴 φ{d}（突起 φ0.75 ± 0.1 が JLC の穴の公差 −0.05 でも入り、遊びが片側 0.1 以下）")
    # LCSC の足跡と: 番号ごとに中心が 0.3 以内（端子は長さの取り方が違う: こちらは図の 1.3〜2.6 を含めて先を 0.2 伸ばした）
    ee = ee_pads("C431540")
    for p in list(pins.values()) + shell:
        e = min((q for q in ee if q[0] == p[0]), key=lambda q: math.hypot(q[1] - p[3], q[2] - p[4]))
        if math.hypot(e[1] - p[3], e[2] - p[4]) > 0.3:
            out.append(f"パッド {p[0]} {p[3], p[4]} が LCSC の足跡 {e[1]:.2f}, {e[2]:.2f} から離れている")
    ox, oy = EE["C431540"]["head"]
    eh = sorted(((x - ox) * EE_UNIT, (y - oy) * EE_UNIT, 2 * r * EE_UNIT) for x, y, r in EE["C431540"]["holes"])
    if any(math.hypot(a[0] - b[3], a[1] - b[4]) > 0.01 or abs(a[2] - b[5]) > 0.01 for a, b in zip(eh, sorted(holes, key=lambda p: p[3]))):
        out.append(f"突起の穴が LCSC の足跡 {eh} と違う")
    return out


def test_the_power_switch_land_is_the_drawing_and_sits_where_jlc_places_the_part():
    assert psw_problems(fp_pads("cckb-click.pretty", "SW_MSK12C02")) == []
    assert (S.PSW_BODY, S.PSW_H, S.PSW_KNOB, S.PSW_TRAVEL, S.PSW_ORIGIN_TO_BODY) == (
        MSK_DRAWING["body"], MSK_DRAWING["height"], MSK_DRAWING["knob"], MSK_DRAWING["travel"], MSK_AXIS)


@pytest.mark.parametrize("edit, word", [
    (lambda p: p[:3] + (p[3] + 0.1,) + p[4:] if p[0] == "2" else p, "端子 2"),
    (lambda p: p[:4] + (p[4] + 0.7,) + p[5:] if p[0] == "1" else p, "含んでいない"),
    (lambda p: p[:4] + (p[4] + 0.1,) + p[5:] if p[1] == "np_thru_hole" else p, "突起の穴"),
    (lambda p: p[:5] + (0.8, 0.8) + p[7:] if p[1] == "np_thru_hole" else p, "φ0.8"),
])
def test_the_power_switch_check_notices_a_break(edit, word):
    pads = [edit(p) for p in fp_pads("cckb-click.pretty", "SW_MSK12C02")]
    assert any(word in b for b in psw_problems(pads)), psw_problems(pads)


# ---------------------------------------------------------------------------
# 配置: 未配線の板（KiCad が読んだ物）と、回路の宣言
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def unrouted(tmp_path_factory):
    """いまの生成器で作り直した未配線の板の事実（パッド・部品。projects/cckb/tools/board_geometry.py の書式）。"""
    require(paths.KICAD_PYTHON, "基板の生成")
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", "cckb-click"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and "スイッチ 62" in r.stdout, r.stdout + r.stderr
    out = tmp_path_factory.mktemp("click") / "geo.json"
    board = PROJECT.root / "pcb" / "unrouted" / "cckb-click_main.kicad_pcb"
    r = subprocess.run([paths.KICAD_PYTHON, str(ROOT / "projects/cckb/tools/board_geometry.py"), str(board), str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
    return json.loads(out.read_text())


def netlist_problems(geo, want=None, mech_refs=None):
    """宣言 → 板のパッドのネット。**物の数で**数える（宣言に無い部品・板に無い部品・番号ごとの全部のパッド）。"""
    want = circuit.expected_pad_nets(PROJECT) if want is None else want
    mech_refs = circuit.mechanical_refs(PROJECT) if mech_refs is None else mech_refs
    have = {}
    for p in geo["pads"]:
        if p["num"]:
            have.setdefault(p["ref"], {}).setdefault(p["num"], set()).add(p["net"])
    refs = {f["ref"] for f in geo["footprints"]}
    out = [f"板に無い: {r}" for r in sorted(set(want) - refs)]
    out += [f"宣言に無い: {r}" for r in sorted(refs - set(want) - mech_refs)]
    out += [f"穴が板に無い: {r}" for r in sorted(mech_refs - refs)]
    for ref, pads in want.items():
        got = have.get(ref, {})
        if set(got) != set(pads):
            out.append(f"{ref}: パッド {sorted(got)} / 宣言 {sorted(pads)}")
            continue
        for num, net in pads.items():
            if got[num] != {net}:
                out.append(f"{ref}.{num}: {sorted(got[num])} / 宣言 {net!r}")
    return out


def test_every_pad_of_the_unrouted_board_carries_the_declared_net(unrouted):
    assert netlist_problems(unrouted) == []
    want = circuit.expected_pad_nets(PROJECT)
    assert len(want) == 62 * 2 + 22 + 13 and sum(1 for p in unrouted["pads"] if p["net"]) > 62 * 6 + 22 * 4


def test_the_netlist_check_notices_a_wrong_net_on_one_of_two_twin_pads(unrouted):
    geo = copy.deepcopy(unrouted)
    twin = [p for p in geo["pads"] if p["ref"] == "SW30" and p["num"] == "1"]
    assert len(twin) == 2
    twin[1]["net"] = ""
    assert any("SW30.1" in b for b in netlist_problems(geo))
    geo = copy.deepcopy(unrouted)
    geo["footprints"].append(dict(ref="X1"))
    assert netlist_problems(geo) == ["宣言に無い: X1"]


def test_the_circuit_is_the_same_as_cckb_except_the_battery_and_the_power_switch():
    """電気の設計は CCKB と同じ（ピンが同じなので ZMK のシールドは同じ形）。違うのは電池の部品・電源スイッチの部品と端子だけ。"""
    sys.path.insert(0, str(ROOT / "projects" / "cckb"))
    import circuit as cckb                                  # noqa: E402
    assert circuit.XIAO_PINS == cckb.XIAO_PINS and circuit.POWER_NETS == cckb.POWER_NETS
    ours = {r: (k, p) for r, k, p in circuit.electronics()}
    theirs = {r: (k, p) for r, k, p in cckb.electronics()}
    # 足したのは、部品の載らない銅だけ: 試験用のランド（VBAT_SW）と、載せないコンデンサのランド 2 つ（1 回目の監査 A 重要 1・D 重要 1）
    assert set(ours) - set(theirs) == {"TP_VSW", "C_BAT", "C_3V3"} and not set(theirs) - set(ours)
    assert ours.pop("TP_VSW") == ("testpoint", {"1": "VBAT_SW"})
    assert ours.pop("C_BAT") == ("cap_land", {"1": "VBAT_SW", "2": "GND"})        # 電源スイッチの後ろ・D_PWR の手前（スイッチで切れる）
    assert ours.pop("C_3V3") == ("cap_land", {"1": "V3V3", "2": "GND"})           # D_PWR の後ろ
    assert {S.FAB_KINDS[r"C_(BAT|3V3)"]} <= S.NOT_ASSEMBLED
    diff = sorted(r for r in ours if ours[r] != theirs[r])
    assert diff == ["BT1", "SW_PWR"]
    assert ours["BT1"][1] == theirs["BT1"][1]                 # ＋ と − のネットは同じ
    nets = lambda d: sorted(n for n in d.values() if n not in ("NC", "GND"))   # noqa: E731
    assert nets(ours["SW_PWR"][1]) == nets(theirs["SW_PWR"][1]) == ["VBAT_IN", "VBAT_SW"]
    # 行列: 同じキーに同じ行・列・ダイオードの向き
    mine = {r: p for r, k, p in circuit.matrix(PROJECT) if not re.fullmatch(r"SW[AB]\d+", r)}
    assert mine == {r: p for r, k, p in cckb.matrix()} and len(mine) == 124


def site_problems(geo, lay=LAY):
    """スイッチの置き場: 真ん中 62・空きランド 22（幅の広いキー 11 個の左右）。空きランドは真ん中と同じネット・同じ高さ・
    穴の中（リブ・柱の下に入らない）・真ん中のランドに重ならない。"""
    out = []
    fps = {f["ref"]: f for f in geo["footprints"]}
    nets = {}
    for p in geo["pads"]:
        nets.setdefault(p["ref"], {}).setdefault(p["num"], set()).add(p["net"])
    side = sorted(r for r in fps if re.fullmatch(r"SW[AB]\d+", r))
    wide = [k for k in lay.keys if k.w >= 1.5]
    if sorted(WIDE.items()) != sorted({w: sum(1 for k in wide if k.w == w) for w in {k.w for k in wide}}.items()):
        out.append(f"幅の広いキー {[(k.label, k.w) for k in wide]}")
    if side != sorted(f"SW{ab}{k.i}" for k in wide for ab in "AB"):
        out.append(f"空きランド {side}")
    for k in wide:
        hole = lay.hole(k)
        for ab, sgn in (("A", -1), ("B", 1)):
            ref = f"SW{ab}{k.i}"
            if ref not in fps:
                continue
            f = fps[ref]
            if f["fp"] != mech.SKRA_FP or abs(f["y"] - k.y) > 1e-6 or (f["x"] - k.x) * sgn <= 0:
                out.append(f"{ref}: 足跡 {f['fp']}・位置 {f['x'], f['y']}")
            land = lay.land(f["x"], f["y"])
            if not (hole[0] <= land[0] and land[2] <= hole[2]):
                out.append(f"{ref}: ランド {land} が穴 {hole} の外（リブの下）")
            if L.rect_gap(land, lay.land(k.x, k.y)) < 0.2:
                out.append(f"{ref}: 真ん中のランドとの間 {L.rect_gap(land, lay.land(k.x, k.y)):.3f}")
            if nets[ref] != nets[f"SW{k.i}"]:
                out.append(f"{ref}: ネット {nets[ref]} が真ん中 {nets[f'SW{k.i}']} と違う")
            other = fps.get(f"SW{'B' if ab == 'A' else 'A'}{k.i}")
            if other is not None and abs(f["x"] + other["x"] - 2 * k.x) > 1e-6:
                out.append(f"{ref}: 左右が対称でない")
    return out


def test_every_wide_key_has_two_parallel_side_lands_inside_its_hole(unrouted):
    assert site_problems(unrouted) == []
    assert len(LAY.switch_sites()) == 84 and sum(1 for s in LAY.switch_sites() if s[3]) == 62
    # 空きランドの位置はキャップの形から: 穴の端から SIDE_SW_END（ランドの外端が穴の端のすぐ内側）
    k = next(k for k in LAY.keys if k.w == 2.25)
    assert LAY.side_offset(k) == pytest.approx((2.25 * UNIT - 2.0) / 2 - 4.3) and LAY.hole(k)[2] - LAY.land(k.x + LAY.side_offset(k), k.y)[2] == pytest.approx(0.05)


def test_the_site_check_notices_a_missing_and_a_misplaced_side_land(unrouted):
    geo = copy.deepcopy(unrouted)
    geo["footprints"] = [f for f in geo["footprints"] if f["ref"] != "SWA43"]
    assert any("空きランド" in b for b in site_problems(geo))
    geo = copy.deepcopy(unrouted)
    next(f for f in geo["footprints"] if f["ref"] == "SWB16")["x"] += 0.2
    assert any("SWB16" in b and "穴" in b for b in site_problems(geo))
    geo = copy.deepcopy(unrouted)
    next(p for p in geo["pads"] if p["ref"] == "SWB42" and p["num"] == "2")["net"] = "SW41_D"
    assert any("SWB42" in b and "ネット" in b for b in site_problems(geo))


def paste_and_side_problems(geo_board):
    """板の S 式から: 部品は全部表・空きランドと XIAO にはんだを載せない・電池の −の裸の銅にも載せない。"""
    text = geo_board.read_text()
    out = []
    for m in re.finditer(r'\(footprint "[^"]*"\s*\(layer "([^"]+)"\)[\s\S]*?\(property "Reference" "([^"]+)"', text):
        if m.group(1) != "F.Cu":
            out.append(f"{m.group(2)} が {m.group(1)}（裏に部品を置かない）")
    blocks = re.split(r'\n\t\(footprint ', text)[1:]
    for b in blocks:
        ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
        paste = len(re.findall(r'\(pad "[^"]*" smd[\s\S]*?\(layers[^)]*"F\.Paste"', b))
        smd = len(re.findall(r'\(pad "[^"]*" smd', b))
        dry = bool(re.fullmatch(r"SW[AB]\d+|U_MCU|TP_VSW|C_BAT|C_3V3", ref))
        if dry and paste:
            out.append(f"{ref}: JLC が実装しないのに、はんだが載るパッド {paste} 個")
        if not dry and smd and paste != smd:
            out.append(f"{ref}: はんだの載らない表面実装のパッド {smd - paste} 個")
        if ref == "BT1" and re.search(r'\(pad "2" connect[\s\S]*?\(layers[^)]*"F\.Paste"', b):
            out.append("BT1: −の裸の銅にはんだが載る")
    return out


def test_everything_sits_on_top_and_only_the_jlc_parts_get_paste(unrouted):
    board = PROJECT.root / "pcb" / "unrouted" / "cckb-click_main.kicad_pcb"
    assert paste_and_side_problems(board) == []
    assert len(re.findall(r'\n\t\(footprint ', board.read_text())) == 62 * 2 + 22 + 13 + 32       # 穴: 外周 20・中 8・予備 2・蓋 2


def test_the_paste_check_notices_paste_on_a_side_land_and_a_part_on_the_back(tmp_path, unrouted):
    src = (PROJECT.root / "pcb" / "unrouted" / "cckb-click_main.kicad_pcb").read_text()
    i = src.index('(property "Reference" "SWA16"')
    j = src.index('(layers "F.Cu" "F.Mask")', i)
    f = tmp_path / "b.kicad_pcb"
    f.write_text(src[:j] + '(layers "F.Cu" "F.Paste" "F.Mask")' + src[j + len('(layers "F.Cu" "F.Mask")'):])
    assert any("SWA16" in b for b in paste_and_side_problems(f))


def placement_problems(geo, lay=LAY):
    """部品（コートヤード）が、柱・中の押さえの足・外周の壁・ねじの穴に当たらない。角の部品が図面どおりの向き。"""
    out = []
    s = lay.s
    posts = lay.post_rects()
    key_area = lay.key_area
    feet = [(c, s.HOLDDOWN_D / 2) for _, c, kind in lay.screws() if kind == "holddown"]
    holes = [(c, s.SCREW_HOLE_D / 2 + 0.2) for _, c, kind in lay.screws() if kind != "cover"]
    # 蓋のねじ穴は電池クリップのコートヤード（外接の矩形）の中にある。クリップの板の端が基板の 3.7 上に張り出すだけの所なので、
    # 物（＋のランド・止めに当てた電池）で見る: test_the_corner_parts_face_the_way_the_case_needs
    cover = [(c, s.SCREW_HOLE_D / 2 + 0.2) for _, c, kind in lay.screws() if kind == "cover"]
    corners = [lay.corner("left"), lay.corner("right")]
    for f in geo["footprints"]:
        box = f["courtyard"].get("front")
        if box is None:
            if not re.fullmatch(r"H\d+", f["ref"]):
                out.append(f"{f['ref']}: 表のコートヤードが無い")
            continue
        if re.fullmatch(r"H\d+|TP_VSW", f["ref"]):          # 穴と、試験用のランド（銅だけ。リブの下でよい）
            continue
        if re.fullmatch(r"SW[AB]?\d+", f["ref"]):
            # スイッチは**ランド**で見る（コートヤードの余白 0.15 は決まりごとで、物ではない。本体はランドより 1.15 内側）
            box = lay.land(f["x"], f["y"])
        for p in posts:
            if L.rect_gap(box, p) < 0.2:
                out.append(f"{f['ref']} が柱 {p} に {L.rect_gap(box, p):.2f}")
        for c, r in feet + holes + ([] if f["ref"] == "BT1" else cover):
            if L.circle_rect_gap(c, r, box) < 0.2:
                out.append(f"{f['ref']} が足・ねじの穴 {c} に {L.circle_rect_gap(c, r, box):.2f}")
        in_corner = any(L.rect_gap(box, c) < 0 for c in corners)
        if not in_corner and not (key_area[0] <= box[0] and box[2] <= key_area[2] and key_area[1] <= box[1] and box[3] <= key_area[3]):
            out.append(f"{f['ref']} がキー領域の外（外周の壁の下）")
        if not in_corner:
            # キーの穴の中に収まる（リブの下に部品を置かない）
            if not any(h[0] <= box[0] and box[2] <= h[2] and h[1] <= box[1] and box[3] <= h[3] for h in map(lay.hole, lay.keys)):
                out.append(f"{f['ref']} のコートヤード {box} がどのキーの穴にも収まらない")
    return out


def test_no_part_sits_under_a_post_a_foot_a_rib_or_the_wall(unrouted):
    assert placement_problems(unrouted) == []
    assert len(LAY.posts()) > 100


def test_the_placement_check_notices_a_part_under_a_post_and_under_a_rib(unrouted):
    geo = copy.deepcopy(unrouted)
    d = next(f for f in geo["footprints"] if f["ref"] == "D20")
    b = d["courtyard"]["front"]
    d["courtyard"]["front"] = [b[0], b[1] - 2.2, b[2], b[3] - 2.2]
    assert any("D20" in x for x in placement_problems(geo))
    geo = copy.deepcopy(unrouted)
    u = next(f for f in geo["footprints"] if f["ref"] == "U1")
    b = u["courtyard"]["front"]
    u["courtyard"]["front"] = [b[0] + 10, b[1], b[2] + 10, b[3]]
    assert any("U1" in x for x in placement_problems(geo))


def test_the_corner_parts_face_the_way_the_case_needs(unrouted):
    pads = {(p["ref"], p["num"], round(p["x"], 3), round(p["y"], 3)): p for p in unrouted["pads"]}
    # 電池クリップ: ＋のランドが左右・口は手前（止めが奥）→ 電池の中心 = 原点
    plus = sorted(k[2] for k in pads if k[0] == "BT1" and k[1] == "1")
    assert plus == pytest.approx([S.CLIP_AT[0] - 10.025, S.CLIP_AT[0] + 10.025])
    # 電池は**止めに当たる所**に座る（図面 MY-CP-0247: 止めから口 15.10・板厚 0.25。止めの外面は足跡で軸から 8.76）:
    # 中心は軸から 8.76 − 0.25 − 8.0 = 0.51 奥。手前の縁は枠の外面から 1.71
    assert LAY.cell()[0][1] - S.CLIP_AT[1] == pytest.approx(8.76 - 0.25 - 16.0 / 2) and S.CLIP_SHEET_T == 0.25
    assert LAY.cell_recess() == pytest.approx(1.71)
    # 表の銅を置かない範囲の奥の端は、止めの外面から 1.0（止めに当てた電池の缶の縁から 1.25）
    assert LAY.cell_keepout()[3] - (LAY.cell()[0][1] + LAY.cell()[1]) == pytest.approx(1.25)
    # 蓋のねじ穴（電池クリップのコートヤードの中）: ＋のランドから 1.0 以上・止めに当てた電池の缶の縁から 1.0 以上
    (cx, cy), r = LAY.cell()
    cover = [c for _, c, kind in LAY.screws() if kind == "cover"]
    assert len(cover) == 2
    for c in cover:
        assert min(L.circle_rect_gap(c, S.SCREW_HOLE_D / 2, b) for b in LAY.clip_pads()) >= 1.0
        assert math.dist(c, (cx, cy)) - r - S.SCREW_HOLE_D / 2 == pytest.approx(1.02, abs=0.01)
    # 電源スイッチ: 端子は本体の左（内側）・つまみは右。端子 3 が奥。**つまみの先は、入でも切でも基板の縁の 0.30 内側・枠の外面の 0.60 内側**
    # （外へ出ない。利用者の決定 2026-10-04）。本体は基板の縁から 1.75（JLC の規約の 2.5 は満たさない）。本体の位置は、板の上の突起の穴（本体の中心線）から取る
    pins = {k[1]: (k[2], k[3]) for k in pads if k[0] == "SW_PWR" and k[1] in "123" and k[1]}
    body = LAY.psw_body()
    assert all(x < body[0] for x, _ in pins.values()) and pins["3"][1] > S.PSW_AT[1] > pins["1"][1]
    pegs = [p for p in unrouted["pads"] if p["ref"] == "SW_PWR" and p["npth"]]
    assert len(pegs) == 2 and all(p["x"] == pytest.approx((body[0] + body[2]) / 2) for p in pegs)
    body_edge = pegs[0]["x"] + MSK_DRAWING["body"][1] / 2
    assert LAY.pcb[2] - body_edge == pytest.approx(S.PSW_BODY_TO_EDGE) and S.PSW_BODY_TO_EDGE == 1.75 and body[2] == pytest.approx(body_edge)
    for pos in (1, -1):
        tip = LAY.psw_knob(pos)[2]
        assert tip == pytest.approx(body_edge + MSK_DRAWING["knob"][1])
        assert LAY.pcb[2] - tip == pytest.approx(S.PSW_TIP_INSIDE) and S.PSW_TIP_INSIDE == 0.3 and LAY.frame[2] - tip == pytest.approx(0.60)
    assert LAY.psw_knob_sweep()[3] - LAY.psw_knob_sweep()[1] == pytest.approx(S.PSW_TRAVEL + S.PSW_KNOB[0])
    assert (S.PSW_TRAVEL_TOL, S.PSW_FORCE_MAX) == (0.2, pytest.approx(0.250 * 9.8, abs=0.01))       # 承認書 4.2・4.1（150 ± 100 gf）
    # 壊すと落ちる: 最初の位置（1.0 外）なら、本体は縁から 0.75・つまみは枠の外へ 0.40
    assert LAY.pcb[2] - (body_edge + 1.0) == pytest.approx(0.75) and LAY.frame[2] - (LAY.psw_knob(1)[2] + 1.0) == pytest.approx(-0.40)
    # XIAO: USB の口が基板の左の縁・枠の外面から USB_RECESS
    assert LAY.usb_shell()[0] == pytest.approx(LAY.frame[0] + S.USB_RECESS) and LAY.usb_shell()[0] == pytest.approx(LAY.pcb[0])
    d = {k[1]: (k[2], k[3]) for k in pads if k[0] == "U_MCU" and not pads[k]["back"]}
    assert d["D0"][1] < S.XIAO_AT[1] < d["5V"][1] and d["D0"][0] < d["D6"][0]


def test_the_screws_sit_mid_key_on_the_wall_and_the_feet_hang_on_a_post():
    f = LAY.frame
    edge_keys = {"back": [k for k in LAY.keys if k.r == 0], "front": [k for k in LAY.keys if k.r == 4]}
    n = dict(perimeter=0, holddown=0, spare=0, cover=0)
    for ref, (x, y), kind in LAY.screws():
        n[kind] += 1
        if kind == "holddown":
            post = LAY.holddown_foot((x, y))                          # 無ければ落ちる
            k = next(k for k in LAY.keys if LAY.hole(k)[0] < x < LAY.hole(k)[2] and abs(k.y - y) < 1e-6)
            assert k.w == 1.0 and abs(post[0] - k.x0) < 1e-6
            assert L.circle_rect_gap((x, y), S.HOLDDOWN_D / 2, LAY.land(k.x, k.y)) >= 0.4
            assert abs(k.x0 - LAY.seam_x(k.y)) > UNIT / 2                # 継ぎ目の列ではない
            continue
        d = min(x - f[0], f[2] - x, y - f[1], f[3] - y)
        assert d == pytest.approx(S.SCREW_FROM_EDGE), ref
        on_x = min(y - f[1], f[3] - y) == pytest.approx(S.SCREW_FROM_EDGE)
        in_corner = any(L.rect_gap((x, y, x, y), c) < 6 for c in (LAY.corner("left"), LAY.corner("right")))
        if not in_corner:
            # 壁を厚くする所（ねじ ± SCREW_BOSS_HALF）が、つば（穴の角から TAB_LEN ＋ TAB_REACH ＋ POCKET_CLEAR）の来ない範囲にある
            if on_x:
                k = min(edge_keys["back" if y > 0 else "front"], key=lambda k: abs(k.x - x))
                lo, hi, v = LAY.hole(k)[0], LAY.hole(k)[2], x
            else:
                k = min((k for k in LAY.keys if (k.x < 0) == (x < 0)), key=lambda k: (abs(k.y - y), -abs(k.x)))
                lo, hi, v = LAY.hole(k)[1], LAY.hole(k)[3], y
            free = S.TAB_LEN + S.POCKET_CLEAR + S.CAP_CLEAR      # つばは辺に沿って TAB_LEN。くぼみの隙と、キャップが横にずれる分
            half = LAY.boss_half((x, y))
            assert half == (S.SCREW_BOSS_HALF if on_x or k.w < 1.5 else S.SCREW_BOSS_HALF_SIDE), ref
            assert lo + free <= v - half + 1e-9 and v + half <= hi - free + 1e-9, f"{ref} の壁の厚い所がつばに掛かる"
            if not on_x and k.w >= 1.5:                               # 空きランドの上端から 0.3
                assert y - half - (k.y + 2.5) == pytest.approx(0.1) and y - k.y == pytest.approx(S.SIDE_SCREW_DY)
            if kind == "spare":                                      # 予備は手前の継ぎ目の両側・継ぎ目から 7 以内
                assert on_x and y < 0 and abs(x - S.FRAME_SPLIT[-1]) <= 7.0, ref
    assert n == dict(perimeter=20, holddown=8, spare=2, cover=2) and S.MOUNTS == {"main": []}
    # 蓋のねじ穴: 電池の中心から左右に同じだけ・電池の口の中（枠に下穴は無い）
    cov = sorted(c for _, c, kind in LAY.screws() if kind == "cover")
    assert [c[0] - S.CLIP_AT[0] for c in cov] == pytest.approx([-7.0, 7.0]) and all(LAY.cover()["x0"] < c[0] < LAY.cover()["x1"] for c in cov)
    assert not any(kind == "cover" for _, _, kind in LAY.wall_screws())
    assert sorted(x - S.FRAME_SPLIT[-1] > 0 for _, (x, _), kind in LAY.screws() if kind == "spare") == [False, True]
    # 穴の縁から基板の縁まで 1.0（foundry.pcb の下限。外へ寄せられるのはここまで）・頭 φ4.0 は基板の縁の内側
    edge = S.SCREW_FROM_EDGE - S.PCB_INSET_X
    assert edge - S.SCREW_HOLE_D / 2 == pytest.approx(1.0) and edge - S.SCREW_HEAD_D / 2 >= 0.1 - 1e-9
    # 下穴は φ1.6（利用者が試し刷り v2 で締めて決めた。φ1.8 は空回りした）。内側の肉（下穴の縁からキーの穴の縁まで）は 0.8・外側は 1.6
    wall = S.PLATE_MARGIN_Y + LAY.rib() / 2
    assert S.SCREW_PILOT_D == 1.6 and LAY.pilot() == (1.6, 2.8)
    assert wall - S.SCREW_FROM_EDGE - S.SCREW_PILOT_D / 2 == pytest.approx(0.8) and S.SCREW_FROM_EDGE - S.SCREW_PILOT_D / 2 == pytest.approx(1.6)
    # 継ぎ目の両側に、奥と手前で 1 本ずつ（継ぎ目から 1 キー以内）
    for y, sx in ((S.SCREWS_PERIMETER[0][1], S.FRAME_SPLIT[0]), (S.SCREWS_PERIMETER[9][1], S.FRAME_SPLIT[-1])):
        xs = sorted(p[0] - sx for p in S.SCREWS_PERIMETER if p[1] == y)
        assert max(v for v in xs if v < 0) > -UNIT * 1.2 and min(v for v in xs if v > 0) < UNIT * 1.2


def test_the_new_pin_maps_cover_every_pad_of_their_footprints():
    for kind, lib, name in (("coin_clip_my1632", "cckb-click.pretty", "BAT_MY-1632-03-R"),
                            ("slide_msk12c02", "cckb-click.pretty", "SW_MSK12C02"),
                            ("keyswitch", "keyswitch.pretty", mech.SKRA_FP)):
        nums = {p[0] for p in fp_pads(lib, name) if p[0]}
        assert nums == {v[0] for v in pinmap.PINS[kind].values()}, kind


def test_the_stack_is_8_1_thick_and_only_the_screw_heads_go_below_the_board():
    z = LAY.z()
    assert z["total"] == pytest.approx(8.1) and z["cap_top"] == pytest.approx(6.0) and z["frame_top"] == pytest.approx(5.0)
    assert z["head_below_sheet"] <= 0.1 + 1e-9                    # 頭 0.5 ± 0.1 はシート 0.5 の厚さの中（公差の端で 0.1 出る）
    # 外周のねじ: 先は下穴の中・くぼみ（3.0 から）に届かない。掛かりは 2.4（M2 の 6 山）
    assert z["screw_tip"] < z["pilot_top"] < S.FRAME_UNDER and z["screw_grip"] == pytest.approx(2.4)
    # 中の押さえ: ねじの先は、縁を押し切ったキャップの下面（公差の端で 1.62）より低い。掛かりは 1.4
    assert z["holddown_tip"] <= 1.56 + 1e-9 and z["holddown_top"] <= 1.4 + 1e-9 and z["holddown_grip"] == pytest.approx(1.4)
    # 角の部品は枠の上面より低い
    assert max(z["xiao_body_top"], z["usb_top"], z["clip_top"], z["cell_top"], z["psw_top"]) < z["frame_top"]
    assert LAY.pilot()[0] < S.SCREW_D and LAY.seam_offsets() == (pytest.approx(1.0), pytest.approx(1.0 + S.FRAME_SEAM_GAP))
    assert LAY.col_via(LAY.keys[0]) == pytest.approx((LAY.keys[0].x + 5.2, LAY.keys[0].y + 2.0))
