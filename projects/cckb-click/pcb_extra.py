"""cckb-click の基板に、キー以外の物を置く（foundry.pcb が呼ぶ `place(board, ctx)`）。**KiCad の Python。**

置くもの（**全部表**。裏には部品を置かない）:
  - 幅の広いキー 11 個の空きランド（SWA{i}・SWB{i}。真ん中のスイッチと並列・JLC は実装しない・はんだを載せない）
  - XIAO（平ら・キャステレーション・手はんだ）・電池クリップ・電源スイッチ・74LVC595 ×2・パスコン・電源のショットキー・分圧
  - ルール領域: アンテナの銅の禁止域（全層）・XIAO の下の表の銅の禁止・ねじの頭の下の裏の銅の禁止・
    電池の下と抜き差しの道の表の銅の禁止・スイッチの本体の下のビアの禁止・外形の縁の帯
  - ネットクラス POWER

**寸法は持たない**（spec.py・click_layout.py）。**回路は持たない**（click_circuit.py。pinmap を通してパッドにネットを張るだけ。
宣言と足跡のパッドの過不足は落とす）。
"""

import math
import re
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import click_circuit                              # noqa: E402
import click_layout                               # noqa: E402
from foundry import paths                         # noqa: E402
from foundry.mech import SKRA_FP                  # noqa: E402
from foundry.pcb_rules import JLC, TRACK_W, VIA_D, VIA_DRILL   # noqa: E402
from foundry.project import load                  # noqa: E402

KEYSWITCH_LIB = paths.LIB / "keyswitch.pretty"
CLICK_LIB = paths.LIB / "cckb-click.pretty"
STD = paths.KICAD_FOOTPRINTS
FP = {  # 参照名 → (ライブラリ, 名前)
    "U_MCU": (paths.LIB / "xiao.pretty", "XIAO_nRF52840_SMD"),
    "BT1": (CLICK_LIB, "BAT_MY-1632-03-R"),
    "SW_PWR": (CLICK_LIB, "SW_MSK12C02"),
    "U1": (STD / "Package_SO.pretty", "TSSOP-16_4.4x5mm_P0.65mm"),
    "U2": (STD / "Package_SO.pretty", "TSSOP-16_4.4x5mm_P0.65mm"),
    "C_U1": (STD / "Capacitor_SMD.pretty", "C_0805_2012Metric"),
    "C_U2": (STD / "Capacitor_SMD.pretty", "C_0805_2012Metric"),
    "R_HI": (STD / "Resistor_SMD.pretty", "R_0805_2012Metric"),
    "R_LO": (STD / "Resistor_SMD.pretty", "R_0805_2012Metric"),
    "D_PWR": (STD / "Diode_SMD.pretty", "D_SOD-123"),
    "TP_VSW": (STD / "TestPoint.pretty", "TestPoint_Pad_D1.0mm"),
}
VALUE = {"U_MCU": "XIAO_nRF52840", "BT1": "MY-1632-03-R", "SW_PWR": "MSK12C02",
         "U1": "SN74LVC595APWR", "U2": "SN74LVC595APWR",
         "C_U1": "0.1uF", "C_U2": "0.1uF", "R_HI": "1M", "R_LO": "1M", "D_PWR": "BAT46W", "TP_VSW": "TP_VBAT_SW"}
SIDE_LAND_VALUE = "SKRA_side_land_unpopulated"
# 外形の縁の、配線・ビアを入れない帯の幅。JLC の銅と外形の規則に 0.02 足す（Freerouting は外形をネットクラスの間隔でしか避けない）
EDGE_BAND = JLC["edge_clearance"] + 0.02
# キーのダイオードの名札（部品の中心から。CAD）。既定の位置（上）はスイッチの手前のランドに近い。カソードの左へ
DIODE_REF_AT = (-4.4, 0.0)
LAYER = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


def _cad(q, origin):
    return (pcbnew.ToMM(q.x) - origin[0], origin[1] - pcbnew.ToMM(q.y))


def _put(board, ctx, lib, name, ref, value, at, deg):
    fp = ctx["load"](lib, name)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(ctx["to_kicad"](*at))
    fp.SetOrientationDegrees(deg)
    board.Add(fp)
    return fp


