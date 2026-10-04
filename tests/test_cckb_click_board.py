"""cckb-click の**配線して塗った板**（projects/cckb-click/pcb/cckb-click_main.kicad_pcb・発注に使う板）の検査。

相手にするのは KiCad が読んだ板そのもの（projects/cckb/tools/board_facts.py が pcbnew で書き出す事実）と、外の事実
（回路の宣言・ファームの overlay・ZMK の gpio_595 のビット順・JLC の部品データ・kicad-cli の DRC・発注道具の出力）。
**生成器の意図とは比べない。**各検査の下に「故意に壊すと落ちる」検査を置く（壊すのは事実の写しか、板の写し）。

CCKB の監査で見つかった型（.superpowers/sdd/cckb-autonomy/audit-v2-findings.md・projects/cckb/docs/open-gaps.md）を、この板でも見る:
ネットの無いパッド・短い長円の穴・パッドの中のビア・金属の下の銅・GND の細い帯の先・XIAO の下の表の銅・アンテナの禁止域。
"""

import copy
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, require
from foundry import drc, paths
from foundry.pcb_rules import JLC
from foundry.project import load

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
import click_circuit as circuit  # noqa: E402
import click_layout as L  # noqa: E402
from test_cckb_click_pcb import EE as EE_CLICK  # noqa: E402
from test_cckb_click_pcb import EE_UNIT, netlist_problems  # noqa: E402

PROJECT = load("cckb-click")
S = PROJECT.spec
LAY = L.Layout(PROJECT)
PCB = PROJECT.root / "pcb"
BOARD = PCB / "cckb-click_main.kicad_pcb"
UNROUTED = PCB / "unrouted" / "cckb-click_main.kicad_pcb"
SHIELD = ROOT / "config" / "boards" / "shields" / "cckb_click"
CCKB_SHIELD = ROOT / "config" / "boards" / "shields" / "cckb"
FT_PLUGIN = Path.home() / "Documents/KiCad/10.0/3rdparty/plugins"
N_JLC = 62 + 62 + 2 + 2 + 2 + 1 + 1 + 1          # スイッチ・ダイオード・595・パスコン・抵抗・D_PWR・電池クリップ・電源スイッチ
# JLC が実装しない物（BOM・CPL に出さない）: 空きランド・XIAO・ねじの穴・試験用のランド・載せないコンデンサのランド。**名前を列挙する**
NOT_JLC = r"SW[AB]\d+|U_MCU|H\d+|TP_VSW|C_BAT|C_3V3"
DRY = r"SW[AB]\d+|U_MCU|TP_VSW|C_BAT|C_3V3"       # はんだを載せない物（穴はパッドが無い）
CLICK_FACTS = ROOT / "projects/cckb-click/tools/click_facts.py"


def control(r, dx=0.0, dy=20.0):
    return (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)


def regions():
    """board_facts に渡す領域 {名前: 引数}。禁止域ごとに、銅のあるはずの対照を並べる（0 しか返さない検査器は 0 を証明しない）。"""
    out = {"antenna": LAY.antenna_keepout(), "antenna_control": control(LAY.antenna_keepout(), dx=30.0, dy=0.0)}
    for n, r in LAY.xiao_exposed().items():
        out[f"xiao_{n}"] = r
    out["cell"] = LAY.cell_keepout()
    s = LAY.antenna_front_strip()                    # アンテナの禁止域の手前の端と行 4 の線の間（線の縁から 0.02 上から）
    out["ant_front"] = (s[0], s[1] + 0.12, s[2], s[3])
    for ref, c, r in LAY.screw_head_keepouts():
        out[f"head_{ref}"] = ("c", c[0], c[1], r - 0.02)
    c0 = LAY.screw_head_keepouts()[0]
    out["head_control"] = ("c", c0[1][0] + 8.0, c0[1][1] - 12.0, c0[2])
    return out


def _arg(r):
    return "c:" + ",".join(str(v) for v in r[1:]) if r[0] == "c" else ",".join(str(v) for v in r)


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    require(paths.KICAD_PYTHON, "板の事実の書き出し")
    out = tmp_path_factory.mktemp("clickboard") / "facts.json"
    r = subprocess.run([paths.KICAD_PYTHON, str(ROOT / "projects/cckb/tools/board_facts.py"), str(BOARD), str(out)]
                       + [_arg(r) for r in regions().values()], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
    f = json.loads(out.read_text())
    f["region"] = {n: f["copper_in"][i]["area"] for i, n in enumerate(regions())}
    return f


def geo_of(facts):
    """netlist_problems が読む形（未配線の板の事実と同じ鍵）に。"""
    return dict(pads=[dict(ref=p["ref"], num=p["num"], net=p["net"]) for p in facts["pads"]],
                footprints=[dict(ref=f["ref"]) for f in facts["footprints"]])


# ---------------------------------------------------------------------------
# (a) 結線と DRC
# ---------------------------------------------------------------------------

def test_every_pad_of_the_routed_board_carries_the_declared_net(facts):
    assert netlist_problems(geo_of(facts)) == []
    assert facts["unconnected"] == 0 and len(facts["tracks"]) > 700


def test_the_netlist_check_notices_a_pad_without_a_net(facts):
    g = geo_of(facts)
    next(p for p in g["pads"] if p["ref"] == "U2" and p["num"] == "3")["net"] = ""
    assert any("U2.3" in b for b in netlist_problems(g))


def board_copy(d):
    for suf in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(BOARD.with_suffix(suf), d / ("b" + suf))
    return d / "b.kicad_pcb"


@pytest.fixture(scope="module")
def drc_record(tmp_path_factory):
    require(paths.KICAD_CLI, "DRC")
    return drc.run(board_copy(tmp_path_factory.mktemp("clickdrc")))


def test_the_routed_board_has_no_drc_violation_nothing_unrouted_and_no_warning(drc_record):
    assert (drc_record["violations"], drc_record["unconnected"]) == (0, 0), drc_record["details"]
    assert drc_record["warnings"] == 0, drc_record["warning_kinds"]
    committed = json.loads(drc.report_path(BOARD).read_text())
    for k in ("violations", "unconnected", "warnings", "warning_kinds"):
        assert committed[k] == drc_record[k], k
    assert getattr(S, "DRC_SEVERITY", None) is None                   # 規則を軽くしていない


def test_the_drc_notices_a_short_on_a_copy(tmp_path):
    require(paths.KICAD_CLI, "DRC")
    b = board_copy(tmp_path)
    t = b.read_text()
    m = re.search(r'\(segment\s*\(start ([\d.]+) ([\d.]+)\)\s*\(end ([\d.]+) ([\d.]+)\)\s*\(width [\d.]+\)\s*\(layer "F.Cu"\)\s*\(net "ROW2"\)', t)
    assert m, "ROW2 の表の線が見つからない"
    x0, y0, x1, y1 = (float(v) for v in m.groups())
    xm = round((x0 + x1) / 2, 3)
    short = (f'\t(segment (start {xm} {y0}) (end {xm} {y0 - 6.0}) (width 0.2) (layer "F.Cu") (net "ROW2")'
             f' (uuid "00000000-0000-4000-8000-00000000c11c"))\n')
    i = t.rindex(")")
    b.write_text(t[:i] + short + t[i:])
    r = drc.run(b)
    assert r["violations"] > 0, r


def test_the_hole_clearance_rule_is_jlcs_and_holes_are_round(facts):
    pro = json.loads(BOARD.with_suffix(".kicad_pro").read_text())
    assert pro["board"]["design_settings"]["rules"]["min_hole_clearance"] == JLC["pth_to_track"]
    # JLC は短い長円（長さ < 幅 × 2）を作れない（CCKB の監査 C 重要 1）。この板の穴は全部丸
    holes = [p for p in facts["pads"] if p["drill"] > 0]
    assert len(holes) >= 28 + 2 + 7 + 3 and not any(p["slot"] for p in holes)
    assert all(p["drill_wh"][0] == p["drill_wh"][1] for p in holes)
    npth = sorted({p["drill"] for p in holes if p["npth"]})
    assert npth == [0.9, S.SCREW_HOLE_D]


# ---------------------------------------------------------------------------
# (b) 発注: 全部表・載せる物だけにはんだ・JLC が置く位置 = 板のパッド
# ---------------------------------------------------------------------------

def side_problems(facts):
    out = []
    n = 0
    for f in facts["footprints"]:
        ref = f["ref"]
        if f["flipped"]:
            out.append(f"{ref} が裏")
        skip = re.fullmatch(NOT_JLC, ref)
        if skip and not (f["exclude_bom"] and f["exclude_pos"]):
            out.append(f"{ref}: JLC が実装しない物が BOM/CPL に載る")
        if not skip:
            n += 1
            if f["exclude_bom"] or f["exclude_pos"]:
                out.append(f"{ref}: BOM/CPL から外れている")
            if not f["fields"].get("LCSC"):
                out.append(f"{ref}: LCSC の番号が無い")
    if n != N_JLC:
        out.append(f"JLC が実装する部品 {n} 個（{N_JLC} のはず）")
    for p in facts["pads"]:
        dry = re.fullmatch(DRY, p["ref"]) or (p["ref"] == "BT1" and p["num"] == "2")
        if dry and p.get("paste"):
            out.append(f"{p['ref']}.{p['num']}: はんだを載せない所に載る")
        if not dry and p["smd"] and not p.get("paste") and not p["npth"]:
            out.append(f"{p['ref']}.{p['num']}: JLC が実装する部品のパッドにはんだが無い")
    return out


def test_everything_is_on_top_and_only_the_jlc_parts_are_in_the_bom(facts):
    assert side_problems(facts) == []


def test_the_side_check_notices_a_side_land_in_the_bom_and_paste_on_the_bare_pad(facts):
    f = copy.deepcopy(facts)
    fp = next(x for x in f["footprints"] if x["ref"] == "SWA43")
    fp["exclude_bom"] = fp["exclude_pos"] = False
    assert any("SWA43" in b for b in side_problems(f))
    f = copy.deepcopy(facts)
    next(p for p in f["pads"] if p["ref"] == "BT1" and p["num"] == "2" and p["smd"] is False and not p["drill"])["paste"] = True
    assert any("BT1.2" in b for b in side_problems(f))


def ee_parts():
    old = json.loads((ROOT / "tests/fixtures/easyeda/footprints.json").read_text())["parts"]
    out = {c: dict(head=p["head"], pads=[[n] + v for n, v in p["pads"].items()]) for c, p in old.items()}
    out.update({c: dict(head=p["head"], pads=p["pads"], marks=p.get("marks", {})) for c, p in EE_CLICK.items()})
    return out


# JLC の部品データのパッドの番号 → こちらの足跡の番号（違う物だけ）。スイッチは JLC が端子 1〜4・こちらは奥の 2 つが 1・手前の 2 つが 2
EE_NUMBER = {"C202383": {"1": "1", "2": "1", "3": "2", "4": "2"}}


def cpl_misplacements(rows, lcsc_of, facts, ee, tol=0.15):
    """JLC は CPL の座標に自分の部品データ（EasyEDA）の原点を置き、回転 R をかける（表）。その部品データのパッドごとに、
    板の同じ部品の**同じ番号の**パッド（はんだの載る物）のいちばん近い中心までを測る（番号を見ないと、180° 回った IC や
    逆向きのダイオードが、パッドの位置の集まりは同じなので通ってしまう）。[(参照名, 最大のずれ)]"""
    ox, oy = facts["origin"]
    out = []
    for r in rows:
        ref = r["Designator"]
        part = ee[lcsc_of[ref]]
        hx, hy = part["head"]
        mid = (float(r["Mid X"]), float(r["Mid Y"]))
        a = math.radians(float(r["Rotation"]))
        want = []
        for n, x, y, _, _ in part["pads"]:
            px, py = (x - hx) * EE_UNIT, -(y - hy) * EE_UNIT
            n = EE_NUMBER.get(lcsc_of[ref], {}).get(n, n)
            want.append((n, (mid[0] + px * math.cos(a) - py * math.sin(a), mid[1] + px * math.sin(a) + py * math.cos(a))))
        have = [(p["num"], (p["pos"][0] + ox, p["pos"][1] - oy)) for p in facts["pads"]
                if p["ref"] == ref and p["num"] and not p["npth"] and not p["drill"]]
        if len(have) != len(want) or r["Layer"] != "top" or {n for n, _ in have} != {n for n, _ in want}:
            out.append((ref, math.inf))
            continue
        worst = max(min(math.dist(w, h) for m, h in have if m == n) for n, w in want)
        # 向きの印（パッドが対称で、180° 回っても同じ番号のパッドに載る部品）: JLC の部品データの印が、板の上のあるべき所に来るか
        for name, (x, y) in part.get("marks", {}).items():
            px, py = (x - hx) * EE_UNIT, -(y - hy) * EE_UNIT
            got = (mid[0] + px * math.cos(a) - py * math.sin(a), mid[1] + px * math.sin(a) + py * math.cos(a))
            wx, wy = ORIENT_MARKS[ref][name]
            worst = max(worst, math.dist(got, (wx + ox, wy - oy)))
        if worst > tol:
            out.append((ref, round(worst, 3)))
    return out


def orient_marks():
    """部品の向きの印が板の上で来るべき所 {参照名: {印: (x, y)}}（CAD）。電池クリップ: 折り返しの止めが奥・口が手前
    （枠の電池の口と指の切り欠きは手前の壁にある）。"""
    b = LAY.clip_body()
    x = S.CLIP_AT[0]
    return {"BT1": {"stop": (x, b[3]), "mouth": (x, b[1])}}


ORIENT_MARKS = orient_marks()


@pytest.fixture(scope="module")
def production(tmp_path_factory):
    """**実際に発注する道具**（Fabrication Toolkit）を板の写しに通した BOM と CPL。"""
    require(paths.KICAD_PYTHON, "Fabrication Toolkit")
    require(FT_PLUGIN / "com_github_bennymeg_JLC-Plugin-for-KiCad", "Fabrication Toolkit")
    d = tmp_path_factory.mktemp("clickft")
    b = board_copy(d)
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "com_github_bennymeg_JLC-Plugin-for-KiCad.cli", "-p", str(b), "-t", "-nI", "-nB"],
                       cwd=FT_PLUGIN, capture_output=True, text=True, timeout=900)
    prod = d / "production"
    assert (prod / "positions.csv").exists(), r.stdout[-2000:] + r.stderr[-2000:]
    rows = list(csv.DictReader((prod / "positions.csv").open(encoding="utf-8-sig")))
    bom = list(csv.DictReader((prod / "bom.csv").open(encoding="utf-8-sig")))
    return rows, bom, prod


