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
from pathlib import Path

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


def xiao_bottom_rects():
    """XIAO の裏の露出パッド 8 個（spec.XIAO_BOTTOM_PADS）＋ XIAO_BOTTOM_CLEAR を板の上の矩形（CAD）で。
    {パッド番号: (名前, 矩形)}。表とは別に STEP・Seeed と突き合わせる（下の検査）。"""
    x, y = SPEC.XIAO_AT
    c = SPEC.XIAO_BOTTOM_CLEAR
    return {n: (name, (x + r[0] - c, y + r[1] - c, x + r[2] + c, y + r[3] + c))
            for n, (name, r) in SPEC.XIAO_BOTTOM_PADS.items()}


def xiao_slot_rects():
    """XIAO の裏の USB のシールドのめっきの長穴 4 個（spec.XIAO_BOTTOM_SLOTS）＋ XIAO_BOTTOM_CLEAR。{名前: 矩形}。"""
    x, y = SPEC.XIAO_AT
    c = SPEC.XIAO_BOTTOM_CLEAR
    return {n: (x + r[0] - c, y + r[1] - c, x + r[2] + c, y + r[3] + c)
            for n, r in SPEC.XIAO_BOTTOM_SLOTS.items()}


def _d7_control(r):
    """対照の円: D7 のパッドの上（銅がある所）。数え方が 0 しか返さないのではないことを見る。"""
    d7 = (SPEC.XIAO_AT[0] + SPEC.XIAO_PIN_SHIFT + 7.62, SPEC.XIAO_AT[1] + SPEC.XIAO_W / 2)
    return d7, r


def regions(ifc):
    """board_facts に渡す領域と、事実の copper_in の添字。{名前: (添字, 引数)}。
    [禁止域, 対照, 露出パッド 8, 金属の円（interface.metal_keepouts の順）, 金属の対照, 長穴 4]"""
    out = [("antenna", ",".join(str(v) for v in ifc.antenna_keepout())),
           ("antenna_control", ",".join(str(v) for v in _control_rect(ifc)))]
    out += [(f"pad{n}", ",".join(str(v) for v in r)) for n, (_, r) in xiao_bottom_rects().items()]
    ks = ifc.metal_keepouts()
    out += [(f"metal{i}", f"c:{c[0]},{c[1]},{r}") for i, (_, _, c, r) in enumerate(ks)]
    (cx, cy), cr = _d7_control(max(r for _, _, _, r in ks))
    out += [("metal_control", f"c:{cx},{cy},{cr}")]
    out += [(n, ",".join(str(v) for v in r)) for n, r in xiao_slot_rects().items()]
    out += [(n, ",".join(str(v) for v in r)) for n, r in psw_tab_rects(ifc).items()]
    return {n: (i, a) for i, (n, a) in enumerate(out)}


def psw_tab_rects(ifc):
    """電源スイッチの枠の爪の下（pcb_extra.psw_tab_keepouts と**同じ式を独立に**: 本体の最大＋
    METAL_COPPER_CLEAR の、真ん中の足から ±ピッチ/2 より外）を、足のランドの列（x ±PSW_PAD_D/2 ＋0.05）
    の左右に割った 4 つ。ここに表の銅（線・ビア・ベタ）が 0 であること。ランドそのものは数えない。
    対照: 同じ大きさを 12mm 左（ホルダの上・表のベタのある所）へずらした物。"""
    s = ifc.s
    x, y = s.PSW_AT
    b = I.grow(ifc.psw_body(), s.METAL_COPPER_CLEAR)
    h, c = s.PSW_PIN_PITCH / 2, s.PSW_PAD_D / 2 + 0.05
    out = {}
    for k, (y0, y1) in enumerate(((y + h, b[3]), (b[1], y - h))):
        out[f"psw_tab{k}L"] = (b[0], y0, x - c, y1)
        out[f"psw_tab{k}R"] = (x + c, y0, b[2], y1)
    r = out["psw_tab0L"]
    out["psw_tab_control"] = (r[0] - 12, r[1], r[2] - 12, r[3])
    return out


def _rect_args(ifc):
    return [a for _, a in sorted(regions(ifc).values())]


def copper_in(facts, ifc, name):
    return facts["copper_in"][regions(ifc)[name][0]]


def run_facts(board, out, ifc):
    r = subprocess.run([paths.KICAD_PYTHON, str(ROOT / "projects/cckb/tools/board_facts.py"),
                        str(board), str(out)] + _rect_args(ifc),
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def facts(tmp_path_factory, ifc):
    require(paths.KICAD_PYTHON, "板の事実の書き出し")
    return run_facts(BOARD, tmp_path_factory.mktemp("cckbpcb") / "facts.json", ifc)


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
    # 母数（物の数）: キー 62 × (スイッチ + ダイオード) ＋ 電子部品 10 ＋ 穴 11 ＋ V2 のスタビの穴 4
    assert len(facts["footprints"]) == 62 * 2 + len(circuit.electronics()) + 11 + 4
    assert len(circuit.electronics()) == 10
    copper = [p for p in facts["pads"] if not p["npth"] and p["num"]]
    # スイッチ 2・ダイオード 2・XIAO 14+7（D0〜D6 のパッド内ビア）・595 16×2・C 2×2・R 2×2・
    # D_PWR 2・ホルダ 2・電源スイッチ 3（スルーホール）
    assert len(copper) == 62 * 4 + 21 + 32 + 4 + 4 + 2 + 2 + 3
    nc = sorted(f"{p['ref']}.{p['num']}" for p in copper if not p["net"])
    # ネットの無いパッドは**宣言した NC だけ**（XIAO 5V・D1×2・D9、595 U2 の QH と QH'、
    # 電源スイッチの手前の足 3）
    assert nc == sorted(["U_MCU.5V", "U_MCU.D1", "U_MCU.D1", "U_MCU.D9", "U2.7", "U2.9",
                         "SW_PWR.3"]), nc


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
    "silk_edge_clearance",      # シルクが外形・逃げ穴に近い（刷れずに欠けるだけ）
    "silk_overlap",             # シルクどうしの重なり（読みにくいだけ）
    "silk_over_copper",
}


def board_copy(d):
    """発注する板を .kicad_pro ごと d へ同じ名前で写す。**原本を KiCad に開かせない**
    （kicad-cli の DRC は隣に .kicad_prl を書く。最終レビュー M8）。"""
    d.mkdir(parents=True, exist_ok=True)
    for suf in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(BOARD.with_suffix(suf), d / BOARD.with_suffix(suf).name)
    return d / BOARD.name


@pytest.fixture(scope="module")
def drc_record(tmp_path_factory):
    from foundry import drc

    require(paths.KICAD_CLI, "DRC")
    return drc.run(board_copy(tmp_path_factory.mktemp("drc")))


def test_the_committed_drc_record_is_what_the_drc_says_now(drc_record):
    """コミットした記録（cckb_main.drc.json・数を人が読む所）が、いまの板の DRC と同じ。
    前は検査が原本に DRC をかけて記録を書き直していた（M8）ので、古い記録は検査の副作用で
    黙って直っていた。今は写しで回して、記録と突き合わせる。"""
    from foundry import drc

    assert json.loads(drc.report_path(BOARD).read_text()) == drc_record


def test_the_routed_board_has_no_drc_violation_and_nothing_unrouted(drc_record, facts):
    r = drc_record
    print("DRC 警告の内訳:", r["warning_kinds"])
    assert r["violations"] == 0, r["details"]
    assert r["unconnected"] == 0
    assert facts["unconnected"] == 0            # KiCad の連結（pcbnew）でも 0
    assert set(r["warning_kinds"]) <= KNOWN_WARNINGS, r["warning_kinds"]
    # 数を固定する（監査 C 2 回目 軽微 3: 種類の集合だけでは名札がずれて増えても緑のままだった）。
    # silk_edge_clearance は 0。2026-09-25〜26 の 4 件（V2 のスタビのキー D42・D43・D58・D60 の名札が箱の穴に近い）は
    # 名札をダイオードの左へ動かして消した（spec.REF_TEXT_AT・監査 C 軽微 3）
    assert r["warning_kinds"].get("silk_edge_clearance", 0) == 0, r["warning_kinds"]
    assert r["warning_kinds"].get("silk_overlap", 0) == 0 and r["warning_kinds"].get("silk_over_copper", 0) == 0


