"""CCKB の要求。**HHKB 英語配列の実物の KLE と突き合わせる**（設計書 §1）。

守るもの: スペース以外の全キーの中心・幅・刻印、ピッチ、最下段の空き（左 1.5u・右 2.5u）、
スペースが 4.0〜10.0u を 3 キーで隙間なく覆うこと。
"""

import re
import shutil
import subprocess

import pytest

from conftest import FIXTURES, ROOT, require
from foundry import paths
from foundry.layout import UNIT, load_layout
from foundry.project import load

HHKB = FIXTURES / "hhkb_original.json"
SHIELD = paths.ROOT / "config" / "boards" / "shields" / "cckb"


def _row(k):
    return round(k.y_mm / UNIT - 0.5)


def differences(ours, ref):
    """スペース以外で、HHKB と違うキーを返す（空なら準拠）。"""
    key = lambda k: (_row(k), round(k.left_u, 4))
    a = {key(k): k for k in ours if k.label != "Space"}
    b = {key(k): k for k in ref if k.label != "Space"}
    out = sorted(f"{p}: {'無い' if p not in a else ''}{'余分' if p not in b else ''}"
                 for p in set(a) ^ set(b))
    for p in set(a) & set(b):
        if (a[p].label, a[p].w_u, round(a[p].x_mm, 4), round(a[p].y_mm, 4)) != \
           (b[p].label, b[p].w_u, round(b[p].x_mm, 4), round(b[p].y_mm, 4)):
            out.append(f"{p}: {a[p]} / HHKB {b[p]}")
    return out


def test_every_key_but_space_is_where_the_hhkb_has_it():
    ours = load("cckb").keys()
    ref = load_layout(HHKB)
    assert len(ref) == 60 and len(ours) == 62            # 空どうしで緑にしない
    assert differences(ours, ref) == []


def test_the_three_space_keys_cover_the_hhkb_space_exactly():
    ref = [k for k in load_layout(HHKB) if k.label == "Space"]
    sp = sorted((k for k in load("cckb").keys() if k.label == "Space"), key=lambda k: k.x_mm)
    assert [k.w_u for k in sp] == [2.25, 1.5, 2.25]
    assert abs(sp[0].left_u - ref[0].left_u) < 1e-9 and abs(sp[-1].right_u - ref[0].right_u) < 1e-9
    assert all(abs(a.right_u - b.left_u) < 1e-9 for a, b in zip(sp, sp[1:]))   # 隙間なし
    assert len({round(k.y_mm, 4) for k in sp + ref}) == 1


def test_the_bottom_row_leaves_the_hhkb_corners_empty():
    bottom = [k for k in load("cckb").keys() if _row(k) == 4]
    assert min(k.left_u for k in bottom) == 1.5 and max(k.right_u for k in bottom) == 12.5


def test_the_checker_notices_a_moved_key(tmp_path):
    """**検査器が壊れていないか。**Q を 0.25u 動かした配列で差が出ること。"""
    import json

    raw = json.loads(HHKB.read_text())
    row = raw[2]
    row.insert(row.index("Q"), {"x": 0.25})
    f = tmp_path / "moved.json"
    f.write_text(json.dumps(raw))
    assert differences(load_layout(f), load_layout(HHKB))


def test_the_machine_uses_choc_v1():
    from foundry.mech import switch_of

    assert switch_of(load("cckb").spec).name == "choc_v1"
    assert (paths.PROJECTS / "cckb" / "layout.json").exists()


