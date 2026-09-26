"""CCKB の要求。**HHKB 英語配列の実物の KLE と突き合わせる**（設計書 §1）。

守るもの: スペース以外の全キーの中心・幅・刻印、ピッチ、最下段の空き（左 1.5u・右 2.5u）、
スペースが 4.0〜10.0u を 3 キーで隙間なく覆うこと。
"""

import json
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


def test_the_machine_uses_choc_v2():
    from foundry.mech import switch_of

    assert switch_of(load("cckb").spec).name == "choc_v2"
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
    """V2 のスタビの羽（mech.CHOC_V2_STAB_PLATE・kerf 0）は、プレートでは STAB_KERF だけ広げて開けていること:
    羽の外の辺から 0.1mm 外は穴、STAB_KERF + 0.1mm 外は板（羽の高さの真ん中・スタビのキー 4 つの左右）。"""
    from foundry.mech import CHOC_V2_STAB_PLATE, STAB_KERF, switch_of

    p, part, _, positions = plate
    sw = switch_of(p.spec)
    outer = max(x for x, _ in CHOC_V2_STAB_PLATE)            # 14.9375（羽の外の辺）
    lobe = [y for x, y in CHOC_V2_STAB_PLATE if x == outer]
    ym = (min(lobe) + max(lobe)) / 2
    probed = 0
    for (x, y), k in zip(positions, p.keys()):
        if sw.stab_offset_for(k.w_u) is None:
            continue
        for side in (-1, 1):
            edge = x + side * outer
            assert not _solid(part, edge + side * 0.1, y + ym), (k.label, side)
            assert _solid(part, edge + side * (STAB_KERF + 0.1), y + ym), (k.label, side)
            probed += 1
    assert probed == 4 * 2, probed                            # Enter・左 Shift・スペース 2 つ


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
    from foundry.plate import choc_stab_polygons, choc_v2_stab_polygons

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
        if sw.stab_kind == "choc":
            return choc_stab_polygons(s, at=pos)
        return choc_v2_stab_polygons(at=pos) if sw.stab_kind == "choc_v2_screw" else []

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
            xs = [x - half_cell_x + dx for dx in (2.0, half_cell_x, half_cell_x * 1.25)
                  if 2.0 <= dx <= half_cell_x * 2 and x - half_cell_x + dx < left_edge]
        else:
            xs = [x + half_cell_x - dx for dx in (2.0, half_cell_x, half_cell_x * 1.25)
                  if 2.0 <= dx <= half_cell_x * 2 and x + half_cell_x - dx > right_edge]
        for r in (7.2, 8.2, 9.2):
            py = y - r
            for px in xs:
                # 前提: プローブ点は自分のスタビの開口の外（V2 の羽は中心から y −9.6 まで下へ伸びるが、
                # 羽の x の範囲にプローブは来ない）。**推測で除外せず** assert で確かめる
                assert not any(_in_opening(px, py, poly) for poly in stabs), \
                    (k.label, r, px, "プローブがスタビ開口にかかった")
                checked_total += 1
                assert _solid(part, px, py), (k.label, r, px)

    assert checked_total > 0, "probe 点が 1 つも取れなかった"


def test_the_plate_has_no_floating_island(plate):
    """開口どうしが板を切り離して、浮いた島を作っていない（プレートは 1 つの立体）。"""
    _, part, _, _ = plate
    assert len(part.solids()) == 1, [tuple(round(v, 1) for v in (s.bounding_box().min.X, s.bounding_box().min.Y))
                                     for s in part.solids()]


def test_the_island_check_notices_the_first_band(monkeypatch):
    """1 回目の読み違え（帯を y 9.85〜10.85 に置き、スイッチの開口との間を板に残した）で落ちること。"""
    import foundry.mech as mech_mod
    from foundry.plate import build_plate

    old = ((0.0, 9.85), (6.9, 9.85), (6.9, 6.64375), (8.87, 6.64375), (8.87, -9.45),
           (15.0375, -9.45), (15.0375, 10.85), (0.0, 10.85))
    monkeypatch.setattr(mech_mod, "CHOC_V2_STAB_PLATE", old)
    p = load("cckb")
    part, _, _ = build_plate(p.spec, p.keys(), "main")
    assert len(part.solids()) > 1