def test_jlc_places_every_part_of_the_cpl_on_its_pads(production, facts):
    rows, bom, prod = production
    lcsc_of = {d.strip(): b["LCSC Part #"] for b in bom for d in b["Designator"].split(",")}
    refs = sorted(r["Designator"] for r in rows)
    assert len(rows) == N_JLC and set(lcsc_of) == set(refs) and all(r["Layer"] == "top" for r in rows)
    assert not [r for r in refs if re.fullmatch(NOT_JLC, r)]
    count = {}
    for c in lcsc_of.values():
        count[c] = count.get(c, 0) + 1
    assert count == {"C202383": 62, "C54110": 63, "C52287685": 2, "C49678": 2, "C17514": 2, "C20606805": 1, "C431540": 1}
    assert cpl_misplacements(rows, lcsc_of, facts, ee_parts()) == []
    # ドリルのファイルに長円が無い（JLC へ行く物そのもの）
    drl = "".join(p.read_text(errors="ignore") for p in prod.rglob("*.drl")) if list(prod.rglob("*.drl")) else None
    if drl is not None:
        assert "G85" not in drl


def test_the_battery_clip_faces_its_mouth_to_the_front_in_the_cpl(production, facts):
    """B 軽微 1: 電池クリップの ＋のランドは左右対称で番号も同じ。180° 回って置かれても、パッドの検査は通ってしまう
    （口が奥を向き、電池が入らない）。JLC の部品データの外形（止めと口）で向きを見る。"""
    rows, bom, _ = production
    lcsc_of = {d.strip(): b["LCSC Part #"] for b in bom for d in b["Designator"].split(",")}
    ee = ee_parts()
    assert set(ee[lcsc_of["BT1"]]["marks"]) == {"stop", "mouth"}
    assert cpl_misplacements(rows, lcsc_of, facts, ee) == []
    # 外の事実と図面: 止めは原点から 8.76・口は 6.35（図面の 15.10 = 8.76 ＋ 6.34）
    hx, hy = ee[lcsc_of["BT1"]]["head"]
    m = ee[lcsc_of["BT1"]]["marks"]
    assert (hy - m["stop"][1]) * EE_UNIT == pytest.approx(S.CLIP_STOP, abs=0.01) and (m["mouth"][1] - hy) * EE_UNIT == pytest.approx(S.CLIP_MOUTH, abs=0.01)
    # 口は手前の壁の側・電池の口（枠の切り欠き）と同じ x
    assert ORIENT_MARKS["BT1"]["mouth"][1] < S.CLIP_AT[1] < ORIENT_MARKS["BT1"]["stop"][1] and LAY.cell()[0][0] == S.CLIP_AT[0]
    # 壊すと落ちる: 180° 回った電池クリップ（パッドだけなら通る）
    turned = copy.deepcopy(rows)
    r = next(r for r in turned if r["Designator"] == "BT1")
    r["Rotation"] = str((float(r["Rotation"]) + 180) % 360)
    assert [m_[0] for m_ in cpl_misplacements(turned, lcsc_of, facts, ee)] == ["BT1"]
    no_marks = {c: dict(p, marks={}) for c, p in ee.items()}
    assert cpl_misplacements(turned, lcsc_of, facts, no_marks) == []          # 印が無ければ見つけられない（この検査が要る理由）


@pytest.mark.parametrize("ref, drot, dx", [("SW_PWR", 180, 0.0), ("BT1", 0, 0.5), ("D1", 90, 0.0), ("U1", 180, 0.0), ("SW30", 0, 0.3)])
def test_the_cpl_check_notices_a_turned_or_shifted_part(production, facts, ref, drot, dx):
    rows, bom, _ = production
    lcsc_of = {d.strip(): b["LCSC Part #"] for b in bom for d in b["Designator"].split(",")}
    rows = copy.deepcopy(rows)
    r = next(r for r in rows if r["Designator"] == ref)
    r["Rotation"] = str((float(r["Rotation"]) + drot) % 360)
    r["Mid X"] = str(float(r["Mid X"]) + dx)
    assert [m[0] for m in cpl_misplacements(rows, lcsc_of, facts, ee_parts())] == [ref]


# ---------------------------------------------------------------------------
# (c) 禁止域: 置いただけでなく、塗った後に銅が無い
# ---------------------------------------------------------------------------

def keepout_problems(facts):
    reg = facts["region"]
    out = []
    for layer in ("F.Cu", "B.Cu"):
        if reg["antenna"][layer] > 1e-6:
            out.append(f"アンテナの禁止域の {layer} に銅 {reg['antenna'][layer]}")
    if min(reg["antenna_control"].values()) < 5.0:
        out.append("アンテナの対照に銅が無い（検査器が数えていない）")
    if reg["ant_front"]["B.Cu"] > 1e-6:
        out.append(f"アンテナの禁止域の手前の細い帯（裏）に銅 {reg['ant_front']['B.Cu']}")
    for n in LAY.xiao_exposed():
        if reg[f"xiao_{n}"]["F.Cu"] > 1e-6:
            out.append(f"XIAO の裏の {n} の下の表に銅 {reg[f'xiao_{n}']['F.Cu']}")
    for ref, _, _ in LAY.screw_head_keepouts():
        if reg[f"head_{ref}"]["B.Cu"] > 1e-6:
            out.append(f"ねじの頭 {ref} の下の裏に銅 {reg[f'head_{ref}']['B.Cu']}")
    if reg["head_control"]["B.Cu"] < 5.0:
        out.append("ねじの頭の対照に銅が無い")
    # 電池の下と抜き差しの道: 表の銅は −の裸の銅と、＋のランドの内側の端だけ
    k = LAY.cell_keepout()
    pads = 0.0
    for p in facts["pads"]:
        if p["ref"] == "BT1" and not p["drill"]:
            b = p["box"]
            w, h = min(b[2], k[2]) - max(b[0], k[0]), min(b[3], k[3]) - max(b[1], k[1])
            if w > 0 and h > 0:
                pads += math.pi * (S.CLIP_NEG_PAD_D / 2) ** 2 if p["num"] == "2" else w * h
    if abs(reg["cell"]["F.Cu"] - pads) > 0.3:
        out.append(f"電池の下の表の銅 {reg['cell']['F.Cu']:.2f}（電池のパッドだけなら {pads:.2f}）")
    return out


