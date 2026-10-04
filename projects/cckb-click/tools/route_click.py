"""cckb-click の基板を配線して、発注に使う板 projects/cckb-click/pcb/cckb-click_main.kicad_pcb を作る。**KiCad の Python。**

    tools/kb cckb-click pcb                                          # 未配線の板（置く・ネットを張る）
    "$KICAD_PYTHON" projects/cckb-click/tools/route_click.py         # ここ。配線 → ベタ → GND ビア
    "$KICAD_PYTHON" projects/cckb-click/tools/route_click.py --freeroute   # SPI・電源の枝を Freerouting で引き直す（形が変わる → 監査し直す）
    .venv/bin/python3 -m foundry.drc projects/cckb-click/pcb/cckb-click_main.kicad_pcb

順序（docs/knowledge/pcb.md。CCKB の projects/cckb/tools/route_pcb.py と同じ）:
  1. 行列を決まった形で引く（click_routes.plan。板の上のパッドから）
  2. GND の SMD パッドに同じ層のスタブ → ビア（ベタが偶然被っている接続に頼らない）
  3. 残り（SPI・595 どうし・電源の枝）は、**監査した板で Freerouting 2.3.0 が引いた形を置き直す**（pcb/freerouted.json）。
     Freerouting は同じ入力でも引くたびに形が変わるので、板のほかの所を直すたびに監査した配線が変わらないようにした（2026-10-04）。
     `--freeroute` を付けると Freerouting で引き直して freerouted.json を書き直す（行列は網ごと外して線を障害物として渡す）
  4. SES の取り込みは既存の配線を作り直す → 行列と GND のスタブが残っているかを数えて確かめる。ルール領域の層も戻す
  5. 両面の GND ベタ → リング（アンテナの禁止域の縁）→ フェンス → 格子 → 離島 → 塗り直し
  6. 保存と記録（route.json）

**ベタ・ビア・置けるかの判定は CCKB の道具をそのまま使う**（監査を 4 回通した物。projects/cckb/tools/route_pcb.py を読み込む。
CCKB の側は変えない）。ここが持つのは、この機種の網の名前と、DSN の絞り方だけ。
"""

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ROOT = PROJ.parents[1]
CCKB = ROOT / "projects" / "cckb"
for p in (str(ROOT), str(PROJ)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rp = _load("cckb_route_pcb", CCKB / "tools" / "route_pcb.py")       # Space・gnd_fanout・pour・ring・fence_and_grid・離島 ほか
board_geometry = sys.modules["board_geometry"]                      # rp が読み込んだ projects/cckb/tools/board_geometry.py

import click_layout                                     # noqa: E402
import click_routes                                     # noqa: E402
from foundry import boardhash, paths                    # noqa: E402
from foundry.pcb import sync_project_rules              # noqa: E402
from foundry.pcb_rules import TRACK_W, VIA_D, VIA_DRILL  # noqa: E402
from foundry.project import load                        # noqa: E402

SRC = PROJ / "pcb" / "unrouted" / "cckb-click_main.kicad_pcb"
OUT = PROJ / "pcb" / "cckb-click_main.kicad_pcb"
PREWIRED = re.compile(r"GND|SW\d+_D|ROW\d+|COL\d+|VBAT_SENSE|VBAT_IN")   # 自分で引き切った網（DSN から外す。線は protect）
FIXED = re.compile(r"(?!)")                             # 最後の 1 本だけ Freerouting に繋がせる網（いまは無い）
# Freerouting の「最適化」の段を回さない。行列の 628 本を障害物（protect）として渡すと、最適化の 1 回が 17 分かかり、
# 点数も配線も変わらなかった（2026-10-03 実測: 配線は 17 秒で未配線 0・最適化 2 回で 34 分）。配線の良し悪しは KiCad の DRC と検査が見る
OPTIMIZER_OFF = "--router.optimizer.enabled=false"
DRIVERS = ("U_MCU", "U1", "U2")
MM = pcbnew.FromMM


def _extra():
    """projects/cckb-click/pcb_extra.py（ルール領域の名前と層・ベタだけを禁止する領域）。"""
    return sys.modules.get("click_pcb_extra") or _load("click_pcb_extra", PROJ / "pcb_extra.py")


def rule_layers():
    return _extra().RULE_LAYERS


def matrix_ends(board):
    """行列の網ごとに、Freerouting に繋がせる 2 つのピン {網: (駆動側の参照名の集合, 相手のピン名)}。
    相手は、駆動側のパッドにいちばん近い行列の部品（列 = スイッチ・行 = ダイオード）の、その網の最初のパッド
    （同じ番号のパッドが 2 つある足跡は、DSN では 2 つ目が「番号@1」になる。1 つ目を使う）。"""
    pads = {}
    for fp in board.GetFootprints():
        seen = set()
        for p in fp.Pads():
            n = p.GetNetname()
            if FIXED.fullmatch(n or "") and (n, p.GetNumber()) not in seen:
                seen.add((n, p.GetNumber()))
                pads.setdefault(n, []).append((fp.GetReference(), p))
    out = {}
    for n, ps in pads.items():
        drv = [(r, p) for r, p in ps if r in DRIVERS]
        mx = [(r, p) for r, p in ps if re.fullmatch(r"SW\d+", r)]
        if len(drv) != 1 or not mx:
            raise SystemExit(f"{n}: 駆動側 {len(drv)} / 行列 {len(mx)}")
        q = drv[0][1].GetPosition()
        r, p = min(mx, key=lambda rp_: (rp_[1].GetPosition().x - q.x) ** 2 + (rp_[1].GetPosition().y - q.y) ** 2)
        out[n] = ({drv[0][0]}, f"{r}-{p.GetNumber()}")
    return out


def edit_dsn(dsn, ends, margin_um, power=None):
    t = dsn.read_text()
    # (a) 引き切った網（GND・SW*_D）を丸ごと外し、線は障害物（protect）にする
    names = sorted({n for n in re.findall(r"\(net ([^\s()]+)", t) if PREWIRED.fullmatch(n)})
    for n in names:
        e = re.escape(n)
        t = re.sub(rf"\s*\(plane {e} \(polygon [\s\S]*?\)\)", "", t)
        t = re.sub(rf"\s*\(net {e}\s*\n\s*\(pins [^)]*\)\s*\n\s*\)", "", t)
        t = re.sub(rf"(\(class \S+ [^)]*?)\b{e}\b", r"\1", t)
        t = re.sub(rf"\(net {e}\)\s*\(type route\)", "(type protect)", t)
    left = [n for n in re.findall(r"\(net ([^\s()]+)", t) if n in names]
    if left:
        raise SystemExit(f"DSN から外しきれない網: {sorted(set(left))}")
    # (b) 行列の網: ピンを 2 つ（駆動側・最寄りの行列のパッド）に絞り、線は protect
    n_pins = {}

    def narrow(m):
        net, pins = m.group(1), m.group(2).split()
        drv, anchor = ends[net]
        keep = [p for p in pins if p.rsplit("-", 1)[0] in drv] + [anchor]
        if anchor not in pins or len(keep) < 2:
            raise SystemExit(f"{net}: DSN のピン {pins[:6]}… に {anchor} / 駆動側 {drv} が無い")
        n_pins[net] = len(keep)
        return f"(net {net}\n      (pins {' '.join(keep)})"
    t = re.sub(r"\(net (COL\d+)\s*\n\s*\(pins ([^)]*)\)", narrow, t)
    if set(n_pins) != set(ends):
        raise SystemExit(f"DSN で絞れなかった行列の網: {set(ends) - set(n_pins)}")
    n_fix = [0]

    def protect(m):
        n_fix[0] += 1
        return "(type protect)"
    t = re.sub(r"\(net COL\d+\)\s*\(type route\)", protect, t)
    # (b1) 電源の決まった線の網: 決まった線でもう繋いだピン（to の端・C_BAT のランド）を外し、線は protect
    #      （残りのピンを Freerouting が frm の端へ繋ぐ。外さないと、線の途中に付く C_BAT を「未配線 1」と数えて止まらなかった）
    n_pw = {}
    for net, drops in (power or {}).items():
        def narrow_power(m, drops=drops):
            pins = m.group(2).split()
            if set(drops) - set(pins):
                raise SystemExit(f"{m.group(1)}: DSN のピン {pins} に {sorted(set(drops) - set(pins))} が無い")
            n_pw[m.group(1)] = len(pins) - len(drops)
            return f"(net {m.group(1)}\n      (pins {' '.join(q for q in pins if q not in drops)})"
        t = re.sub(rf"\(net ({re.escape(net)})\s*\n\s*\(pins ([^)]*)\)", narrow_power, t)
        t = re.sub(rf"\(net {re.escape(net)}\)\s*\(type route\)", "(type protect)", t)
    if set(n_pw) != set(power or {}):
        raise SystemExit(f"DSN で絞れなかった電源の網: {set(power or {}) - set(n_pw)}")
    # (b2) XIAO の D0〜D6 はパッドとパッド内ビアが同じ番号（DSN では "D2" がビア・"D2@1" がパッド）。2 つを別のピンとして
    # 渡すと Freerouting はパッド → ビアだけ引いて止まる（CCKB 2026-09-24）。パッド（@1）を網からも部品の形からも外す
    n_twin = [0]

    def drop_twin(m):
        pins = m.group(2).split()
        keep = [p for p in pins if not (p.startswith("U_MCU-") and p.endswith("@1") and p[:-2] in pins)]
        n_twin[0] += len(pins) - len(keep)
        return f"(net {m.group(1)}\n      (pins {' '.join(keep)})"
    t = re.sub(r"\(net (\S+)\s*\n\s*\(pins ([^)]*)\)", drop_twin, t)
    img = re.search(r"\(image XIAO_nRF52840_SMD[\s\S]*?\n    \)", t)
    body = img.group(0)
    twins = re.findall(r"\n\s*\(pin \S+ (D\d+)@1 [^)]*\)", body)
    t = t.replace(body, re.sub(r"\n\s*\(pin \S+ D\d+@1 [^)]*\)", "", body))
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
    dsn.write_text(t)
    return dict(stripped=names, protected_wires=n_fix[0], clearances=n[0], narrowed=n_pins, twins_dropped=n_twin[0], power_narrowed=n_pw)


def freeroute(board, work):
    if not rp.JAR.exists():
        raise SystemExit(f"Freerouting が無い: {rp.JAR}")
    rev = rp.freerouting_revision(rp.JAR)
    if rev != rp.FREEROUTING_REVISION:
        raise SystemExit(f"Freerouting の版が違う: {rp.JAR} の Build-Revision {rev}（v2.3.0 は {rp.FREEROUTING_REVISION}）")
    dsn, ses = work / "click.dsn", work / "click.ses"
    ends = matrix_ends(board)
    tried = []
    for margin in rp.DSN_CLEARANCE_MARGINS_UM:
        for f in (dsn, ses):
            if f.exists():
                f.unlink()
        if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
            raise SystemExit("DSN の書き出しに失敗")
        how = load(PROJ).spec.POWER_RUN
        spec = load(PROJ).spec
        v3 = spec.V3V3_RUN
        info = edit_dsn(dsn, ends, margin, {how["net"]: (f"{how['to'][0]}-{how['to'][1]}", "C_BAT-1"),
                                            v3["net"]: (f"{v3['to'][0]}-{v3['to'][1]}",)})
        log = work / f"freerouting_{margin}.log"
        with log.open("w") as fh:
            r = subprocess.run([rp._java(), "-jar", str(rp.JAR), "-de", str(dsn), "-do", str(ses),
                                "-mp", str(rp.PASSES), "--gui.enabled=false", OPTIMIZER_OFF],
                               stdout=fh, stderr=subprocess.STDOUT, timeout=3600)
        text = log.read_text()
        if r.returncode != 0 or not ses.exists():
            raise SystemExit(f"Freerouting が失敗（{r.returncode}）:\n{text[-3000:]}")
        m = re.findall(r"\((\d+) unrouted and", text)
        left = int(m[-1]) if m else None
        tried.append((margin, left))
        print(f"   Freerouting 余裕 {margin}µm: ログの未配線 {left}", flush=True)
        if left == 0:
            break
    else:
        raise SystemExit(f"Freerouting がどの余裕でも引ききれない: {tried}")
    before = {f.GetReference(): (f.GetPosition(), f.GetOrientationDegrees()) for f in board.GetFootprints()}
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("SES の取り込みに失敗")
    moved = 0
    for f in board.GetFootprints():               # SES の取り込みで部品が丸めの分動く。配線器に部品を動かさせない
        pos, deg = before[f.GetReference()]
        if f.GetPosition() != pos or f.GetOrientationDegrees() != deg:
            f.SetOrientationDegrees(deg)
            f.SetPosition(pos)
            moved += 1
    info.update(footprints_restored=moved, tried=tried, margin_um=margin)
    return info


FROZEN = PROJ / "pcb" / "freerouted.json"


def _key(net, layer, a, b):
    a, b = (round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))
    return (net, layer, min(a, b), max(a, b))