@pytest.fixture(scope="module")
def plate_parts(plate):
    """刷るプレートの部品全部: 1 枚の板（分ける前）・左右の半分・スタビのキーの枠（別に刷る物）。"""
    from foundry.plate import plate_frames, split_plate

    p, main, _, positions = plate
    keys = p.keys()
    halves = dict(split_plate(p.spec, main, "main", keys))
    frames = plate_frames(p.spec, keys, "main")
    return p, main, halves, frames, positions


def test_no_plate_web_is_thinner_than_the_minimum(plate_parts):
    """刷るプレートのどの部品にも、幅 PLATE_MIN_WEB（0.4 ノズル 3 本）未満の帯・突起が無い。
    穴どうし・穴と外形の間を、生成した立体の上面を縮めて戻して測る（foundry.plate.thin_webs）。"""
    from foundry.plate import thin_webs

    p, main, halves, frames, _ = plate_parts
    bad = {}
    for name, part in [("板", main)] + list(halves.items()) + list(frames):
        t = thin_webs(part, p.spec.PLATE_MIN_WEB)
        if t:
            bad[name] = t
    assert not bad, bad


def _framed(parts, x, y):
    from build123d import Vector

    return any(part.is_inside(Vector(x, y, 0.6)) for part in parts)


def switch_frame_problems(p, parts, positions):
    """スイッチの開口の 4 辺（スタビのキーは奥の辺を除く。そこはワイヤの帯）の外側に板があるか。
    辺から 0.3 と 1.0 の所を、辺に沿って 5 点ずつ刺す（爪は ±x の辺の ±2.25〜3.25。
    decisions/2026-09-25-choc-v2 §10-6）。板 = 刷るプレートのどれか（半分・枠）。"""
    from foundry.mech import switch_of

    sw = switch_of(p.spec)
    c = sw.cutout / 2
    out = []
    for (x, y), k in zip(positions, p.keys()):
        stab = sw.stab_offset_for(k.w_u) is not None
        sides = {"手前": (0, -1), "左": (-1, 0), "右": (1, 0)}
        if not stab:
            sides["奥"] = (0, 1)
        for name, (nx, ny) in sides.items():
            for d in (0.3, 1.0):
                for t in (-6.0, -2.75, 0.0, 2.75, 6.0):
                    px = x + nx * (c + d) + (t if nx == 0 else 0.0)
                    py = y + ny * (c + d) + (t if ny == 0 else 0.0)
                    if not _framed(parts, px, py):
                        out.append(f"{k.label}（{x:.1f}, {y:.1f}）の{name}")
                        break
                else:
                    continue
                break
    return sorted(set(out))


def test_every_switch_is_framed_by_plate(plate_parts):
    """62 個のスイッチ全部で、開口の周り（スタビのキーは手前・左・右）に板がある。
    **外形まで抜けて板の無いスイッチを作らない**（V2 のスペース 2 つと左 Shift が一度そうなった・2026-09-25）。

    **見るのは「周りに板があるか」だけ。**スペースの 2 キーの周りの板は別に刷る枠で、枠はプレートにも基板にも
    留まらずスイッチに挟まってぶら下がる（スイッチを留めるのは基板のはんだ）。枠がスイッチを保持するかはこの検査では
    分からない（2026-09-26 の監査 E 重要 4。一枚板にするかは利用者の判断 O15）。"""
    p, _, halves, frames, positions = plate_parts
    parts = list(halves.values()) + [f for _, f in frames]
    assert len(positions) == 62
    assert switch_frame_problems(p, parts, positions) == []


def test_the_web_check_notices_salicylics_back_edge(monkeypatch):
    """羽の奥の端をサリチル酸さんの 10.85 に戻すと、1 段奥の開口との帯 1.075 がスタビのキー 4 つで見つかる。
    桟の上の突起（0.525 幅）を戻しても見つかる。"""
    import foundry.mech as mech_mod
    from foundry.plate import build_plate, thin_webs

    p = load("cckb")
    back = tuple((x, 10.85 if y == mech_mod.CHOC_V2_STAB_PLATE_BACK else y) for x, y in mech_mod.CHOC_V2_STAB_PLATE)
    nub = ((0.0, 6.64375), (7.55, 6.64375), (7.55, 7.14375), (8.375, 7.14375), (8.375, 6.64375)) \
        + mech_mod.CHOC_V2_STAB_PLATE[1:]
    for poly, want in ((back, 1.08), (nub, 0.5)):
        monkeypatch.setattr(mech_mod, "CHOC_V2_STAB_PLATE", poly)
        part, _, _ = build_plate(p.spec, p.keys(), "main")
        found = thin_webs(part, p.spec.PLATE_MIN_WEB)
        assert any(abs(min(size) - want) < 0.03 for _, _, size in found), found


