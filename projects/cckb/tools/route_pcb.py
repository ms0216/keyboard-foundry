"""CCKB の基板を配線して、発注に使う板 projects/cckb/pcb/cckb_main.kicad_pcb を作る。**KiCad の Python。**

    tools/kb cckb pcb                                        # 未配線の板（置く・ネットを張る）
    "$KICAD_PYTHON" projects/cckb/tools/route_pcb.py         # ここ。配線 → ベタ → GND ビア
    .venv/bin/python3 -m foundry.drc projects/cckb/pcb/cckb_main.kicad_pcb

順序（docs/knowledge/pcb.md）:
  1. 行列を決まった形で引く（matrix_routes.plan。板の上のパッドから）
  2. GND の SMD パッドに同じ層のスタブ → ビア（ベタが偶然被っている接続に頼らない）
  3. 残りを Freerouting 2.3.0（行列の線は protect・行列のネットは駆動側と最寄りのパッドの 2 ピンに
     絞る。GND・SW*_D はネットごと外して線は protect）
  4. SES の取り込みは既存の配線を作り直す → **行列と GND のスタブが残っているかを数えて確かめる**
     （足りなければ置き直し、置き直せなければ落とす）。ルール領域の層も戻す（SES 往復で消える）
  5. 両面の GND ベタ → フェンス（長い配線の脇）→ リング（アンテナの禁止域の縁）→ 格子 →
     離島（面積で見る。つなぎ直し、残りは消して面積を記録）→ 塗り直し
  6. 保存と記録（route.json: 未配線の板の指紋・Freerouting・数）

**寸法は持たない**（spec.py・pcb_rules.py）。**配線を加工する判定を書かない**——線は置くか、
置いた線が残っているかを数えるだけ（HHKB の教訓）。
"""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ROOT = PROJ.parents[1]
for p in (str(ROOT), str(PROJ), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import board_geometry                                   # noqa: E402
import interface                                        # noqa: E402
import matrix_routes                                    # noqa: E402
from foundry import boardhash                           # noqa: E402
from foundry.pcb import ORIGIN, sync_project_rules      # noqa: E402
from foundry.pcb_rules import JLC, TRACK_W, VIA_D, VIA_DRILL   # noqa: E402
from foundry.project import load                        # noqa: E402

SRC = PROJ / "pcb" / "unrouted" / "cckb_main.kicad_pcb"
OUT = PROJ / "pcb" / "cckb_main.kicad_pcb"
JAR = Path(os.environ.get("FREEROUTING_JAR",
                          Path.home() / ".local/share/freerouting/freerouting-2.3.0.jar"))
JAVA_CANDIDATES = ("/opt/homebrew/opt/openjdk/bin/java", "/usr/local/opt/openjdk/bin/java")
PASSES = 100
# Freerouting は丸めで規則を下回る（HHKB: 20→30）。**同じ入力なら同じ結果**（HHKB で 3 回確かめた）
# だが、板を少し変えると未配線が 0 から 2 に揺れた（2026-09-24・名札を動かしただけ）。
# そこで余裕を決まった順に試し、Freerouting のログで未配線 0 の最初を採る（どれを採ったかは記録）
DSN_CLEARANCE_MARGINS_UM = (30, 35, 25, 40)
PREWIRED = re.compile(r"GND|SW\d+_D|ROW\d+")   # 自分で引き切ったネット（DSN から外す）
FIXED = re.compile(r"COL\d+")    # 自分で引いたが、595 までの最後の 1 本は Freerouting が繋ぐ

MM = pcbnew.FromMM
GND_CLEAR = 0.25                    # ベタとほかのネットの間
VIA_R = VIA_D / 2
# 縫いのビアと**同じネットの**パッドの間（銅の縁どうし）。パッドの中・縁に掛けない（はんだを
# 吸わない）ための逃げで、電気の間隔ではない。監査 C の提案「ビアの輪 ＋ 0.1 以上」
SAME_NET_PAD_CLEAR = 0.1


def kpt(x, y):
    return pcbnew.VECTOR2I_MM(ORIGIN[0] + x, ORIGIN[1] - y)


def cad(v):
    return (pcbnew.ToMM(v.x) - ORIGIN[0], ORIGIN[1] - pcbnew.ToMM(v.y))


LAYER = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


# ---------------------------------------------------------------------------
# 1. 行列
# ---------------------------------------------------------------------------

def matrix_segments(board):
    """行列（plan）と XIAO から行のバスまで（escape）。([線], [ビア])"""
    geo = board_geometry.dump_board(board)
    proj = load(PROJ)
    m = matrix_routes.plan(proj, geo["pads"])
    e, vias = matrix_routes.escape(proj, geo["pads"], others=m)
    return m + e, vias


def lay_vias(board, vias):
    have = {(v.GetPosition().x, v.GetPosition().y) for v in board.GetTracks()
            if v.GetClass() == "PCB_VIA"}
    n = 0
    for net, p in vias:
        q = kpt(*p)
        if (q.x, q.y) in have:
            continue
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(q)
        v.SetWidth(MM(VIA_D))
        v.SetDrill(MM(VIA_DRILL))
        v.SetNet(board.FindNet(net))
        board.Add(v)
        n += 1
    return n


def lay_segments(board, segs, width=TRACK_W):
    n = 0
    for net, layer, a, b in segs:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(kpt(*a))
        t.SetEnd(kpt(*b))
        t.SetWidth(MM(width))
        t.SetLayer(LAYER[layer])
        ni = board.FindNet(net)
        if ni is None:
            raise SystemExit(f"板にネット {net} が無い")
        t.SetNet(ni)
        board.Add(t)
        n += 1
    return n


def _nm(p):
    v = kpt(*p)
    return (v.x, v.y)


def _key_nm(net, layer, a, b):
    """比べるのは KiCad の整数座標（nm）。mm の小数を丸めて比べると丸めの向きで食い違う。"""
    return (net, layer) + tuple(sorted([a, b]))


def tracks_present(board, segs):
    """計画の線が板に**そのまま**あるか。無いものを返す。"""
    have = set()
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK":
            s, e = t.GetStart(), t.GetEnd()
            have.add(_key_nm(t.GetNetname(), t.GetLayerName(), (s.x, s.y), (e.x, e.y)))
    return [s for s in segs if _key_nm(s[0], s[1], _nm(s[2]), _nm(s[3])) not in have]


# ---------------------------------------------------------------------------
# 置けるかの判定（ビア・スタブ）。**板の実物の形**（pcbnew の SHAPE）で当てる
# ---------------------------------------------------------------------------

class Space:
    def __init__(self, board):
        self.board = board
        self.refresh()
        self.edges = [s for s in board.GetDrawings()
                      if s.GetLayer() == pcbnew.Edge_Cuts]
        # 外形（スタビの逃げ穴を穴として含む）。**縁の線に近いかだけでは足りない**——逃げ穴の
        # 真ん中（縁から 0.35 より遠い）に置いたビアが通っていた（2026-09-24 の 1 回目）
        self.outline = pcbnew.SHAPE_POLY_SET()
        if not board.GetBoardPolygonOutlines(self.outline, False):
            raise SystemExit("外形の多角形が作れない")
        self.rules = [z for z in board.Zones() if z.GetIsRuleArea()]

    def refresh(self):
        b = self.board
        self.items = []                        # (bbox, 層, ネット, 形の取り出し)
        for fp in b.GetFootprints():
            for p in fp.Pads():
                self.items.append((p.GetBoundingBox(), p))
        for t in b.GetTracks():
            self.items.append((t.GetBoundingBox(), t))

    def free(self, pos, net, layers=(pcbnew.F_Cu, pcbnew.B_Cu), r=VIA_R, drill=VIA_DRILL / 2,
             clear=0.25, stub_from=None, stub_layer=None):
        """pos（KiCad の点）にビア（半径 r）を置けるか。stub_from があれば、そこから
        stub_layer の上のスタブ（幅 0.3）も当てる。"""
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(pos)
        via.SetWidth(MM(2 * r))
        via.SetDrill(MM(2 * drill))
        shapes = [(lay, via.GetEffectiveShape(lay)) for lay in layers]
        if stub_from is not None:
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(stub_from)
            t.SetEnd(pos)
            t.SetWidth(MM(0.3))
            t.SetLayer(stub_layer)
            shapes.append((stub_layer, t.GetEffectiveShape(stub_layer)))
        if not self.outline.Contains(pos):
            return False
        # 絞り込みの窓は**スタブも含めて**（ビアの周りだけ見て、長いスタブが隣のパッドを
        # 横切った。2026-09-24 の 1 回目: R_LO の GND のスタブが同じ部品の VBAT_SENSE を跨いだ）
        reach = MM(r + 1.5)
        lo_x, hi_x, lo_y, hi_y = pos.x - reach, pos.x + reach, pos.y - reach, pos.y + reach
        if stub_from is not None:
            lo_x, hi_x = min(lo_x, stub_from.x - reach), max(hi_x, stub_from.x + reach)
            lo_y, hi_y = min(lo_y, stub_from.y - reach), max(hi_y, stub_from.y + reach)
        for bb, it in self.items:
            if bb.GetLeft() > hi_x or bb.GetRight() < lo_x or \
                    bb.GetTop() > hi_y or bb.GetBottom() < lo_y:
                continue
            same = it.GetNetname() == net and net != ""
            if isinstance(it, pcbnew.PCB_VIA):       # 穴どうし（JLC 0.45）は**ネットに関係なく**
                d = math.hypot(pos.x - it.GetPosition().x, pos.y - it.GetPosition().y)
                if d - MM(drill) - it.GetDrillValue() / 2 < MM(JLC["hole_to_hole"] + 0.05):
                    return False      # 1 回目: 同じ GND のビアを丸ごと飛ばし、穴間 0.38 が 27 件
            if isinstance(it, pcbnew.PAD):
                if it.GetDrillSize().x > 0:          # 穴どうし（JLC 0.45）
                    d = math.hypot(pos.x - it.GetPosition().x, pos.y - it.GetPosition().y)
                    if d - MM(drill) - it.GetDrillSize().x / 2 < MM(JLC["hole_to_hole"] + 0.05):
                        return False
                    if it.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                        if d - MM(r) - it.GetDrillSize().x / 2 < MM(0.3):
                            return False
                        continue
                if same:
                    # **同じネットのパッドもビアの障害物**（ビアの輪 ＋ SAME_NET_PAD_CLEAR）。
                    # 前は飛ばしていて、縫いのビアが C_U1（JLC がリフローで付ける 0805）と
                    # BT1 の GND パッドの**中**に落ちた（監査 C 重要 1・2026-09-24）。パッドの上の
                    # ビアははんだを吸う（JLC PCBA FAQ Part 2 Q17）。スタビ（自分のパッドから
                    # 出る線）は同じネットなので当ててよい——当てるのはビアの形だけ
                    for lay, sh in shapes[:len(layers)]:
                        if it.IsOnLayer(lay) and \
                                it.GetEffectiveShape(lay).Collide(sh, MM(SAME_NET_PAD_CLEAR)):
                            return False
                    continue
            elif same:
                continue
            for lay, sh in shapes:
                if not it.IsOnLayer(lay):
                    continue
                if it.GetEffectiveShape(lay).Collide(sh, MM(clear)):
                    return False
        # 外形・逃げ穴（Edge.Cuts）から
        for e in self.edges:
            if e.GetEffectiveShape().Collide(shapes[0][1], MM(JLC["edge_clearance"] + 0.05)):
                return False
        for z in self.rules:
            for lay, sh in shapes:
                if z.IsOnLayer(lay) and (z.GetDoNotAllowVias() or z.GetDoNotAllowTracks()) and \
                        z.Outline().Collide(sh, MM(0.1)):
                    return False
        return True

    def add_via(self, pos, net, stub_from=None, stub_layer=None):
        b = self.board
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pos)
        v.SetWidth(MM(VIA_D))
        v.SetDrill(MM(VIA_DRILL))
        v.SetNet(b.FindNet(net))
        b.Add(v)
        self.items.append((v.GetBoundingBox(), v))
        if stub_from is not None:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(stub_from)
            t.SetEnd(pos)
            t.SetWidth(MM(0.3))
            t.SetLayer(stub_layer)
            t.SetNet(b.FindNet(net))
            b.Add(t)
            self.items.append((t.GetBoundingBox(), t))
        return v


