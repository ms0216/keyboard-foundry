"""cckb-click の試し刷り v2（刷る物だけ）。docs/coupon-test.md 8 章。**2026-10-04 に利用者が刷った。結果は本番に入れた**
（下穴 φ1.6・つまみは (ii)・切り欠きの形。蓋は 3 つとも使えなかった）。ここは、刷った物と同じ形を出し続ける（A と B）。

    .venv/bin/python3 projects/cckb-click/click_coupon_v2.py        # STL と絵を build/cckb-click/ に
    .venv/bin/python3 projects/cckb-click/tools/slice_v2.py         # スライスして G-code を検査 → coupon_v2_plate_n04.gcode.3mf

2026-10-04 に利用者が角とねじの試し刷り（v1）を刷った結果: ねじが空回りする・蓋が留まらない・つまみが奥すぎる。v2 はその 3 つを 1 枚で試した:

  A ねじ    本番の枠から切り出した壁（奥の壁・左の壁 = 幅の広いキーの脇の薄い壁）に、下穴 φ1.5 / 1.6 / 1.7（外面の溝の数 1・2・3）
  B つまみ  電源スイッチの位置 2 つを並べた壁の切れ端: (i) 前の位置（本番から 0.75 内）・(ii) 本番の位置。切り欠きは本番の形
  （C 蓋    留め方 3 通りの差し込み式の蓋。**3 つとも使えなかったので、形はここから消した**（2026-10-04: 蓋はねじで留める形に変えた。
            枠の口も変わったので、同じ物はもう出せない。刷った結果は docs/coupon-test.md 8 章・決定記録 2026-10-04-coupon-v2）

**寸法は持たない**（spec.COUPON_V2_*）。座標は本番と同じ（CAD・基板の上面 = 0）。
"""

from __future__ import annotations

import copy
import math
import sys
import types
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build123d import Box, Compound, Cylinder, Pos, Rot, Sphere, export_stl  # noqa: E402

import click_case as C  # noqa: E402
import click_parts as P  # noqa: E402
from foundry.layout import UNIT  # noqa: E402

LAY, S = C.LAY, C.S
EPS = C.EPS
OUT = C.OUT
TOP = S.FRAME_UNDER + S.FRAME_T
_box, _union = C._box, C._union
FENCE = 1.8                  # 当て板の縁の当て（幅）。高さ 2.0（v1 の角の試し刷りと同じ）


def vol(a, b):
    c = a & b
    try:
        return 0.0 if c is None else float(c.volume)
    except (AttributeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# A ねじ
# ---------------------------------------------------------------------------

def thread_engagement(d):
    """下穴 d に M2 を切ったときの掛かり（半径）と、山の高さに対する割合。"""
    major, minor = S.M2_THREAD
    e = min(major - d, major - minor) / 2
    return e, e / ((major - minor) / 2)


def flesh(piece, x, y, d, zs=(0.3, 1.4, 2.5), step=10):
    """下穴（径 d）の縁から外へ、立体の中にいる間の距離のいちばん短い物（全方位）。(肉, 角度)。"""
    loc = piece & (Pos(x, y, 2.0) * Box(10.0, 10.0, 8.0))
    best = (9.0, 0)
    for z in zs:
        for a in range(0, 360, step):
            r = d / 2 + 0.01
            while r < 4.0 and loc.is_inside((x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a)), z)):
                r += 0.02
            best = min(best, (round(r - d / 2, 2), a))
    return best


def _repilot(part, c, d):
    """本番の下穴（SCREW_PILOT_D）を埋めて、径 d で開け直す（深さは本番と同じ）。"""
    old, depth = LAY.pilot()
    x, y = c
    part = part + Pos(x, y, 0.0) * Cylinder(old / 2 + 0.03, depth + 0.03, align=C.CEN_MIN)
    return part - Pos(x, y, -1.0) * Cylinder(d / 2, depth + 1.0, align=C.CEN_MIN)


def _marks(n, at, along, face, sign):
    """外面の縦の溝 n 本。at = ねじの中心の、壁に沿う座標・along = "x" / "y"・face = 外面の座標・sign = 外へ向かう向き。"""
    w, depth, pitch, first = S.COUPON_V2_MARK
    out = []
    for j in range(n):
        u = at + first + pitch * j
        lo, hi = sorted((face - sign * depth, face + sign * 1.0))
        r = (u - w / 2, lo, u + w / 2, hi) if along == "x" else (lo, u - w / 2, hi, u + w / 2)
        out.append(_box(r, -1.0, TOP + 1.0))
    return out