def test_no_copper_where_the_antenna_the_xiao_pads_the_screw_heads_and_the_cell_are(facts):
    assert keepout_problems(facts) == []
    names = {z["name"] for z in facts["zones"] if z["rule"]}
    assert names == {"ANTENNA_KEEPOUT", "XIAO_UNDERSIDE", "EDGE_KEEPOUT", "SCREW_HEAD_KEEPOUT", "CELL_KEEPOUT", "SW_BODY_KEEPOUT", "FANOUT_NO_FILL",
                     "XIAO_BACK_NO_FILL", "ANT_FRONT_NO_FILL", "IC_BAND", "TP_VIA_KEEPOUT"}
    assert sum(1 for z in facts["zones"] if z["name"] == "SCREW_HEAD_KEEPOUT") == 32          # 外周 20 ＋ 中 8 ＋ 予備 2 ＋ 蓋 2
    assert sum(1 for z in facts["zones"] if z["name"] == "SW_BODY_KEEPOUT") == 84


def test_the_keepout_check_notices_copper(facts):
    for key, layer, word in (("antenna", "B.Cu", "アンテナ"), ("xiao_pad22", "F.Cu", "pad22"), ("head_H3", "B.Cu", "H3"), ("cell", "F.Cu", "電池"),
                             ("ant_front", "B.Cu", "細い帯")):
        f = copy.deepcopy(facts)
        f["region"][key][layer] += 1.0
        assert any(word in b for b in keepout_problems(f)), key


def via_problems(facts):
    """ビアが、スイッチの本体の下（Alps の仕様書 10.3(4)）・パッドの中（はんだを吸う）・電池の下に無い。"""
    out = []
    bodies = [(ref, LAY.switch_body(x, y)) for ref, x, y, _ in LAY.switch_sites()]
    k = LAY.cell_keepout()
    smd = [p for p in facts["pads"] if p["smd"]]
    for v in facts["vias"]:
        x, y = v["pos"]
        r = v["d"] / 2
        for ref, b in bodies:
            if b[0] - r < x < b[2] + r and b[1] - r < y < b[3] + r:
                out.append(f"ビア {v['net']} ({x}, {y}) が {ref} の本体の下")
        if k[0] < x < k[2] and k[1] < y < k[3]:
            out.append(f"ビア {v['net']} ({x}, {y}) が電池の下")
        for p in smd:
            b = p["box"]
            if b[0] - r < x < b[2] + r and b[1] - r < y < b[3] + r:
                out.append(f"ビア {v['net']} ({x}, {y}) が {p['ref']}.{p['num']} のパッドに掛かる")
    return out


def test_no_via_under_a_switch_body_in_a_pad_or_under_the_cell(facts):
    assert via_problems(facts) == []
    assert len(facts["vias"]) > 700


def test_the_via_check_notices_each_kind(facts):
    sw = next(f for f in facts["footprints"] if f["ref"] == "SWB42")
    for pos, word in ((sw["pos"], "本体"), (list(S.CLIP_AT), "電池"),
                      (next(p["pos"] for p in facts["pads"] if p["ref"] == "C_U1" and p["num"] == "2"), "パッド")):
        f = copy.deepcopy(facts)
        f["vias"].append(dict(net="GND", pos=list(pos), d=0.6, drill=0.3))
        assert any(word in b for b in via_problems(f)), word


# ---------------------------------------------------------------------------
# (d) GND: 両面のベタ・パッドごとのビア・細い帯の先
# ---------------------------------------------------------------------------

def test_both_layers_are_poured_and_every_gnd_smd_pad_has_its_own_via(facts):
    area = {z["name"]: z["area"] for z in facts["zones"] if not z["rule"]}
    board = (LAY.pcb[2] - LAY.pcb[0]) * (LAY.pcb[3] - LAY.pcb[1])
    assert area["GND_F"]["F.Cu"] > 0.6 * board and area["GND_B"]["B.Cu"] > 0.8 * board, area
    vias = [v["pos"] for v in facts["vias"] if v["net"] == "GND"]
    stubs = [(t["a"], t["b"]) for t in facts["tracks"] if t["net"] == "GND"]
    gnd = [p for p in facts["pads"] if p["net"] == "GND" and p["smd"]]
    assert len(gnd) == 2 + 1 + 4 + 1 + 4 + 2        # パスコン 2・R_LO・595 の GND と OE ×2・XIAO・電源スイッチの枠 4・載せないコンデンサのランド 2
    for p in gnd:
        ends = [b if math.dist(a, p["pos"]) < 1e-3 else a for a, b in stubs if min(math.dist(a, p["pos"]), math.dist(b, p["pos"])) < 1e-3]
        assert any(min(math.dist(e, v) for v in vias) < 1e-3 for e in ends), f"{p['ref']}.{p['num']} にスタブとビアが無い"
    thermal = {(p["ref"], p["num"]) for p in facts["pads"] if p["thermal"]}
    assert thermal == {(r, n) for r, nums in S.THERMAL_PADS.items() for n in nums}


def gnd_far(facts, step=0.5, skip=None):
    """GND のベタの上で、最寄りの GND のビア（か GND のスルーホールのパッド）までの**銅の上の道のり**がいちばん遠い所。
    {層: (道のり, (x, y))}。ベタを step の格子に落として、ビアのある升から幅優先で広げる（斜めは √2）。
    細い帯の先にビアが無いと、そこが 2.4 GHz で共振する棒になる（CCKB の 2 回目の V2 監査 D-1: 33 mm）。"""
    import heapq

    import numpy as np
    from matplotlib.path import Path as MPath

    x0, y0, x1, y1 = LAY.pcb
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    xs = x0 + (np.arange(nx) + 0.5) * step
    ys = y0 + (np.arange(ny) + 0.5) * step
    gx, gy = np.meshgrid(xs, ys)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    seeds = [v["pos"] for v in facts["vias"] if v["net"] == "GND"]
    seeds += [p["pos"] for p in facts["pads"] if p["net"] == "GND" and p["drill"] and not p["npth"]]
    out = {}
    for layer, islands in facts["gnd_fill"].items():
        mask = np.zeros(len(pts), dtype=bool)
        for isl in islands:
            inside = MPath(isl["outline"]).contains_points(pts)
            for h in isl["holes"]:
                inside &= ~MPath(h).contains_points(pts)
            mask |= inside
        mask = mask.reshape(ny, nx)
        dist = np.full((ny, nx), np.inf)
        heap = []
        for sx, sy in seeds:
            i, j = int((sy - y0) / step), int((sx - x0) / step)
            if 0 <= i < ny and 0 <= j < nx:
                dist[i, j] = 0.0
                heap.append((0.0, i, j))
        heapq.heapify(heap)
        while heap:
            d, i, j = heapq.heappop(heap)
            if d > dist[i, j]:
                continue
            for di, dj, w in ((1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)):
                a, b = i + di, j + dj
                if 0 <= a < ny and 0 <= b < nx and mask[a, b] and d + w * step < dist[a, b]:
                    dist[a, b] = d + w * step
                    heapq.heappush(heap, (d + w * step, a, b))
        if skip is not None:                      # この矩形の中は「いちばん遠い所」の候補から外す（道としては通る）
            inside = ((gx > skip[0]) & (gx < skip[2]) & (gy > skip[1]) & (gy < skip[3]))
            mask = mask & ~inside
        reach = np.where(mask, dist, -1.0)
        k = int(np.argmax(np.where(np.isinf(reach), -1.0, reach)))
        cut = int((mask & np.isinf(dist)).sum())
        out[layer] = (float(reach.ravel()[k]), (float(pts[k][0]), float(pts[k][1])), cut)
    return out


# mm。銅の上の道のり。FR-4 の上の 2.4 GHz の 1/4 波長（約 17）より短く。
# CCKB は、ビアを足せない 1 か所で 10.3 を記録して受け入れた（projects/cckb/docs/open-gaps.md P14）。
# **595 のいるキー（左 Shift）の中も同じ上限で見る**: 前はここだけ 30 まで許していた（Freerouting の引き方で 13.8〜25.8 と毎回変わった。
# open-gaps P4）。595 の本体の下の帯に線を通さず（spec.IC_BAND）、帯にビアを先に打つようにして、板の全部が上限の内に入った
GND_REACH_MAX = 15.0


def test_no_gnd_strip_ends_far_from_a_via(facts):
    far = gnd_far(facts)
    assert set(far) == {"F.Cu", "B.Cu"}
    for layer, (d, at, cut) in far.items():
        assert d <= GND_REACH_MAX, f"{layer}: ビアから銅の上で {d:.1f} mm の所がある {at}"
        assert cut <= 40, f"{layer}: 格子の上でビアに届かない升が {cut} 個（幅 {0.5} 未満の橋の先）"
    # 595 の本体の下の帯のビア 4 本（配線の前に打つ）がある
    for x in S.IC_BAND_VIA_X:
        assert any(v["net"] == "GND" and math.dist(v["pos"], (x, S.PART_AT["U1"][1])) < 1e-3 for v in facts["vias"]), x


def test_the_reach_check_notices_a_region_without_vias(facts):
    f = copy.deepcopy(facts)
    f["vias"] = [v for v in f["vias"] if not (v["net"] == "GND" and 20 < v["pos"][0] < 75)]
    far = gnd_far(f)
    assert max(d for d, _, _ in far.values()) > GND_REACH_MAX


