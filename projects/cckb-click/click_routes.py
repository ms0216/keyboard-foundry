"""cckb-click の行列の配線を決まった形で引く計画。**寸法は持たない**（spec.py・click_layout.py から読む）。

    表 F.Cu  スイッチのランドどうし（同じ番号の 2 つ・空きランド）を本体の下で結ぶ横線（奥の列 = 列の網・手前の列 = スイッチとダイオードの間）
             手前右のランド → ダイオードのアノード（真下へ縦の 1 本）
             ダイオードのカソード → 行のバス（キーの中心から ROW_BUS_DY の高さの横一直線・段ごとに 1 本）
             奥右のランド → 列を裏へ落とすビア（COL_VIA・幅の広いキーは COL_VIA_WIDE）
    裏 B.Cu  列: 上の段のビア → 下へ → 段の境目で横に渡り → 下の段のビアへ（裏には部品が無い）

**板の上のパッドの実際の位置から引く**（pcbnew が回転まで解いた世界座標。tools/route_pcb.py が板を読んで渡す）。
線と板の物（パッド・穴・ねじの頭の禁止域・外形）の間隔は、CCKB の matrix_routes.Obstacles で自分で確かめる（近ければ落とす）。
XIAO（D2〜D6）から行のバスまでも決まった形で引く（spec.XIAO_ESCAPE）。最後の判定は KiCad の DRC。
595 から列までも決まった形で引く（fanout）。SPI・電源は Freerouting が引く。

KiCad の Python（3.9）からも読むので標準ライブラリだけ。座標は CAD（Y 上向き・mm）。
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT), str(HERE), str(ROOT / "projects" / "cckb")):
    if _p not in sys.path:
        sys.path.append(_p)

import click_layout                                # noqa: E402
import matrix_routes as mr                         # noqa: E402  （CCKB の物を**道具として**借りる: Obstacles・clashes・距離）
from foundry.layout import UNIT                    # noqa: E402

F, B = "F.Cu", "B.Cu"
# ランドどうしを結ぶ線が部品（595）に当たるとき: 595 の本体の下（2 列のピンの間）を通す。ランドの列から、キーの中心線の側へ
# spec.LINK_UNDER 寄せる。縦の脚は、ランドの中心から LINK_LEG（ランドの端から 0.625）。
# **595 を線で囲まない**（外を回すと、595 のピンから表で出る道が無くなり、Freerouting が列を繋げなかった）
LINK_LEG = 2.0
# 行のバスの左端を LEFT へ伸ばした所にビアを置き、XIAO からの裏の線を受ける
ROW_VIA_DX = 2.0
# 列が段の境目を横に渡る高さを、境目からずらす候補（近い順）。境目の真上は、表の柱の下で、裏には何も無い
CROSS_OFFSETS = (0.0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, 2.4, -2.4)


def _r(p):
    return (round(p[0], 4), round(p[1], 4))


def fanout(lay, by, col_vias, segs, lay_seg, put_via):
    """595（U1 = 列 0〜7・U2 = 列 8〜14）から列へ。表の、段 FANOUT_ROW のすぐ奥の帯を横の束で走る（spec の FANOUT_*）。

    奥の列のピン（Q1〜Q7）: ピンから奥へ上がり、束の中の自分の高さで右へ走り、行き先の x で手前へ下りる。行き先は
      - その列の段 FANOUT_ROW のキーの「列を裏へ落とすビア」（もうある。そこへ表の線で下りる）
      - U のいるキー自身の列（列 1）は、右の空きランドの奥左のランド
      - 段 FANOUT_ROW にキーの無い列（列 12）は、その列の裏の縦線の上に新しいビア
    手前の列の Q0（U1 = 列 0・U2 = 列 8）: ピンの手前のビアで裏へ落ち、595 の下を奥へ抜けて、束の中のビアで表へ戻る。
      列 0 は左へ走り、左 Ctrl のビアの真下で裏へ落ちて上がる。列 8 は束のいちばん奥を右へ走り、列 8 の裏の縦線の上のビアで終わる。
    高さの順: U1 の線（行き先が近い順に手前から）→ 列 0 → U2 の線（同じ順）→ 列 8。**ピンから上がる線が、ほかの線をまたがない**
    （ピンは右ほど行き先が近い = 低い。U2 は U1 の左にあり、U2 の線は U1 の線より奥）。またぎは最後に clashes が見る。"""
    s = lay.s
    row_y = lay.rows()[s.FANOUT_ROW]
    y0 = row_y + s.FANOUT_Y0
    host = next(k for k in lay.keys if k.r == s.FANOUT_ROW and lay.hole(k)[0] < s.PART_AT["U1"][0] < lay.hole(k)[2])
    row_via = {net: v for net, lst in col_vias.items() for r, v, i in lst if r == s.FANOUT_ROW}

    def bottom_vertical(net, y, skip_x=None):
        xs = [a[0] for n, layer, a, b in segs if n == net and layer == B and a[0] == b[0] and a[0] != skip_x
              and min(a[1], b[1]) <= y <= max(a[1], b[1])]
        if len(xs) != 1:
            raise ValueError(f"{net}: 高さ {y} を通る裏の縦線が {len(xs)} 本")
        return xs[0]

    def pins(ref):
        north, south = [], None
        for (r, num), ps in by.items():
            if r != ref or not re.fullmatch(r"COL\d+", ps[0]["net"]):
                continue
            (north.append(ps[0]) if ps[0]["y"] > s.PART_AT[ref][1] else None)
            if ps[0]["y"] < s.PART_AT[ref][1]:
                south = ps[0]
        if south is None or len(north) < 6:
            raise ValueError(f"{ref}: 奥の列の出力 {len(north)} 本・手前の列の出力 {south}")
        return sorted(north, key=lambda p: -p["x"]), south          # 右のピンから

    level = 0.0
    done = {}
    for ref in ("U1", "U2"):
        north, q0 = pins(ref)
        targets = []
        for p in north:
            net = p["net"]
            if net == f"COL{host.c}":
                pad = min(by[(f"SWB{host.i}", "1")], key=lambda q: q["x"])      # 自分のキー: 右の空きランドの奥左
                targets.append((pad["x"], p, (pad["x"], pad["y"]), False))
            elif net in row_via:
                targets.append((row_via[net][0], p, row_via[net], False))
            else:
                targets.append((None, p, None, True))
        for i, (tx, p, end, new_via) in enumerate(targets):
            if tx is None:
                targets[i] = (bottom_vertical(p["net"], y0 + 2.0), p, None, True)
        order = sorted(targets, key=lambda t: t[0])
        if [t[1]["num"] for t in order] != [p["num"] for p in north]:
            raise ValueError(f"{ref}: 行き先の近い順 {[t[1]['net'] for t in order]} とピンの右からの順 {[p['net'] for p in north]} が違う"
                             "（ピンから上がる線がほかの線をまたぐ）")
        for tx, p, end, new_via in order:
            y = round(y0 + level, 4)
            net = p["net"]
            if new_via:
                # 新しいビア: 線の端から手前へ 0.3 下りた所（奥の隣の線から 0.7）。手前の線はもう終わっている
                v = (tx, round(y - 0.3, 4))
                lay_seg(net, F, [(p["x"], p["y"]), (p["x"], y), (tx, y), v], f"{ref}→{net}")
                put_via(net, v)
            else:
                lay_seg(net, F, [(p["x"], p["y"]), (p["x"], y), (tx, y), end], f"{ref}→{net}")
            done[net] = y
            level += s.FANOUT_PITCH
        # Q0: 手前のビア → 裏で奥へ → 束の中のビア
        level += s.FANOUT_VIA_GAP - s.FANOUT_PITCH
        y = round(y0 + level, 4)
        net = q0["net"]
        va = (q0["x"], round(s.PART_AT[ref][1] - s.FANOUT_HOP_DY, 4))
        vb = (q0["x"], y)
        lay_seg(net, F, [(q0["x"], q0["y"]), va], f"{ref}→{net}（手前のビア）")
        put_via(net, va)
        lay_seg(net, B, [va, vb], f"{ref}→{net}（595 の下）")
        put_via(net, vb)
        if ref == "U1":
            # 列 0: 左へ。いちばん下のキー（左 Ctrl）のビアの真下で裏へ落ち、そのビアまで上がる
            r, v, i = max(col_vias[net])
            vc = (v[0], y)
            lay_seg(net, F, [vb, vc], f"{ref}→{net}（左へ）")
            put_via(net, vc)
            lay_seg(net, B, [vc, v], f"{ref}→{net}（SW{i} のビアへ）")
        else:
            tx = bottom_vertical(net, y, skip_x=_r(vb)[0])
            lay_seg(net, F, [vb, (tx, y)], f"{ref}→{net}（右へ）")
            put_via(net, (tx, y))
        done[net] = y
        level += s.FANOUT_VIA_GAP
    if len(done) != 15:
        raise ValueError(f"595 から引いた列が {len(done)} 本（15 本のはず）: {sorted(done)}")
    return done


def power_run(lay, by, segs, obs):
    """電源の長い線（spec.POWER_RUN・表・太さ POWER_TRACK_W）。[(net, layer, a, b)]。
    frm のランドから、段 row のバスの POWER_RUN_BELOW 手前を右へ走り、to のパッドの左 jog で手前へ下りてパッドへ入る。
    板の物との間隔は太い線の半幅で、ほかの決まった線との間隔も見る。近ければ落とす。"""
    s = lay.s
    how = s.POWER_RUN
    net = how["net"]
    a = by[tuple(how["frm"])][0]
    b = by[tuple(how["to"])][0]
    if a["net"] != net or b["net"] != net:
        raise ValueError(f"{net}: 端のパッドの網が {a['net']}・{b['net']}")
    y = round(lay.rows()[how["row"]] + s.ROW_BUS_DY - s.POWER_RUN_BELOW, 4)
    if abs(a["y"] - y) > 1e-3:
        raise ValueError(f"{net}: {how['frm']} の高さ {a['y']} が線の高さ {y} でない（spec.TP_VSW_AT）")
    xj = round(b["x"] - how["jog"], 4)
    pts = [(a["x"], y), (xj, y), (xj, b["y"]), (b["x"], b["y"])]
    half = s.POWER_TRACK_W / 2
    out = []
    for p, q in zip(pts, pts[1:]):
        bad = obs.problems(net, F, p, q, half=half)
        bad += [(m, c, d) for m, layer, c, d in segs
                if layer == F and m != net and mr.seg_seg_dist(p, q, c, d) < mr.CLEAR + half + mr.HALF_W - 1e-9]
        if bad:
            raise ValueError(f"{net} {p}->{q} が近い: {bad[:3]}")
        out.append((net, F, _r(p), _r(q)))
    return out


def sense_run(lay, by, vpad, lay_seg, put_via):
    """電池電圧の線（spec.SENSE_RUN）。XIAO のパッド内ビア → 裏を左の縁へ寄せて上がる → ビア → 表で分圧の中点の 2 つのパッドへ。"""
    how = lay.s.SENSE_RUN
    net = how["net"]
    if net not in vpad:
        raise ValueError(f"{net}: XIAO のパッド内ビアが無い")
    x0, y0 = vpad[net]
    a = by[tuple(how["to"])][0]
    b = by[tuple(how["link"])][0]
    if a["net"] != net or b["net"] != net:
        raise ValueError(f"{net}: 端のパッドの網が {a['net']}・{b['net']}")
    v = (how["lane_x"], how["via_y"])
    lay_seg(net, B, [(x0, y0), (x0, how["turn_y"]), (how["lane_x"], how["turn_y"]), v], "XIAO→分圧")
    put_via(net, v)
    lay_seg(net, F, [v, (a["x"], how["via_y"]), (a["x"], a["y"])], "分圧の中点へ")
    if abs(a["y"] - b["y"]) > 1e-3:
        raise ValueError(f"{net}: 分圧の 2 つのパッドの高さが違う")
    lay_seg(net, F, [(a["x"], a["y"]), (b["x"], b["y"])], "分圧の中点どうし")


def cap_land_run(lay, by, wide, segs, obs):
    """載せないコンデンサのランド C_BAT の 1 番（VBAT_SW）を、電源の長い線の縦の区間へ横にまっすぐ繋ぐ（表・電源の太さ）。"""
    s = lay.s
    net = s.POWER_RUN["net"]
    p = by[("C_BAT", "1")][0]
    if p["net"] != net:
        raise ValueError(f"C_BAT.1 の網が {p['net']}")
    vert = [(a, b) for m, layer, a, b in wide if m == net and a[0] == b[0] and min(a[1], b[1]) <= p["y"] <= max(a[1], b[1])]
    if len(vert) != 1:
        raise ValueError(f"C_BAT.1 の高さ {p['y']} を通る {net} の縦の区間が {len(vert)} 本")
    a, b = (p["x"], p["y"]), (vert[0][0][0], p["y"])
    half = s.POWER_TRACK_W / 2
    bad = obs.problems(net, F, a, b, half=half)
    bad += [(m, c, d) for m, layer, c, d in segs
            if layer == F and m != net and mr.seg_seg_dist(a, b, c, d) < mr.CLEAR + half + mr.HALF_W - 1e-9]
    if bad:
        raise ValueError(f"{net} {a}->{b} が近い: {bad[:3]}")
    return [(net, F, _r(a), _r(b))]


def v3v3_run(lay, by, segs, obs_f, obs_b, put_via):
    """載せないコンデンサのランド C_3V3 の 1 番を、U1 のパスコンの 1 番へ（spec.V3V3_RUN）。[(net, layer, a, b)]（電源の太さ）。"""
    s = lay.s
    how = s.V3V3_RUN
    net = how["net"]
    a = by[tuple(how["frm"])][0]
    b = by[tuple(how["to"])][0]
    if a["net"] != net or b["net"] != net:
        raise ValueError(f"{net}: 端のパッドの網が {a['net']}・{b['net']}")
    va = (a["x"], round(a["y"] - how["down"], 4))
    vb = (b["x"], round(b["y"] - how["below"], 4))
    half = s.POWER_TRACK_W / 2
    out = []
    for layer, obs, pts in ((F, obs_f, [(a["x"], a["y"]), va]), (B, obs_b, [va, (vb[0], va[1])]),
                            (B, obs_b, [(vb[0], va[1]), vb]), (F, obs_f, [vb, (b["x"], b["y"])])):
        p, q = pts
        bad = obs.problems(net, layer, p, q, half=half)
        bad += [(m, c, d) for m, lyr, c, d in segs
                if lyr == layer and m != net and mr.seg_seg_dist(p, q, c, d) < mr.CLEAR + half + mr.HALF_W - 1e-9]
        if bad:
            raise ValueError(f"{net} {layer} {p}->{q} が近い: {bad[:3]}")
        out.append((net, layer, _r(p), _r(q)))
    put_via(net, va)
    put_via(net, vb)
    return out


def gnd_return_run(lay, by, segs, obs_f, obs_b, put_via):
    """パスコンの GND（2 番）から、その 595 の GND のピン（8 番）までの戻り（spec.GND_RETURN）。[(net, layer, a, b)]（電源の太さ）。
    595 の Q0 を裏へ落とすビアの手前を回る。"""
    s = lay.s
    how = s.GND_RETURN
    half = s.POWER_TRACK_W / 2
    out = []
    for ref in ("U1", "U2"):
        c = by[(f"C_{ref}", "2")][0]
        g = by[(ref, "8")][0]
        q0 = next(ps[0] for (r, num), ps in by.items() if r == ref and ps[0]["y"] < s.PART_AT[ref][1] and re.fullmatch(r"COL\d+", ps[0]["net"]))
        if c["net"] != "GND" or g["net"] != "GND":
            raise ValueError(f"{ref}: パスコンの 2 番・595 の 8 番の網が {c['net']}・{g['net']}")
        v1 = (c["x"], round(c["y"] + how["up"], 4))
        v8 = (round(g["x"] - how["left"], 4), g["y"])
        y = round(s.PART_AT[ref][1] - s.FANOUT_HOP_DY - how["below_hop"], 4)
        if not (v8[0] < q0["x"] < v1[0]):
            raise ValueError(f"{ref}: Q0 のピン x {q0['x']} が、8 番のビア {v8[0]} とパスコンのビア {v1[0]} の間に無い")
        runs = ((F, obs_f, [(c["x"], c["y"]), v1]), (B, obs_b, [v1, (v1[0], y)]), (B, obs_b, [(v1[0], y), (v8[0], y)]),
                (B, obs_b, [(v8[0], y), v8]), (F, obs_f, [v8, (g["x"], g["y"])]))
        for layer, obs, (p, q) in runs:
            bad = obs.problems("GND", layer, p, q, half=half)
            bad += [(m, a, b) for m, lyr, a, b in segs
                    if lyr == layer and m != "GND" and mr.seg_seg_dist(p, q, a, b) < mr.CLEAR + half + mr.HALF_W - 1e-9]
            if bad:
                raise ValueError(f"GND の戻り（{ref}）{layer} {p}->{q} が近い: {bad[:3]}")
            out.append(("GND", layer, _r(p), _r(q)))
        put_via("GND", v1)
        put_via("GND", v8)
    return out


def plan(project, pads, edge=None, head_keepouts=None):
    """(細い線 [(net, layer, a, b)], ビア [(net, (x, y))], 太い線 [(net, layer, a, b)])。pads は板から読んだパッド（projects/cckb/tools/board_geometry.dump の書式）。"""
    lay = click_layout.Layout(project)
    s = lay.s
    edge = lay.pcb if edge is None else edge
    heads = [(c, r) for _, c, r in lay.screw_head_keepouts()] if head_keepouts is None else head_keepouts
    obs_f = mr.Obstacles(pads, [], edge)
    obs_b = mr.Obstacles(pads, [], edge, heads)          # ねじの頭の禁止域は裏だけ
    by = {}
    for p in pads:
        if p["num"]:
            by.setdefault((p["ref"], p["num"]), []).append(p)
    segs, vias = [], []

    def lay_seg(net, layer, pts, why):
        obs = obs_f if layer == F else obs_b
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9:
                raise ValueError(f"{net}（{why}）: 斜めの線")
            bad = obs.problems(net, layer, a, b)
            if bad:
                raise ValueError(f"{net}（{why}）{layer} {a}->{b} が板の物に近い: {bad[:3]}")
            segs.append((net, layer, _r(a), _r(b)))

    def ok(net, layer, pts):
        obs = obs_f if layer == F else obs_b
        return not any(obs.problems(net, layer, a, b) for a, b in zip(pts, pts[1:]) if a != b)

    def put_via(net, p):
        for layer, obs in ((F, obs_f), (B, obs_b)):
            bad = obs.problems(net, layer, p, p, half=mr.VIA_R)
            if bad:
                raise ValueError(f"{net} のビア {p} が板の物に近い: {bad[:3]}")
        vias.append((net, _r(p)))

    col_vias = {}
    rows = {}
    for k in lay.keys:
        sites = [f"SW{k.i}"] + ([f"SWA{k.i}", f"SWB{k.i}"] if lay.side_offset(k) is not None else [])
        for num in ("1", "2"):
            ps = sorted((p for ref in sites for p in by[(ref, num)]), key=lambda p: p["x"])
            nets = {p["net"] for p in ps}
            ys = {round(p["y"], 4) for p in ps}
            if len(nets) != 1 or len(ys) != 1:
                raise ValueError(f"SW{k.i} のパッド {num}: 網 {nets}・高さ {ys}（1 つずつのはず）")
            sgn = 1 if num == "1" else -1
            for pa, pb in zip(ps, ps[1:]):
                # まっすぐ結ぶ。あいだに部品（595）がある所は、その本体の下を通す
                a0, b0 = (pa["x"], pa["y"]), (pb["x"], pb["y"])
                yu = a0[1] - sgn * s.LINK_UNDER
                under = [a0, (a0[0] + LINK_LEG, a0[1]), (a0[0] + LINK_LEG, yu), (b0[0] - LINK_LEG, yu), (b0[0] - LINK_LEG, b0[1]), b0]
                path = next((c for c in ([a0, b0], under) if ok(pa["net"], F, c)), None)
                if path is None:
                    raise ValueError(f"SW{k.i} のランド {num}: {a0}→{b0} を結ぶ道が無い")
                lay_seg(pa["net"], F, path, f"SW{k.i} のランド {num}")
        # 手前のランド（アノードの真上にある物。ふつうは真ん中のスイッチの手前右）→ アノード
        a = by[(f"D{k.i}", "2")][0]
        kk = by[(f"D{k.i}", "1")][0]
        p2 = min((p for ref in sites for p in by[(ref, "2")]), key=lambda p: abs(p["x"] - a["x"]))
        if p2["net"] != a["net"] or not re.fullmatch(r"ROW\d+", kk["net"]):
            raise ValueError(f"SW{k.i}/D{k.i} の網が行列の形でない: {p2['net']} {a['net']} {kk['net']}")
        if abs(p2["x"] - a["x"]) > 1e-3:
            raise ValueError(f"D{k.i} のアノード x {a['x']} が手前のランド x {p2['x']} の真下でない")
        lay_seg(a["net"], F, [(p2["x"], p2["y"]), (a["x"], a["y"])], f"SW{k.i}→D{k.i}")
        bus_y = round(k.y + s.ROW_BUS_DY, 4)
        lay_seg(kk["net"], F, [(kk["x"], kk["y"]), (kk["x"], bus_y)], f"D{k.i}→バス")
        rows.setdefault(kk["net"], []).append((kk["x"], bus_y))
        # 奥右のランド → ビア
        p1 = max(by[(f"SW{k.i}", "1")], key=lambda p: p["x"])
        v = lay.col_via(k)
        if abs(v[0] - p1["x"]) < 1e-3:                    # 板の座標は 0.1µm に丸まっている。軸をランドに合わせる
            v = (p1["x"], v[1])
        elif abs(v[1] - p1["y"]) < 1e-3:
            v = (v[0], p1["y"])
        else:
            raise ValueError(f"SW{k.i}: ビア {v} が奥右のランド {(p1['x'], p1['y'])} の真横・真上でない")
        lay_seg(p1["net"], F, [(p1["x"], p1["y"]), v], f"SW{k.i}→ビア")
        put_via(p1["net"], v)
        col_vias.setdefault(p1["net"], []).append((k.r, v, k.i))

    # 行のバス（表）
    for net, pts in sorted(rows.items()):
        ys = {y for _, y in pts}
        if len(ys) != 1:
            raise ValueError(f"{net}: バスの高さが揃わない {ys}")
        xs = sorted(x for x, _ in pts)
        y = ys.pop()
        lay_seg(net, F, [(xs[0], y), (xs[-1], y)], "バス")

    # XIAO（D2〜D6 のパッド内ビア・手前の列）→ 行のバス。**裏を通す**（XIAO の下の表は銅の禁止。裏には部品が無い）
    #   行 0〜2  ビアから turn_y まで上がり、左の縁の通り道 lane_x へ寄って、そのバスの高さまで上がり、右へバスの左端のビアへ。
    #            turn_y は行 0 がいちばん手前・lane_x は行 0 がいちばん左（裏の線どうしがまたがない）
    #   行 3     まっすぐ上がってバスの高さで右へ（XIAO の下。アンテナの禁止域の左）
    #   行 4     run_y まで上がり、アンテナの禁止域の手前を右へ、バスの左端のビアの下で上がる
    vpad = {p_["net"]: (p_["x"], p_["y"]) for p_ in pads
            if p_["ref"] == "U_MCU" and not p_["npth"] and p_["front"] and p_["back"] and p_["net"]}
    vpad_all = dict(vpad)
    for net, pts in sorted(rows.items()):
        how = s.XIAO_ESCAPE[net]
        if net not in vpad:
            raise ValueError(f"{net}: XIAO のパッド内ビアが無い")
        x0, y0 = vpad[net]
        y = pts[0][1]
        xb = min(x for x, _ in pts)
        vx = round(how.get("via_x", xb - ROW_VIA_DX), 4)
        lay_seg(net, F, [(vx, y), (xb, y)], "バスの左端")
        put_via(net, (vx, y))
        if "lane_x" in how:
            path = [(x0, y0), (x0, how["turn_y"]), (how["lane_x"], how["turn_y"]), (how["lane_x"], y), (vx, y)]
        elif "run_y" in how:
            path = [(x0, y0), (x0, how["run_y"]), (vx, how["run_y"]), (vx, y)]
        else:
            path = [(x0, y0), (x0, y), (vx, y)]
        lay_seg(net, B, path, "XIAO→バス")
    if set(s.XIAO_ESCAPE) != set(rows):
        raise ValueError(f"spec.XIAO_ESCAPE {sorted(s.XIAO_ESCAPE)} と行の網 {sorted(rows)} が違う")

    # 列（裏）
    for net, ks in sorted(col_vias.items()):
        ks.sort()
        for (ru, vu, iu), (rl, vl, il) in zip(ks, ks[1:]):
            yb = lay.rows()[ru] - UNIT / 2
            path = None
            first = getattr(s, "COL_CROSS_OFFSET", {}).get(rl - 1)
            for off in ((first,) if first is not None else ()) + CROSS_OFFSETS:
                yj = round(yb - (rl - ru - 1) * UNIT + off, 4)       # 段を飛ばすときは、下のキーのすぐ上の境目で渡る
                cand = [vu, (vu[0], yj), (vl[0], yj), vl]
                if ok(net, B, cand):
                    path = cand
                    break
            if path is None:
                raise ValueError(f"{net}: SW{iu}→SW{il} の裏の道が無い")
            lay_seg(net, B, path, f"SW{iu}→SW{il}")

    fanout(lay, by, col_vias, segs, lay_seg, put_via)
    sense_run(lay, by, vpad_all, lay_seg, put_via)
    for x in s.IC_BAND_VIA_X:                           # 595 の本体の下の GND の帯のビア（spec.IC_BAND）
        put_via("GND", (x, s.PART_AT["U1"][1]))
    wide = power_run(lay, by, segs, obs_f)
    wide += cap_land_run(lay, by, wide, segs, obs_f)
    wide += v3v3_run(lay, by, segs, obs_f, obs_b, put_via)
    wide += gnd_return_run(lay, by, segs + wide, obs_f, obs_b, put_via)

    bad = mr.clashes(segs)
    bad += [f"ビア {n} {p} が {m} {a}->{b} に近い" for n, p in vias for m, _, a, b in segs
            if m != n and mr.seg_seg_dist(p, p, a, b) < mr.VIA_R + mr.CLEAR + mr.HALF_W - 1e-9]
    if bad:
        raise ValueError("行列の配線の計画が自分とぶつかる:\n  " + "\n  ".join(bad[:10]))
    return segs, vias, wide