@lru_cache(maxsize=None)
def screw_v2():
    """{名前: 立体}。frame_back = 奥の壁の切れ端（ねじ 3 本 = 下穴 3 通り・内の肉 0.7 の側）・frame_side = 左の壁の切れ端を 3 つ継いだ物
    （幅の広いキーの脇 = 斜めの肉 0.49 の側）・base_* = 当て板（厚さ PCB_T・穴 SCREW_HOLE_D）。holes = {名前: [(中心, 径)]}。"""
    full = C.frame_full()
    boxes = C.screw_coupon_boxes()
    pilots = S.COUPON_V2_PILOTS
    f, p = LAY.frame, LAY.pcb
    out, holes = {}, {}
    box, screws, _ = boxes["back"]
    part = full & _box(box, -1.0, TOP + 1.0)
    for i, (c, d) in enumerate(zip(screws, pilots)):
        part = _repilot(part, c, d) - _union(_marks(i + 1, c[0], "x", f[3], 1))
    out["frame_back"], holes["back"] = part.clean(), list(zip(screws, pilots))
    out["base_back"] = _plate((max(box[0], p[0]), max(box[1], p[1]), min(box[2], p[2]), min(box[3], p[3])), screws)
    box, (c,), _ = boxes["side"]
    raw = full & _box(box, -1.0, TOP + 1.0)
    pieces, centres = [], []
    for i, d in enumerate(pilots):
        dy = (i - 1) * UNIT
        piece = _repilot(raw, c, d) - _union(_marks(i + 1, c[1], "y", f[0], -1))
        pieces.append(Pos(0, dy, 0) * piece)
        centres.append((c[0], c[1] + dy))
    part = _union(pieces).clean()
    out["frame_side"], holes["side"] = part, list(zip(centres, pilots))
    out["base_side"] = _plate((max(box[0], p[0]), box[1] - UNIT, min(box[2], p[2]), box[3] + UNIT), centres)
    for name in ("frame_back", "frame_side"):
        if len(out[name].solids()) != 1:
            raise RuntimeError(f"ねじの試し刷り v2 {name} が {len(out[name].solids())} 個の塊")
    out["holes"] = holes
    return out


def _plate(r, screws=()):
    """基板の代わりの当て板（厚さ PCB_T）。ねじ穴は基板と同じ径。"""
    plate = _box(r, -S.PCB_T, 0.0)
    if screws:
        plate = plate - _union([Pos(x, y, -S.PCB_T - 1.0) * Cylinder(S.SCREW_HOLE_D / 2, S.PCB_T + 2.0, align=C.CEN_MIN) for x, y in screws])
    return plate


# ---------------------------------------------------------------------------
# B つまみ
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def shifted(dx=0.0):
    """電源スイッチを本番の位置から dx だけ外（+x）へ動かしたときの配置（click_layout の関数がそのまま使える）。"""
    if not dx:
        return LAY
    s2 = types.SimpleNamespace(**{k: getattr(S, k) for k in dir(S) if not k.startswith("__")})
    s2.PSW_AT = (S.PSW_AT[0] + dx, S.PSW_AT[1])
    lay = copy.copy(LAY)
    lay.s = s2
    return lay


def knob_box():
    x0, half = S.COUPON_V2_KNOB_BOX
    y = S.PSW_AT[1]
    return (x0, y - half, LAY.frame[2], y + half)


@lru_cache(maxsize=None)
def knob_stub(dx=0.0, dots=0, leg=True, mark=False):
    """右の壁の切れ端（つまみの前後 ± COUPON_V2_KNOB_BOX[1]）を**式から**作る: 壁（0〜上面）・屋根（枠の下面〜上面）・スイッチの上の厚い屋根、
    から、スイッチの空間と切り欠き（本番と同じ click_case.corner_cuts）を引く。dx = 0 は本番の位置（tests が本番の枠の立体と突き合わせる）。
    leg = 左の端に足す壁（当て板に載せるため。本番には無い）。dots = 上面の点の数。mark = 入の印（本番にはある。刷った試し刷りには無い）。"""
    lay = shifted(dx)
    box = knob_box()
    a2, f2 = LAY.key_area[2], LAY.frame[2]
    ceil = C.psw_ceiling(lay)
    body = [_box((a2, box[1], f2, box[3]), 0.0, TOP), _box((box[0], box[1], f2, box[3]), S.FRAME_UNDER, TOP),
            _box(C.psw_roof_rect(lay), ceil, S.FRAME_UNDER + EPS)]
    if leg:
        body.append(_box((box[0], box[1], box[0] + S.COUPON_CORNER_WALL, box[3]), 0.0, S.FRAME_UNDER + EPS))
    cc = C.corner_cuts(lay)
    cuts = [cc["psw"], cc["psw_notch"]] + ([cc["on_mark"]] if mark else [])
    d, depth, pitch = S.COUPON_V2_DOT
    cuts += [Pos(box[0] + 3.0, S.PSW_AT[1] + (k - (dots - 1) / 2) * pitch, TOP - depth) * Cylinder(d / 2, depth + 1.0, align=C.CEN_MIN)
             for k in range(dots)]
    part = (_union(body) - _union(cuts)).clean()
    if len(part.solids()) != 1:
        raise RuntimeError(f"つまみの切れ端が {len(part.solids())} 個の塊")
    return part