def test_no_long_gnd_island_hangs_on_a_single_via(facts):
    # ビア 1 本の島は、その 1 本を根元にした棒になる。長さは gnd_far と同じ上限で見る（ビア 0 本の島は配線の道具が消している）
    bad = [i for i in facts["islands"] if i["vias"] <= 1 and max(i["box"][2] - i["box"][0], i["box"][3] - i["box"][1]) > GND_REACH_MAX]
    assert not bad, bad
    assert len(facts["islands"]) >= 2


def gnd_return(facts, a, b, step=0.25, margin=25.0):
    """GND のパッド a から b（(参照名, 番号)）まで、**GND の銅の上だけ**を通るいちばん短い道のり mm（両面。ビアで層を移る）。
    銅 = 塗ったベタ・GND の線・GND のパッド。繋がっていなければ inf。パスコンの戻り（コンデンサの GND → IC の GND のピン）を測る:
    裏のベタが信号の線で切られていると、すぐ隣のピンへ大回りする（1 回目の監査 D 軽微 1: C_U2 → U2 で 31 mm）。"""
    import heapq

    import numpy as np
    from matplotlib.path import Path as MPath

    pa = next(p for p in facts["pads"] if (p["ref"], p["num"]) == a and p["net"] == "GND")
    pb = next(p for p in facts["pads"] if (p["ref"], p["num"]) == b and p["net"] == "GND")
    x0 = min(pa["pos"][0], pb["pos"][0]) - margin
    x1 = max(pa["pos"][0], pb["pos"][0]) + margin
    y0 = min(pa["pos"][1], pb["pos"][1]) - margin
    y1 = max(pa["pos"][1], pb["pos"][1]) + margin
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    gx, gy = np.meshgrid(x0 + (np.arange(nx) + 0.5) * step, y0 + (np.arange(ny) + 0.5) * step)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    layers = ("F.Cu", "B.Cu")
    mask = {}
    for layer in layers:
        m = np.zeros(len(pts), dtype=bool)
        for isl in facts["gnd_fill"].get(layer, []):
            xs = [q[0] for q in isl["outline"]]
            ys = [q[1] for q in isl["outline"]]
            if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
                continue
            inside = MPath(isl["outline"]).contains_points(pts)
            for h in isl["holes"]:
                inside &= ~MPath(h).contains_points(pts)
            m |= inside
        m = m.reshape(ny, nx)
        for tr in facts["tracks"]:
            if tr["net"] == "GND" and tr["layer"] == layer:
                (ax, ay), (bx, by) = tr["a"], tr["b"]
                n = max(2, int(math.dist(tr["a"], tr["b"]) / (step / 2)) + 1)
                for k in range(n):
                    i, j = int((ay + (by - ay) * k / (n - 1) - y0) / step), int((ax + (bx - ax) * k / (n - 1) - x0) / step)
                    if 0 <= i < ny and 0 <= j < nx:
                        m[i, j] = True
        for p in facts["pads"]:
            if p["net"] == "GND" and p["front" if layer == "F.Cu" else "back"]:
                bx0, by0, bx1, by1 = p["box"]
                m |= (gx > bx0) & (gx < bx1) & (gy > by0) & (gy < by1)
        mask[layer] = m
    hop = np.zeros((ny, nx), dtype=bool)
    seeds = [v["pos"] for v in facts["vias"] if v["net"] == "GND"]
    seeds += [p["pos"] for p in facts["pads"] if p["net"] == "GND" and p["drill"] and not p["npth"]]
    for sx, sy in seeds:
        i, j = int((sy - y0) / step), int((sx - x0) / step)
        if 0 <= i < ny and 0 <= j < nx:
            hop[i, j] = True
            for layer in layers:
                mask[layer][i, j] = True

    def cell(p):
        return int((p["pos"][1] - y0) / step), int((p["pos"][0] - x0) / step)

    start, goal = (0,) + cell(pa), cell(pb)
    dist = {start: 0.0}
    heap = [(0.0,) + start]
    board_t = S.PCB_T
    while heap:
        d, L_, i, j = heapq.heappop(heap)
        if d > dist.get((L_, i, j), math.inf):
            continue
        if (i, j) == goal and (pb["front"] if L_ == 0 else pb["back"]):
            return round(d, 2)
        nxt = [(L_, i + di, j + dj, w * step) for di, dj, w in
               ((1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142))]
        if hop[i, j]:
            nxt.append((1 - L_, i, j, board_t))
        for L2, a2, b2, w in nxt:
            if 0 <= a2 < ny and 0 <= b2 < nx and mask[layers[L2]][a2, b2] and d + w < dist.get((L2, a2, b2), math.inf):
                dist[(L2, a2, b2)] = d + w
                heapq.heappush(heap, (d + w, L2, a2, b2))
    return math.inf


# mm。パスコンの GND から、その 595 の GND のピン（8 番）まで、GND の銅の上の道のり。まっすぐなら 11.1（パッドの中心の間）。
# 595 の Q0 の裏の線（595 の下を奥へ抜ける。ピンの並びで決まる）が裏のベタを切るので、その端を回る分は残る: 25 まで
# （監査の時の板は U2 で 31.6・U1 で 23.7。**ベタに任せると、引くたびに 21〜32 と変わった** → GND の線で決まった形に引いた: 23.9 以下。
# **まっすぐの 2 倍は構造として残っている**: open-gaps P4）。OE（13 番・GND へ落としてある）までは 20 まで（監査の時の板は U2 で 39.1）
DECOUPLING_RETURN_MAX = 25.0
DECOUPLING_TO_OE_MAX = 20.0


def test_each_decoupling_capacitor_returns_to_its_ic_without_a_detour(facts):
    for c, u in (("C_U1", "U1"), ("C_U2", "U2")):
        d = gnd_return(facts, (c, "2"), (u, "8"))
        assert d <= DECOUPLING_RETURN_MAX, f"{c} の GND から {u} の 8 番まで GND の銅の上で {d} mm"
        assert d >= math.dist(*[next(p["pos"] for p in facts["pads"] if (p["ref"], p["num"]) == k) for k in ((c, "2"), (u, "8"))]) - 0.5
        d = gnd_return(facts, (c, "2"), (u, "13"))
        assert d <= DECOUPLING_TO_OE_MAX, f"{c} の GND から {u} の 13 番まで {d} mm"
    # 戻りは GND の**線**で引いてある（ベタの形に頼らない）: 595 ごとに、裏に GND の線が 3 区間・合わせて 15 mm 以上
    for u in ("U1", "U2"):
        x, y, _ = S.PART_AT[u]
        back = [t for t in facts["tracks"] if t["net"] == "GND" and t["layer"] == "B.Cu"
                and all(abs(p[0] - x) < 8 and abs(p[1] - y) < 8 for p in (t["a"], t["b"]))]
        assert len(back) == 3 and sum(math.dist(t["a"], t["b"]) for t in back) > 15, (u, back)


def test_the_return_check_notices_a_cut_ground(facts):
    # 595 のまわりのビアを抜くと、層を移れずに遠回りになる（か、届かない）
    f = copy.deepcopy(facts)
    x, y, _ = S.PART_AT["U2"]
    base = gnd_return(facts, ("C_U2", "2"), ("U2", "8"))
    f["vias"] = [v for v in f["vias"] if not (v["net"] == "GND" and abs(v["pos"][0] - x) < 9 and abs(v["pos"][1] - y) < 9)]
    assert gnd_return(f, ("C_U2", "2"), ("U2", "8")) > base + 3.0


def test_no_silk_text_sits_on_a_mask_opening(facts):
    bad = [s for s in facts["silk_to_mask"] if s["dist"] < 0.15]
    assert not bad, bad


# ---------------------------------------------------------------------------
# (e) 配線の形: 決めた形で引いた線が板にある・595 の束が順に並ぶ
# ---------------------------------------------------------------------------

def fanout_problems(facts):
    """595 から列への束（表・段 2 と段 3 の間）: 15 本が別々の高さ・隣どうし FANOUT_PITCH 以上・どの線も段 2 のバスと段 3 のランドの間。"""
    row_y = LAY.rows()[S.FANOUT_ROW]
    lo, hi = row_y + S.FANOUT_Y0, row_y + L.UNIT + S.ROW_BUS_DY
    levels = {}
    for t in facts["tracks"]:
        if t["layer"] == "F.Cu" and re.fullmatch(r"COL\d+", t["net"]) and t["a"][1] == t["b"][1] \
                and lo - 1e-6 <= t["a"][1] < hi and abs(t["a"][0] - t["b"][0]) > 2.0:
            levels.setdefault(t["net"], set()).add(t["a"][1])
    out = []
    if len(levels) != 15 or any(len(v) != 1 for v in levels.values()):
        out.append(f"束の線 {sorted((n, sorted(v)) for n, v in levels.items())}")
        return out
    ys = sorted(next(iter(v)) for v in levels.values())
    if min(b - a for a, b in zip(ys, ys[1:])) < S.FANOUT_PITCH - 1e-6:
        out.append(f"束の線の間隔 {ys}")
    if ys[-1] > hi - 0.4 - 1e-6:
        out.append(f"いちばん奥の線 {ys[-1]} が段 2 のバス {hi} に近い")
    return out


def test_the_fanout_bundle_holds_fifteen_ordered_lines(facts):
    assert fanout_problems(facts) == []


def test_the_fanout_check_notices_a_missing_line(facts):
    f = copy.deepcopy(facts)
    f["tracks"] = [t for t in f["tracks"] if not (t["net"] == "COL12" and t["layer"] == "F.Cu")]
    assert fanout_problems(f)


def test_the_rows_leave_the_xiao_on_the_back_and_nothing_else_is_on_top_under_it(facts):
    b = LAY.xiao()
    under = [t for t in facts["tracks"] if t["layer"] == "F.Cu"
             and any(b[0] < p[0] < b[2] and LAY.pcb[1] < p[1] < b[3] - S.XIAO_PAD_IN - 0.01 for p in (t["a"], t["b"]))]
    assert not under, under[:3]
    for r in range(5):
        assert any(t["net"] == f"ROW{r}" and t["layer"] == "B.Cu" for t in facts["tracks"])