def test_the_frames_are_the_two_space_keys(plate_parts):
    """外形まで抜けて切り離された枠は、最下段のスペース 2 キーだけ（左 Shift は右の羽の側で板に繋がる）。
    枠は 1 つの立体で、厚さはプレートと同じ。"""
    p, _, _, frames, _ = plate_parts
    assert [n for n, _ in frames] == ["Space", "Space"]
    for _, f in frames:
        assert len(f.solids()) == 1 and abs(f.bounding_box().size.Z - 1.2) < 1e-6


def test_the_frame_check_notices_a_plate_without_frames(plate_parts):
    """枠を刷らない（前の形: 枠ごと抜いた）と、スペース 2 キーの手前・左・右に板が無い。"""
    p, _, halves, _, positions = plate_parts
    bad = switch_frame_problems(p, list(halves.values()), positions)
    assert len(bad) == 6 and all(b.startswith("Space") for b in bad), bad


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
    from foundry.mech import CHOC_V2_FP, CHOC_V2_STAB_FP

    assert all(parts[r]["fp"].endswith(CHOC_V2_FP) for r in sw)
    st = [r for r in parts if re.fullmatch(r"ST\d+", r)]
    assert sorted(st) == ["ST42", "ST43", "ST58", "ST60"]           # Enter・左 Shift・スペース 2 つ
    assert all(parts[r]["fp"].endswith(CHOC_V2_STAB_FP) for r in st)
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


# ---------------------------------------------------------------------------
# 核の約束: ダイオードの置き換えと DRC の重大度（最終レビュー M2・M3。KiCad は要らない）
# ---------------------------------------------------------------------------

def test_the_diode_override_is_not_used_with_v2():
    """V2 はスタビのキーでもいつもの位置（mech.CHOC_V2.diode_offset）に置く。上書きが残っていれば落とす。"""
    assert load("cckb").diode_override("main") == {}


@pytest.mark.parametrize("over, msg", [
    ({"mian": {42: (5.55, 2.9, 180)}}, "PIECES"),            # 部品名の綴り違い
    ({"main": {63: (5.55, 2.9, 180)}}, "1〜62"),              # 無いキー番号
    ({"main": {0: (5.55, 2.9, 180)}}, "1〜62"),               # 0 始まりと取り違えた
])
def test_the_diode_override_refuses_a_typo(over, msg):
    p = load("cckb")
    p.spec.DIODE_OVERRIDE = over
    with pytest.raises(ValueError, match=msg):
        p.diode_override("main")


def _pro(tmp_path):
    (tmp_path / "x.kicad_pro").write_text("{}")
    return tmp_path / "x.kicad_pcb"


def test_the_project_rules_take_the_spec_severity(tmp_path):
    """機種が spec.DRC_SEVERITY で下げた重大度が .kicad_pro に書かれる（CCKB は 2026-09-24 から下げて
    いない。仕組みは残すので、下げる例を直に渡して見る）。"""
    from foundry.pcb_rules import sync_project_rules

    sync_project_rules(_pro(tmp_path), {"npth_inside_courtyard": "warning"})
    doc = json.loads((tmp_path / "x.kicad_pro").read_text())
    assert doc["board"]["design_settings"]["rule_severities"] == {"npth_inside_courtyard": "warning"}


def test_the_project_rules_raise_the_hole_clearance_only_when_asked(tmp_path):
    """spec.DRC_PTH_HOLE_CLEARANCE（CCKB は True）のときだけ穴と銅の距離を JLC の PTH と線 0.28 にする。
    渡さなければ書かない（HHKB は KiCad の既定 0.25 のまま・核の既定を変えない）。"""
    from foundry.pcb_rules import JLC, sync_project_rules

    sync_project_rules(_pro(tmp_path))
    rules = json.loads((tmp_path / "x.kicad_pro").read_text())["board"]["design_settings"]["rules"]
    assert "min_hole_clearance" not in rules
    sync_project_rules(_pro(tmp_path), pth_hole_clearance=True)
    rules = json.loads((tmp_path / "x.kicad_pro").read_text())["board"]["design_settings"]["rules"]
    assert rules["min_hole_clearance"] == JLC["pth_to_track"] == 0.28


