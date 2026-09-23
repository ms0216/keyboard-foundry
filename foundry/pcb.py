"""キーマトリクスの基板（未配線）を生成する。**KiCad 同梱の Python で動かす。**

    "$KICAD_PYTHON" -m foundry.pcb <機種>        # tools/kb <機種> pcb でも同じ

出すもの（projects/<機種>/pcb/unrouted/<機種>_<部品>.kicad_pcb）:
  外形（プレート外形 − PCB_INSET）・キーごとのホットスワップソケット／ダイオード
  （裏面）／スタビ・行列のネット・取付穴・JLCPCB の規則とネットクラス・
  裏面シルクのキー名と部品名

出さないもの（機種ごとに違う）: MCU・電源・コネクタ・GND ベタ・配線。
MCU などは projects/<機種>/pcb_extra.py の `place(board, ctx)` で足す。
配線と GND ビアの作法は docs/knowledge/pcb.md（HHKB の finalize_pcb / gnd_fanout が参照実装）。

**このファイルは寸法を持たない。**寸法は spec.py と mech.py、配列は layout、
行列は matrix が唯一の出どころ（HHKB でネジ位置を二重に持って食い違わせた）。
"""

import importlib.util
import json
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from foundry import paths, pinmap                                  # noqa: E402
from foundry.layout import centered                                # noqa: E402
from foundry.mech import stab_flipped, switch_of                   # noqa: E402
from foundry.pcb_rules import (JLC, NPTH_EDGE_MIN, TRACK_W,        # noqa: E402
                               VIA_D, VIA_DRILL)
from foundry.project import load                                   # noqa: E402

# 基板の中心を置く KiCad 上の座標（mm）。0,0 だと座標が負になり GUI で扱いにくい
ORIGIN = (150.0, 100.0)
KEYSWITCH_LIB = paths.LIB / "keyswitch.pretty"
MOUNT_FP = ("MountingHole", "MountingHole_2.2mm_M2")    # M2 のバカ穴
DIODE_FP = ("Diode_SMD", "D_SOD-123")


def to_kicad(x, y):
    """CAD 座標（原点中心・Y 上向き・mm）→ KiCad（Y 下向き）。変換はここだけ。"""
    return pcbnew.VECTOR2I_MM(ORIGIN[0] + x, ORIGIN[1] - y)


def _load(lib_dir, name):
    fp = pcbnew.FootprintLoad(str(lib_dir), name)
    if fp is None:                    # 握り潰さない
        raise RuntimeError(f"フットプリントを読めない: {lib_dir} / {name}")
    return fp


def _outline(board, w, h, r):
    """角丸矩形を Edge.Cuts に引く（プレートと同じ角丸）。"""
    hw, hh = w / 2, h / 2
    for (x1, y1), (x2, y2) in (((-hw + r, -hh), (hw - r, -hh)), ((hw, -hh + r), (hw, hh - r)),
                               ((hw - r, hh), (-hw + r, hh)), ((-hw, hh - r), (-hw, -hh + r))):
        seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(to_kicad(x1, y1))
        seg.SetEnd(to_kicad(x2, y2))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)
    corners = [(-hw + r, -hh + r), (hw - r, -hh + r), (hw - r, hh - r), (-hw + r, hh - r)]
    for i, (cx, cy) in enumerate(corners):
        a0 = [180, 270, 0, 90][i]
        pts = [(cx + r * math.cos(math.radians(t)), cy + r * math.sin(math.radians(t)))
               for t in (a0, a0 + 45, a0 + 90)]
        arc = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        arc.SetArcGeometry(*(to_kicad(*p) for p in pts))
        arc.SetLayer(pcbnew.Edge_Cuts)
        arc.SetWidth(pcbnew.FromMM(0.1))
        board.Add(arc)


def _apply_rules(board):
    d = board.GetDesignSettings()
    mm = pcbnew.FromMM
    d.m_TrackMinWidth = mm(JLC["track_min"])
    d.m_MinClearance = mm(JLC["clearance_min"])
    d.m_ViasMinSize = mm(JLC["via_dia_min"])
    d.m_ViasMinDrill = mm(JLC["via_drill_min"])
    d.m_MinThroughDrill = mm(JLC["hole_min"])
    d.m_HoleToHoleMin = mm(JLC["hole_to_hole"])
    d.m_CopperEdgeClearance = mm(JLC["edge_clearance"])
    d.m_SilkClearance = mm(JLC["silk_width"])
    d.m_ViasMinAnnularWidth = mm(JLC["annular_ring"])
    # 自動配線器はネットクラスしか見ない。最小値とは別に実際の寸法を明示する
    nc = d.m_NetSettings.GetDefaultNetclass()
    nc.SetTrackWidth(mm(TRACK_W))
    nc.SetClearance(mm(TRACK_W))
    nc.SetViaDiameter(mm(VIA_D))
    nc.SetViaDrill(mm(VIA_DRILL))