def _wire(fp, pads, net):
    """宣言（{パッド番号: ネット名}）どおりにパッドへネットを張る（同じ番号のパッドは全部）。**過不足は落とす。**"""
    have = {p.GetNumber() for p in fp.Pads() if p.GetNumber()}
    if have != set(pads):
        raise RuntimeError(f"{fp.GetReference()}: フットプリントのパッド {sorted(have)} と回路の宣言 {sorted(pads)} が違う")
    for p in fp.Pads():
        n = pads.get(p.GetNumber(), "")
        if n:
            p.SetNet(net(n))


def rule_area(board, ctx, box, layers, name, tracks=True, vias=True, fills=True):
    """配線・ビア・ベタを禁止する領域（パッド・部品は許す）。box は CAD の (x0, y0, x1, y1) か多角形 [(x, y), ...]。"""
    poly = box if isinstance(box[0], (tuple, list)) else \
        [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowZoneFills(fills)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    for lay in layers:
        ls.addLayer(lay)
    z.SetLayerSet(ls)
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in poly:
        pts.append(ctx["to_kicad"](x, y))
    z.AddPolygon(pts)
    board.Add(z)
    return z


def circle_poly(c, r, n=24):
    """半径 r の円を**外に接する** n 角形で（円を必ず覆う）。"""
    R = r / math.cos(math.pi / n)
    return [(c[0] + R * math.cos(2 * math.pi * (i + 0.5) / n),
             c[1] + R * math.sin(2 * math.pi * (i + 0.5) / n)) for i in range(n)]


# ルール領域の名前 → 層（tools/route_pcb.py が SES の取り込みの後で戻す。SES の往復で層が消える）
RULE_LAYERS = {
    "ANTENNA_KEEPOUT": ("F.Cu", "B.Cu"), "XIAO_UNDERSIDE": ("F.Cu",), "EDGE_KEEPOUT": ("F.Cu", "B.Cu"),
    "SCREW_HEAD_KEEPOUT": ("B.Cu",), "CELL_KEEPOUT": ("F.Cu",), "SW_BODY_KEEPOUT": ("F.Cu", "B.Cu"),
}
# ベタだけを禁止する領域（線・ビアは通す）。**配線の後で足す**（tools/route_click.py が no_fill_areas を呼ぶ）:
# 未配線の板に置くと、DSN へは「配線も禁止」として出て、Freerouting がその中のパッド（XIAO の D0）から出られなくなった（2026-10-03）
NO_FILL_LAYERS = {"FANOUT_NO_FILL": ("F.Cu",), "XIAO_BACK_NO_FILL": ("B.Cu",)}


def no_fill_areas(board, lay, to_kicad):
    """ベタだけを禁止する領域を足す。足した数。
      FANOUT_NO_FILL      595 から列への束の帯（表）: 線と線の間に、ビアの打てない細い帯が 100 mm 以上残る
      XIAO_BACK_NO_FILL   XIAO の下（裏）: 行の線で細い帯に切られ、ビアも打てない（click_layout.xiao_back_no_fill）"""
    ctx = dict(to_kicad=to_kicad)
    rule_area(board, ctx, lay.fanout_band(), (pcbnew.F_Cu,), "FANOUT_NO_FILL", tracks=False, vias=False, fills=True)
    rule_area(board, ctx, lay.xiao_back_no_fill(), (pcbnew.B_Cu,), "XIAO_BACK_NO_FILL", tracks=False, vias=False, fills=True)
    return 2



def place(board, ctx):
    project = load(HERE)
    s = project.spec
    lay = click_layout.Layout(project)
    origin = pcbnew.ToMM(ctx["to_kicad"](0, 0).x), pcbnew.ToMM(ctx["to_kicad"](0, 0).y)
    net = ctx["net"]
    want = click_circuit.expected_pad_nets(project)

    # --- 幅の広いキーの空きランド ----------------------------------------------
    for ref, x, y, populated in lay.switch_sites():
        if not populated:
            fp = _put(board, ctx, KEYSWITCH_LIB, SKRA_FP, ref, SIDE_LAND_VALUE, (x, y), 0)
            _wire(fp, want[ref], net)

    # --- ねじの穴（外周 ＋ 中の押さえ）-------------------------------------------
    for ref, c, _ in lay.screws():
        h = _put(board, ctx, CLICK_LIB, "Hole_M2_2.2", ref, "Hole_M2_2.2", c, 0)
        if abs(pcbnew.ToMM(h.Pads()[0].GetDrillSize().x) - s.SCREW_HOLE_D) > 1e-6:
            raise RuntimeError(f"{ref}: 穴の径が spec.SCREW_HOLE_D {s.SCREW_HOLE_D} でない")

    # --- 角の部品 -------------------------------------------------------------
    # XIAO: 原点はピンの並びの中心。USB を −x に向ける（USB は足跡で −y にあるので +90°）
    x, y = s.XIAO_AT
    u = _put(board, ctx, *FP["U_MCU"], "U_MCU", VALUE["U_MCU"], (x + s.XIAO_PIN_SHIFT, y), 90)
    d0 = _cad(u.FindPadByNumber("D0").GetPosition(), origin)
    d6 = _cad(u.FindPadByNumber("D6").GetPosition(), origin)
    v5 = _cad(u.FindPadByNumber("5V").GetPosition(), origin)
    u.Reference().SetPosition(ctx["to_kicad"](x, y))          # 既定の位置は基板の縁の外。XIAO の下（中心）へ
    if not (d0[1] < y and v5[1] > y and d0[0] < d6[0]):
        raise RuntimeError(f"XIAO の向きが違う: D0 {d0} D6 {d6} 5V {v5}（D0〜D6 は手前・D0 が USB 側）")
    # 電池クリップ: 口が手前（足跡の +y〔KiCad〕= CAD の −y）
    _put(board, ctx, *FP["BT1"], "BT1", VALUE["BT1"], s.CLIP_AT, 0)
    # 電源スイッチ: つまみを右（+x）へ。足跡ではつまみが +y（KiCad）なので +90°。端子 3 が奥
    sw = _put(board, ctx, *FP["SW_PWR"], "SW_PWR", VALUE["SW_PWR"], s.PSW_AT, 90)
    p1, p3 = (_cad(sw.FindPadByNumber(n).GetPosition(), origin) for n in "13")
    holes = [_cad(p.GetPosition(), origin) for p in sw.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    body_x = s.PSW_AT[0] + s.PSW_ORIGIN_TO_BODY
    if not (p3[1] > s.PSW_AT[1] > p1[1] and p1[0] < body_x and all(abs(h[0] - body_x) < 1e-3 for h in holes)):
        raise RuntimeError(f"電源スイッチの向きが違う: 端子 1 {p1}・3 {p3}・突起の穴 {holes}（3 が奥・端子は左・穴は本体の中心線）")

    # --- 表の電子部品 -----------------------------------------------------------
    for ref, (px, py, deg) in s.PART_AT.items():
        fp = _put(board, ctx, *FP[ref], ref, VALUE[ref], (px, py), deg)
        if ref in s.REF_TEXT_AT:
            dx, dy = s.REF_TEXT_AT[ref]
            fp.Reference().SetPosition(ctx["to_kicad"](px + dx, py + dy))
            fp.Reference().SetTextAngleDegrees(0)
    tp = _put(board, ctx, *FP["TP_VSW"], "TP_VSW", VALUE["TP_VSW"], s.TP_VSW_AT, 0)
    tp.Reference().SetVisible(False)                     # リブの下。名札は刷らない（位置は手順書の絵で）
    if set(s.REF_TEXT_AT) - set(s.PART_AT):
        raise RuntimeError(f"REF_TEXT_AT の {sorted(set(s.REF_TEXT_AT) - set(s.PART_AT))} が PART_AT に無い")

    # --- キーのダイオードの名札 ---------------------------------------------------
    moved = {f"D{i}" for i in project.diode_override("main")}       # 置き場所を変えたダイオードは、名札を右へ（左は 595 のパスコン）
    for fp in board.GetFootprints():
        if re.fullmatch(r"D\d+", fp.GetReference()):
            px, py = _cad(fp.GetPosition(), origin)
            sgn = -1 if fp.GetReference() in moved else 1
            fp.Reference().SetPosition(ctx["to_kicad"](px + sgn * DIODE_REF_AT[0], py + DIODE_REF_AT[1]))

    # --- JLC が実装しない物（spec.NOT_ASSEMBLED）のパッドからペーストの層を外す --------------
    # JLC はペーストの層からステンシルを作り、載せない部品のパッドにもはんだを盛ってリフローする
    for fp in board.GetFootprints():
        kind = next((k for pat, k in s.FAB_KINDS.items() if re.fullmatch(pat, fp.GetReference())), None)
        if kind in s.NOT_ASSEMBLED:
            for p in fp.Pads():
                ls = p.GetLayerSet()
                ls.removeLayer(pcbnew.F_Paste)
                ls.removeLayer(pcbnew.B_Paste)
                p.SetLayerSet(ls)

    # --- ネット（click_circuit.py の宣言どおり）---------------------------------
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    for ref, _, _ in click_circuit.electronics():
        _wire(fps[ref], want[ref], net)
    for ref, nums in s.THERMAL_PADS.items():
        for num in nums:
            ps = [p for p in fps[ref].Pads() if p.GetNumber() == num]
            if len(ps) != 1 or ps[0].GetNetname() != "GND":
                raise RuntimeError(f"{ref}.{num}: サーマルにする GND のパッドが {len(ps)} 個")
            ps[0].SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_THERMAL)

    # --- ルール領域 -------------------------------------------------------------
    both = (pcbnew.F_Cu, pcbnew.B_Cu)
    rule_area(board, ctx, lay.antenna_keepout(), both, "ANTENNA_KEEPOUT")
    for box in lay.xiao_underside():
        rule_area(board, ctx, box, (pcbnew.F_Cu,), "XIAO_UNDERSIDE")
    # ねじの頭（金属）は基板の下面に着く。締め付けでマスクが欠けると、下の信号が頭を通して GND や隣の線に落ちる
    for _, c, r in lay.screw_head_keepouts():
        rule_area(board, ctx, circle_poly(c, r), (pcbnew.B_Cu,), "SCREW_HEAD_KEEPOUT")
    # 電池の下と抜き差しの道: 表の銅（線・ビア・ベタ）を置かない。−の裸の銅（パッド）だけが残る
    rule_area(board, ctx, lay.cell_keepout(), (pcbnew.F_Cu,), "CELL_KEEPOUT")
    # スイッチの本体の下にビアを置かない（Alps の仕様書 10.3(4)「No through holes shall be located underneath and/or
    # near the switch」。空きランドも、あとでスイッチを付けるので同じ）。線は通してよい（ランドどうしを本体の下で結ぶ）
    for _, sx, sy, _ in lay.switch_sites():
        rule_area(board, ctx, lay.switch_body(sx, sy), both, "SW_BODY_KEEPOUT", tracks=False, fills=False)
    x0, y0, x1, y1 = lay.pcb
    w = EDGE_BAND
    for strip in ((x0, y0, x1, y0 + w), (x0, y1 - w, x1, y1), (x0, y0, x0 + w, y1), (x1 - w, y0, x1, y1)):
        rule_area(board, ctx, strip, both, "EDGE_KEEPOUT", fills=False)

    # --- ネットクラス（**Recompute しないと割り当てが効かない**）---------------
    d = board.GetDesignSettings()
    ns = d.m_NetSettings
    cls = pcbnew.NETCLASS("POWER")
    cls.SetTrackWidth(pcbnew.FromMM(s.POWER_TRACK_W))
    cls.SetClearance(pcbnew.FromMM(TRACK_W))
    cls.SetViaDiameter(pcbnew.FromMM(VIA_D))
    cls.SetViaDrill(pcbnew.FromMM(VIA_DRILL))
    ns.SetNetclass("POWER", cls)
    for n in click_circuit.POWER_NETS:
        ns.SetNetclassPatternAssignment(n, "POWER")
    ns.RecomputeEffectiveNetclasses()
    return board