# ---------------------------------------------------------------------------
# 2. GND のファンアウト
# ---------------------------------------------------------------------------

def gnd_fanout(board, space):
    """GND の SMD パッドごとに、同じ層のスタブ（0.3）→ ビア。部品の中心から外向きを優先。"""
    placed, failed = [], []
    for fp in board.GetFootprints():
        c = fp.GetPosition()
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            q = p.GetPosition()
            half = max(p.GetBoundingBox().GetWidth(), p.GetBoundingBox().GetHeight()) / 2
            out = math.atan2(q.y - c.y, q.x - c.x) if (q.x, q.y) != (c.x, c.y) else 0.0
            dirs = sorted((math.radians(a) for a in range(0, 360, 15)),
                          key=lambda a: abs(math.remainder(a - out, 2 * math.pi)))
            done = False
            for dist in (0.9, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0):
                for a in dirs:
                    pos = pcbnew.VECTOR2I(int(q.x + math.cos(a) * (half + MM(dist))),
                                          int(q.y + math.sin(a) * (half + MM(dist))))
                    if space.free(pos, "GND", stub_from=q, stub_layer=layer):
                        space.add_via(pos, "GND", stub_from=q, stub_layer=layer)
                        placed.append(f"{fp.GetReference()}.{p.GetNumber()}")
                        done = True
                        break
                if done:
                    break
            if not done:
                failed.append(f"{fp.GetReference()}.{p.GetNumber()}")
    if failed:
        raise SystemExit(f"GND のファンアウトが置けないパッド: {failed}")
    return placed