KNOB_VARIANTS = ((-S.COUPON_V2_PSW_SHIFT, 1), (0.0, 2))     # (本番の位置から外へ寄せる量, 点の数)。(i) 前の位置・(ii) 本番の位置


def knob_pitch():
    return 2 * S.COUPON_V2_KNOB_BOX[1]


def _knob_block(lay):
    """電源スイッチの本体の代わり（溝つき・つまみの出る窓）。v1 の角の試し刷りと同じ作り。"""
    z = lay.z()
    fit = S.COUPON_FIT
    pb, ch, ks = lay.psw_body(), C.knob_channel(lay), lay.psw_knob_sweep()
    return _box(pb, -EPS, z["psw_top"]) - _box(ch, 0.0, z["psw_top"] + 1.0) \
        - _box((ch[2] - EPS, ks[1] - fit, pb[2] + 1.0, ks[3] + fit), 0.0, z["psw_top"] + 1.0)


@lru_cache(maxsize=None)
def knob_v2():
    """{名前: 立体}。frame = 切れ端 2 つを y に並べて継いだ物（手前 = (i) 前の位置・奥 = (ii) 0.75 外 = 本番の位置）・
    base = 当て板（基板の縁は本番と同じ）＋ 本体の代わり 2 つ ＋ 左と奥の当て・knob_1 / knob_2 = つまみの代わり（入の位置）。"""
    box, pitch, fit = knob_box(), knob_pitch(), S.COUPON_FIT
    frame = _union([Pos(0, i * pitch, 0) * knob_stub(dx, dots) for i, (dx, dots) in enumerate(KNOB_VARIANTS)]).clean()
    if len(frame.solids()) != 1:
        raise RuntimeError("つまみの切れ端 2 つが 1 つの塊にならない")
    y1 = box[3] + pitch * (len(KNOB_VARIANTS) - 1)
    p2 = LAY.pcb[2]
    base = [_plate((box[0] - fit - FENCE, box[1], p2, y1 + fit + FENCE)),
            _box((box[0] - fit - FENCE, box[1], box[0] - fit, y1 + fit + FENCE), -EPS, 2.0),
            _box((box[0] - fit - FENCE, y1 + fit, p2, y1 + fit + FENCE), -EPS, 2.0)]
    out = {"frame": frame}
    for i, (dx, _) in enumerate(KNOB_VARIANTS):
        lay = shifted(dx)
        base.append(Pos(0, i * pitch, 0) * _knob_block(lay))
        out[f"knob_{i + 1}"] = Pos(0, i * pitch, 0) * C.knob_standin(1, lay)
    out["base"] = _union(base).clean()
    return out


def finger_reach(dx=0.0, r=None, desk=True):
    """指先の硬い球が、切り欠きへどこまで入るか（click_case.finger_reach を、位置 dx の切れ端・当て板・本体の代わりに当てる）。"""
    lay = shifted(dx)
    box = knob_box()
    things = Compound([knob_stub(dx, 0, False), _box((box[0], box[1], LAY.pcb[2], box[3]), -S.PCB_T, 0.0),
                       _box(lay.psw_body(), 0.0, lay.z()["psw_top"])])
    return C.finger_reach(things, lay, r, desk)


# ---------------------------------------------------------------------------
# 1 枚に並べる
# ---------------------------------------------------------------------------