def sync_project_rules(pcb_path, severities=None):
    """`.kicad_pro` の規則を JLC に揃える。**kicad-cli の DRC はここを読む。**

    HHKB で JLC の値を直しても DRC が古い規則で判定し続けた（#50）。
    規則以外（利用者が KiCad で設定した重大度など）は触らない。

    severities: 機種が spec.DRC_SEVERITY で**理由を書いて**変える重大度（例: 違反 → 警告）。
    **消す（ignore）ことはさせない**——警告に下げたものも drc.py が種類ごとに数えて出す。
    """
    pro = Path(str(pcb_path)[:-len(".kicad_pcb")] + ".kicad_pro")
    doc = json.loads(pro.read_text())
    rules = doc.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules.update({
        "min_track_width": JLC["track_min"],
        "min_clearance": JLC["clearance_min"],
        "min_via_diameter": JLC["via_dia_min"],
        "min_through_hole_diameter": JLC["hole_min"],
        "min_hole_to_hole": JLC["hole_to_hole"],
        "min_copper_edge_clearance": JLC["edge_clearance"],
        "min_silk_clearance": JLC["silk_width"],
        "min_via_annular_width": JLC["annular_ring"],
    })
    for kind, sev in (severities or {}).items():
        if sev not in ("error", "warning"):
            raise ValueError(f"{kind}: 重大度 {sev!r} は error / warning だけ（ignore で隠さない）")
        doc["board"]["design_settings"].setdefault("rule_severities", {})[kind] = sev
    pro.write_text(json.dumps(doc, indent=2) + "\n")


def npth_too_close_to_edge(board, w, h):
    """穴（NPTH）の縁から外形（矩形）までが NPTH_EDGE_MIN 未満のもの。

    DRC は銅しか見ず、配置の検査は部品の中心しか見なかったので、HHKB では
    スペースのスタビの大穴が基板前縁まで 0.381mm のまま発注直前まで残った（#53）。
    """
    bad = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                continue
            q = pad.GetPosition()
            x, y = pcbnew.ToMM(q.x) - ORIGIN[0], pcbnew.ToMM(q.y) - ORIGIN[1]
            gap = min(w / 2 - abs(x), h / 2 - abs(y)) - pcbnew.ToMM(pad.GetDrillSize().x) / 2
            if gap < NPTH_EDGE_MIN:
                bad.append(f"{fp.GetReference()} の穴 φ{pcbnew.ToMM(pad.GetDrillSize().x):.3f}"
                           f" が外形まで {gap:.3f}mm")
    return bad