# ---------------------------------------------------------------------------
# 3. Freerouting
# ---------------------------------------------------------------------------

def _java():
    tried = []
    for cand in (shutil.which("java"),) + JAVA_CANDIDATES:
        if not cand or not Path(cand).exists():
            continue
        tried.append(cand)
        r = subprocess.run([cand, "-version"], capture_output=True, timeout=60)
        if r.returncode == 0:
            return cand
    raise SystemExit(f"動く java が無い（brew install openjdk）。試したもの: {tried}")


def matrix_ends(board):
    """行列のネットごとに、Freerouting に繋がせる 2 つのピン {ネット: (駆動側の参照名, 相手のピン名)}。

    行列は自分で引き切ってある（matrix_routes）。残るのは XIAO・595 から行列までの 1 本だけ
    なので、DSN ではネットのピンを「駆動側（XIAO か 595）」と「そのネットで駆動側に最も近い
    行列のパッド」の 2 つに絞る。行列の線は障害物（protect）として渡す。
    （fix で渡すと Freerouting 2.3.0 は線を接続と見ず、未配線 67・違反 230 から動かなかった。
    2026-09-24 実測）
    """
    out = {}
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if FIXED.fullmatch(n or ""):
                pads.setdefault(n, []).append((fp.GetReference(), p))
    for n, ps in pads.items():
        drv = [(r, p) for r, p in ps if r in ("U_MCU", "U1", "U2")]
        mx = [(r, p) for r, p in ps if re.fullmatch(r"(SW|D)\d+", r)]
        if len(drv) < 1 or not mx:
            raise SystemExit(f"{n}: 駆動側 {len(drv)} / 行列 {len(mx)}")
        q = drv[0][1].GetPosition()
        r, p = min(mx, key=lambda rp: math.hypot(rp[1].GetPosition().x - q.x,
                                                  rp[1].GetPosition().y - q.y))
        out[n] = ({d[0] for d in drv}, f"{r}-{p.GetNumber()}")
    return out