def test_the_plate_openings_are_exactly_the_empty_corners():
    """角の開口の**内側の 2 辺**は角のセルの境目ちょうど（隣のキーの桟を削らない）、
    **外側の 2 辺**はプレートの外形の外まで（外周に細い帯を残さない）。"""
    from foundry.layout import centered

    p = load("cckb")
    keys = p.keys()
    positions, (kw, kh) = centered(keys)
    bottom = [(pos, k) for pos, k in zip(positions, keys) if _row(k) == 4]
    y_bottom = bottom[0][0][1]
    left_edge = min(pos[0] - k.w_mm / 2 for pos, k in bottom)
    right_edge = max(pos[0] + k.w_mm / 2 for pos, k in bottom)
    top = y_bottom + UNIT / 2
    px, py = kw / 2 + p.spec.PLATE_MARGIN_X, kh / 2 + p.spec.PLATE_MARGIN_Y
    got = [(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
           for cx, cy, w, h in p.spec.PLATE_OPENINGS["main"]]
    assert len(got) == 2
    (l0, l1, l2, l3), (r0, r1, r2, r3) = sorted(got)
    assert abs(l2 - left_edge) < 1e-6 and abs(l3 - top) < 1e-6
    assert abs(r0 - right_edge) < 1e-6 and abs(r3 - top) < 1e-6
    assert l0 < -px - 0.5 and l1 < -py - 0.5 and r2 > px + 0.5 and r1 < -py - 0.5


@pytest.fixture(scope="module")
def plate():
    from foundry.plate import build_plate

    p = load("cckb")
    part, size, positions = build_plate(p.spec, p.keys(), "main")
    return p, part, size, positions


def _solid(part, x, y):
    from build123d import Vector

    return part.is_inside(Vector(x, y, 0.6))


def test_the_plate_is_open_at_every_key_and_at_both_corners(plate):
    p, part, _, positions = plate
    assert len(positions) == 62
    for x, y in positions:
        assert not _solid(part, x, y)
    for cx, cy, w, h in p.spec.PLATE_OPENINGS["main"]:
        assert not _solid(part, cx, cy), (cx, cy)


def _in_polygon(x, y, poly):
    # 簡易な内外判定（レイ・キャスティング）。開口はどれも軸並行に近い凸形
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < xin:
                inside = not inside
    return inside


def _in_opening(x, y, poly, kerf=None):
    """プレートに開く穴（輪郭を kerf だけ角を丸めず広げたもの）の中か。

    輪郭は軸に平行な辺だけなので、INTERSECTION のオフセットは「輪郭の中、または
    どれかの辺からチェビシェフ距離 kerf 以内」と同じになる。
    """
    from foundry.mech import STAB_KERF

    kerf = STAB_KERF if kerf is None else kerf
    if _in_polygon(x, y, poly):
        return True
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        assert x1 == x2 or y1 == y2, "軸に平行でない辺（この判定は使えない）"
        dx = max(min(x1, x2) - x, 0.0, x - max(x1, x2))
        dy = max(min(y1, y2) - y, 0.0, y - max(y1, y2))
        if max(dx, dy) <= kerf:
            return True
    return False


def test_the_choc_stab_openings_are_widened_by_the_kerf(plate):
    """Keebio の輪郭は幅がハウジングと同じ 6.30（隙間 0）。プレートでは STAB_KERF だけ
    広げて開けていること: 輪郭の横の辺から 0.1mm 外は穴、STAB_KERF + 0.1mm 外は板。"""
    from foundry.mech import CHOC_STAB_OUTLINE, STAB_KERF, switch_of

    p, part, _, positions = plate
    sw = switch_of(p.spec)
    half = max(x for x, _ in CHOC_STAB_OUTLINE)             # 3.15（横の辺）
    probed = 0
    for (x, y), k in zip(positions, p.keys()):
        s = sw.stab_offset_for(k.w_u)
        if s is None:
            continue
        for centre in (x - s, x + s):
            for side in (-1, 1):
                edge = centre + side * half
                assert not _solid(part, edge + side * 0.1, y), (k.label, centre, side)
                assert _solid(part, edge + side * (STAB_KERF + 0.1), y), (k.label, centre, side)
                probed += 1
    assert probed == 4 * 4, probed                            # Enter・左 Shift・スペース 2 つ


def test_the_web_around_the_corner_keys_survives(plate):
    """角の開口が隣接するキー（最下段の角のキーと、その 1 段上で角にかぶるキー）の
    自分のセルの桟を削っていないこと（Review Focus 4）。

    **spec.PLATE_OPENINGS を判定に使わない。**角の開口そのものが検査対象なので、
    それを使って「ここは角の中だから見なくてよい」と判定すると、開口を広げる・
    ずらす壊し方が自分自身を免除してしまう（実測で確認済み）。角に触れるキーは
    レイアウトから導く（test_the_plate_openings_are_exactly_the_empty_corners と同じ手）。

    左の角（x 0〜1.5u）の真上は最下段の 1 段上の左 Shift（2.25u・0〜2.25u）、
    右の角（x 12.5〜15u）の真上は右 Shift（1.75u・12.25〜14u）と Fn（1u・14〜15u）に
    かぶる。これらの底辺（角に向く側）もプローブする。
    """
    from foundry.layout import centered
    from foundry.mech import switch_of
    from foundry.plate import choc_stab_polygons

    p, part, _, positions = plate
    keys = p.keys()
    _, (kw, kh) = centered(keys)
    sw = switch_of(p.spec)
    bottom = [(pos, k) for pos, k in zip(positions, keys) if _row(k) == 4]
    left_key = min(bottom, key=lambda pk: pk[0][0])
    right_key = max(bottom, key=lambda pk: pk[0][0])

    row3 = [(pos, k) for pos, k in zip(positions, keys) if _row(k) == 3]
    left_edge = min(pos[0] - k.w_mm / 2 for pos, k in bottom)
    right_edge = max(pos[0] + k.w_mm / 2 for pos, k in bottom)
    # 角（最下段の外側）の真上にセルがかぶっている段 3 のキー
    above_corner = [(pos, k) for pos, k in row3
                    if pos[0] - k.w_mm / 2 < left_edge or pos[0] + k.w_mm / 2 > right_edge]
    assert above_corner, "角の上にかぶる段 3 のキーが見つからない"

    def own_stab_polys(pos, k):
        s = sw.stab_offset_for(k.w_u)
        if s is None:
            return []
        return choc_stab_polygons(s, at=pos) if sw.stab_kind == "choc" else []

    checked_total = 0

    # 最下段の角のキー: 角に向く横側をプローブ
    for pos, k, side in ((left_key[0], left_key[1], -1), (right_key[0], right_key[1], 1)):
        x, y = pos
        half_cell = k.w_mm / 2
        stabs = own_stab_polys(pos, k)
        for r in (7.2, 8.2, 9.2):
            if r >= half_cell:
                continue   # セルの外に出てしまう距離は使わない
            px = x + side * r
            for dy in (-5.0, 0.0, 5.0):
                py = y + dy
                # 前提: プローブ点は自分のスタビ開口（広げたあと）の外。外れたら気づく
                assert not any(_in_opening(px, py, poly) for poly in stabs), \
                    (k.label, side, r, dy, "プローブがスタビ開口にかかった")
                checked_total += 1
                assert _solid(part, px, py), (k.label, side, r, dy)

    # 段 3 の、角にかぶるキー: 角に向く下側（-y）をプローブ
    for pos, k in above_corner:
        x, y = pos
        half_cell_x = k.w_mm / 2
        stabs = own_stab_polys(pos, k)
        # 角にかぶっている部分の x 範囲（セルの中、角の側）
        if x - half_cell_x < left_edge:
            xs = [x - half_cell_x + dx for dx in (2.0, half_cell_x, half_cell_x * 1.6)
                  if 2.0 <= dx <= half_cell_x * 2]
        else:
            xs = [x + half_cell_x - dx for dx in (2.0, half_cell_x, half_cell_x * 1.6)
                  if 2.0 <= dx <= half_cell_x * 2]
        for r in (7.2, 8.2, 9.2):
            py = y - r
            for px in xs:
                # 前提: スタビの開口は中心から y −3.05 − kerf までしか下に伸びないので、
                # 7.2mm 以上下のプローブは開口の外。**推測で除外せず** assert で確かめる
                assert not any(_in_opening(px, py, poly) for poly in stabs), \
                    (k.label, r, px, "プローブがスタビ開口にかかった")
                checked_total += 1
                assert _solid(part, px, py), (k.label, r, px)

    assert checked_total > 0, "probe 点が 1 つも取れなかった"


def test_the_plate_is_1_2mm_and_printable_as_a_check(plate, tmp_path):
    from foundry.verify import to_mesh

    _, part, (w, h), _ = plate
    assert abs(part.bounding_box().size.Z - 1.2) < 1e-6
    mesh, _ = to_mesh(part, tmp_path / "plate.stl")
    assert mesh.is_watertight


@pytest.fixture(scope="module")
def board(tmp_path_factory):
    require(paths.KICAD_PYTHON, "基板の生成")
    d = tmp_path_factory.mktemp("cckb") / "cckb"
    shutil.copytree(paths.PROJECTS / "cckb", d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(d)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d / "pcb" / "unrouted" / "cckb_main.kicad_pcb"


def test_the_board_has_one_switch_and_one_diode_per_key(board):
    from foundry.board_dump import key_parts

    parts = key_parts(board.read_text())
    sw = [r for r in parts if re.fullmatch(r"SW\d+", r)]
    d = [r for r in parts if re.fullmatch(r"D\d+", r)]
    assert len(sw) == 62 and len(d) == 62
    assert all(parts[r]["fp"].endswith("SW_Kailh_Choc_V1") for r in sw)
    assert all(parts[r]["back"] for r in d)                      # ダイオードは裏（D8）


def test_the_matrix_nets_are_5_rows_by_15_columns(board):
    nets = set(re.findall(r'\(net "([^"]+)"\)', board.read_text()))
    assert {n for n in nets if re.fullmatch(r"ROW\d+", n)} == {f"ROW{i}" for i in range(5)}
    assert {n for n in nets if re.fullmatch(r"COL\d+", n)} == {f"COL{i}" for i in range(15)}


def test_the_unrouted_board_has_no_drc_violations(board):
    """Review Focus 5。**警告も数えて記録する**（隠さない）。"""
    from foundry import drc

    require(paths.KICAD_CLI, "DRC")
    r = drc.run(board)
    assert r["violations"] == 0, r["details"]
    print("DRC 警告の内訳:", r["warning_kinds"])


def test_every_layer_has_62_bindings():
    from foundry.check_zmk_config import count_bindings

    layers = count_bindings(SHIELD / "cckb.keymap")
    assert [n for _, n in layers] == [62, 62, 62, 62], layers


def test_the_three_space_keys_all_send_space_on_both_bases():
    """Review Focus 2。3 つのスペースは別のスイッチで、既定では 3 つとも SPACE（設計書 §1）。"""
    import re

    from foundry import zmk

    p = load("cckb")
    rows, _ = zmk.layout(p)
    idx = [i for i, (_, k, _) in enumerate(rows) if k.label == "Space"]
    assert len(idx) == 3 and len({rows[i][2] for i in idx}) == 3     # (row, col) が別々
    text = re.sub(r"/\*.*?\*/|//[^\n]*", " ", (SHIELD / "cckb.keymap").read_text(), flags=re.S)
    for layer in ("base_mac", "base_win"):
        body = re.search(layer + r"\s*\{\s*bindings\s*=\s*<(.*?)>;", text, re.S).group(1)
        binds = re.findall(r"&\w+(?:\s+[A-Z_0-9]+(?:\s+\d+)?)?", body)
        assert [binds[i].split()[-1] for i in idx] == ["SPACE"] * 3, layer


def test_the_recovery_bindings_exist():
    km = (SHIELD / "cckb.keymap").read_text()
    assert "&bootloader" in km and "&bt BT_CLR" in km        # ケースを開けずに復旧


def test_the_shield_config_passes_the_checker():
    import subprocess
    import sys

    from conftest import ROOT

    r = subprocess.run([sys.executable, "-m", "foundry.check_zmk_config"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_order_gate_is_closed_until_the_startup_test_and_the_board_review_are_done():
    from foundry import gate

    doc = (paths.PROJECTS / "cckb" / "docs" / "open-gaps.md").read_text()
    b = set(gate.blockers(doc))
    assert {"1", "4"} <= b, b             # 起動試験・基板（発注前の人の確認と独立監査）
    # #5 CI（09-23）・#2 角の断面（09-24 境界の決定）・#3 ケース（09-24 ケースの段と統合）は解消
    assert not {"2", "3", "5"} & b, b
    assert not gate.is_gate_open(doc)


# ---- 描き出した基板・transform が行列と揃っているか（生成し直し忘れを捕まえる）----

PCB = paths.PROJECTS / "cckb" / "pcb" / "unrouted" / "cckb_main.kicad_pcb"
TRANSFORM = SHIELD / "cckb-transform.dtsi"


def test_the_committed_transform_is_what_the_generator_makes_now():
    """コミット済みの transform が、いまの配列と spec の行列から作るものと 1 字違わないこと。"""
    from foundry import zmk

    assert TRANSFORM.read_text() == zmk.transform_dtsi(load("cckb")), \
        "python -m foundry.zmk cckb で作り直すこと"


def test_the_freshness_check_notices_a_changed_rc(tmp_path, monkeypatch):
    """**検査器が壊れていないか。**RC を 1 つ書き換えた transform で落ちること。"""
    import test_cckb

    text = TRANSFORM.read_text()
    assert "RC(4,12)" in text
    fake = tmp_path / TRANSFORM.name
    fake.write_text(text.replace("RC(4,12)", "RC(4,11)"))
    monkeypatch.setattr(test_cckb, "TRANSFORM", fake)
    with pytest.raises(AssertionError):
        test_cckb.test_the_committed_transform_is_what_the_generator_makes_now()


def _transform_rcs(text):
    """transform の map を、キーマップの並び順の [(row, col)] で。"""
    body = re.search(r"map\s*=\s*<(.*?)>;", re.sub(r"/\*.*?\*/", " ", text, flags=re.S), re.S)
    return [(int(r), int(c)) for r, c in re.findall(r"RC\((\d+),(\d+)\)", body.group(1))]


def board_matrix_mismatches(pcb_text, dtsi_text):
    """基板の各スイッチの COL とそのダイオードの ROW が、同じ位置のキーの transform の
    RC と違うものを返す（空なら一致）。

    キーは**物理の位置**で引く（参照番号の並びを信じない）。基板は ORIGIN（pcb.py）を
    原点に Y 下向き、layout.centered は Y 上向き。ダイオードは参照番号ではなく、
    スイッチの COL でない側のネットを共有するものを引く。
    """
    from foundry import zmk
    from foundry.board_dump import key_parts
    from foundry.layout import centered

    p = load("cckb")
    rows, _ = zmk.layout(p)
    positions, _ = centered([k for _, k, _ in rows])            # キーマップ順
    rcs = _transform_rcs(dtsi_text)
    assert len(rcs) == len(positions) == 62, (len(rcs), len(positions))

    parts = key_parts(pcb_text)
    switches = sorted((r for r in parts if re.fullmatch(r"SW\d+", r)), key=lambda r: int(r[2:]))
    diodes = [r for r in parts if re.fullmatch(r"D\d+", r)]
    assert len(switches) == 62 and len(diodes) == 62

    out, seen = [], set()
    for ref in switches:
        sw = parts[ref]
        hit = [j for j, (x, y) in enumerate(positions)
               if abs(sw["x"] - x) < 1e-3 and abs(-sw["y"] - y) < 1e-3]
        if len(hit) != 1:
            out.append(f"{ref}: 位置 ({sw['x']}, {-sw['y']}) のキーが {len(hit)} 個")
            continue
        j = hit[0]
        seen.add(j)
        r, c = rcs[j]
        label = rows[j][1].label
        nets = set(sw["pads"].values())
        cols = {n for n in nets if re.fullmatch(r"COL\d+", n)}
        if cols != {f"COL{c}"}:
            out.append(f"{ref}（{label}）: 列 {sorted(cols)} / transform COL{c}")
        others = nets - cols - {""}
        ds = [d for d in diodes if others & set(parts[d]["pads"].values())]
        drows = {n for d in ds for n in parts[d]["pads"].values() if re.fullmatch(r"ROW\d+", n)}
        if len(ds) != 1 or drows != {f"ROW{r}"}:
            out.append(f"{ref}（{label}）: ダイオード {ds} の行 {sorted(drows)} / transform ROW{r}")
    if len(seen) != len(positions):
        out.append(f"基板にスイッチの無いキー {sorted(set(range(len(positions))) - seen)}")
    return out


def test_the_committed_board_wires_every_key_as_the_transform_says():
    assert board_matrix_mismatches(PCB.read_text(), TRANSFORM.read_text()) == []


def test_the_board_check_notices_two_swapped_columns():
    """**検査器が壊れていないか。**2 つのスイッチの COL を入れ替えた基板で落ちること。"""
    from foundry.board_dump import key_parts

    text = PCB.read_text()
    parts = key_parts(text)
    col = lambda ref: next(n for n in parts[ref]["pads"].values() if re.fullmatch(r"COL\d+", n))
    a, b = "SW1", "SW2"
    assert col(a) != col(b)
    # 各スイッチのブロックの中だけで COL のネット名を入れ替える
    from foundry.boardhash import _blocks

    out = text
    for name, blk in _blocks(text):
        m = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if m and m.group(1) in (a, b):
            other = col(b) if m.group(1) == a else col(a)
            new = re.sub(r'(\(net (?:\d+ )?")' + col(m.group(1)) + r'"', r"\g<1>" + other + '"', blk)
            assert new != blk
            out = out.replace(blk, new, 1)
    assert out != text
    bad = board_matrix_mismatches(out, TRANSFORM.read_text())
    assert len(bad) == 2, bad