# ---------------------------------------------------------------------------
# (f) ファーム ↔ 基板
# ---------------------------------------------------------------------------
# xiao_ble の xiao_spi: SCK = D8・MOSI = D10。ZMK gpio_595: &shifter n は鎖の先頭（MOSI に繋がる 595）から n//8 個目の Q(n%8)
Q_PAD = {0: "15", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7"}       # TI SCASE93A Table 4-1（QA = 15 番）


def firmware_problems(facts, overlay):
    net = {(p["ref"], p["num"]): p["net"] for p in facts["pads"]}
    out = []
    rows = [int(n) for n in re.findall(r"<&xiao_d (\d+) \(GPIO_ACTIVE_HIGH \| GPIO_PULL_DOWN\)>", overlay)]
    for r, d in enumerate(rows):
        if net[("U_MCU", f"D{d}")] != f"ROW{r}":
            out.append(f"行 {r}: overlay は D{d}・板は {net[('U_MCU', f'D{d}')]}")
    cols = [int(n) for n in re.findall(r"<&shifter (\d+) GPIO_ACTIVE_HIGH>", overlay)]
    chain = ["U1", "U2"]
    if net[("U1", "14")] != net[("U_MCU", "D10")] or net[("U2", "14")] != net[("U1", "9")] or net[("U1", "9")] == "":
        out.append("595 の鎖: U1 の SER が MOSI・U2 の SER が U1 の QH' でない")
    for c, n in enumerate(cols):
        ref, pad = chain[n // 8], Q_PAD[n % 8]
        if net[(ref, pad)] != f"COL{c}":
            out.append(f"列 {c}: overlay は &shifter {n}（{ref} の {pad} 番）・板は {net[(ref, pad)]}")
    cs = int(re.search(r"cs-gpios = <&xiao_d (\d+)", overlay).group(1))
    for ref in chain:
        if net[(ref, "12")] != net[("U_MCU", f"D{cs}")] or net[(ref, "11")] != net[("U_MCU", "D8")]:
            out.append(f"{ref}: RCLK・SRCLK が CS（D{cs}）・SCK（D8）でない")
        if net[(ref, "13")] != "GND" or net[(ref, "10")] != net[("U_MCU", "3V3")] or net[(ref, "16")] != net[("U_MCU", "3V3")]:
            out.append(f"{ref}: OE が GND・SRCLR と VCC が 3V3 でない")
    adc = int(re.search(r"io-channels = <&adc (\d+)>", overlay).group(1))
    if net[("U_MCU", f"D{adc}")] != "VBAT_SENSE" or net[("R_HI", "2")] != "VBAT_SENSE" or net[("R_LO", "1")] != "VBAT_SENSE":
        out.append("電池電圧: ADC のピンと分圧の中点が VBAT_SENSE でない")
    if len(rows) != 5 or len(cols) != 15:
        out.append(f"overlay の行 {len(rows)}・列 {len(cols)}")
    # 電源: 電池 ＋ → スイッチの共通 → 入の端子 → D_PWR のアノード → カソード → 3V3。XIAO の BAT は基板に出ない
    if not (net[("BT1", "1")] == net[("SW_PWR", "2")] == "VBAT_IN" and net[("SW_PWR", "3")] == net[("D_PWR", "2")] == net[("R_HI", "1")] == "VBAT_SW"
            and net[("D_PWR", "1")] == net[("U_MCU", "3V3")] == "V3V3" and net[("SW_PWR", "1")] == "" and net[("BT1", "2")] == "GND"):
        out.append("電源の道が 電池 → スイッチ → D_PWR（A→K）→ 3V3 でない")
    return out


def test_the_board_matches_the_firmware_pin_map(facts):
    overlay = (SHIELD / "cckb_click.overlay").read_text()
    assert firmware_problems(facts, overlay) == []
    assert not any(p["ref"] == "U_MCU" and p["num"] == "BAT" for p in facts["pads"])


@pytest.mark.parametrize("old, new", [("<&xiao_d 2 (GPIO", "<&xiao_d 3 (GPIO"), ("<&shifter 8 GPIO", "<&shifter 15 GPIO"),
                                      ("cs-gpios = <&xiao_d 7", "cs-gpios = <&xiao_d 9"), ("<&adc 0>", "<&adc 1>")])
def test_the_firmware_check_notices_a_changed_overlay(facts, old, new):
    overlay = (SHIELD / "cckb_click.overlay").read_text()
    assert old in overlay
    assert firmware_problems(facts, overlay.replace(old, new, 1))


def test_the_shield_is_cckbs_with_only_the_name_and_the_debounce_changed():
    """回路が CCKB と同じなので、overlay・キーマップ・行列表は CCKB と同じ中身。違うのは名前と、タクトスイッチのデバウンスだけ。"""
    def body(text):
        return re.sub(r"/\*.*?\*/", "", text, count=1, flags=re.S).replace("cckb_click-transform", "cckb-transform").strip()
    # overlay は「cckb-click だけ」の印より上が CCKB と同じ（下は SPI の MISO のプルダウン: 次の検査）
    ours_overlay = (SHIELD / "cckb_click.overlay").read_text()
    assert ours_overlay.count(CLICK_ONLY) == 1
    assert body(ours_overlay.split(CLICK_ONLY)[0]) == body((CCKB_SHIELD / "cckb.overlay").read_text())
    assert body((SHIELD / "cckb_click.keymap").read_text()) == body((CCKB_SHIELD / "cckb.keymap").read_text())
    rc = lambda t: re.findall(r"RC\(\d+,\d+\)", t)         # noqa: E731
    assert rc((SHIELD / "cckb_click-transform.dtsi").read_text()) == rc((CCKB_SHIELD / "cckb-transform.dtsi").read_text())
    assert len(rc((SHIELD / "cckb_click-transform.dtsi").read_text())) == 62
    conf = lambda p: {ln.split("=")[0]: ln.split("=")[1] for ln in p.read_text().splitlines() if ln.startswith("CONFIG_")}   # noqa: E731
    ours, theirs = conf(SHIELD / "cckb_click.conf"), conf(CCKB_SHIELD / "cckb.conf")
    diff = {k for k in set(ours) | set(theirs) if ours.get(k) != theirs.get(k)}
    assert diff == {"CONFIG_ZMK_KEYBOARD_NAME", "CONFIG_ZMK_KSCAN_DEBOUNCE_PRESS_MS", "CONFIG_ZMK_KSCAN_DEBOUNCE_RELEASE_MS"}
    # Alps の仕様書 6.4: ON・OFF とも跳ねは 10 ms 以下 → 離す側は 10 以上
    assert int(ours["CONFIG_ZMK_KSCAN_DEBOUNCE_RELEASE_MS"]) >= 10 and int(ours["CONFIG_ZMK_KSCAN_DEBOUNCE_PRESS_MS"]) >= 5
    from foundry import check_zmk_config
    assert check_zmk_config.xiao_pin_conflicts((SHIELD / "cckb_click.overlay").read_text()) == []
    assert "shield: cckb_click" in (ROOT / "build.yaml").read_text()


CLICK_ONLY = "/* ---- cckb-click だけ（ここから下は cckb.overlay に無い）---- */"
UPSTREAM_PINCTRL = ROOT / "foundry" / "upstream" / "xiao_ble-pinctrl.dtsi"


def pinctrl_groups(text, node, indent="\t"):
    """dts の pinctrl の節 node（spi2_default など）の組 [(ピンの集合, 性質の集合)]。indent は、その節の字下げ
    （節の閉じ括弧を、中の組の閉じ括弧と取り違えないため。ボードの定義はタブ 1 つ・overlay は行頭）。"""
    m = re.search(rf"{node}(?::\s*{node})?\s*\{{(.*?)\n{indent}\}};", text, re.S)
    assert m, node
    out = []
    for g in re.findall(r"group\d+\s*\{(.*?)\}", m.group(1), re.S):
        pins = set(re.findall(r"NRF_PSEL\((\w+),\s*(\d+),\s*(\d+)\)", g))
        flags = set(re.findall(r"^\s*([a-z][a-z,-]+);", g, re.M))
        out.append((pins, flags))
    return out


def miso_problems(overlay, upstream, facts):
    out = []
    tail = overlay.split(CLICK_ONLY)[1]
    for node, want_all in (("spi2_default", set()), ("spi2_sleep", {"low-power-enable"})):
        up = pinctrl_groups(upstream, node)
        mine = pinctrl_groups(tail, f"&{node}", indent="")
        if len(mine) != 2:
            out.append(f"{node}: overlay の組が {len(mine)} 個（SCK・MOSI の組と MISO の組の 2 つのはず）")
            continue
        if set().union(*(p for p, _ in mine)) != set().union(*(p for p, _ in up)):
            out.append(f"{node}: overlay のピン {sorted(set().union(*(p for p, _ in mine)))} がボードの定義と違う")
        for pins, flags in mine:
            is_miso = {p[0] for p in pins} == {"SPIM_MISO"}
            if any(p[0] == "SPIM_MISO" for p in pins) and not is_miso:
                out.append(f"{node}: MISO がほかのピンと同じ組（プルがほかのピンにも掛かる）")
            if flags != want_all | ({"bias-pull-down"} if is_miso else set()):
                out.append(f"{node}: 組 {sorted(p[0] for p in pins)} の性質 {sorted(flags)}")
    # D9（MISO = P1.14）は基板で何にも繋がっていない（だからプルが要る）
    if any(p["ref"] == "U_MCU" and p["num"] == "D9" and p["net"] for p in facts["pads"]):
        out.append("D9 に網がある（プルダウンを付ける前提が違う）")
    return out


def test_the_unconnected_miso_pin_is_pulled_down(facts):
    """A 軽微 1。外の事実 = ボードの pinctrl の写し（spi2 は SCK P1.13・MOSI P1.15・MISO P1.14）。"""
    overlay = (SHIELD / "cckb_click.overlay").read_text()
    upstream = UPSTREAM_PINCTRL.read_text()
    assert miso_problems(overlay, upstream, facts) == []
    assert pinctrl_groups(upstream, "spi2_default") == [({("SPIM_SCK", "1", "13"), ("SPIM_MOSI", "1", "15"), ("SPIM_MISO", "1", "14")}, set())]
    # 壊すと落ちる: ピンを取り違える・プルダウンを消す・MISO を SCK と同じ組に戻す
    assert miso_problems(overlay.replace("NRF_PSEL(SPIM_MISO, 1, 14)", "NRF_PSEL(SPIM_MISO, 1, 12)"), upstream, facts)
    assert miso_problems(overlay.replace("\t\tbias-pull-down;\n", "", 1), upstream, facts)
    f = copy.deepcopy(facts)
    next(p for p in f["pads"] if p["ref"] == "U_MCU" and p["num"] == "D9")["net"] = "X"
    assert miso_problems(overlay, upstream, f)


def battery_millivolts(pin_mv, driver, overlay):
    """電池電圧のドライバ（firmware/drivers/battery_alkaline.c）の式を、ソースから読んだ定数で計算する。
    nRF52840 の SAADC: 内部基準 0.6 V（Nordic の PS）・利得 1/6 → 入力の満量 3.6 V・12 bit。"""
    gain = re.search(r"\.gain = ADC_GAIN_(\d)_(\d)", driver).groups()
    bits = int(re.search(r"as\.resolution = (\d+)", driver).group(1))
    assert re.search(r"\.reference = ADC_REF_INTERNAL", driver)
    full_scale = 600.0 * int(gain[1]) / int(gain[0])
    raw = int(pin_mv / full_scale * (1 << bits))
    out_ohm = int(re.search(r"output-ohms = <(\d+)>", overlay).group(1))
    full_ohm = int(re.search(r"full-ohms = <(\d+)>", overlay).group(1))
    assert "(uint64_t)val * cfg->full_ohm / cfg->output_ohm" in driver
    return raw * full_scale / (1 << bits) * full_ohm / out_ohm, full_scale * full_ohm / out_ohm


def test_the_battery_voltage_formula_matches_the_divider_on_the_board(facts):
    """A 軽微 2: config/west.yml は ZMK の main を追う（固定していない）。ドライバの式と overlay の定数と基板の分圧が
    合っていることを、ここで見る（ZMK が上がって ADC の API が変われば、ビルドが落ちるか、この式の読みが外れる）。"""
    driver = (ROOT / "firmware" / "drivers" / "battery_alkaline.c").read_text()
    overlay = (SHIELD / "cckb_click.overlay").read_text()
    value = {f["ref"]: f["value"] for f in facts["footprints"]}
    assert value["R_HI"] == value["R_LO"] == "1M"                      # 基板: 1 MΩ ＋ 1 MΩ → ピンは電池の半分
    for cell_mv in (3200, 3000, 2400, 2000):
        got, limit = battery_millivolts(cell_mv / 2, driver, overlay)
        assert got == pytest.approx(cell_mv, abs=4) and cell_mv < limit, (cell_mv, got)
    # 壊すと落ちる: 分圧の比を取り違えた overlay（full-ohms 1 MΩ）では半分に読む
    wrong, _ = battery_millivolts(1500, driver, overlay.replace("full-ohms = <2000000>", "full-ohms = <1000000>"))
    assert wrong == pytest.approx(1500, abs=4)
    # ADC の入力は AIN0 = P0.02 = D0（ボードの写しの D0 と、overlay の &adc 0）
    assert re.search(r"io-channels = <&adc 0>", overlay) and next(
        p["net"] for p in facts["pads"] if p["ref"] == "U_MCU" and p["num"] == "D0") == "VBAT_SENSE"


def test_the_switch_sees_more_than_its_minimum_load_when_scanned():
    """Alps の仕様書 5.2「Minimum ratings 1 V DC 10 µA」。走査のとき、押したスイッチには 595 の High（レール）− ダイオードの Vf が
    掛かり、行のプルダウン（nRF52840 の内蔵。Nordic の PS: 11〜16 kΩ・代表 13）へ電流が流れる。レールがいちばん低いとき（電池の打ち止め 2.0 V）でも足りる。"""
    rail_min, vf_max, pull_max = 2.0, 0.25, 16e3          # V・BAT46W の保証値 @0.1 mA・Ω
    current = (rail_min - vf_max) / pull_max
    assert current > 10e-6 * 5 and rail_min > 1.0, current       # 109 µA（仕様の下限の 10 倍）


# ---------------------------------------------------------------------------
# (h) 1 回目の監査（2026-10-04）で、検査が見ていなかった所
# ---------------------------------------------------------------------------

def click_facts(board, cell, tmp):
    """projects/cckb-click/tools/click_facts.py（KiCad の Python）を板に通す。cell = (x, y, 半径)。"""
    require(paths.KICAD_PYTHON, "板の事実の書き出し")
    out = tmp / "click_facts.json"
    r = subprocess.run([paths.KICAD_PYTHON, str(CLICK_FACTS), str(board), str(out), ",".join(str(v) for v in cell)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout + r.stderr
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def extra(tmp_path_factory):
    (x, y), r = LAY.cell()
    return click_facts(BOARD, (x, y, r), tmp_path_factory.mktemp("clickextra"))


# 電池の缶（＋）の縁から表の銅まで。擦れてマスクが剥げた GND に缶が触れると、電池が短絡する
CELL_TO_COPPER_MIN = 0.5


def test_the_seated_cell_and_its_way_out_stay_clear_of_front_copper(extra, tmp_path):
    """E 重要 1: 止めに当てた電池は、クリップの原点より 0.51 奥に座る。前の板は、その缶の縁が表の GND のベタの縁の真上だった（余裕 0）。
    KiCad が読んだ板の銅（ベタ・線・ビア・電池クリップ以外のパッド）までを測る。"""
    c = extra["cell"]
    assert c["seated"] >= CELL_TO_COPPER_MIN and c["path"] >= CELL_TO_COPPER_MIN - 1e-3, c
    # 外の事実: 止めの位置は図面（止めから口 15.10・板厚 0.25）と足跡（止めの外面が軸から 8.76）から
    assert c["center"][1] - S.CLIP_AT[1] == pytest.approx(8.76 - 0.25 - 8.0)
    # 壊すと落ちる: 電池がもう 1.0 奥なら足りない（いまの余裕は 0.7〜1.25）・電池が 1.0 右へずれた道は銅に当たる
    (x, y), r = LAY.cell()
    assert click_facts(BOARD, (x, y + 1.0, r), tmp_path)["cell"]["seated"] < CELL_TO_COPPER_MIN
    assert click_facts(BOARD, (x + 1.0, y, r), tmp_path)["cell"]["path"] < 0.01


def silk_graphic_problems(extra):
    out = []
    for g in extra["silk_graphics"]:
        if g["width"] < JLC["silk_width"] - 1e-9:
            out.append(f"{g['owner']} のシルクの{g['shape']}の太さ {g['width']}（JLC の下限 {JLC['silk_width']}）")
        if g["dist"] < 0.15:
            out.append(f"{g['owner']} のシルクの{g['shape']}が {g['near']} のマスクの開口から {g['dist']}")
    return out


def test_no_silk_graphic_is_thin_or_touches_a_mask_opening(extra):
    """C 軽微 1: 試験用のランドのシルクの輪が、パッドのマスクの開口から 0.10・太さ 0.12 だった（文字の検査は図形を見ていなかった）。"""
    assert silk_graphic_problems(extra) == []
    assert len(extra["silk_graphics"]) > 150                    # ダイオード 63 個 × 3 本ほか
    ring = [g for g in extra["silk_graphics"] if g["owner"] == "TP_VSW"]
    assert len(ring) == 1 and ring[0]["dist"] >= 0.2


def test_the_silk_graphic_check_notices_a_thin_and_a_close_shape(extra):
    e = copy.deepcopy(extra)
    e["silk_graphics"][0]["width"] = 0.12
    e["silk_graphics"][1]["dist"] = 0.10
    assert len(silk_graphic_problems(e)) == 2


def test_the_drc_limits_are_the_sizes_this_board_uses(facts, tmp_path):
    """C 軽微 5: DRC の下限を、この板が実際に使うビア（φ0.6 / 穴 0.3）に上げてある。小さいビアが紛れたら落ちる。"""
    require(paths.KICAD_CLI, "DRC")
    rules = json.loads(BOARD.with_suffix(".kicad_pro").read_text())["board"]["design_settings"]["rules"]
    assert (rules["min_via_diameter"], rules["min_through_hole_diameter"]) == (0.6, 0.3)
    assert {(v["d"], v["drill"]) for v in facts["vias"]} == {(0.6, 0.3)}
    assert min(p["drill"] for p in facts["pads"] if p["drill"] and not p["npth"]) >= 0.3
    # 壊すと落ちる: 板の写しに φ0.5 / 穴 0.25 のビア（JLC では作れる大きさ）を 1 本足す
    b = board_copy(tmp_path)
    t = b.read_text()
    at = next(v["pos"] for v in facts["vias"] if v["net"] == "GND" and abs(v["pos"][0]) < 20 and abs(v["pos"][1]) < 10)
    ox, oy = facts["origin"]
    small = (f'\t(via (at {at[0] + ox + 1.5} {oy - at[1]}) (size 0.5) (drill 0.25) (layers "F.Cu" "B.Cu") (net "GND")'
             f' (uuid "00000000-0000-4000-8000-00000000c11d"))\n')
    i = t.rindex(")")
    b.write_text(t[:i] + small + t[i:])
    r = drc.run(b)
    assert r["violations"] > 0 and any("via" in k or "hole" in k or "annul" in k for k in r["violation_kinds"]), r


def test_a_machine_cannot_loosen_the_rules(tmp_path):
    from foundry.pcb_rules import sync_project_rules
    pro = tmp_path / "x.kicad_pro"
    pro.write_text("{}")
    sync_project_rules(tmp_path / "x.kicad_pcb", tighten=S.DRC_RULES)
    assert json.loads(pro.read_text())["board"]["design_settings"]["rules"]["min_via_diameter"] == 0.6
    with pytest.raises(ValueError):
        sync_project_rules(tmp_path / "x.kicad_pcb", tighten={"min_via_diameter": 0.3})          # JLC の下限 0.45 より小さい
    with pytest.raises(ValueError):
        sync_project_rules(tmp_path / "x.kicad_pcb", tighten={"min_hole_to_hole": 0.6})          # 変えてよい鍵でない


def seg_dist(a, b, c, d):
    """線分 ab と cd の距離。"""
    def pt(p, q, r):
        vx, vy = r[0] - q[0], r[1] - q[1]
        L2 = vx * vx + vy * vy
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - q[0]) * vx + (p[1] - q[1]) * vy) / L2))
        return math.hypot(p[0] - q[0] - u * vx, p[1] - q[1] - u * vy)
    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def sense_problems(facts, clear=1.0, parallel_max=4.0):
    """D 軽微 3: 電池電圧の線（1 MΩ の分圧の中点 = 高い出どころ）が、裏で行の線のすぐ脇を長く並んで走らない。
    行の線から clear 未満の所にいる長さの合計が parallel_max 以下（XIAO のパッド内ビアから出る所は 2.54 おきなので避けられない）。"""
    sense = [t for t in facts["tracks"] if t["net"] == "VBAT_SENSE"]
    rows = [t for t in facts["tracks"] if re.fullmatch(r"ROW\d+", t["net"])]
    out = []
    near = 0.0
    for s in sense:
        n = max(2, int(math.dist(s["a"], s["b"]) / 0.25) + 1)
        for k in range(n - 1):
            p = [s["a"][i] + (s["b"][i] - s["a"][i]) * (k + 0.5) / (n - 1) for i in (0, 1)]
            if any(r["layer"] == s["layer"] and seg_dist(p, p, r["a"], r["b"]) < clear for r in rows):
                near += math.dist(s["a"], s["b"]) / (n - 1)
    if near > parallel_max:
        out.append(f"VBAT_SENSE が行の線から {clear} 未満の所を {near:.1f} mm 走る")
    if not any(s["layer"] == "B.Cu" and math.dist(s["a"], s["b"]) > 15 for s in sense):
        out.append("VBAT_SENSE の裏の長い縦線が無い（決まった形で引いていない）")
    return out