def _extra(project):
    """projects/<機種>/pcb_extra.py があれば読む（MCU などを置く）。"""
    f = project.root / "pcb_extra.py"
    if not f.exists():
        return None
    s = importlib.util.spec_from_file_location(f"pcb_extra_{project.root.name}", f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def build(project, piece):
    spec = project.spec
    keys, rc = project.matrix(piece)          # キーマップ順（行列とファームが同じ並び）
    positions, (kw, kh) = centered(keys)
    pcb_w = kw + 2 * (spec.PLATE_MARGIN_X - spec.PCB_INSET_X)
    pcb_h = kh + 2 * (spec.PLATE_MARGIN_Y - spec.PCB_INSET_Y)

    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(2)              # 2 層で足りた（HHKB。4 層の根拠は実測で消えた）
    _apply_rules(board)
    _outline(board, pcb_w, pcb_h, spec.CORNER_R)

    nets = {}

    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])
        return nets[name]

    kind = switch_of(spec)
    n_stab = 0
    for i, ((kx, ky), k, (r, c)) in enumerate(zip(positions, keys, rc), start=1):
        sw = _load(KEYSWITCH_LIB, kind.footprint(k.w_u))
        sw.SetPosition(to_kicad(kx, ky))
        sw.SetReference(f"SW{i}")
        # Value は JLC の部品照合に使われる。キー名を入れると BOM から静かに漏れる（HHKB）
        sw.SetValue(kind.value)
        board.Add(sw)
        s = kind.stab_offset_for(k.w_u)
        if s is not None and s in kind.stab_fp:
            st = _load(KEYSWITCH_LIB, kind.stab_fp[s])
            st.SetPosition(to_kicad(kx, ky))
            if stab_flipped(k, keys):
                st.SetOrientationDegrees(180)
            st.SetReference(f"ST{i}")
            board.Add(st)
            n_stab += 1
        # 組み立てる人が見るのは裏面。通し番号だけでは 60 個を取り違える
        t = pcbnew.PCB_TEXT(board)
        t.SetText(k.label)
        t.SetPosition(to_kicad(kx, ky + 8.2))
        t.SetLayer(pcbnew.B_SilkS)
        t.SetMirrored(True)
        t.SetTextSize(pcbnew.VECTOR2I_MM(1.1, 1.1))
        t.SetTextThickness(pcbnew.FromMM(0.18))
        board.Add(t)
        # col2row: 列 → スイッチ → ダイオード（A→K）→ 行
        d = _load(paths.KICAD_FOOTPRINTS / f"{DIODE_FP[0]}.pretty", DIODE_FP[1])
        # 機種がキーごとに置き場所を変えられる（spec.DIODE_OVERRIDE。値は
        # Switch.diode_offset と同じ KiCad の向き・キー中心から (dx, dy, 角度)）。
        # CCKB ではスタビの逃げ穴がいつもの場所に重なる 4 キーだけ（O7）
        dx, dy, ang = getattr(spec, "DIODE_OVERRIDE", {}).get(piece, {}).get(
            i, (kind.diode_offset[0], kind.diode_offset[1], kind.diode_angle))
        d.SetPosition(pcbnew.VECTOR2I_MM(ORIGIN[0] + kx + dx, ORIGIN[1] - ky + dy))
        d.SetOrientationDegrees(ang)
        d.SetReference(f"D{i}")
        d.SetValue("BAT46W")
        board.Add(d)
        d.Flip(d.GetPosition(), False)        # **Add の後で。**前だと segfault する
        # パッドは pinmap から引く。引けなければ落ちる（握り潰すとネットの無い
        # パッドが DRC 0 のまま残る。HHKB で 74LVC595 が丸ごと消えていた）
        sw.FindPadByNumber(pinmap.resolve("keyswitch", "1")).SetNet(net(f"COL{c}"))
        sw.FindPadByNumber(pinmap.resolve("keyswitch", "2")).SetNet(net(f"SW{i}_D"))
        d.FindPadByNumber(pinmap.resolve("diode", "A")).SetNet(net(f"SW{i}_D"))
        d.FindPadByNumber(pinmap.resolve("diode", "K")).SetNet(net(f"ROW{r}"))

    for i, (mx, my) in enumerate(spec.MOUNTS[piece]):
        h = _load(paths.KICAD_FOOTPRINTS / f"{MOUNT_FP[0]}.pretty", MOUNT_FP[1])
        h.SetPosition(to_kicad(mx, my))
        h.SetReference(f"H{i}")
        board.Add(h)

    extra = _extra(project)
    if extra is not None:
        extra.place(board, dict(piece=piece, net=net, to_kicad=to_kicad, load=_load,
                                keys=keys, positions=positions, size=(pcb_w, pcb_h)))

    # 左右・機種の識別。届いた 2 枚が見分けられないと組み立ても修理も誤る。
    # **他社の商標を刷らない**（HHKB は "SSKB" にした）
    label = pcbnew.PCB_TEXT(board)
    label.SetText(f"{spec.NAME} {piece.upper()}")
    label.SetPosition(pcbnew.VECTOR2I_MM(ORIGIN[0], ORIGIN[1] + pcb_h / 2 - 3.0))
    label.SetLayer(pcbnew.B_SilkS)
    label.SetMirrored(True)
    label.SetTextSize(pcbnew.VECTOR2I_MM(2.5, 2.5))
    label.SetTextThickness(pcbnew.FromMM(0.3))
    board.Add(label)

    # シルクを JLC の最小線幅まで太らせる。**全部品を置いてから**（HHKB では
    # ダイオードより前にあり、61 個だけ 0.12 のまま残った。子基板の生成器には
    # 処理自体が無かった）
    silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    for fp in board.GetFootprints():
        for it in fp.GraphicalItems():
            if it.GetLayer() not in silk:
                continue
            if isinstance(it, pcbnew.PCB_TEXT):       # 文字は線幅ではなく太さ（CCKB の XIAO の "USB"）
                it.SetTextThickness(max(it.GetTextThickness(), pcbnew.FromMM(JLC["silk_width"])))
            elif it.GetWidth() < pcbnew.FromMM(JLC["silk_width"]):
                it.SetWidth(pcbnew.FromMM(JLC["silk_width"]))
        for fld in (fp.Reference(), fp.Value()):
            if fld.GetLayer() in silk:
                fld.SetTextThickness(max(fld.GetTextThickness(), pcbnew.FromMM(JLC["silk_width"])))

    bad = npth_too_close_to_edge(board, pcb_w, pcb_h)
    if bad:                               # 黙って出さない。外形公差 ±0.2 で橋が折れる
        raise RuntimeError(f"{piece}: 穴が外形に近すぎる（要 {NPTH_EDGE_MIN}mm）:\n  "
                           + "\n  ".join(bad))

    out = project.root / "pcb" / "unrouted"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{project.root.name}_{piece}.kicad_pcb"
    board.Save(str(path))
    sync_project_rules(path, getattr(spec, "DRC_SEVERITY", None))
    return path, (pcb_w, pcb_h), len(keys), n_stab, len(nets)


def main(argv):
    p = load(argv[0])
    for piece in p.spec.PIECES:
        path, (w, h), n_sw, n_stab, n_net = build(p, piece)
        print(f"{piece:6s} 基板 {w:7.2f} x {h:6.2f}mm  スイッチ {n_sw} / ダイオード {n_sw}"
              f" / スタビ {n_stab} / 取付穴 {len(p.spec.MOUNTS[piece])} / ネット {n_net}")
        print(f"       {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