def test_the_warning_count_notices_a_label_on_the_edge(tmp_path):
    """板の写しで表のシルクに文字を 1 つ外形の縁に置くと silk_edge_clearance が 0 から増える
    （数を固定した検査が名札のずれに気づく）。"""
    from foundry import drc

    require(paths.KICAD_CLI, "DRC")
    for suf in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(BOARD.with_suffix(suf), tmp_path / ("x" + suf))
    t = (tmp_path / "x.kicad_pcb").read_text()
    x = 150 - 143.175 + 0.2                      # 左の縁の 0.2 内（CAD の x −142.975・KiCad の x）
    label = (f'(gr_text "EDGE" (at {x} 100 90) (layer "F.SilkS") '
             '(effects (font (size 1 1) (thickness 0.15))))\n')
    i = t.rindex(")")
    (tmp_path / "x.kicad_pcb").write_text(t[:i] + label + t[i:])
    r = drc.run(tmp_path / "x.kicad_pcb")
    assert r["warning_kinds"].get("silk_edge_clearance", 0) > 0, r["warning_kinds"]


def test_the_drc_notices_silk_text_below_the_jlc_minimum(tmp_path):
    """**壊して落ちることを示す。**板の写しに JLC の下限（文字の高さ 1.0・線 0.15）より小さい 0.9/0.1 の文字を
    置くと、DRC が text_height・text_thickness を出す（前は KiCad の既定 0.8・0.08 のままで黙った・
    4 回目の監査 C 軽微 3。規則は foundry.pcb_rules.JLC が .kicad_pro に書く）。"""
    from foundry import drc

    require(paths.KICAD_CLI, "DRC")
    for suf in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(BOARD.with_suffix(suf), tmp_path / ("x" + suf))
    t = (tmp_path / "x.kicad_pcb").read_text()
    label = ('(gr_text "SMALL" (at 150 100 0) (layer "F.SilkS") '
             '(effects (font (size 0.9 0.9) (thickness 0.1))))\n')
    i = t.rindex(")")
    (tmp_path / "x.kicad_pcb").write_text(t[:i] + label + t[i:])
    r = drc.run(tmp_path / "x.kicad_pcb")
    kinds = set(r["warning_kinds"]) | set(r["violation_kinds"])
    assert {"text_height", "text_thickness"} <= kinds, r


def test_the_project_downgrades_no_drc_rule():
    """前は電源スイッチ（裏）の位置決めの穴がホルダのコートヤードの下に来るので npth_inside_courtyard を
    警告に下げていた。2026-09-24 に表のスルーホールの SS-12D00G3 に替えて穴が無くなったので、下げない
    （spec.DRC_SEVERITY を消した）。発注する板の .kicad_pro でも KiCad の既定（error）に戻っていること。"""
    assert not hasattr(SPEC, "DRC_SEVERITY")
    for pro in (BOARD.with_suffix(".kicad_pro"), UNROUTED.with_suffix(".kicad_pro")):
        sev = json.loads(pro.read_text())["board"]["design_settings"]["rule_severities"]
        assert sev["npth_inside_courtyard"] == "error", pro


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

JLC_REFS = re.compile(r"D\d+|U[12]|C_U[12]|R_(HI|LO)|D_PWR")
# 利用者が手で付ける物（BOM・CPL に載せない）。電源スイッチは 2026-09-24 の監査で JLC の実装から
# 外した（つまみが外形から出る。spec.NOT_ASSEMBLED・決定記録 2026-09-24-audit-fixes §R2）
HAND_REFS = ("U_MCU", "BT1", "SW_PWR")


def side_problems(facts):
    out = []
    pads = {}
    for p in facts["pads"]:
        pads.setdefault(p["ref"], []).append(p)
    jlc = [f for f in facts["footprints"] if JLC_REFS.fullmatch(f["ref"])]
    if len(jlc) != 62 + 7:
        out.append(f"JLC が実装する部品が {len(jlc)} 個（62 + 7 のはず）")
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
        if f["ref"] in HAND_REFS and not (f["exclude_bom"] and f["exclude_pos"]):
            out.append(f"{f['ref']}: 利用者が手はんだする物が BOM/CPL に載る")
        if re.fullmatch(r"SW\d+", f["ref"]) and not (f["exclude_bom"] and f["exclude_pos"]):
            out.append(f"{f['ref']}: 利用者が手はんだするスイッチが BOM/CPL に載る")
    return out


def test_jlc_parts_are_all_on_the_bottom(facts):
    assert side_problems(facts) == []


def paste_problems(facts):
    """ペーストの層（JLC はここからステンシルを作り、載せない部品のパッドにもはんだを盛る）は、
    JLC が実装する部品の SMD パッドにだけある。手はんだの部品（spec.NOT_ASSEMBLED・キーのスイッチ）には無い。"""
    out = []
    kinds = dict((f["ref"], next((k for pat, k in SPEC.FAB_KINDS.items() if re.fullmatch(pat, f["ref"])),
                                 "keyswitch" if re.fullmatch(r"SW\d+", f["ref"]) else None))
                 for f in facts["footprints"])
    for p in facts["pads"]:
        hand = kinds.get(p["ref"]) in SPEC.NOT_ASSEMBLED
        if hand and p["paste"]:
            out.append(f"{p['ref']}.{p['num']}: 手はんだの部品のパッドにペースト")
        if JLC_REFS.fullmatch(p["ref"]) and p["smd"] and not p["paste"]:
            out.append(f"{p['ref']}.{p['num']}: JLC が実装するパッドにペーストが無い")
    return out


def test_only_the_jlc_parts_get_solder_paste(facts):
    """監査 B 2 回目 B2-1・C 軽微 1: 手はんだの電源スイッチの 7 パッドに B.Paste があり、盛られて届いた。"""
    assert paste_problems(facts) == []
    assert sum(1 for p in facts["pads"] if p["paste"]) == 62 * 2 + 2 + 2 * 2 + 2 * 2 + 2 * 16


def test_the_paste_check_notices_paste_on_the_power_switch(facts):
    f = copy.deepcopy(facts)
    next(p for p in f["pads"] if p["ref"] == "SW_PWR" and p["num"] == "2")["paste"] = True
    assert any("SW_PWR.2" in b for b in paste_problems(f))


def test_the_side_check_notices_a_part_on_top(facts):
    f = copy.deepcopy(facts)
    for p in f["pads"]:
        if p["ref"] == "C_U1":
            p["front"], p["back"] = True, False
    assert any("C_U1" in b for b in side_problems(f))


def test_the_side_check_notices_the_power_switch_back_in_the_bom(facts):
    f = copy.deepcopy(facts)
    for fp in f["footprints"]:
        if fp["ref"] == "SW_PWR":
            fp["exclude_bom"] = fp["exclude_pos"] = False
    assert any("SW_PWR" in b for b in side_problems(f))


# ---------------------------------------------------------------------------
# (c2) **発注道具の出力**（Fabrication Toolkit の BOM・CPL）で JLC が置く位置 = 板のパッド
# ---------------------------------------------------------------------------
# 監査 B の照合: JLC は CPL の座標に**自分の部品データ（EasyEDA）の原点**を置き、回転 R をかける。
# 裏の部品は「裏から見て反時計回りに R」（= R 回してから左右を裏返す。Fabrication Toolkit と KiKit
# が同じ式。ほかの 3 通りの裏返し方では 69 個のうち 60 個以上が 3.3mm 以上ずれることを確かめた）。EasyEDA のパッドを番号ごとに板の同じ番号のパッドと比べる。
# 部品データは tests/fixtures/easyeda/footprints.json（API から取った原点とパッド）

FT_PLUGIN = Path.home() / "Documents/KiCad/10.0/3rdparty/plugins"
EE_UNIT = 0.254


def _ee_pads(part):
    ox, oy = part["head"]
    return {n: ((x - ox) * EE_UNIT, -(y - oy) * EE_UNIT) for n, (x, y, _, _) in part["pads"].items()}


def cpl_misplacements(rows, lcsc_of, facts, ee, tol=0.15):
    """[(参照名, 最大のずれ mm)] で tol を超えたもの（パッドの番号が合わない物は inf）。"""
    ORIGIN = facts["origin"]
    board_pads = facts["pads"]
    out = []
    for r in rows:
        ref = r["Designator"]
        pads = _ee_pads(ee[lcsc_of[ref]])
        mid = (float(r["Mid X"]), float(r["Mid Y"]))
        a = math.radians(float(r["Rotation"]))
        bottom = r["Layer"] == "bottom"
        act = {p["num"]: (p["pos"][0] + ORIGIN[0], p["pos"][1] - ORIGIN[1])     # KiCad の (x, −y)
               for p in board_pads if p["ref"] == ref and p["num"] and not p["npth"]}
        if set(act) != set(pads):
            out.append((ref, math.inf))
            continue
        worst = 0.0
        for n, (x, y) in pads.items():
            rx, ry = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
            if bottom:                  # 回してから左右を裏返す（上から見た座標で）
                rx = -rx
            px, py = mid[0] + rx, mid[1] + ry
            worst = max(worst, math.dist((px, py), act[n]))
        if worst > tol:
            out.append((ref, round(worst, 3)))
    return out