def test_the_battery_sense_line_keeps_away_from_the_row_lines(facts):
    assert sense_problems(facts) == []
    how = S.SENSE_RUN
    lane = [t for t in facts["tracks"] if t["net"] == how["net"] and t["layer"] == "B.Cu" and t["a"][0] == t["b"][0] == how["lane_x"]]
    assert len(lane) == 1 and abs(lane[0]["a"][1] - lane[0]["b"][1]) > 15
    assert how["lane_x"] - S.XIAO_ESCAPE["ROW0"]["lane_x"] == pytest.approx(-1.8)
    # 分圧の定数は足していない（監査: コンデンサは足さない）
    assert sorted(r for r, k, _ in circuit.electronics() if k == "res_1M") == ["R_HI", "R_LO"]


def test_the_sense_check_notices_a_line_run_beside_a_row(facts):
    # 監査の時の板と同じ形: 行 0 の縦線の 0.76 左を並んで走る
    f = copy.deepcopy(facts)
    x = S.XIAO_ESCAPE["ROW0"]["lane_x"] - 0.76
    for t in f["tracks"]:
        if t["net"] == "VBAT_SENSE" and t["layer"] == "B.Cu" and t["a"][0] == t["b"][0] == S.SENSE_RUN["lane_x"]:
            t["a"][0] = t["b"][0] = x
    assert any("並" in b or "未満" in b for b in sense_problems(f))


