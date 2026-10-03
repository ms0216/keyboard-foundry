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


def control(r, dx=0.0, dy=20.0):
    return (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)


def regions():
    """board_facts に渡す領域 {名前: 引数}。禁止域ごとに、銅のあるはずの対照を並べる（0 しか返さない検査器は 0 を証明しない）。"""
    out = {"antenna": LAY.antenna_keepout(), "antenna_control": control(LAY.antenna_keepout(), dx=30.0, dy=0.0)}
    for n, r in LAY.xiao_exposed().items():
        out[f"xiao_{n}"] = r
    out["cell"] = LAY.cell_keepout()
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
        skip = re.fullmatch(r"SW[AB]\d+|U_MCU|H\d+|TP_VSW", ref)
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
        dry = re.fullmatch(r"SW[AB]\d+|U_MCU|TP_VSW", p["ref"]) or (p["ref"] == "BT1" and p["num"] == "2")
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
    out.update({c: dict(head=p["head"], pads=p["pads"]) for c, p in EE_CLICK.items()})
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
        if worst > tol:
            out.append((ref, round(worst, 3)))
    return out


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
    assert not [r for r in refs if re.fullmatch(r"SW[AB]\d+|U_MCU|H\d+|TP_VSW", r)]
    count = {}
    for c in lcsc_of.values():
        count[c] = count.get(c, 0) + 1
    assert count == {"C202383": 62, "C54110": 63, "C52287685": 2, "C49678": 2, "C17514": 2, "C20606805": 1, "C431540": 1}
    assert cpl_misplacements(rows, lcsc_of, facts, ee_parts()) == []
    # ドリルのファイルに長円が無い（JLC へ行く物そのもの）
    drl = "".join(p.read_text(errors="ignore") for p in prod.rglob("*.drl")) if list(prod.rglob("*.drl")) else None
    if drl is not None:
        assert "G85" not in drl


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
    assert names == {"ANTENNA_KEEPOUT", "XIAO_UNDERSIDE", "EDGE_KEEPOUT", "SCREW_HEAD_KEEPOUT", "CELL_KEEPOUT", "SW_BODY_KEEPOUT", "FANOUT_NO_FILL", "XIAO_BACK_NO_FILL"}
    assert sum(1 for z in facts["zones"] if z["name"] == "SCREW_HEAD_KEEPOUT") == 28
    assert sum(1 for z in facts["zones"] if z["name"] == "SW_BODY_KEEPOUT") == 84


def test_the_keepout_check_notices_copper(facts):
    for key, layer, word in (("antenna", "B.Cu", "アンテナ"), ("xiao_pad22", "F.Cu", "pad22"), ("head_H3", "B.Cu", "H3"), ("cell", "F.Cu", "電池")):
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
    assert len(gnd) == 2 + 1 + 4 + 1 + 4            # パスコン 2・R_LO・595 の GND と OE ×2・XIAO・電源スイッチの枠 4
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


# mm。銅の上の道のり。FR-4 の上の 2.4 GHz の 1/4 波長（約 17）より短く（595 のいるキーの中だけは別: 下の IC_CELL_REACH_MAX）。
# CCKB は、ビアを足せない 1 か所で 10.3 を記録して受け入れた（projects/cckb/docs/open-gaps.md P14）
GND_REACH_MAX = 15.0


# 595 の 2 個がいるキー（左 Shift）の穴の中。表は 595・パスコン・空きランド・SPI の線で混み、GND のベタが幅 0.3〜0.5 の首でだけ
# 繋がった所が残る（Freerouting の引き方で毎回変わる。2026-10-03 の板で 13.8〜25.8 mm）。ここだけ上限を別にして、数を見張る。
# **直していない**（首を塗らないようにすると、595 の GND のピンのビアが表のベタから切れて配線の道具が止まる）。open-gaps P4
IC_CELL_REACH_MAX = 30.0


def ic_cell():
    k = next(k for k in LAY.keys if LAY.hole(k)[0] < S.PART_AT["U1"][0] < LAY.hole(k)[2] and abs(k.y - S.PART_AT["U1"][1]) < 1.0)
    return L.grow(LAY.hole(k), 2.0)


def test_no_gnd_strip_ends_far_from_a_via(facts):
    far = gnd_far(facts, skip=ic_cell())
    assert set(far) == {"F.Cu", "B.Cu"}
    for layer, (d, at, cut) in far.items():
        assert d <= GND_REACH_MAX, f"{layer}: ビアから銅の上で {d:.1f} mm の所がある {at}"
        assert cut <= 40, f"{layer}: 格子の上でビアに届かない升が {cut} 個（幅 {0.5} 未満の橋の先）"
    whole = gnd_far(facts)
    assert max(d for d, _, _ in whole.values()) <= IC_CELL_REACH_MAX, whole


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
    assert body((SHIELD / "cckb_click.overlay").read_text()) == body((CCKB_SHIELD / "cckb.overlay").read_text())
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


def test_the_switch_sees_more_than_its_minimum_load_when_scanned():
    """Alps の仕様書 5.2「Minimum ratings 1 V DC 10 µA」。走査のとき、押したスイッチには 595 の High（レール）− ダイオードの Vf が
    掛かり、行のプルダウン（nRF52840 の内蔵。Nordic の PS: 11〜16 kΩ・代表 13）へ電流が流れる。レールがいちばん低いとき（電池の打ち止め 2.0 V）でも足りる。"""
    rail_min, vf_max, pull_max = 2.0, 0.25, 16e3          # V・BAT46W の保証値 @0.1 mA・Ω
    current = (rail_min - vf_max) / pull_max
    assert current > 10e-6 * 5 and rail_min > 1.0, current       # 109 µA（仕様の下限の 10 倍）


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