def edit_dsn(dsn, ends, margin_um):
    t = dsn.read_text()
    # (a) 引き切ったネット（GND・SW*_D）を丸ごと外し、線は障害物（protect）にする
    names = sorted({n for n in re.findall(r"\(net (\S+)", t) if PREWIRED.fullmatch(n)})
    for n in names:
        e = re.escape(n)
        t = re.sub(rf"\s*\(plane {e} \(polygon [\s\S]*?\)\)", "", t)
        t = re.sub(rf"\s*\(net {e}\s*\n\s*\(pins [^)]*\)\s*\n\s*\)", "", t)
        t = re.sub(rf"(\(class \S+ [^)]*?)\b{e}\b", r"\1", t)
        t = re.sub(rf"\(net {e}\)\s*\(type route\)", "(type protect)", t)
    left = [n for n in re.findall(r"\(net (\S+)", t) if PREWIRED.fullmatch(n)]
    if left:
        raise SystemExit(f"DSN から外しきれないネット: {sorted(set(left))}")
    # (b) 行列のネット: ピンを 2 つ（駆動側・最寄りの行列のパッド）に絞り、線は protect
    n_pins = {}

    def narrow(m):
        net, pins = m.group(1), m.group(2).split()
        drv, anchor = ends[net]
        keep = [p for p in pins if p.rsplit("-", 1)[0] in drv] + [anchor]
        if anchor not in pins or len(keep) < 2:
            raise SystemExit(f"{net}: DSN のピン {pins} に {anchor} / 駆動側 {drv} が無い")
        n_pins[net] = len(keep)
        return f"(net {net}\n      (pins {' '.join(keep)})"
    t = re.sub(r"\(net (COL\d+)\s*\n\s*\(pins ([^)]*)\)", narrow, t)
    if set(n_pins) != set(ends):
        raise SystemExit(f"DSN で絞れなかった行列のネット: {set(ends) - set(n_pins)}")
    n_fix = [0]

    def protect(m):
        n_fix[0] += 1
        return "(type protect)"
    t = re.sub(r"\(net COL\d+\)\s*\(type route\)", protect, t)
    # (b2) XIAO の D0〜D6 はパッドとパッド内ビアが同じ番号（DSN では "D2" がビア・"D2@1" が
    # パッド）。**2 つを別のピンとして渡すと Freerouting はパッド → ビアの 1.2mm だけ引いて
    # 止まった**（1 回目: 行 5 本とも XIAO から出なかった）。パッドとビアは銅が重なって
    # 1 つ（KiCad の連結でも 1 つ）なので、DSN からはパッド（@1）を外し、裏へ抜けるビアから引かせる
    n_twin = [0]

    def drop_twin(m):
        pins = m.group(2).split()
        keep = [p for p in pins if not (p.startswith("U_MCU-") and p.endswith("@1")
                                        and p[:-2] in pins)]
        n_twin[0] += len(pins) - len(keep)
        return f"(net {m.group(1)}\n      (pins {' '.join(keep)})"
    t = re.sub(r"\(net (\S+)\s*\n\s*\(pins ([^)]*)\)", drop_twin, t)
    # ネットから外すだけでは、パッドは「ネットの無い障害物」としてビアに被さって残り、
    # ビアから 1 本も出なかった（2 回目）。**XIAO の部品の形（image）からも外す**
    img = re.search(r"\(image XIAO_nRF52840_SMD[\s\S]*?\n    \)", t)
    body = img.group(0)
    twins = re.findall(r"\n\s*\(pin \S+ (D\d+)@1 [^)]*\)", body)
    body2 = re.sub(r"\n\s*\(pin \S+ D\d+@1 [^)]*\)", "", body)
    t = t.replace(body, body2)
    if sorted(twins) != [f"D{i}" for i in range(7)]:
        raise SystemExit(f"XIAO の image から外したパッド {twins}（D0〜D6 の 7 つのはず）")
    # (c) クリアランスを少し増やす（KiCad の規則は変えない）
    n = [0]

    def bump(m):
        n[0] += 1
        return f"(clearance {int(m.group(1)) + margin_um})"
    t = re.sub(r"\(clearance (\d+)\)(?!\s*\(type)", bump, t)
    if not n[0]:
        raise SystemExit("DSN にクリアランスが無い（書式が変わった？）")
    # (d) (autoroute_settings) は入れない。**あるだけで Freerouting 2.3.0 が
    # ネットを 1 本も見なくなった**（CCKB 2026-09-24: "0 unrouted items"・"no SMD pins"。
    # HHKB の子基板でも同じ。ブロックを消すと同じ DSN で配線が始まった）
    dsn.write_text(t)
    return dict(stripped=names, protected_wires=n_fix[0], clearances=n[0], narrowed=n_pins,
                twins_dropped=n_twin[0])