def test_the_capacitor_lands_take_a_1206_and_an_0805_and_stay_bare(facts):
    """A 重要 1・D 重要 1: あとから容量を足す場所。外の事実 = KiCad の標準の足跡（0805・1206。IPC-7351 の値）のパッド。"""
    from test_cckb_click_pcb import fp_pads

    land = [p for p in fp_pads("cckb-click.pretty", "C_1206_0805_Land") if p[0]]
    assert len(land) == 2 and all(set(p[7]) == {"F.Cu", "F.Mask"} for p in land)       # ペーストの層が無い

    def std(name):
        text = (paths.KICAD_FOOTPRINTS / "Capacitor_SMD.pretty" / f"{name}.kicad_mod").read_text()
        return [(float(x), float(y), float(w), float(h)) for x, y, w, h in
                re.findall(r'\(pad "\d" smd \w+\s*\(at ([-\d.]+) ([-\d.]+)[^)]*\)\s*\(size ([-\d.]+) ([-\d.]+)\)', text)]

    for name in ("C_0805_2012Metric", "C_1206_3216Metric"):
        pads = std(name)
        assert len(pads) == 2, name
        for x, y, w, h in pads:
            mine = next(p for p in land if (p[3] > 0) == (x > 0))
            assert mine[3] - mine[5] / 2 <= x - w / 2 + 1e-9 and x + w / 2 <= mine[3] + mine[5] / 2 + 1e-9, (name, x, w)
            assert mine[6] >= h - 1e-9, (name, h)
    # 板の上: JLC は載せない・はんだも載せない・網は宣言どおり・GND の側はサーマル（手はんだ）
    for ref, net in (("C_BAT", "VBAT_SW"), ("C_3V3", "V3V3")):
        fp = next(f for f in facts["footprints"] if f["ref"] == ref)
        assert fp["exclude_bom"] and fp["exclude_pos"] and not fp["flipped"] and not fp["fields"].get("LCSC")
        pads = {p["num"]: p for p in facts["pads"] if p["ref"] == ref}
        assert pads["1"]["net"] == net and pads["2"]["net"] == "GND" and not any(p["paste"] for p in pads.values())
        assert pads["2"]["thermal"]
    # C_BAT は電源スイッチの後ろ（D_PWR の手前）= スイッチを切ると電池から外れる
    net = {(p["ref"], p["num"]): p["net"] for p in facts["pads"]}
    assert net[("C_BAT", "1")] == net[("SW_PWR", "3")] == net[("D_PWR", "2")] != net[("BT1", "1")]
    assert net[("C_3V3", "1")] == net[("D_PWR", "1")] == net[("U_MCU", "3V3")]
    # 置き場所: C_BAT は右の角の屋根の下（背 3.0 まで）・C_3V3 は Z のキーの穴の中（キャップの下。背は click_case の検査が見る）
    assert L.rect_gap(L.rect(*S.PART_AT["C_BAT"][:2], 0.1, 0.1), LAY.corner("right")) < 0
    z = next(k for k in LAY.keys if k.label == "Z")
    h = LAY.hole(z)
    assert h[0] < S.PART_AT["C_3V3"][0] < z.x - 4.25 and h[1] < S.PART_AT["C_3V3"][1] < h[3]
    assert S.CAP_LAND_H == {"C_BAT": 2.8, "C_3V3": 1.45}


def pad_bbox(facts, ref, pick=lambda p: True):
    boxes = [p["box"] for p in facts["pads"] if p["ref"] == ref and p["num"] and not p["drill"] and pick(p)]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def test_the_frame_reliefs_are_taken_from_the_pads_of_the_board(facts):
    """E 軽微 1・2: 枠の逃げは「パッドの外接 ＋ PART_CLEAR」。その外接（click_layout.psw_pads・xiao_pads）が、KiCad が読んだ板のパッドと同じか。
    前は電源スイッチの本体の外形から取っていて、枠のランドとの隙が 0.1 しか無かった。"""
    assert pad_bbox(facts, "SW_PWR") == pytest.approx(list(LAY.psw_pads()), abs=0.01)
    xp = LAY.xiao_pads()
    got = pad_bbox(facts, "U_MCU")
    assert (got[1], got[3]) == pytest.approx((xp[1], xp[3]), abs=0.01) and xp[0] <= got[0] and got[2] <= xp[2]
    # 壊すと落ちる: 本体の外形（前の取り方）はパッドの外接と違う
    assert pad_bbox(facts, "SW_PWR") != pytest.approx(list(LAY.psw_body()), abs=0.05)
    assert S.PART_CLEAR >= 0.4


def test_no_via_sits_on_the_test_pad(facts):
    tp = next(p for p in facts["pads"] if p["ref"] == "TP_VSW")
    assert min(math.dist(v["pos"], tp["pos"]) for v in facts["vias"]) >= 0.5 + 0.3 + 0.1


def test_the_spare_screw_holes_are_in_the_board(facts):
    """E 重要 3: 手前の継ぎ目の両側の予備の穴（非めっき φ2.2）。裏の頭の下に銅が無いことは keepout_problems が全部の穴で見る。"""
    spare = [(ref, c) for ref, c, kind in LAY.screws() if kind == "spare"]
    assert len(spare) == 2
    for ref, c in spare:
        hole = [p for p in facts["pads"] if p["ref"] == ref]
        assert len(hole) == 1 and hole[0]["npth"] and hole[0]["drill"] == S.SCREW_HOLE_D and hole[0]["pos"] == pytest.approx(list(c))
        assert f"head_{ref}" in facts["region"]
    # 外周の穴は全部、基板の縁から 2.1（穴の縁から 1.0）
    for ref, c, kind in LAY.wall_screws():
        d = min(c[0] - LAY.pcb[0], LAY.pcb[2] - c[0], c[1] - LAY.pcb[1], LAY.pcb[3] - c[1])
        assert d == pytest.approx(2.1), ref


