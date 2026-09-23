"""CCKB の基板に、キー以外の物を置く（foundry.pcb が呼ぶ `place(board, ctx)`）。**KiCad の Python。**

置くもの（決定記録 decisions/2026-09-24-interface.md §5-5 の凍結した境界）:
  - スタビの逃げ穴 8 つ（Edge.Cuts・interface.stab_reliefs）
  - XIAO（表・平ら・キャステレーション）・電池ホルダ（表）・電源スイッチ（裏）・右のふたの柱の穴
  - 裏の電子部品（74LVC595 ×2・パスコン・B5819W・分圧）
  - ルール領域: アンテナの銅の禁止域（全層）・XIAO の下の表の銅の禁止（XIAO の裏のパッドと短絡させない）
  - ネットクラス POWER

**寸法は持たない**（spec.py・interface.py）。**回路は持たない**（circuit.py。ここは pinmap を通して
パッドにネットを張るだけ。引けないピン・宣言に無いパッドは落とす）。
"""

import math
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import circuit                                   # noqa: E402
import interface                                 # noqa: E402
from foundry import paths                        # noqa: E402
from foundry.pcb_rules import TRACK_W, VIA_D, VIA_DRILL   # noqa: E402
from foundry.project import load                 # noqa: E402

XIAO_LIB = paths.LIB / "xiao.pretty"
CCKB_LIB = paths.LIB / "cckb.pretty"
FP = {  # 参照名 → (ライブラリ, 名前, 表か)
    "U_MCU": (XIAO_LIB, "XIAO_nRF52840_SMD", True),
    "BT1": (CCKB_LIB, "BAT_BS-16-B4AK003", True),
    "SW_PWR": (CCKB_LIB, "SW_MK-12C02-G025", False),
    "H_LID": (CCKB_LIB, "Hole_NPTH_6.0mm", True),
    "U1": (paths.KICAD_FOOTPRINTS / "Package_SO.pretty", "TSSOP-16_4.4x5mm_P0.65mm", False),
    "U2": (paths.KICAD_FOOTPRINTS / "Package_SO.pretty", "TSSOP-16_4.4x5mm_P0.65mm", False),
    "C_U1": (paths.KICAD_FOOTPRINTS / "Capacitor_SMD.pretty", "C_0805_2012Metric", False),
    "C_U2": (paths.KICAD_FOOTPRINTS / "Capacitor_SMD.pretty", "C_0805_2012Metric", False),
    "R_HI": (paths.KICAD_FOOTPRINTS / "Resistor_SMD.pretty", "R_0805_2012Metric", False),
    "R_LO": (paths.KICAD_FOOTPRINTS / "Resistor_SMD.pretty", "R_0805_2012Metric", False),
    "D_PWR": (paths.KICAD_FOOTPRINTS / "Diode_SMD.pretty", "D_SOD-123", False),
}
VALUE = {"U_MCU": "XIAO_nRF52840", "BT1": "BS-16-B4AK003", "SW_PWR": "MK-12C02-G025",
         "H_LID": "Hole_6.0", "U1": "SN74LVC595APWR", "U2": "SN74LVC595APWR",
         "C_U1": "0.1uF", "C_U2": "0.1uF", "R_HI": "1M", "R_LO": "1M", "D_PWR": "B5819W"}


def _mm(v):
    return pcbnew.ToMM(v)


def _cad(q, origin):
    return (_mm(q.x) - origin[0], origin[1] - _mm(q.y))


def _put(board, ctx, ref, at, deg, front):
    lib, name, _ = FP[ref]
    fp = ctx["load"](lib, name)
    fp.SetReference(ref)
    fp.SetValue(VALUE[ref])
    fp.SetPosition(ctx["to_kicad"](*at))
    fp.SetOrientationDegrees(deg)
    board.Add(fp)
    if not front:
        fp.Flip(fp.GetPosition(), False)        # Add の後で（前だと segfault）
    return fp


def _wire(fp, pads, net):
    """宣言（{パッド番号: ネット名}）どおりにパッドへネットを張る。**過不足は落とす。**"""
    have = {p.GetNumber() for p in fp.Pads() if p.GetNumber()}
    if have != set(pads):
        raise RuntimeError(f"{fp.GetReference()}: フットプリントのパッド {sorted(have)} と"
                           f"回路の宣言 {sorted(pads)} が違う（黙って飛ばさない）")
    for p in fp.Pads():
        n = pads.get(p.GetNumber(), "")
        if n:
            p.SetNet(net(n))


def _poly_on(board, ctx, poly, layer):
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(ctx["to_kicad"](x1, y1))
        s.SetEnd(ctx["to_kicad"](x2, y2))
        s.SetLayer(layer)
        s.SetWidth(pcbnew.FromMM(0.1))
        board.Add(s)