def lay_frozen(board):
    """監査した板で Freerouting が引いた線とビア（pcb/freerouted.json）を置く。(線の数, ビアの数, 記録)。"""
    rec = json.loads(FROZEN.read_text())
    for t in rec["tracks"]:
        if PREWIRED.fullmatch(t["net"]) or board.FindNet(t["net"]) is None:
            raise SystemExit(f"freerouted.json の網 {t['net']} は置けない（自分で引く網か、板に無い）")
        rp.lay_segments(board, [(t["net"], t["layer"], tuple(t["a"]), tuple(t["b"]))], width=t["w"])
    rp.lay_vias(board, [(v["net"], tuple(v["at"])) for v in rec["vias"]])
    return len(rec["tracks"]), len(rec["vias"]), rec


def write_frozen(board, planned, planned_vias):
    """Freerouting が引いた線とビア（自分で引いた網・決まった線を除く）を pcb/freerouted.json に書く。"""
    plan = {_key(n, l, a, b) for n, l, a, b in planned}
    pv = {(n, (round(p[0], 3), round(p[1], 3))) for n, p in planned_vias}
    tracks, vias = [], []
    for t in board.GetTracks():
        n = t.GetNetname()
        if PREWIRED.fullmatch(n or ""):
            continue
        if t.GetClass() == "PCB_VIA":
            p = rp.cad(t.GetPosition())
            if (n, (round(p[0], 3), round(p[1], 3))) not in pv:
                vias.append(dict(net=n, at=[round(p[0], 6), round(p[1], 6)]))
        else:
            a, b = rp.cad(t.GetStart()), rp.cad(t.GetEnd())
            if _key(n, t.GetLayerName(), a, b) not in plan:
                tracks.append(dict(net=n, layer=t.GetLayerName(), a=[round(a[0], 6), round(a[1], 6)], b=[round(b[0], 6), round(b[1], 6)],
                                   w=round(pcbnew.ToMM(t.GetWidth()), 4)))
    tracks.sort(key=lambda t: (t["net"], t["layer"], t["a"], t["b"]))
    vias.sort(key=lambda v: (v["net"], v["at"]))
    FROZEN.write_text(json.dumps(dict(note="route_click.py --freeroute が書いた。**形が変わったので監査し直す**", source_sha256=None,
                                      freerouting=rp.JAR.name, tracks=tracks, vias=vias), ensure_ascii=False, indent=1) + "\n")
    return len(tracks), len(vias)