@pytest.fixture(scope="module")
def production_dir(tmp_path_factory):
    """**実際に発注する道具**（Fabrication Toolkit・`-t`）を板の写しに通した出力の置き場（production/）。"""
    require(paths.KICAD_PYTHON, "Fabrication Toolkit")
    # 発注の CPL を確かめる検査。**REQUIRE_KICAD=1 なら無いのは赤**（前は黙って skip した。I6）
    require(FT_PLUGIN / "com_github_bennymeg_JLC-Plugin-for-KiCad", "Fabrication Toolkit")
    d = tmp_path_factory.mktemp("ft")
    for suf in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(BOARD.with_suffix(suf), d / ("cckb_main" + suf))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "com_github_bennymeg_JLC-Plugin-for-KiCad.cli",
                        "-p", str(d / "cckb_main.kicad_pcb"), "-t", "-nI", "-nB"],
                       cwd=FT_PLUGIN, capture_output=True, text=True, timeout=600)
    prod = d / "production"
    assert (prod / "positions.csv").exists(), r.stdout[-2000:] + r.stderr[-2000:]
    return prod


@pytest.fixture(scope="module")
def production(production_dir):
    """発注の道具が出した BOM と CPL。"""
    import csv

    prod = production_dir
    rows = list(csv.DictReader((prod / "positions.csv").open(encoding="utf-8-sig")))
    bom = list(csv.DictReader((prod / "bom.csv").open(encoding="utf-8-sig")))
    return rows, bom


def test_jlc_places_every_part_of_the_cpl_on_its_pads(production, facts):
    rows, bom = production
    ee = json.loads((ROOT / "tests/fixtures/easyeda/footprints.json").read_text())["parts"]
    lcsc_of = {d.strip(): b["LCSC Part #"] for b in bom for d in b["Designator"].split(",")}
    refs = sorted(r["Designator"] for r in rows)
    assert len(rows) == 62 + 7 and "SW_PWR" not in refs and sum(
        len(b["Designator"].split(",")) for b in bom) == 69, (len(rows), bom)
    assert set(lcsc_of) == set(refs) and all(r["Layer"] == "bottom" for r in rows)
    assert all(c in ee for c in lcsc_of.values()), set(lcsc_of.values()) - set(ee)
    assert cpl_misplacements(rows, lcsc_of, facts, ee) == []


@pytest.mark.parametrize("ref, drot, dx", [("U1", 180, 0.0), ("D1", 90, 0.0), ("D_PWR", 0, 0.45)])
def test_the_cpl_check_notices_a_turned_or_shifted_part(production, facts, ref, drot, dx):
    """**壊すと落ちる**: 回転を 180°/90° 違える・原点を 0.45（B-1 の電源スイッチのずれ）ずらす。"""
    rows, bom = production
    ee = json.loads((ROOT / "tests/fixtures/easyeda/footprints.json").read_text())["parts"]
    lcsc_of = {d.strip(): b["LCSC Part #"] for b in bom for d in b["Designator"].split(",")}
    rows = copy.deepcopy(rows)
    r = next(r for r in rows if r["Designator"] == ref)
    r["Rotation"] = str((float(r["Rotation"]) + drot) % 360)
    r["Mid X"] = str(float(r["Mid X"]) + dx)
    assert [m[0] for m in cpl_misplacements(rows, lcsc_of, facts, ee)] == [ref]


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
    # 電池の電圧: adc 0 = AIN0 = P0.02 = D0（zmk-and-xiao.md「ADC は D0〜D5 だけ（P0.02/03/28/29/04/05）」）。
    # nRF52840: P0.02 = AIN0・P0.03 = AIN1・P0.28 = AIN4・P0.29 = AIN5・P0.04 = AIN2・P0.05 = AIN3
    # （AIN7 = P0.31 は XIAO の中の分圧。前は D4・D5 を 7・2 と書いていた・4 回目の監査 F 軽微 1）
    ain = {0: "D0", 1: "D1", 4: "D2", 5: "D3", 2: "D4", 3: "D5"}.get(adc)
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
    keep, ctrl = facts["copper_in"][:2]
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


def xiao_underside_problems(facts):
    """XIAO の下の表: ルール領域 XIAO_UNDERSIDE（表だけ・配線/ビア/ベタ禁止）があり、露出パッド
    8 個それぞれ（＋ XIAO_BOTTOM_CLEAR）を覆う。塗った後の表の銅（ベタ・線・ビア・パッド）が 8 個の
    どの矩形の中にも 0。本体の矩形の中に表の線の端点もビアも無い。"""
    out = []
    zs = [z for z in facts["zones"] if z["name"] == "XIAO_UNDERSIDE"]
    if not zs or any(z["layers"] != ["F.Cu"] or not (z["no_vias"] and z["no_tracks"] and z["no_fill"])
                     for z in zs):
        out.append(f"XIAO_UNDERSIDE のルール領域 {zs}")
    rects = dict(xiao_bottom_rects())
    rects.update({n: (n, r) for n, r in xiao_slot_rects().items()})
    idx = regions(I.Interface())
    for n, (name, r) in rects.items():
        cu = facts["copper_in"][idx[f"pad{n}" if f"pad{n}" in idx else n][0]]
        if cu["rect"] != list(r):
            out.append(f"{n} {name}: 事実の矩形の順がずれた")
        if not any(z["outline"][0] <= r[0] + 1e-3 and z["outline"][1] <= r[1] + 1e-3 and
                   z["outline"][2] >= r[2] - 1e-3 and z["outline"][3] >= r[3] - 1e-3 for z in zs):
            out.append(f"{n} {name}: 禁止域に覆われていない")
        if cu["area"]["F.Cu"] > 0:
            out.append(f"{n} {name}: 表の銅 {cu['area']['F.Cu']} mm²")
    body = max(zs, key=lambda z: (z["outline"][2] - z["outline"][0]) * (z["outline"][3] - z["outline"][1]))
    x0, y0, x1, y1 = body["outline"]
    for tr in facts["tracks"]:
        if tr["layer"] == "F.Cu":
            for q in (tr["a"], tr["b"]):
                if x0 < q[0] < x1 and y0 < q[1] < y1:
                    out.append(f"XIAO の下に表の線 {tr['net']} {q}")
    for v in facts["vias"]:
        if x0 - 0.3 < v["pos"][0] < x1 + 0.3 and y0 - 0.3 < v["pos"][1] < y1 + 0.3:
            out.append(f"XIAO の下にビア {v['net']} {v['pos']}")
    return out


def test_nothing_on_top_under_the_xiao(facts, ifc):
    """XIAO の裏の露出パッド 8 個（SWDIO・SWCLK・EN・GND・VBAT・GND・NFC1・NFC2）と USB のシールドの
    めっきの長穴 4 個の下に表の銅を置かない。**名指しで 12 個全部**（前は 6 個しか数えず、NFC2 の真下に
    D7 のパッドと GND のビアがあった。長穴は 2 回目の監査 D 軽微 4 で足した）。"""
    assert len(SPEC.XIAO_BOTTOM_PADS) == 8 and len(SPEC.XIAO_BOTTOM_SLOTS) == 4
    assert xiao_underside_problems(facts) == []


def test_the_underside_check_notices_the_old_long_xiao_pad(tmp_path, ifc):
    """**板の写しで D7 のパッドを前の長さ（縁から内 2.85・パッド 3.45）に戻すと** NFC2 の下に銅が出て落ちる。"""
    require(paths.KICAD_PYTHON, "板の事実の書き出し")
    t = BOARD.read_text()
    i = t.index('(property "Reference" "U_MCU"')
    blk = t.rfind("(footprint", 0, i)
    m = re.compile(r'\(pad "D7" smd rect\s*\(at (-?[\d.]+) (-?[\d.]+)( -?[\d.]+)?\)\s*\(size ([\d.]+) ([\d.]+)\)')
    hit = m.search(t, blk)
    assert hit and abs(float(hit.group(1)) - 8.09) < 1e-3 and float(hit.group(4)) == 2.8, \
        hit and hit.group(0)
    old = (f'(pad "D7" smd rect (at 7.765 {hit.group(2)}{hit.group(3) or ""}) (size 3.45 {hit.group(5)})')
    b2 = tmp_path / "x.kicad_pcb"
    b2.write_text(t[:hit.start()] + old + t[hit.end():])
    f = run_facts(b2, tmp_path / "f.json", ifc)
    bad = xiao_underside_problems(f)
    assert any("NFC2" in b and "表の銅" in b for b in bad), bad