@pytest.mark.parametrize("sev, msg", [
    ({"npth_inside_courtyard": "ignore"}, "ignore で隠さない"),   # 消させない
    ({"clearance": "warning"}, "警告に下げられない"),              # 製造に効く種類は下げさせない
])
def test_the_project_rules_refuse_to_hide_a_violation(tmp_path, sev, msg):
    from foundry.pcb_rules import sync_project_rules

    with pytest.raises(ValueError, match=msg):
        sync_project_rules(_pro(tmp_path), sev)


# ---- 組み立て手順書のゴーストの試験の組が、行列で四角になっているか ----

GUIDE = paths.ROOT / "projects" / "cckb" / "docs" / "assembly-guide.md"
GHOST = re.compile(r"（例 (\w+)・(\w+)・(\w+)）を同時に押して、4 つ目の角（(\w+)）が出ないか")


def ghost_trio_problems(guide_text, dtsi_text, keymap_text):
    """手順書の「3 つを押して 4 つ目が出ないか」の組が、**行列の**四角の 3 つの角と 4 つ目か。

    4 つ目の角にキーが無ければ、ダイオードが逆でも何も出ず試験にならない（4 回目の文書の監査 重要 1:
    A・S・W → Q）。キーの名前は base_mac の &kp の名前、位置は transform の RC（キーマップの並び）。
    """
    m = GHOST.search(guide_text)
    if not m:
        return ["手順書にゴーストの試験の組が見つからない"]
    text = re.sub(r"/\*.*?\*/|//[^\n]*", " ", keymap_text, flags=re.S)
    body = re.search(r"base_mac\s*\{\s*bindings\s*=\s*<(.*?)>;", text, re.S).group(1)
    binds = re.findall(r"&\w+(?:\s+[A-Z_0-9]+(?:\s+\d+)?)?", body)
    rcs = _transform_rcs(dtsi_text)
    assert len(binds) == len(rcs) == 62, (len(binds), len(rcs))
    where = {b.split()[-1]: rc for b, rc in zip(binds, rcs) if b.startswith("&kp ")}
    names = m.groups()
    missing = [n for n in names if n not in where]
    if missing:
        return [f"キーマップに無いキー: {missing}"]
    three = [where[n] for n in names[:3]]
    rows, cols = {r for r, _ in three}, {c for _, c in three}
    if len(set(three)) != 3 or len(rows) != 2 or len(cols) != 2:
        return [f"3 つのキー {names[:3]} = {three} は行列の四角の 3 つの角ではない"]
    fourth = next((r, c) for r in rows for c in cols if (r, c) not in three)
    at = [n for n, rc in where.items() if rc == fourth]
    if not at:
        return [f"4 つ目の角 {fourth} にキーが無い（ダイオードが逆でも何も出ない）"]
    if names[3] not in at:
        return [f"4 つ目の角 {fourth} のキーは {at}。手順書は {names[3]}"]
    return []


def test_the_ghost_test_in_the_guide_is_a_matrix_rectangle():
    assert ghost_trio_problems(GUIDE.read_text(), TRANSFORM.read_text(),
                               (SHIELD / "cckb.keymap").read_text()) == []


def test_the_ghost_check_notices_the_old_trio():
    """**壊して落ちることを示す。**前の組（A・S・W → Q）は 4 つ目の角 (1,2) にキーが無い。"""
    old = "（例 A・S・W）を同時に押して、4 つ目の角（Q）が出ないか"
    bad = ghost_trio_problems(old, TRANSFORM.read_text(), (SHIELD / "cckb.keymap").read_text())
    assert bad and "(1, 2)" in bad[0], bad
    wrong = "（例 W・E・S）を同時に押して、4 つ目の角（F）が出ないか"
    assert ghost_trio_problems(wrong, TRANSFORM.read_text(), (SHIELD / "cckb.keymap").read_text())