def drop_one_layer_vias(board):
    """Freerouting が引いた網のビアのうち、片方の層にしか線・パッドが付いていない物を消す（消した数）。
    Freerouting は先にピンの脇へビアを打ち（Fanout）、使わなかったビアを表の線の途中に残す（KiCad の via_dangling）。
    線は同じ点で繋がったままなので、ビアだけ消す。自分で引いた網（PREWIRED）は触らない。"""
    gone = []
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    for v in [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]:
        net = v.GetNetname()
        if PREWIRED.fullmatch(net or ""):
            continue
        q = v.GetPosition()
        layers = {t.GetLayer() for t in tracks if t.GetNetname() == net and q in (t.GetStart(), t.GetEnd())}
        layers |= {lay for p in pads if p.GetNetname() == net and p.HitTest(q)
                   for lay in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(lay)}
        if len(layers) < 2:
            gone.append(v)
    for v in gone:
        board.Remove(v)
    return len(gone)


def drop_duplicate_tracks(board):
    """同じ網・同じ層・同じ両端の線が 2 本以上あれば 1 本にする（消した数）。決まった形で引いた GND の線は、SES の取り込みの後で
    「電源の決まった線」と「GND のスタブ」の両方として置き直されて、同じ所に 2 本重なった（2026-10-04）。"""
    seen, gone = set(), []
    for t in board.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        # 1 µm に丸めて比べる（SES の往復で端が 0.1 µm 単位でずれる）
        a, b = (round(t.GetStart().x, -3), round(t.GetStart().y, -3)), (round(t.GetEnd().x, -3), round(t.GetEnd().y, -3))
        key = (t.GetNetname(), t.GetLayer(), min(a, b), max(a, b))
        if key in seen:
            gone.append(t)
        seen.add(key)
    for t in gone:
        board.Remove(t)
    return len(gone)