def test_the_xiao_bottom_pads_are_the_official_ones(xiao_bottom_faces):
    """spec.XIAO_BOTTOM_PADS = 公式 STEP の下面の露出した面（**毎回数える: 8 個**）∪ Seeed 公式の
    フットプリント XIAO-nRF52840-SMD のパッド 15〜22（tests/fixtures/seeed_xiao）。名前は Seeed の記号。"""
    step, seeed, names = xiao_bottom_faces
    assert len(step) == 8 and len(seeed) == 8
    got = {}
    for f in step:
        c = ((f[0] + f[2]) / 2, (f[1] + f[3]) / 2)
        n = min(seeed, key=lambda k: math.dist(c, ((seeed[k][0] + seeed[k][2]) / 2,
                                                  (seeed[k][1] + seeed[k][3]) / 2)))
        s = seeed[n]
        assert math.dist(c, ((s[0] + s[2]) / 2, (s[1] + s[3]) / 2)) < 0.15, (n, f, s)
        got[n] = (names[n], (min(f[0], s[0]), min(f[1], s[1]), max(f[2], s[2]), max(f[3], s[3])))
    assert sorted(got) == sorted(SPEC.XIAO_BOTTOM_PADS) == [str(i) for i in range(15, 23)]
    for n, (name, r) in got.items():
        want = SPEC.XIAO_BOTTOM_PADS[n]
        assert want[0] == name and all(abs(a - b) < 2e-3 for a, b in zip(r, want[1])), (n, r, want)


@pytest.fixture(scope="module")
def xiao_bottom_faces():
    """公式 STEP の下面（Y −0.24）の平らな面で、XIAO の縁（幅方向）に触れないもの＝露出パッド、と
    Seeed 公式のフットプリントのパッド 15〜22。どちらも**板の上の向き・XIAO の本体の中心から**
    (x0, y0, x1, y1)。"""
    from build123d import GeomType, import_step

    step = import_step(str(paths.LIB / "xiao.3dshapes" / "XIAO_nRF52840.step"))
    board = max(step.solids(), key=lambda so: so.bounding_box().size.X * so.bounding_box().size.Z)
    bb = board.bounding_box()
    cx, cz = (bb.min.X + bb.max.X) / 2, (bb.min.Z + bb.max.Z) / 2
    chip = [so for so in step.solids() if abs(so.bounding_box().size.X - 1.6) < 0.01
            and abs(so.bounding_box().size.Z - 3.2) < 0.01][0].bounding_box()
    front = 1 if (chip.min.Z + chip.max.Z) / 2 > cz else -1
    faces = []
    for f in board.faces():
        b = f.bounding_box()
        if f.geom_type == GeomType.PLANE and abs(b.max.Y - b.min.Y) < 1e-3 and \
                abs(b.min.Y + 0.24) < 0.005 and \
                not (abs(b.min.Z - bb.min.Z) < 0.01 or abs(b.max.Z - bb.max.Z) < 0.01):
            xs = sorted([-(b.min.X - cx), -(b.max.X - cx)])
            ys = sorted([-front * (b.min.Z - cz), -front * (b.max.Z - cz)])
            faces.append((xs[0], ys[0], xs[1], ys[1]))
    fx = ROOT / "tests" / "fixtures" / "seeed_xiao"
    text = (fx / "XIAO-nRF52840-SMD.kicad_mod").read_text()
    pads = {}
    for m in re.finditer(r'\(pad "(\d+)" smd \w+\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)\s*'
                         r'\(size ([\d.]+) ([\d.]+)\)', text):
        n, x, y, r, w, h = m.groups()
        x, y, w, h = float(x), float(y), float(w), float(h)
        if int(float(r or 0)) % 180 == 90:
            w, h = h, w
        pads[n] = (x, y, w, h)
    # ピンの並びの中心（D0 = 1・D7 = 8 の列の中点、1〜7 の長手の中点）。フットプリントの長手 y は
    # USB が −y、幅 x は D0〜D6 が −x。板の上では長手 → x（USB が −x）・幅 → y（D0〜D6 が −y）。
    # ピンの並びの中心は本体の中心から +x へ XIAO_PIN_SHIFT（spec）
    gx, gy = (pads["1"][0] + pads["8"][0]) / 2, (pads["1"][1] + pads["7"][1]) / 2
    seeed = {}
    for n in map(str, range(15, 23)):
        x, y, w, h = pads[n]
        dx, dy = (y - gy) + SPEC.XIAO_PIN_SHIFT, x - gx
        seeed[n] = (dx - h / 2, dy - w / 2, dx + h / 2, dy + w / 2)
    names = json.loads((fx / "pins.json").read_text())["pins"]
    return faces, seeed, names


# ---------------------------------------------------------------------------
# パッドの中にビアを置かない（JLC PCBA FAQ Part 2 Q17: パッドの上のビアははんだを吸う）
# ---------------------------------------------------------------------------

# 意図したパッド内ビア: XIAO の手前の列 D0〜D6 のパッドの外寄りにある同じ番号のスルーホール
# （lib/xiao.pretty・open-gaps P6。手はんだ）。**名指しで 7 個**
INTENDED_VIA_IN_PAD = {("U_MCU", f"D{i}") for i in range(7)}


def via_in_pad(facts):
    """銅のパッド（NPTH を除く全部）に、ビア（と φ0.4 以下の穴のスルーホールパッド）の輪が掛かる組。
    [(ビアの持ち主, 位置, パッドの持ち主.番号)]。丸いパッドは円、ほかは外接矩形で見る（回っていても
    90° おき。電源スイッチの角を落とした耳は矩形で見るので厳しい側）。"""
    holes = [("via", v["pos"], v["d"] / 2) for v in facts["vias"]]
    holes += [(f"{p['ref']}.{p['num']}", p["pos"], (p["box"][2] - p["box"][0]) / 2)
              for p in facts["pads"] if not p["npth"] and 0 < p["drill"] <= 0.4]
    out = []
    for p in facts["pads"]:
        if p["npth"] or p["drill"] > 0 and p["drill"] <= 0.4:
            continue
        b = p["box"]
        for who, (x, y), r in holes:
            if p["round"]:                    # 丸いパッドは円で（外接矩形の角で誤って当たる）
                hit = math.dist((x, y), p["pos"]) < r + (b[2] - b[0]) / 2
            else:
                hit = math.hypot(max(b[0] - x, 0, x - b[2]), max(b[1] - y, 0, y - b[3])) < r
            if hit:
                out.append((who, (x, y), f"{p['ref']}.{p['num']}"))
    return out


def test_no_via_inside_any_pad(facts):
    """全部の銅のパッドについて、ビアの輪が掛からない。例外は XIAO の D0〜D6 の 7 個だけ（名指し・数を固定）。
    前は縫いのビアが C_U1（JLC がリフローで付ける 0805）と BT1 の GND パッドの中にあった（監査 C 重要 1）。"""
    hits = via_in_pad(facts)
    intended = [h for h in hits if tuple(h[0].split(".")) in INTENDED_VIA_IN_PAD
                and h[2] == h[0]]
    # XIAO のパッド内ビアは同じ番号の SMD パッドの中（別の番号には掛からない）
    xiao = [h for h in hits if h[0].startswith("U_MCU.")]
    assert all(h[2] == h[0] for h in xiao), xiao
    assert len(xiao) == 7 and {h[0] for h in xiao} == {f"U_MCU.D{i}" for i in range(7)}, xiao
    assert [h for h in hits if not h[0].startswith("U_MCU.")] == [], hits
    assert intended == xiao


def test_the_via_in_pad_check_notices_a_via_on_the_c_u1_pad(facts):
    f = copy.deepcopy(facts)
    p = next(p for p in f["pads"] if p["ref"] == "C_U1" and p["num"] == "2")
    f["vias"].append(dict(net="GND", pos=[p["box"][0] + 0.35, p["pos"][1]], d=0.6, drill=0.3))
    with pytest.raises(AssertionError):
        test_no_via_inside_any_pad(f)


# ---------------------------------------------------------------------------
# 基板の面に当たる金属（キーの下のナット 9・H3 のインサート）の下に、当たる側の銅を置かない
# （監査 E 1 回目 重要 3・2 回目 重要 1: 配線し直しで H5・H6 のナットの下を CS が通った）
# ---------------------------------------------------------------------------

HOLE_REFS = re.compile(r"H\d+|H_LID")