def cover_hole_problems(facts):
    """蓋のねじ穴（利用者の決定 2026-10-04・既定では使わない）: 非めっき φ2.2 が 2 つ・基板の縁から 2.1・表は電池の道（銅を置かない範囲）の中・
    裏は頭の円（半径 2.3）から、GND 以外の線・ビアまで 0.2 以上（頭の下に銅が無いことは keepout_problems が全部の穴で見る）。"""
    out = []
    cover = [(ref, c) for ref, c, kind in LAY.screws() if kind == "cover"]
    if len(cover) != 2:
        out.append(f"蓋のねじ穴が {len(cover)} 個")
    k = LAY.cell_keepout()
    for ref, c in cover:
        hole = [p for p in facts["pads"] if p["ref"] == ref]
        if len(hole) != 1 or not hole[0]["npth"] or hole[0]["drill"] != S.SCREW_HOLE_D or math.dist(hole[0]["pos"], c) > 1e-3:
            out.append(f"{ref}: 板の上の穴が {[(p['pos'], p['drill'], p['npth']) for p in hole]}")
        if abs(c[1] - LAY.pcb[1] - 2.1) > 1e-6:
            out.append(f"{ref}: 基板の縁から {c[1] - LAY.pcb[1]:.3f}")
        h = S.SCREW_HOLE_D / 2 + S.METAL_COPPER_CLEAR             # 表: 穴の縁 ＋ 0.3 まで、銅を置かない範囲の中（頭は裏）
        if not (k[0] + h <= c[0] <= k[2] - h and k[1] <= c[1] <= k[3] - h):
            out.append(f"{ref}: 穴が、表の銅を置かない範囲 {k} の縁に掛かる")
        r = S.SCREW_HEAD_D / 2 + S.METAL_COPPER_CLEAR
        for t in facts["tracks"]:
            if t["layer"] == "B.Cu" and t["net"] != "GND" and seg_dist(c, c, t["a"], t["b"]) - t.get("w", 0.3) / 2 < r + 0.2:
                out.append(f"{ref}: 裏の {t['net']} の線が頭の円から {seg_dist(c, c, t['a'], t['b']) - r:.2f}")
        for v in facts["vias"]:
            if math.dist(v["pos"], c) - v["d"] / 2 < r + 0.2:
                out.append(f"{ref}: ビア {v['net']} が頭の円から {math.dist(v['pos'], c) - v['d'] / 2 - r:.2f}")
    return out


def test_the_cover_screw_holes_are_in_the_board_and_clear_of_copper(facts):
    assert cover_hole_problems(facts) == []
    assert all(f"head_{ref}" in facts["region"] for ref, _, kind in LAY.screws() if kind == "cover")
    # 裏の VBAT_IN の線（電池の下をくぐる）は穴の中心から 4.16
    under = [t for t in facts["tracks"] if t["net"] == "VBAT_IN" and t["layer"] == "B.Cu" and t["a"][1] == t["b"][1]]
    assert len(under) == 1 and under[0]["a"][1] - S.SCREWS_COVER[0][1] == pytest.approx(4.16)


def test_the_cover_hole_check_notices_a_moved_hole_and_a_line_under_the_head(facts):
    f = copy.deepcopy(facts)
    for t in f["tracks"]:
        if t["net"] == "VBAT_IN" and t["layer"] == "B.Cu" and t["a"][1] == t["b"][1]:
            t["a"][1] = t["b"][1] = S.SCREWS_COVER[0][1] + 2.4
    assert any("VBAT_IN" in b for b in cover_hole_problems(f))
    f = copy.deepcopy(facts)
    next(p for p in f["pads"] if p["ref"] == "H30")["pos"][0] += 0.5
    assert any("H30" in b for b in cover_hole_problems(f))


def jlc_edge_problems(facts):
    """JLC の実装の規約（Terms and Conditions of JLCPCB Assembly Service・2026-10-04 に読んだ）: 載せる部品の本体は基板の縁から 2.5 mm 以上。
    縁の近くの部品（電源スイッチ・電池クリップ）を、板の上のパッド・突起の穴の位置と、図面の本体の寸法で見る。縁の外へ出る物が無いこと。"""
    out = []
    e = LAY.pcb
    pegs = [p["pos"] for p in facts["pads"] if p["ref"] == "SW_PWR" and p["npth"]]
    if len(pegs) != 2:
        return [f"電源スイッチの突起の穴が {len(pegs)} 個"]
    cx = pegs[0][0]                                              # 本体の中心線（図面: 突起は本体の中心線の上）
    body = cx + S.PSW_BODY[1] / 2
    tip = body + S.PSW_KNOB[1]
    if e[2] - body < S.PSW_EDGE_MIN - 1e-6:
        out.append(f"電源スイッチの本体が基板の縁から {e[2] - body:.3f}（{S.PSW_EDGE_MIN} 以上）")
    if tip > e[2]:
        out.append(f"電源スイッチのつまみが基板の縁から {tip - e[2]:.3f} 出る")
    for p in facts["pads"]:
        if p["ref"] in ("SW_PWR", "BT1") and not p["npth"]:
            b = p["box"]
            if min(b[0] - e[0], e[2] - b[2], b[1] - e[1], e[3] - b[3]) < 2.0:
                out.append(f"{p['ref']}.{p['num']} のランドが基板の縁から 2.0 未満")
    return out


def test_the_power_switch_body_is_2_5_inside_the_board_edge_and_nothing_overhangs(facts):
    assert jlc_edge_problems(facts) == []
    assert S.PSW_EDGE_MIN == 2.5


def test_the_edge_check_notices_the_old_overhanging_switch(facts):
    f = copy.deepcopy(facts)
    for p in f["pads"]:
        if p["ref"] == "SW_PWR":
            p["pos"][0] += 1.75                                  # 前の位置
            p["box"] = [p["box"][0] + 1.75, p["box"][1], p["box"][2] + 1.75, p["box"][3]]
    bad = jlc_edge_problems(f)
    assert any("本体" in b for b in bad) and any("つまみ" in b for b in bad), bad


def frozen_problems(facts, rec):
    """SPI・595 どうし・電源の枝は、監査した板（rec["source_sha256"]）で Freerouting が引いた形のまま（pcb/freerouted.json）。
    その網の線・ビアが、記録と過不足なく同じ（決まった形で引く区間は除く: 記録に無い線は、click_routes の計画に無ければ指摘）。"""
    out = []
    nets = {t["net"] for t in rec["tracks"]}
    key = lambda n, layer, a, b: (n, layer) + tuple(sorted([(round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))]))   # noqa: E731
    have = {key(t["net"], t["layer"], t["a"], t["b"]) for t in facts["tracks"] if t["net"] in nets}
    want = {key(t["net"], t["layer"], t["a"], t["b"]) for t in rec["tracks"]}
    if want - have:
        out.append(f"記録の線 {len(want - have)} 本が板に無い: {sorted(want - have)[:3]}")
    vh = {(v["net"], round(v["pos"][0], 3), round(v["pos"][1], 3)) for v in facts["vias"] if v["net"] in nets}
    vw = {(v["net"], round(v["at"][0], 3), round(v["at"][1], 3)) for v in rec["vias"]}
    if vw - vh:
        out.append(f"記録のビア {len(vw - vh)} 個が板に無い: {sorted(vw - vh)[:3]}")
    for n in ("SPI_SCK", "SPI_MOSI", "CS", "U1_U2"):               # 決まった形で引く区間の無い網は、線の数まで同じ
        if sum(1 for k in have if k[0] == n) != sum(1 for k in want if k[0] == n):
            out.append(f"{n}: 板の線 {sum(1 for k in have if k[0] == n)} 本・記録 {sum(1 for k in want if k[0] == n)} 本")
    return out


def test_the_freerouted_branches_are_the_audited_ones(facts):
    rec = json.loads((PCB / "freerouted.json").read_text())
    assert frozen_problems(facts, rec) == []
    assert rec["source_sha256"].startswith("4dc68901") and {t["net"] for t in rec["tracks"]} == {"SPI_SCK", "SPI_MOSI", "CS", "U1_U2", "V3V3", "VBAT_SW"}
    route = json.loads((PCB / "route.json").read_text())
    assert route["freerouted"] == "replayed" and route["freerouted_from"] == rec["source_sha256"]
    # 電池の＋は Freerouting の線ではなく、決まった形（直角の 8 区間・ビア 2 個）
    vin = [t for t in facts["tracks"] if t["net"] == "VBAT_IN"]
    assert len(vin) == 8 and all(t["a"][0] == t["b"][0] or t["a"][1] == t["b"][1] for t in vin)
    assert sum(1 for v in facts["vias"] if v["net"] == "VBAT_IN") == 2
    # 壊すと落ちる: 記録の線を 1 本動かす・板の SPI の線を 1 本足す
    bad = copy.deepcopy(rec)
    bad["tracks"][0]["a"][0] += 0.5
    assert any("板に無い" in b for b in frozen_problems(facts, bad))
    f = copy.deepcopy(facts)
    f["tracks"].append(dict(net="CS", layer="F.Cu", a=[0.0, 0.0], b=[1.0, 0.0], w=0.2))
    assert any("CS" in b for b in frozen_problems(f, rec))


# ---------------------------------------------------------------------------
# (g) 鮮度: 置いてある板が、いまの生成器・いまの配置から作った物か
# ---------------------------------------------------------------------------

def test_the_committed_boards_and_records_are_fresh(tmp_path):
    require(paths.KICAD_PYTHON, "基板の生成")
    rec = json.loads((PCB / "route.json").read_text())
    from foundry import boardhash
    # 中身（指紋 = 配置・結線・外形）で比べる。ファイルの sha256 では比べない: tests/test_cckb_click_pcb.py が同じ場所に
    # 板を作り直し、作るたびにバイト列は変わる（全検査を通しで回したときだけ、ここが偽の赤になった）
    before = boardhash.fingerprint(UNROUTED)
    assert rec["unrouted_fingerprint"] == before, "未配線の板を作り直した後、配線し直していない"
    assert rec["unconnected"] == 0 and rec["freerouting"] == "freerouting-2.3.0.jar"
    keep = UNROUTED.read_bytes()
    try:
        r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", "cckb-click"], cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert boardhash.fingerprint(UNROUTED) == before
    finally:
        UNROUTED.write_bytes(keep)
    d = json.loads(drc.report_path(BOARD).read_text())
    assert d["fingerprint"] == boardhash.fingerprint(BOARD)