def rule_area(board, ctx, box, layers, name, fills=True):
    """配線・ビア（・ベタ）を禁止する領域（パッド・部品は許す）。box は CAD の (x0, y0, x1, y1)
    か多角形 [(x, y), ...]。"""
    poly = box if isinstance(box[0], (tuple, list)) else \
        [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
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


def xiao_underside(ifc):
    """XIAO の下で表の銅を禁止する範囲。[(x0, y0, x1, y1), ...]（CAD）。

    XIAO の裏には露出したパッドが 8 個ある（spec.XIAO_BOTTOM_PADS: SWD 系 4・VBAT/GND 2・
    NFC 2。公式 STEP と Seeed 公式のランド）。表の銅（ベタ・配線・ビア）をマスク越しに押し当てない。
    本体: XIAO の外形の中で、手前は基板の縁から、奥は露出パッドの奥の端 ＋ XIAO_BOTTOM_CLEAR まで。
    露出パッドが XIAO の外形の外へ出る所（NFC の 2 個はアンテナ側の端から Seeed のランドが
    0.08 出る）は、そのパッド ＋ XIAO_BOTTOM_CLEAR の矩形を足す。
    **奥の端は奥の列のパッド（D7 など）の内端より手前でなければならない**（越えると落とす）。
    """
    s = ifc.s
    b = ifc.xiao()
    x, y = s.XIAO_AT
    c = s.XIAO_BOTTOM_CLEAR
    pads = [(x + r[0] - c, y + r[1] - c, x + r[2] + c, y + r[3] + c)
            for _, r in s.XIAO_BOTTOM_PADS.values()]
    top = max(p[3] for p in pads)
    pad_inner = y + s.XIAO_W / 2 - s.XIAO_PAD_IN          # 奥の列のパッドの内端
    if top >= pad_inner:
        raise RuntimeError(f"XIAO の下の禁止域の奥 {top:.3f} が奥の列のパッドの内端 {pad_inner:.3f} を越える")
    # 手前は基板の縁まで伸ばす: 手前の列（D0〜D6）はパッド内ビアで裏へ抜けるので、表に線は
    # 要らない。**DSN からパッドを外したら Freerouting が表の線でパッドの列を横切った**
    # （2026-09-24・VBAT_SW が D2〜D6 を短絡）。禁止域なら DSN にも Freerouting にも見える
    out = [(b[0], ifc.pcb[1], b[2], top)]
    for p in pads:
        if p[0] < b[0] or p[2] > b[2] or p[3] > top:
            out.append(p)
    return out


def insert_keepout(ifc):
    """左のふたの熱圧入インサート（H3）が基板の上面に当たる円 ＋ INSERT_COPPER_CLEAR。((x, y), r)。

    インサートは下面から入れて面一で止まり、真鍮の縁（外径 case_spec.INSERT_OD）がネジの締め付けで
    基板の上面を押す。その下に表の銅（配線・ビア・ベタ）を置かない（監査 E 重要 3: CS の線と GND の
    ビアの縁が 0.02 掛かっていた。マスクが欠けると CS が GND に落ちて 595 が 2 個とも止まる）。
    """
    import case_spec
    h3 = [m for m in ifc.mounts() if ifc.in_corner(m)]
    if len(h3) != 1:
        raise RuntimeError(f"角の取付（H3）が {len(h3)} 個")
    return h3[0], case_spec.INSERT_OD / 2 + ifc.s.INSERT_COPPER_CLEAR


def circle_poly(c, r, n=24):
    """半径 r の円を**外に接する** n 角形で（円を必ず覆う）。"""
    R = r / math.cos(math.pi / n)
    return [(c[0] + R * math.cos(2 * math.pi * (i + 0.5) / n),
             c[1] + R * math.sin(2 * math.pi * (i + 0.5) / n)) for i in range(n)]


# 外形・逃げ穴の縁の、配線・ビアを入れない帯の幅。JLC の銅と外形 0.3（pcb_rules）に 0.02。
# 自分で引く行列（matrix_routes の EDGE_GAP 0.35）はこの外にいる
EDGE_BAND = 0.32


def place(board, ctx):
    project = load(HERE)
    s = project.spec
    ifc = interface.Interface(project)
    origin = pcbnew.ToMM(ctx["to_kicad"](0, 0).x), pcbnew.ToMM(ctx["to_kicad"](0, 0).y)
    net = ctx["net"]
    want = circuit.expected_pad_nets(project)

    # --- スタビの逃げ穴（Edge.Cuts）-------------------------------------------
    for poly in ifc.stab_reliefs():
        _poly_on(board, ctx, poly, pcbnew.Edge_Cuts)

    # --- 角の部品 -------------------------------------------------------------
    # XIAO: 原点はピンの並びの中心。USB を −x に向ける（USB は足で −y にあるので +90°）
    x, y = s.XIAO_AT
    u = _put(board, ctx, "U_MCU", (x + s.XIAO_PIN_SHIFT, y), 90, True)
    d0 = _cad(u.FindPadByNumber("D0").GetPosition(), origin)
    d6 = _cad(u.FindPadByNumber("D6").GetPosition(), origin)
    v5 = _cad(u.FindPadByNumber("5V").GetPosition(), origin)
    if not (d0[1] < y and v5[1] > y and d0[0] < d6[0]):
        raise RuntimeError(f"XIAO の向きが違う: D0 {d0} D6 {d6} 5V {v5}（D0〜D6 は手前・D0 が USB 側）")
    _put(board, ctx, "BT1", s.HOLDER_AT, 0, True)
    _put(board, ctx, "H_LID", s.LID_PILLAR_AT, 0, True)
    # 電源スイッチ（裏）。つまみ（足で +y）を +x へ。裏返すと x が鏡になるので裏返す前は −x へ
    sw = _put(board, ctx, "SW_PWR", s.PSW_AT, -90, False)
    term = [_cad(sw.FindPadByNumber(n).GetPosition(), origin)[0] for n in "123"]
    if not all(t < s.PSW_AT[0] for t in term):
        raise RuntimeError(f"電源スイッチの向きが違う: 端子の x {term}（つまみは +x・端子は内側）")

    # --- 裏の電子部品 -----------------------------------------------------------
    for ref, (px, py, deg) in s.PART_AT.items():
        fp = _put(board, ctx, ref, (px, py), deg, FP[ref][2])
        if ref in s.REF_TEXT_AT:
            dx, dy = s.REF_TEXT_AT[ref]
            fp.Reference().SetPosition(ctx["to_kicad"](px + dx, py + dy))

    # --- ネット（circuit.py の宣言どおり）--------------------------------------
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    for ref, _, _ in circuit.electronics():
        _wire(fps[ref], want[ref], net)
    # ベタへの繋ぎ方をサーマル（スポーク）にするパッド（spec.THERMAL_PADS の理由）
    for ref, nums in s.THERMAL_PADS.items():
        for num in nums:
            ps = [p for p in fps[ref].Pads() if p.GetNumber() == num]
            if len(ps) != 1 or ps[0].GetNetname() != "GND":
                raise RuntimeError(f"{ref}.{num}: サーマルにする GND のパッドが {len(ps)} 個")
            ps[0].SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_THERMAL)

    # --- ルール領域 -------------------------------------------------------------
    rule_area(board, ctx, ifc.antenna_keepout(), (pcbnew.F_Cu, pcbnew.B_Cu), "ANTENNA_KEEPOUT")
    for box in xiao_underside(ifc):
        rule_area(board, ctx, box, (pcbnew.F_Cu,), "XIAO_UNDERSIDE")
    c, r = insert_keepout(ifc)
    rule_area(board, ctx, circle_poly(c, r), (pcbnew.F_Cu,), "INSERT_KEEPOUT")
    # 外形とスタビの逃げ穴の縁に、配線・ビアを入れない帯（ベタは入れてよい。ベタは自分の
    # 外形の逃げで離れる）。**Freerouting は外形・逃げ穴をネットクラスの間隔 0.2 でしか避けない**
    # ので、JLC の銅と外形 0.3 を割った（1 回目: 0.237・0.280）。帯は EDGE_BAND 幅
    both = (pcbnew.F_Cu, pcbnew.B_Cu)
    x0, y0, x1, y1 = ifc.pcb
    w = EDGE_BAND
    for strip in ((x0, y0, x1, y0 + w), (x0, y1 - w, x1, y1), (x0, y0, x0 + w, y1),
                  (x1 - w, y0, x1, y1)):
        rule_area(board, ctx, strip, both, "EDGE_KEEPOUT", fills=False)
    for poly in ifc.stab_reliefs():
        rule_area(board, ctx, interface.poly_offset_axis(poly, w), both, "EDGE_KEEPOUT",
                  fills=False)

    # --- ネットクラス（**Recompute しないと割り当てが効かない**）---------------
    d = board.GetDesignSettings()
    ns = d.m_NetSettings
    cls = pcbnew.NETCLASS("POWER")
    cls.SetTrackWidth(pcbnew.FromMM(s.POWER_TRACK_W))
    cls.SetClearance(pcbnew.FromMM(TRACK_W))
    cls.SetViaDiameter(pcbnew.FromMM(VIA_D))
    cls.SetViaDrill(pcbnew.FromMM(VIA_DRILL))
    ns.SetNetclass("POWER", cls)
    for n in circuit.POWER_NETS:
        ns.SetNetclassPatternAssignment(n, "POWER")
    ns.RecomputeEffectiveNetclasses()
    return board