def metal_problems(facts, ifc):
    """**取付の穴を板から数えて**（母数）、どの穴にも金属の判定があり、面に当たる金属の円
    （＋ METAL_COPPER_CLEAR）の中に、当たる側の線・ビア・塗った後の銅が 0 か。"""
    out = []
    holes = sorted(f["ref"] for f in facts["footprints"] if HOLE_REFS.fullmatch(f["ref"]))
    metal = ifc.metal_on_pcb()
    judged = sorted({m["ref"] for m in metal})
    if holes != judged or len(holes) != len(ifc.mounts()) + 1:
        out.append(f"板の取付の穴 {holes} と金属の判定 {judged} が違う")
    pos = {f["ref"]: f["pos"] for f in facts["footprints"]}
    for m in metal:
        if m["ref"] in pos and math.dist(pos[m["ref"]], m["pos"]) > 1e-3:
            out.append(f"{m['ref']}: 板の穴 {pos[m['ref']]} と金属の位置 {m['pos']} が違う")
    ks = ifc.metal_keepouts()
    zs = [z for z in facts["zones"] if z["name"] == "METAL_KEEPOUT"]
    idx = regions(ifc)
    for i, (ref, layer, (hx, hy), r) in enumerate(ks):
        if not any(z["layers"] == [layer] and z["no_tracks"] and z["no_vias"] and z["no_fill"]
                   and z["outline"][0] <= hx - r + 1e-3 and z["outline"][2] >= hx + r - 1e-3
                   and z["outline"][1] <= hy - r + 1e-3 and z["outline"][3] >= hy + r - 1e-3
                   for z in zs):
            out.append(f"{ref}: 円を覆う METAL_KEEPOUT（{layer}・線/ビア/ベタ禁止）が無い")
        for tr in facts["tracks"]:
            if tr["layer"] != layer:
                continue
            d = I.seg_dist((hx, hy), tr["a"], tr["b"]) - tr["w"] / 2
            if d < r:
                out.append(f"{ref}: {layer} の線 {tr['net']} が中心から {d:.3f}")
        for v in facts["vias"]:
            d = math.dist((hx, hy), v["pos"]) - v["d"] / 2
            if d < r:
                out.append(f"{ref}: ビア {v['net']} が中心から {d:.3f}")
        cu = facts["copper_in"][idx[f"metal{i}"][0]]
        if cu["rect"][0] != "c" or abs(cu["rect"][1] - hx) > 1e-9 or abs(cu["rect"][3] - r) > 1e-9:
            out.append(f"{ref}: 事実の円がずれた {cu['rect']}")
        elif cu["area"][layer] > 0:
            out.append(f"{ref}: 円の中の {layer} の銅 {cu['area'][layer]} mm²")
    if len(zs) != len(ks):
        out.append(f"METAL_KEEPOUT が {len(zs)} 個（面に当たる金属は {len(ks)} 個）")
    return out


def test_every_mount_hole_is_judged_and_the_metal_touches_only_the_top():
    """母数: 取付の穴 11（H0〜H9・H_LID）。面に当たる金属は上面のナット 9・インサート 1（H3）で、
    下面に当たる金属は 0（ネジの頭はトレイの中。基板の下はトレイの樹脂のボス）。H_LID は樹脂の柱が
    穴を通るだけで、インサートとネジは基板より上。"""
    ifc = I.Interface()
    touch = [(m["ref"], m["what"], m["side"]) for m in ifc.metal_on_pcb() if m["side"]]
    assert sorted(touch) == sorted([(f"H{i}", "nut", "F.Cu") for i in range(10) if i != 3]
                                   + [("H3", "insert", "F.Cu")]), touch
    assert len(ifc.metal_keepouts()) == 10


def test_nothing_under_the_metal_on_the_board(facts, ifc):
    assert metal_problems(facts, ifc) == []
    # 対照: 同じ半径の円を D7 のパッドの上へ置くと表の銅が数えられる（数え方が 0 しか返さないのではない）
    assert copper_in(facts, ifc, "metal_control")["area"]["F.Cu"] > 1.0


@pytest.mark.parametrize("ref", ["H5", "H6", "H0"])
def test_the_metal_check_notices_a_track_under_a_nut(facts, ifc, ref):
    """2 回目の監査で見つかった形: CS の表の線がナットの中心から 1.603 を横に通る（H5・H6）。"""
    f = copy.deepcopy(facts)
    (hx, hy) = next(m["pos"] for m in ifc.metal_on_pcb() if m["ref"] == ref)
    f["tracks"].append(dict(net="CS", layer="F.Cu", a=[hx - 3, hy - 1.703], b=[hx + 3, hy - 1.703],
                            w=0.2))
    assert any(ref in b and "CS" in b for b in metal_problems(f, ifc))


def test_the_metal_check_notices_a_missing_hole_judgement(facts, ifc):
    f = copy.deepcopy(facts)
    f["footprints"].append(dict(f["footprints"][0], ref="H10"))
    assert any("H10" in b for b in metal_problems(f, ifc))


# ---------------------------------------------------------------------------
# ベタへの繋ぎ方（spec.THERMAL_PADS だけサーマル）
# ---------------------------------------------------------------------------

def test_the_thermal_pads_are_exactly_the_declared_ones(facts):
    got = sorted((p["ref"], p["num"]) for p in facts["pads"] if p.get("thermal"))
    want = sorted((r, n) for r, ns in SPEC.THERMAL_PADS.items() for n in ns)
    assert got == want, got
    assert all(p["net"] == "GND" for p in facts["pads"] if p.get("thermal"))


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


# 2.4GHz の λ/4 は FR4 の上で約 17mm（監査 D 軽微 4）。ビア 1 本だけで繋がった島はその 1 本を根元にした
# 棒になるので、長さをこの 7 割（12mm）未満に抑える。route_pcb の double_single_via_islands が 2 本目を打つ
SINGLE_VIA_ISLAND_MAX = 12.0


def island_problems(facts):
    out = []
    for i in facts["islands"]:
        L = max(i["box"][2] - i["box"][0], i["box"][3] - i["box"][1])
        if i["vias"] == 0:
            out.append(f"ビアの無い GND の島 {i}")
        elif i["vias"] == 1 and L >= SINGLE_VIA_ISLAND_MAX:
            out.append(f"ビア 1 本の島が長さ {L:.1f}mm（{i['layer']}・{i['area']} mm²）")
    return out


def test_no_long_gnd_island_hangs_on_a_single_via(facts):
    assert island_problems(facts) == []
    ones = [i for i in facts["islands"] if i["vias"] == 1]
    rec = json.loads((BOARD.parent / "route.json").read_text())
    print("ビア 1 本の島:", [(i["layer"], i["area"]) for i in ones])
    assert len(ones) == len(rec["single_via_islands"])        # 道具の記録と板が同じ数


def test_the_island_check_notices_a_long_single_via_island(facts):
    """前の板（HEAD 86611d4）には B.Cu に長さ 18.9mm・ビア 1 本の島があった。それを写しに作ると落ちる。"""
    f = copy.deepcopy(facts)
    i = max(f["islands"], key=lambda i: i["area"])
    f["islands"].append(dict(i, vias=1, box=[-62.7, -2.0, -43.8, 2.0]))
    assert island_problems(f)


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
    assert n == 8 * 4                        # V2 の箱の穴は矩形 8 つ（Enter・左 Shift・スペース 2 つの左右）


# スタビ（遊舎工房 A050001-01-1）の基板の穴。**2026-09-26 に利用者と決めた値**（販売者の足跡〔実物の実測〕が正・
# 仕入れ先の図は参照。決定記録 2026-09-25-choc-v2 §10-9）。スタビの座標（支点・箱の中心から。y はワイヤ〔爪〕の側が +。
# 板ではワイヤは奥 = CAD の +y）。生成器の定数（mech.CHOC_V2_STAB_HOLES）とは比べず、決めた数そのものと板を比べる
STAB_DECIDED = dict(pivot=11.9, screw=(-6.2, 3.0), claw=(8.24, 4.0), box=(3.0, 4.0), keepout=2.6)