def restore_rule_areas(board):
    """SES の往復でルール領域の層が消える。名前で層を戻す。知らない名前・足りない名前は落とす。"""
    want = rule_layers()
    seen = set()
    for z in board.Zones():
        if not z.GetIsRuleArea():
            continue
        name = z.GetZoneName()
        if name not in want:
            raise SystemExit(f"知らないルール領域 {name!r}")
        ls = pcbnew.LSET()
        for lay in want[name]:
            ls.addLayer(rp.LAYER[lay])
        z.SetLayerSet(ls)
        seen.add(name)
    if set(want) != seen:
        raise SystemExit(f"ルール領域が足りない: {set(want) - seen}")


def main(argv=()):
    rerun = "--freeroute" in argv or not FROZEN.exists()
    proj = load(PROJ)
    lay = click_layout.Layout(proj)
    work = PROJ / "pcb" / "route_work"
    work.mkdir(exist_ok=True)
    board = pcbnew.LoadBoard(str(SRC))
    geo = board_geometry.dump_board(board)
    segs, mvias, wide = click_routes.plan(proj, geo["pads"])
    n_mx = rp.lay_segments(board, segs)
    rp.lay_vias(board, mvias)
    pw_w = proj.spec.POWER_TRACK_W
    n_pw = rp.lay_segments(board, wide, width=pw_w)
    space = rp.Space(board)
    fan = rp.gnd_fanout(board, space)
    fan_tracks = [(t.GetNetname(), t.GetLayerName(), rp.cad(t.GetStart()), rp.cad(t.GetEnd()))
                  for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == "GND"]
    fan_vias = [rp.cad(t.GetPosition()) for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    print(f"   行列 {n_mx} 区間・ビア {len(mvias)} / 電源の決まった線 {n_pw} 区間 / GND ファンアウト {len(fan)} 個", flush=True)
    if rerun:
        info = freeroute(board, work)
        print(f"   Freerouting: 外した網 {len(info['stripped'])} 本 / protect の線 {info['protected_wires']}"
              f" / 採った余裕 {info['margin_um']}µm（試した {info['tried']}）", flush=True)
        frozen = None
    else:
        n_ft, n_fv, frozen = lay_frozen(board)
        info = dict(margin_um=None, tried=[])
        print(f"   監査した板の Freerouting の線を置き直した: 線 {n_ft}・ビア {n_fv}（{frozen['source_sha256'][:8]}… から）", flush=True)
    restore_rule_areas(board)
    miss = rp.tracks_present(board, segs)
    if miss:
        rp.lay_segments(board, miss)
    n_mv = rp.lay_vias(board, mvias)
    if rp.tracks_present(board, segs):
        raise SystemExit(f"行列の線が置き直せない: {rp.tracks_present(board, segs)[:5]}")
    rp.snap_rounded_twins(board, wide)
    miss_pw = rp.tracks_present(board, wide)
    if miss_pw:
        rp.lay_segments(board, miss_pw, width=pw_w)
    if rp.tracks_present(board, wide):
        raise SystemExit(f"電源の決まった線が置き直せない: {rp.tracks_present(board, wide)[:5]}")
    have_gnd = rp.tracks_present(board, fan_tracks)
    if have_gnd:
        rp.lay_segments(board, have_gnd, width=0.3)
    have_v = {rp.cad(t.GetPosition()) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"}
    for v in fan_vias:
        if v not in have_v:
            nv = pcbnew.PCB_VIA(board)
            nv.SetPosition(rp.kpt(*v))
            nv.SetWidth(MM(VIA_D))
            nv.SetDrill(MM(VIA_DRILL))
            nv.SetNet(board.FindNet("GND"))
            board.Add(nv)
    n_dup = drop_duplicate_tracks(board)
    n_thin = rp.widen_thin(board)
    n_dangling = drop_one_layer_vias(board)
    if rerun:
        print("   freerouted.json を書き直した: 線 %d・ビア %d" % write_frozen(board, segs + wide, mvias), flush=True)
    print(f"   片方の層にしか繋がっていない Freerouting のビアを消した: {n_dangling}", flush=True)
    print(f"   SES 後に置き直した: 行列 {len(miss)} / ビア {n_mv} / GND スタブ {len(have_gnd)} / 細い線 {n_thin} / 重なった線を消した {n_dup}", flush=True)

    from foundry.pcb import to_kicad
    _extra().no_fill_areas(board, lay, to_kicad)     # ベタだけを禁止する領域は、配線の後で足す（理由は pcb_extra.NO_FILL_LAYERS）
    rp.pour(board)
    rp.fill(board)
    space = rp.Space(board)
    n_ring = rp.ring(board, space, lay.antenna_keepout())
    n_fence, n_grid = rp.fence_and_grid(board, space)
    # 束の帯（表のベタを塗らない所）に落ちた格子・フェンスのビアは、表に繋がる銅が無い（KiCad の via_dangling）。
    # **離島の手当ての前に**消す（後で消すと、そのビアだけで繋がっていた島が浮く）
    band = lay.fanout_band()
    in_band = [v for v in board.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() == "GND"
               and rp.cad(v.GetPosition()) not in fan_vias            # パッドのスタブの先のビアは残す（表はスタブに繋がっている）
               and band[0] < rp.cad(v.GetPosition())[0] < band[2] and band[1] - 0.3 < rp.cad(v.GetPosition())[1] < band[3] + 0.3]
    for v in in_band:
        board.Remove(v)
    if in_band:
        rp.fill(board)
    print(f"   束の帯に落ちた縫いのビアを消した: {len(in_band)}", flush=True)
    space = rp.Space(board)
    n_is, left = rp.stitch_islands(board, space)
    n_dbl, single = rp.double_single_via_islands(board, space)
    removed = sum(a for _, a in left)
    for z in rp.gnd_zones(board):                 # 繋げなかった島は消す（浮いた銅は 2.4GHz でアンテナになりうる）
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    rp.fill(board)
    n_join = rp.join_gnd_components(board, rp.Space(board))
    n_orphan = rp.orphan_gnd_vias(board)
    if n_orphan:
        rp.fill(board)
    n_decl = rp.declared_gnd_vias(board, getattr(proj.spec, "GND_STITCH_AT", ()))
    if n_decl:
        rp.fill(board)
    if len(rp.gnd_components(board)) != 1:
        raise SystemExit(f"GND が {len(rp.gnd_components(board))} 個の成分に分かれたまま")
    print(f"   GND ビア: リング {n_ring} / フェンス {n_fence} / 格子 {n_grid} / 離島 {n_is} / 消した島 {len(left)} 個 {removed:.2f} mm²"
          f" / 1 本の島に足した {n_dbl} / 1 本のまま {[(round(a, 1), round(L, 1)) for _, a, L in single]}"
          f" / 浮いた組を本土へつないだビア {n_join} / 浮いた組のビアを消した {n_orphan} / 宣言したビア {n_decl}", flush=True)

    board.BuildConnectivity()
    unconnected = board.GetConnectivity().GetUnconnectedCount(False)
    board.Save(str(OUT))
    shutil.copy(SRC.with_suffix(".kicad_pro"), OUT.with_suffix(".kicad_pro"))
    sync_project_rules(OUT, getattr(proj.spec, "DRC_SEVERITY", None),
                       pth_hole_clearance=getattr(proj.spec, "DRC_PTH_HOLE_CLEARANCE", False),
                       tighten=getattr(proj.spec, "DRC_RULES", None))
    areas = {("F" if lay_ == pcbnew.F_Cu else "B"): round(sum(a for l2, a, _, _ in rp.islands(board) if l2 == lay_), 1)
             for lay_ in (pcbnew.F_Cu, pcbnew.B_Cu)}
    rec = dict(board=OUT.name, unrouted=SRC.name, unrouted_fingerprint=boardhash.fingerprint(SRC),
               unrouted_sha256=hashlib.sha256(SRC.read_bytes()).hexdigest(),
               freerouting=rp.JAR.name, passes=rp.PASSES, freerouting_options=[OPTIMIZER_OFF], margin_um=info["margin_um"], margins_tried=info["tried"],
               freerouted="rerun" if rerun else "replayed", freerouted_from=None if rerun else frozen["source_sha256"],
               freerouted_tracks=None if rerun else len(frozen["tracks"]), freerouted_vias=None if rerun else len(frozen["vias"]),
               matrix_segments=n_mx, matrix_vias=len(mvias), power_segments=n_pw, gnd_fanout=len(fan), ring=n_ring, fence=n_fence, grid=n_grid,
               one_layer_vias_removed=n_dangling, duplicate_tracks_removed=n_dup, band_vias_removed=len(in_band), island_vias=n_is, second_island_vias=n_dbl, declared_vias=n_decl,
               single_via_islands=[dict(layer="F.Cu" if l_ == pcbnew.F_Cu else "B.Cu", area_mm2=round(a, 2), length_mm=round(L, 2))
                                   for l_, a, L in single],
               islands_removed=len(left), islands_removed_mm2=round(removed, 2), joined_vias=n_join,
               orphan_vias_removed=n_orphan, gnd_area_mm2=areas, unconnected=unconnected)
    (PROJ / "pcb" / "route.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    shutil.rmtree(work)
    print(f"{'OK' if unconnected == 0 else 'NG'} {OUT.name}: 未配線 {unconnected} / GND の面積 {areas}")
    return 0 if unconnected == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