def freeroute(board, work):
    if not JAR.exists():
        raise SystemExit(f"Freerouting が無い: {JAR}")
    dsn, ses = work / "cckb.dsn", work / "cckb.ses"
    ends = matrix_ends(board)
    tried = []
    for margin in DSN_CLEARANCE_MARGINS_UM:
        for f in (dsn, ses):
            if f.exists():
                f.unlink()
        if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
            raise SystemExit("DSN の書き出しに失敗")
        info = edit_dsn(dsn, ends, margin)
        log = work / f"freerouting_{margin}.log"
        with log.open("w") as fh:
            r = subprocess.run([_java(), "-jar", str(JAR), "-de", str(dsn), "-do", str(ses),
                                "-mp", str(PASSES), "--gui.enabled=false"],
                               stdout=fh, stderr=subprocess.STDOUT, timeout=3600)
        text = log.read_text()
        if r.returncode != 0 or not ses.exists():
            raise SystemExit(f"Freerouting が失敗（{r.returncode}）:\n{text[-3000:]}")
        m = re.findall(r"\((\d+) unrouted and", text)
        left = int(m[-1]) if m else None
        tried.append((margin, left))
        print(f"   Freerouting 余裕 {margin}µm: ログの未配線 {left}")
        if left == 0:
            break
    else:
        raise SystemExit(f"Freerouting がどの余裕でも引ききれない: {tried}")
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("SES の取り込みに失敗")
    info["tried"] = tried
    info["margin_um"] = margin
    return info


def restore_rule_areas(board):
    """SES の往復でルール領域の層が消える（HHKB 実測）。名前で層を戻す。"""
    want = {"ANTENNA_KEEPOUT": (pcbnew.F_Cu, pcbnew.B_Cu), "XIAO_UNDERSIDE": (pcbnew.F_Cu,),
            "EDGE_KEEPOUT": (pcbnew.F_Cu, pcbnew.B_Cu), "INSERT_KEEPOUT": (pcbnew.F_Cu,)}
    seen = set()
    for z in board.Zones():
        if not z.GetIsRuleArea():
            continue
        name = z.GetZoneName()
        if name not in want:
            raise SystemExit(f"知らないルール領域 {name!r}")
        ls = pcbnew.LSET()
        for lay in want[name]:
            ls.addLayer(lay)
        z.SetLayerSet(ls)
        seen.add(name)
    if seen != set(want):
        raise SystemExit(f"ルール領域が足りない: {set(want) - seen}")