def stab_board_problems(facts, ifc, decided=STAB_DECIDED):
    """発注する板のスタビ 4 つ（ST\\d+）が決めた形か:
      (1) ねじ・爪の穴が**丸い非めっき**で、支点（キーの中心 ± 11.9）の x に揃い、y と径が決めた値（長円は 0）
      (2) 箱の穴（Edge.Cuts）が支点 ± 3.0 × ±4.0 の矩形で、ほかの Edge.Cuts の線がスタビの周りに無い
      (3) 穴の中心から半径 2.6 の中に、線・ビア・パッド（その穴のほか）が無い（両面）。塗ったベタは GND だけ
    """
    D = decided
    out = []
    stabs = [f for f in facts["footprints"] if re.fullmatch(r"ST\d+", f["ref"])]
    keys = {(round(x, 3), round(y, 3)) for x, y in
            (((a[0] + b[0]) / 2, a[1]) for a, b in zip(ifc.stab_pivots()[::2], ifc.stab_pivots()[1::2]))}
    if len(stabs) != 4 or {(round(f["pos"][0], 3), round(f["pos"][1], 3)) for f in stabs} != keys:
        out.append(f"スタビ {len(stabs)} 個・位置 {[f['pos'] for f in stabs]}（2.25u のキー 4 つ {sorted(keys)}）")
    sws = {(round(f["pos"][0], 3), round(f["pos"][1], 3)) for f in facts["footprints"] if re.fullmatch(r"SW\d+", f["ref"])}
    centres = []
    for f in stabs:
        fx, fy = f["pos"]
        if (round(fx, 3), round(fy, 3)) not in sws:
            out.append(f"{f['ref']} がスイッチの中心に無い")
        pads = [p for p in facts["pads"] if p["ref"] == f["ref"]]
        want = sorted((round(sd * D["pivot"], 3), round(D[k][0], 3), D[k][1])
                      for sd in (-1, 1) for k in ("screw", "claw"))
        got = sorted((round(p["pos"][0] - fx, 3), round(p["pos"][1] - fy, 3), p["drill"]) for p in pads)
        if got != want:
            out.append(f"{f['ref']} の穴 {got}（決めた値 {want}）")
        for p in pads:
            if not p["npth"] or p["slot"] or p["drill_wh"][0] != p["drill_wh"][1] or not p["round"]:
                out.append(f"{f['ref']} の穴 {p['pos']} が丸い非めっきでない（{p['drill_wh']}・slot {p['slot']}）")
            centres.append((f["ref"], p["pos"], p["drill"]))
        # 箱の穴: 矩形 4 辺が Edge.Cuts にあり、スタビの周り（キーの中心 ±17 × ±11）の Edge.Cuts はそれだけ
        segs = [(tuple(e["a"]), tuple(e["b"])) for e in facts["edge"]
                if e["shape"] == "Line" and abs(e["a"][0] - fx) < 17 and abs(e["a"][1] - fy) < 11
                and abs(e["b"][0] - fx) < 17 and abs(e["b"][1] - fy) < 11]
        want_e = set()
        for sd in (-1, 1):
            x0, x1 = sorted((fx + sd * (D["pivot"] - D["box"][0]), fx + sd * (D["pivot"] + D["box"][0])))
            y0, y1 = fy - D["box"][1], fy + D["box"][1]
            c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            want_e |= {frozenset(((round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))))
                       for a, b in zip(c, c[1:] + c[:1])}
        got_e = {frozenset(((round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3)))) for a, b in segs}
        if got_e != want_e:
            out.append(f"{f['ref']} の箱の穴（Edge.Cuts）が違う: 余分 {len(got_e - want_e)}・足りない {len(want_e - got_e)}")
    if len(centres) != 16:
        out.append(f"スタビの穴 {len(centres)}（16 のはず）")
    r = D["keepout"]
    for ref, c, _ in centres:
        for tr in facts["tracks"]:
            g = seg_point_dist(c, tr["a"], tr["b"]) - tr["w"] / 2
            if g < r:
                out.append(f"{ref} の穴 {c} の {r} の中に線 {tr['net']} {tr['layer']}（{g:.3f}）")
        for v in facts["vias"]:
            g = math.dist(c, v["pos"]) - v["d"] / 2
            if g < r:
                out.append(f"{ref} の穴 {c} の {r} の中にビア {v['net']}（{g:.3f}）")
        for p in facts["pads"]:
            if p["pos"] == c and p["ref"] == ref:
                continue
            if I.circle_rect_gap(c, r, p["box"]) < 0:
                out.append(f"{ref} の穴 {c} の {r} の中にパッド {p['ref']}.{p['num']} {p['net']}")
    bad_zones = sorted({z["net"] for z in facts["zones"] if not z["rule"] and z["net"] != "GND"})
    if bad_zones:
        out.append(f"GND のほかのベタ {bad_zones}（穴の周りに入りうる）")
    return out