# [(記号, 名前, 刷る向きの立体)]。記号は絵（coupon_v2_howto.png）と docs/coupon-test.md 8 章の表と同じ
def pieces():
    sc, kn = screw_v2(), knob_v2()
    turn = lambda v: Rot(0, 0, 90) * v                                    # noqa: E731（長い辺を X に）
    out = [
        ("A1", "ねじ・奥の壁（下穴 3 通り）", P.flip_to_bed(sc["frame_back"])),
        ("A2", "A1 の当て板", P.to_bed(sc["base_back"])),
        ("A3", "ねじ・左の壁（下穴 3 通り）", P.flip_to_bed(turn(sc["frame_side"]))),
        ("A4", "A3 の当て板", P.to_bed(turn(sc["base_side"]))),
        ("B1", "つまみ・壁の切れ端（位置 2 つ）", P.flip_to_bed(turn(kn["frame"]))),
        ("B2", "B1 の当て板", P.to_bed(turn(kn["base"]))),
        ("B3", "つまみの代わり（(i) 前の位置）", P.to_bed(turn(kn["knob_1"]))),
        ("B4", "つまみの代わり（0.75 外）", P.to_bed(turn(kn["knob_2"]))),
    ]
    return out


def plate_layout(gap=4.0, width=150.0):
    """[(記号, 名前, 置いた立体)]。左から並べ、幅を超えたら次の行。"""
    out, x, y, row = [], 0.0, 0.0, 0.0
    for tag, name, part in pieces():
        bb = part.bounding_box()
        if x > 0 and x + bb.size.X > width:
            x, y, row = 0.0, y + row + gap, 0.0
        out.append((tag, name, Pos(x - bb.min.X, y - bb.min.Y, -bb.min.Z) * part))
        x += bb.size.X + gap
        row = max(row, bb.size.Y)
    return out


def plate():
    return Compound([p for _, _, p in plate_layout()])


def placed_holes():
    """1 枚に並べた板の上での、下穴の中心 {記号: [((x, y), 径)]}（スライスした G-code と突き合わせるため）。
    切れ端と一緒に小さな印を同じ手順で回して置き、印の行き先を読む（変換を式で写さない）。"""
    sc = screw_v2()
    at = {tag: part.bounding_box() for tag, _, part in plate_layout()}
    out = {}
    for tag, name, turn in (("A1", "back", False), ("A3", "side", True)):
        marks = [Pos(x, y, 1.0) * Sphere(0.05) for (x, y), _ in sc["holes"][name]]
        group = Compound([sc[f"frame_{name}"]] + marks)
        group = P.flip_to_bed(Rot(0, 0, 90) * group if turn else group)
        cs = [m.bounding_box().center() for m in list(group.solids())[1:]]
        out[tag] = [((c.X + at[tag].min.X, c.Y + at[tag].min.Y), d) for c, (_, d) in zip(cs, sc["holes"][name])]
    return out


def export(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    part = plate()
    size = part.bounding_box().size
    assert max(size.X, size.Y) <= S.PRINT_MAX, f"coupon_v2_plate: {size.X:.1f} × {size.Y:.1f} が A1 mini に置けない"
    export_stl(part, str(out / "coupon_v2_plate.stl"))
    made = {"coupon_v2_plate": (size.X, size.Y, size.Z)}
    for old in out.glob("coupon_v2_cover_*.stl"):                         # 前は出していた蓋 3 つ。古い STL を「刷る物」と見間違えない
        old.unlink()
    return made


def numbers():
    """文書と絵に載せる数（全部ここで測る・計算する）。"""
    sc = screw_v2()
    out = {"screw": [], "knob": []}
    for name, wall in (("back", "奥の壁"), ("side", "左の壁")):
        for (x, y), d in sc["holes"][name]:
            e, share = thread_engagement(d)
            out["screw"].append(dict(wall=wall, d=d, engage=round(e, 3), share=round(share, 2), flesh=flesh(sc[f"frame_{name}"], x, y, d)[0]))
    for (dx, _), label in zip(KNOB_VARIANTS, ("(i) 前の位置（本体は縁から 2.5）", "(ii) 0.75 外 = 本番の位置")):
        out["knob"].append(dict(label=label, **finger_reach(dx), lifted=finger_reach(dx, desk=False)["bite"]))
    return out


def main():
    import click_coupon_v2_figs as figs

    for stem, size in sorted(export().items()):
        print(f"OK {stem}.stl  {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}")
    num = numbers()
    for row in num["screw"]:
        print("ねじ", row)
    for row in num["knob"]:
        print("つまみ", row)
    print("絵", figs.howto(OUT, num))
    return 0


if __name__ == "__main__":
    sys.exit(main())