def widen_thin(board):
    n = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < MM(TRACK_W):
            t.SetWidth(MM(TRACK_W))
            n += 1
    return n


# ---------------------------------------------------------------------------
# 5. GND ベタとビア
# ---------------------------------------------------------------------------

def pour(board):
    gnd = board.FindNet("GND")
    bb = board.GetBoardEdgesBoundingBox()
    zones = []
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetNet(gnd)
        z.SetLayer(layer)
        z.SetZoneName(f"GND_{'F' if layer == pcbnew.F_Cu else 'B'}")
        z.SetLocalClearance(MM(GND_CLEAR))
        z.SetMinThickness(MM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        # サーマルにするパッド（spec.THERMAL_PADS）のスポーク。JLC の最小の線 0.1 より十分太く、
        # 0805 のパッドの幅 1.0 の半分以下
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.4))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        pts = pcbnew.VECTOR_VECTOR2I()
        for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                     (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
            pts.append(pcbnew.VECTOR2I(x, y))
        z.AddPolygon(pts)
        board.Add(z)
        zones.append(z)
    return zones


def fill(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()


def gnd_zones(board):
    return [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND"]


def islands(board):
    """GND ベタの島ごとに (層, 面積 mm², 繋がっているか, 内部の点)。

    **繋がっているか**は KiCad の連結（塗ったベタ・パッド・線・ビア）で見る: 島の中に
    GND のパッドかビアか線の端が 1 つでもあり、それが本土（最大の島）と同じ連結成分なら本土。
    ここでは簡単に、**島の中に GND のビアかパッドがあるか**で判定し、無ければ浮き島とする。
    """
    anchors = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND":
                anchors.append((p.GetPosition(), p))
    for t in board.GetTracks():
        if t.GetNetname() == "GND" and t.GetClass() == "PCB_VIA":
            anchors.append((t.GetPosition(), t))
    out = []
    for z in gnd_zones(board):
        lay = z.GetLayer()
        polys = z.GetFilledPolysList(lay)
        for i in range(polys.OutlineCount()):
            ol = polys.Outline(i)
            area = abs(ol.Area()) / 1e12
            for h in range(polys.HoleCount(i)):
                area -= abs(polys.Hole(i, h).Area()) / 1e12
            hit = any(it.IsOnLayer(lay) and polys.Contains(pos) and ol.PointInside(pos)
                      for pos, it in anchors)
            out.append((lay, area, hit, i))
    return out


def fence_and_grid(board, space, pitch=6.0, fence_pitch=5.0):
    """長い配線の脇（フェンス）→ 格子。どちらも置ける所だけ。数を返す。"""
    n_fence = 0
    for t in list(board.GetTracks()):
        if t.GetClass() != "PCB_TRACK" or t.GetNetname() == "GND" or \
                re.fullmatch(r"(ROW|COL)\d+|SW\d+_D", t.GetNetname()):
            continue                       # 行列（走査の遅い信号）は格子に任せる
        a, b = t.GetStart(), t.GetEnd()
        L = math.hypot(b.x - a.x, b.y - a.y)
        if L < MM(10):
            continue
        ux, uy = (b.x - a.x) / L, (b.y - a.y) / L
        off = MM(pcbnew.ToMM(t.GetWidth()) / 2 + GND_CLEAR + VIA_R + 0.05)
        k = MM(fence_pitch / 2)
        while k < L:
            for sgn in (1, -1):
                pos = pcbnew.VECTOR2I(int(a.x + ux * k - sgn * uy * off),
                                      int(a.y + uy * k + sgn * ux * off))
                if space.free(pos, "GND"):
                    space.add_via(pos, "GND")
                    n_fence += 1
            k += MM(fence_pitch)
    bb = board.GetBoardEdgesBoundingBox()
    n_grid = 0
    y = bb.GetTop() + MM(pitch / 2)
    while y < bb.GetBottom():
        x = bb.GetLeft() + MM(pitch / 2)
        while x < bb.GetRight():
            pos = pcbnew.VECTOR2I(int(x), int(y))
            near = False
            for dx in (0, 1, -1):
                for dy in (0, 1, -1):
                    p2 = pcbnew.VECTOR2I(int(x + dx * MM(1.0)), int(y + dy * MM(1.0)))
                    if space.free(p2, "GND"):
                        space.add_via(p2, "GND")
                        n_grid += 1
                        near = True
                        break
                if near:
                    break
            x += MM(pitch)
        y += MM(pitch)
    return n_fence, n_grid


def ring(board, space, box, pitch=1.2):
    """アンテナの禁止域の縁（4 辺）に GND ビア。置けた数を辺ごとに返す。"""
    x0, y0, x1, y1 = box
    g = VIA_R + 0.15                    # 禁止域の縁からビアの縁まで 0.15
    sides = {"奥": [(x, y1 + g) for x in _steps(x0, x1, pitch)],
             "手前": [(x, y0 - g) for x in _steps(x0, x1, pitch)],
             "左": [(x0 - g, y) for y in _steps(y0, y1, pitch)],
             "右": [(x1 + g, y) for y in _steps(y0, y1, pitch)]}
    got = {}
    for side, pts in sides.items():
        n = 0
        for x, y in pts:
            pos = kpt(x, y)
            if space.free(pos, "GND"):
                space.add_via(pos, "GND")
                n += 1
        got[side] = (n, len(pts))
    return got


def _steps(a, b, pitch):
    n = max(1, int((b - a) / pitch))
    return [a + (b - a) * i / n for i in range(n + 1)]


def stitch_islands(board, space, rounds=4):
    """浮き島に、反対面のベタと重なる点でビアを打つ。繋げない島の面積を返す。"""
    placed = 0
    for _ in range(rounds):
        fill(board)
        floating = [(lay, area, i) for lay, area, hit, i in islands(board) if not hit]
        if not floating:
            return placed, []
        progress = False
        for lay, area, i in floating:
            z = next(z for z in gnd_zones(board) if z.GetLayer() == lay)
            polys = z.GetFilledPolysList(lay)
            ol = polys.Outline(i)
            bb = ol.BBox()
            step = MM(0.5)
            done = False
            y = bb.GetTop() + step // 2
            while y < bb.GetBottom() and not done:
                x = bb.GetLeft() + step // 2
                while x < bb.GetRight():
                    pos = pcbnew.VECTOR2I(int(x), int(y))
                    if ol.PointInside(pos) and space.free(pos, "GND"):
                        space.add_via(pos, "GND")
                        placed += 1
                        done = progress = True
                        break
                    x += step
                y += step
        if not progress:
            break
    fill(board)
    return placed, [(lay, a) for lay, a, hit, _ in islands(board) if not hit]


def island_vias(board):
    """GND ベタの島ごとに [(層, 面積 mm², 島の外形, [ビアの位置])]。"""
    vias = [t.GetPosition() for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    out = []
    for z in gnd_zones(board):
        lay = z.GetLayer()
        polys = z.GetFilledPolysList(lay)
        for i in range(polys.OutlineCount()):
            ol = polys.Outline(i)
            area = abs(ol.Area()) / 1e12
            inside = [v for v in vias if ol.PointInside(v) and not any(
                polys.Hole(i, h).PointInside(v) for h in range(polys.HoleCount(i)))]
            out.append((lay, area, ol, inside))
    return out


def double_single_via_islands(board, space):
    """ビア 1 本だけで繋がった島に、そのビアから**いちばん遠い**置ける点でもう 1 本打つ。

    1 本だけの島は、その 1 本を根元にした棒になり、長いと 2.4GHz で共振しうる（FR4 の λ/4 は
    約 17mm）。監査 D 軽微 4（B.Cu の 19mm の島がビア 1 本だった）。置けた数と、置けずに
    残った島（層・面積・長さ）を返す。
    """
    fill(board)
    placed, left = 0, []
    for lay, area, ol, inside in island_vias(board):
        if len(inside) != 1:
            continue
        v0 = inside[0]
        bb = ol.BBox()
        step = MM(0.5)
        cands = []
        y = bb.GetTop() + step // 2
        while y < bb.GetBottom():
            x = bb.GetLeft() + step // 2
            while x < bb.GetRight():
                pos = pcbnew.VECTOR2I(int(x), int(y))
                if ol.PointInside(pos):
                    cands.append((math.hypot(pos.x - v0.x, pos.y - v0.y), pos))
                x += step
            y += step
        cands.sort(key=lambda dp: -dp[0])
        done = False
        for d, pos in cands:
            if d < MM(2.0):                     # 近すぎる 2 本目は棒を短くしない
                break
            if space.free(pos, "GND"):
                space.add_via(pos, "GND")
                placed += 1
                done = True
                break
        if not done:
            left.append((lay, area, pcbnew.ToMM(max(bb.GetWidth(), bb.GetHeight()))))
    fill(board)
    return placed, left


def main():
    work = PROJ / "pcb" / "route_work"
    work.mkdir(exist_ok=True)
    board = pcbnew.LoadBoard(str(SRC))
    segs, mvias = matrix_segments(board)
    n_mx = lay_segments(board, segs)
    lay_vias(board, mvias)
    space = Space(board)
    fan = gnd_fanout(board, space)
    fan_tracks = [(t.GetNetname(), t.GetLayerName(), cad(t.GetStart()), cad(t.GetEnd()))
                  for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"
                  and t.GetNetname() == "GND"]
    fan_vias = [cad(t.GetPosition()) for t in board.GetTracks()
                if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    print(f"   行列 {n_mx} 区間 / GND ファンアウト {len(fan)} 個")
    info = freeroute(board, work)
    print(f"   Freerouting: 外したネット {len(info['stripped'])} 本（GND・SW*_D・ROW*）/ protect の線"
          f" {info['protected_wires']} / 採った余裕 {info['margin_um']}µm（試した {info['tried']}）")
    restore_rule_areas(board)
    # SES の取り込みで消えたものを置き直す（位置は決定的）
    miss = tracks_present(board, segs)
    if miss:
        lay_segments(board, miss)
    n_mv = lay_vias(board, mvias)
    miss2 = tracks_present(board, segs)
    if miss2:
        raise SystemExit(f"行列の線が置き直せない: {miss2[:5]}")
    have_gnd = tracks_present(board, fan_tracks)
    if have_gnd:
        lay_segments(board, have_gnd, width=0.3)
    have_v = {cad(t.GetPosition()) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"}
    for v in fan_vias:
        if v not in have_v:
            nv = pcbnew.PCB_VIA(board)
            nv.SetPosition(kpt(*v))
            nv.SetWidth(MM(VIA_D))
            nv.SetDrill(MM(VIA_DRILL))
            nv.SetNet(board.FindNet("GND"))
            board.Add(nv)
    n_thin = widen_thin(board)
    print(f"   SES 後に置き直した: 行列 {len(miss)} / ビア {n_mv} / GND スタブ {len(have_gnd)} / 細い線 {n_thin}")

    pour(board)
    fill(board)
    space = Space(board)
    ifc = interface.Interface(load(PROJ))
    n_ring = ring(board, space, ifc.antenna_keepout())
    n_fence, n_grid = fence_and_grid(board, space)
    n_is, left = stitch_islands(board, space)
    n_dbl, single = double_single_via_islands(board, space)
    # 繋げなかった島は消す（浮いた銅は 2.4GHz でアンテナになりうる）。面積は記録する
    removed = sum(a for _, a in left)
    for z in gnd_zones(board):
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    fill(board)
    print(f"   GND ビア: リング {n_ring} / フェンス {n_fence} / 格子 {n_grid} / 離島 {n_is}"
          f" / 消した島 {len(left)} 個 {removed:.2f} mm² / 1 本の島に足した {n_dbl}"
          f" / 1 本のまま {[(round(a, 1), round(L, 1)) for _, a, L in single]}")

    board.BuildConnectivity()
    unconnected = board.GetConnectivity().GetUnconnectedCount(False)
    board.Save(str(OUT))
    pro_src = SRC.with_suffix(".kicad_pro")
    shutil.copy(pro_src, OUT.with_suffix(".kicad_pro"))
    sync_project_rules(OUT, getattr(load(PROJ).spec, "DRC_SEVERITY", None))
    areas = {("F" if lay == pcbnew.F_Cu else "B"): round(sum(
        a for l2, a, _, _ in islands(board) if l2 == lay), 1) for lay in (pcbnew.F_Cu, pcbnew.B_Cu)}
    rec = dict(board=OUT.name, unrouted=SRC.name,
               unrouted_fingerprint=boardhash.fingerprint(SRC),
               # 指紋（boardhash）は配置・結線・外形だけで、**パッドの形とルール領域を見ない**。
               # 配線した元のファイルそのもの（バイト列）も残す（2026-09-24: XIAO のパッドを縮め、
               # 禁止域を足しても指紋は変わらなかった）
               unrouted_sha256=hashlib.sha256(SRC.read_bytes()).hexdigest(),
               freerouting=JAR.name, passes=PASSES, margin_um=info["margin_um"],
               margins_tried=info["tried"],
               matrix_segments=n_mx, gnd_fanout=len(fan), ring=n_ring, fence=n_fence,
               grid=n_grid, island_vias=n_is, second_island_vias=n_dbl,
               single_via_islands=[dict(layer="F.Cu" if lay == pcbnew.F_Cu else "B.Cu",
                                        area_mm2=round(a, 2), length_mm=round(L, 2))
                                   for lay, a, L in single],
               islands_removed=len(left),
               islands_removed_mm2=round(removed, 2), gnd_area_mm2=areas,
               unconnected=unconnected)
    (PROJ / "pcb" / "route.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    shutil.rmtree(work)
    print(f"{'OK' if unconnected == 0 else 'NG'} {OUT.name}: 未配線 {unconnected} / GND の面積 {areas}")
    return 0 if unconnected == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