def seg_point_dist(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def test_the_stab_holes_are_what_we_decided(facts, ifc):
    assert stab_board_problems(facts, ifc) == []


def _stab_hole(f, kind="screw"):
    st = next(x for x in f["footprints"] if x["ref"] == "ST42")
    d = STAB_DECIDED[kind]
    return next(p for p in f["pads"] if p["ref"] == "ST42" and
                abs(p["pos"][1] - st["pos"][1] - d[0]) < 1e-3 and p["pos"][0] > st["pos"][0])


def _stab_track(f):
    c = _stab_hole(f)["pos"]
    f["tracks"].append(dict(net="COL13", layer="F.Cu", a=[c[0] - 5, c[1] + 2.6], b=[c[0] + 5, c[1] + 2.6], w=0.2))


def _stab_via(f):
    c = _stab_hole(f, "claw")["pos"]
    f["vias"].append(dict(net="GND", pos=[c[0] + 2.8, c[1]], d=0.6, drill=0.3))


def _stab_move(f):
    p = _stab_hole(f)
    p["pos"] = [p["pos"][0] + 0.1, p["pos"][1]]


def _stab_oval(f):
    p = _stab_hole(f)
    p.update(slot=True, drill_wh=[3.2, 3.4], drill=3.2)


def _stab_big(f):
    _stab_hole(f, "claw")["drill"] = 4.4


def _stab_window(f):
    """前の板の箱の穴（支点 12.0 から −3.1〜3.0 ＋ 片側 0.3）に戻す。"""
    for e in f["edge"]:
        for k in ("a", "b"):
            if abs(e[k][0] - (121.44375 + 11.9 + 3.0)) < 1e-3:
                e[k] = [e[k][0] + 0.4, e[k][1]]


def _stab_zone(f):
    f["zones"].append(dict(name="V3V3_F", net="V3V3", rule=False, layers=["F.Cu"], outline=[0, 0, 1, 1],
                           area={"F.Cu": 1.0}, outlines={"F.Cu": 1}))


@pytest.mark.parametrize("breaker", [_stab_track, _stab_via, _stab_move, _stab_oval, _stab_big, _stab_window, _stab_zone])
def test_the_stab_hole_check_notices_a_break(facts, ifc, breaker):
    f = copy.deepcopy(facts)
    breaker(f)
    assert stab_board_problems(f, ifc), breaker.__name__


# JLC の PCB Capabilities（https://jlcpcb.com/capabilities/pcb-capabilities・2026-09-26 に読んだ）:
# 「The length of the slot should be at least 2 times of the width」・非めっきの長円の最小幅 1.0・長円の公差は非めっき ±0.2。
# 丸穴の公差は ±0.08 前後（JLC のブログ npth-design-guide）。**KiCad の DRC はこの比を見ない。**
# V2 の 1 回目の板（sha256 dae52e33…）は位置決め 1.6 × 2.0 ×62・スタビのねじ 3.2 × 3.4 ×8・爪 4.2 × 4.4 ×8 の
# 78 個が比 1.05〜1.25 だった（2026-09-26 の監査 C 重要 1）
SLOT_MIN_RATIO = 2.0
NPTH_SLOT_MIN_W = 1.0
PTH_SLOT_MIN_W = 0.5


def slot_problems(pads):
    """長円の穴で、長さ/幅 < 2 か、幅が JLC の最小を割る物。pads は事実の pads（drill_wh・slot）。**例外は無い**
    （2026-09-26 にスタビのねじ・爪の長円 16 を丸にして、保留していた例外 HELD_STAB_SLOTS を消した）。"""
    out = []
    for p in pads:
        if not p["slot"]:
            continue
        lo, hi = sorted(p["drill_wh"])
        if hi < SLOT_MIN_RATIO * lo - 1e-9:
            out.append(f"{p['ref']} の長円 {p['drill_wh']}（長さ/幅 {hi / lo:.2f} < {SLOT_MIN_RATIO}）")
        if lo < (NPTH_SLOT_MIN_W if p["npth"] else PTH_SLOT_MIN_W) - 1e-9:
            out.append(f"{p['ref']} の長円の幅 {lo}")
    return out


def test_every_slot_on_the_board_is_long_enough_or_round(facts):
    holes = [p for p in facts["pads"] if p["drill"] > 0]
    slots = [p for p in holes if p["slot"]]
    npth = [p for p in holes if p["npth"]]
    print(f"穴 {len(holes)}（非めっき {len(npth)}）・長円 {len(slots)}")
    # 母数: 非めっきはキーごとに中心 1・位置決め 1（62 × 2）、スタビのねじと爪 4 × 4、取付の穴・ふたの柱など
    assert len(npth) >= 62 * 2 + 4 * 4
    assert slot_problems(facts["pads"]) == []


def test_the_slot_check_notices_the_first_v2_board(facts):
    """1 回目の板の位置決めの長穴（1.6 × 2.0）を写しに戻すと落ちる。"""
    f = copy.deepcopy(facts)
    p = next(p for p in f["pads"] if p["npth"] and p["ref"] == "SW1" and p["drill"] < 3)
    p.update(slot=True, drill_wh=[1.6, 2.0])
    assert slot_problems(f["pads"])


def test_the_slot_check_notices_the_old_stab_slots(facts):
    """前の板のスタビのねじ・爪の長円（3.2 × 3.4・4.2 × 4.4）を写しに戻すと、例外なしで落ちる。"""
    f = copy.deepcopy(facts)
    for p in f["pads"]:
        if re.fullmatch(r"ST\d+", p["ref"]):
            p.update(slot=True, drill_wh=[3.2, 3.4] if p["drill"] < 3.5 else [4.2, 4.4])
    assert len(slot_problems(f["pads"])) == 16


def drill_file_slots(text):
    """Excellon（KiCad の出力）の長円の穴: [(工具の径, 長さ)]。KiCad は長円を工具で G01 の道として書く
    （M15 … G01 … M16）。長さ = 道の長さ ＋ 径。丸穴（座標だけの行）は数えない。"""
    import re as _re

    tools, tool, pos, out = {}, None, None, []
    down = False
    for line in text.splitlines():
        m = _re.fullmatch(r"T(\d+)C([\d.]+)", line)
        if m:
            tools[m.group(1)] = float(m.group(2))
            continue
        m = _re.fullmatch(r"T(\d+)", line)
        if m:
            tool = tools[m.group(1)]
            continue
        m = _re.fullmatch(r"(G00|G01)?X([-\d.]+)Y([-\d.]+)", line)
        if m:
            q = (float(m.group(2)), float(m.group(3)))
            if m.group(1) == "G01" and down:
                out.append((tool, math.dist(pos, q) + tool))
            pos = q
            continue
        if line == "M15":
            down = True
        elif line == "M16":
            down = False
    return out


def test_the_drill_files_sent_to_jlc_have_no_short_slot(production_dir):
    """**JLC が読むドリルのファイル**（発注の道具が出した zip の中の PTH/NPTH の .drl）で長円を数える。"""
    import zipfile

    zips = list(production_dir.glob("*.zip"))
    assert len(zips) == 1, zips
    with zipfile.ZipFile(zips[0]) as z:
        names = [n for n in z.namelist() if n.endswith(".drl")]
        assert sorted(n.rsplit("-", 1)[1] for n in names) == ["NPTH.drl", "PTH.drl"], names
        slots = [s for n in names for s in drill_file_slots(z.read(n).decode())]
    print("ドリルのファイルの長円（径, 長さ）:", sorted(set(slots)))
    short = [s for s in slots if s[1] < SLOT_MIN_RATIO * s[0] - 1e-6]
    # 0（2026-09-26 にスタビの 16 も丸にした）。前の板は位置決め 1.6 × 2.0 ×62・スタビ 3.2 × 3.4・4.2 × 4.4 ×16
    assert short == [], short


def test_the_drill_file_reader_sees_a_short_slot():
    """1 回目の板の NPTH.drl の書き方（位置決め 1.6 × 2.0）を読むと、短い長円として見つける。"""
    text = "M48\nMETRIC\nT1C1.600\n%\nG90\nG05\nT1\nG00X11.65Y-66.85\nM15\nG01X11.65Y-67.25\nM16\nG05\n"
    assert [(1.6, pytest.approx(2.0))] == drill_file_slots(text)


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
        out.append("D_PWR（ショットキー）のカソードが XIAO の 3V3 でない")
    if net.get(("D_PWR", a)) != "VBAT_SW":
        out.append("D_PWR（ショットキー）のアノードがスイッチの後ろ（VBAT_SW）でない")
    plus = pinmap.resolve("coin_holder_bs16", "+")
    if net.get(("BT1", plus)) != net.get(("SW_PWR", "2")) or not net.get(("BT1", plus)):
        out.append("ホルダの＋がスイッチの共通（2・真ん中の足）に来ていない")
    if net.get(("BT1", pinmap.resolve("coin_holder_bs16", "-"))) != "GND":
        out.append("ホルダの−が GND でない")
    if net.get(("SW_PWR", "1")) != "VBAT_SW" or net.get(("SW_PWR", "3")):
        out.append("スイッチの 1（奥・入の側）が VBAT_SW でない、か 3 に網がある")
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
    """SS-12D00G3 の図面（秋月の PDF 5 ページ目）の PCB LAYOUT: 3-φ0.8 を 2.5 間隔、足 0.5×0.3。
    板の上の SW_PWR（表・スルーホール）のパッドが 3 個・穴 φ0.8・中心が 2.5 間隔で y に並び、
    真ん中（2・共通）が spec.PSW_AT、並びが interface.psw_pins と同じで、足の対角が穴に入ること。"""
    s = SPEC
    ps = _pads_of(facts, "SW_PWR")
    assert sorted(ps) == ["1", "2", "3"], sorted(ps)
    assert not any(p["ref"] == "SW_PWR" and p["npth"] for p in facts["pads"])
    for n, (x, y) in zip("123", ifc.psw_pins()):
        p = ps[n]
        assert abs(p["drill"] - 0.8) < 1e-3 and p["front"] and p["back"] and not p["smd"], (n, p)
        assert math.dist(p["pos"], (x, y)) < 1e-3, (n, p["pos"], (x, y))
        b = p["box"]
        assert abs((b[2] - b[0]) - s.PSW_PAD_D) < 1e-3 and abs((b[3] - b[1]) - s.PSW_PAD_D) < 1e-3, (n, b)
    assert abs(ps["1"]["pos"][1] - ps["2"]["pos"][1] - 2.5) < 1e-3
    assert abs(ps["2"]["pos"][1] - ps["3"]["pos"][1] - 2.5) < 1e-3
    assert math.dist(ps["2"]["pos"], s.PSW_AT) < 1e-3
    assert math.hypot(*s.PSW_PIN) < 0.8 and s.PSW_DRILL == 0.8


def on_side_problems(facts):
    """入の向き: VBAT_SW（入で電池が繋がる側）の足は、共通の足から spec.PSW_ON の向き（レバーを押す側）に
    ある（レバーの側の足が共通と繋がる・図面の側面図と回路図）。ふたの刻印も PSW_ON を指す。"""
    ps = _pads_of(facts, "SW_PWR")
    com = ps["2"]["pos"]
    on = [p for p in ps.values() if p["net"] == "VBAT_SW"]
    if len(on) != 1:
        return [f"VBAT_SW の足が {len(on)} 本"]
    dy = on[0]["pos"][1] - com[1]
    return [] if dy * SPEC.PSW_ON > 0 else [f"VBAT_SW の足が入の向き（{SPEC.PSW_ON:+d}）の反対（{dy:+.2f}）"]


def test_the_on_side_of_the_power_switch_is_the_marked_side(facts):
    assert on_side_problems(facts) == []


def test_the_on_side_check_notices_swapped_throws(facts):
    f = copy.deepcopy(facts)
    for p in f["pads"]:
        if p["ref"] == "SW_PWR" and p["num"] in "13":
            p["net"] = {"VBAT_SW": "", "": "VBAT_SW"}[p["net"]]
    assert on_side_problems(f)


def test_nothing_on_top_under_the_power_switch_frame_tabs(facts, ifc):
    """電源スイッチの枠（金属）の爪 4 つが立つ所（本体の両端）の表の銅が 0（ランドの列の左右）。
    ルール領域 PSW_TAB_KEEPOUT（表・線/ビア/ベタ禁止）が 2 つある。対照はベタのある所で 0 でない。"""
    zs = [z for z in facts["zones"] if z["name"] == "PSW_TAB_KEEPOUT"]
    assert len(zs) == 2 and all(z["layers"] == ["F.Cu"] and z["no_tracks"] and z["no_vias"]
                                and z["no_fill"] for z in zs), zs
    for n in ("psw_tab0L", "psw_tab0R", "psw_tab1L", "psw_tab1R"):
        cu = copper_in(facts, ifc, n)
        assert cu["area"]["F.Cu"] == 0.0, (n, cu)
    assert copper_in(facts, ifc, "psw_tab_control")["area"]["F.Cu"] > 1.0


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


def board_items(path):
    """板の最上位の項目（フットプリント・ルール領域・線・ネットクラス…）を、UUID を落として並べ替えた一覧。
    **パッドの形・大きさ・ルール領域・ベタへの繋ぎ方まで**比べる（boardhash の指紋は配置・結線・外形
    だけで、2026-09-24 に XIAO のパッドを縮め禁止域を足しても変わらなかった）。生成器は項目の順を
    毎回変えるので並べ替える。"""
    t = re.sub(r'\s*\(uuid "[^"]*"\)|\s*\(tstamp [^)]*\)', "", path.read_text())
    out, depth, start = [], 0, None
    for j in range(1, len(t)):
        c = t[j]
        if c == "(":
            if depth == 0:
                start = j
            depth += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                break
            if depth == 0:
                out.append(t[start:j + 1])
    return sorted(out)


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    require(paths.KICAD_PYTHON, "基板の生成")
    d = tmp_path_factory.mktemp("gen") / "cckb"
    shutil.copytree(paths.PROJECTS / "cckb", d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(d)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d / "pcb/unrouted/cckb_main.kicad_pcb"


def test_the_committed_unrouted_board_is_what_the_generator_makes_now(regenerated):
    from foundry.boardhash import fingerprint

    msg = "tools/kb cckb pcb で作り直し、route_pcb.py で配線し直すこと"
    assert fingerprint(regenerated) == fingerprint(UNROUTED), msg
    assert board_items(regenerated) == board_items(UNROUTED), msg


def test_the_item_check_notices_a_changed_pad_size_that_the_fingerprint_misses(regenerated, tmp_path):
    """**壊すと落ちる**: XIAO の D7 のパッドを前の大きさ（3.45）に戻した写しは、指紋は同じでも
    項目の比較では違う（前の検査だけでは気づけなかった）。"""
    from foundry.boardhash import fingerprint

    t = UNROUTED.read_text()
    i = t.index('(property "Reference" "U_MCU"')
    m = re.compile(r'(\(pad "D7" smd rect[\s\S]{0,120}?\(size )2\.8 ').search(t, t.rfind("(footprint", 0, i))
    assert m, "D7 のパッドの大きさが見つからない"
    f = tmp_path / "u.kicad_pcb"
    f.write_text(t[:m.start()] + m.group(1) + "3.45 " + t[m.end():])
    assert fingerprint(f) == fingerprint(UNROUTED)
    assert board_items(f) != board_items(UNROUTED)


def route_is_fresh(record, unrouted):
    import hashlib

    from foundry.boardhash import fingerprint

    return record["unrouted_fingerprint"] == fingerprint(unrouted) and \
        record["unrouted_sha256"] == hashlib.sha256(unrouted.read_bytes()).hexdigest()


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
    p["pos"] = [p["pos"][0], p["pos"][1] + 0.5]


def _break_psw_tab(f):
    """爪の下にベタが 0.5mm² 残った（ルール領域が効いていない）ことにする。"""
    i = regions(I.Interface())["psw_tab1R"][0]
    f["copper_in"][i]["area"]["F.Cu"] = 0.5


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
    ("test_nothing_on_top_under_the_power_switch_frame_tabs", _break_psw_tab),
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


# ---------------------------------------------------------------------------
# 配線の道具（tools/route_pcb.py）の煙の検査（最終レビュー I3）
# ---------------------------------------------------------------------------
# route_pcb.py は発注前の直しのときしか回らない。interface・matrix_routes・boardhash の API が
# 変わっても、次に回すまで——発注の直前まで——気づかない。KiCad の Python で import し（main は
# 引かない）、route_pcb が相手のモジュールに求める名前が全部あることと、引数の読みを確かめる
_ROUTE_SMOKE = r"""
import ast, sys, types
path, src_path = sys.argv[1], sys.argv[2]        # 置き場所（sys.path の組み方）と中身
src = open(src_path).read()
m = types.ModuleType("route_pcb")
m.__file__ = path
exec(compile(src, path, "exec"), m.__dict__)
assert callable(m.main)
assert m.parse_args([]) is None and m.parse_args(["--reroute", "CS,ROW1"]) == {"CS", "ROW1"}
missing = []
mods = {n: getattr(m, n) for n in ("interface", "matrix_routes", "boardhash", "board_geometry",
                                   "paths", "pcbnew")}
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in mods:
        if not hasattr(mods[node.value.id], node.attr):
            missing.append(node.value.id + "." + node.attr)
print("OK" if not missing else "NG " + " ".join(sorted(set(missing))))
"""


ROUTE_PCB = ROOT / "projects/cckb/tools/route_pcb.py"


def route_smoke(src_path):
    r = subprocess.run([paths.KICAD_PYTHON, "-c", _ROUTE_SMOKE, str(ROUTE_PCB), str(src_path)],
                       cwd=ROOT, capture_output=True, text=True)
    return (r.stdout.strip().splitlines() or [""])[-1] + ("" if r.returncode == 0 else r.stderr[-2000:])


def test_the_routing_tool_imports_and_finds_every_name_it_uses():
    require(paths.KICAD_PYTHON, "route_pcb.py を KiCad の Python で読む")
    out = route_smoke(ROUTE_PCB)
    assert out == "OK", out


def test_the_routing_smoke_check_notices_a_renamed_function(tmp_path):
    """**検査器が壊れていないか。**route_pcb が呼ぶ matrix_routes.plan を別名にした写しは NG。"""
    require(paths.KICAD_PYTHON, "route_pcb.py を KiCad の Python で読む")
    src = ROUTE_PCB.read_text()
    assert "matrix_routes.plan(" in src
    f = tmp_path / "route_pcb.py"            # 中身だけ写す（置き場所は本物として読む）
    f.write_text(src.replace("matrix_routes.plan(", "matrix_routes.plan_renamed("))
    out = route_smoke(f)
    assert out.startswith("NG") and "matrix_routes.plan_renamed" in out, out


def test_the_easyeda_fixture_holds_only_coordinates():
    """lib/README.md の約束: EasyEDA のデータそのものは置かず、座標の事実（パッケージ名・原点・
    パッドの番号・中心・大きさ）だけ（最終レビュー I4）。形の描画などが紛れ込んだら落とす。"""
    d = json.loads((ROOT / "tests/fixtures/easyeda/footprints.json").read_text())
    assert set(d) == {"source", "parts"}
    for c, part in d["parts"].items():
        assert set(part) == {"package", "head", "pads"}, c
        assert len(part["head"]) == 2 and all(isinstance(v, float) for v in part["head"]), c
        for n, pad in part["pads"].items():
            assert re.fullmatch(r"\d+", n) and len(pad) == 4, (c, n, pad)
            assert all(isinstance(v, (int, float)) for v in pad), (c, n, pad)


_PRUNE = r"""
import sys, types
path, board = sys.argv[1], sys.argv[2]
m = types.ModuleType("route_pcb")
m.__file__ = path
exec(compile(open(path).read(), path, "exec"), m.__dict__)
pcbnew = m.pcbnew
b = pcbnew.LoadBoard(board)
nets = {"VBAT_IN", "VBAT_SW"}
n0 = sum(1 for t in b.GetTracks() if t.GetNetname() in nets)
clean = m.prune_dangling(b, nets)
for a, c in (((141.225, -36.1), (139.0, -34.0)), ((139.0, -34.0), (137.0, -34.0))):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(m.kpt(*a))
    t.SetEnd(m.kpt(*c))
    t.SetWidth(m.MM(0.3))
    t.SetLayer(pcbnew.B_Cu)
    t.SetNet(b.FindNet("VBAT_SW"))
    b.Add(t)
stub = m.prune_dangling(b, nets)
left = sum(1 for t in b.GetTracks() if t.GetNetname() in nets)
print(f"OK {clean} {stub} {left} {n0}")
"""


def test_the_routing_tool_prunes_only_dead_ends(tmp_path):
    """route_pcb.prune_dangling（--reroute で引き直した網の行き止まりを消す）: 発注する板では何も消さず、
    奥の足から伸ばした 2 本の行き止まりは 2 本とも消し、ほかの線は残す（2026-09-24 に電源スイッチを動かしたとき足した）。"""
    require(paths.KICAD_PYTHON, "route_pcb.py を KiCad の Python で読む")
    board = board_copy(tmp_path / "b")
    r = subprocess.run([paths.KICAD_PYTHON, "-c", _PRUNE, str(ROUTE_PCB), str(board)],
                       cwd=ROOT, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    assert last.startswith("OK"), r.stdout[-2000:] + r.stderr[-2000:]
    clean, stub, left, n0 = map(int, last.split()[1:])
    assert (clean, stub, left) == (0, 2, n0), last
