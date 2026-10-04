"""cckb-click の試し刷り（基板なし）。**基板を設計する前に刷って、触って決める。**

    .venv/bin/python3 projects/cckb-click/click_coupons.py      # STL・絵・.blend を build/cckb-click/ に出す
    .venv/bin/python3 projects/cckb-click/tools/slice_precise.py   # 精度優先の設定で実際にスライスして G-code を検査

何を刷って何を見るかは docs/coupon-test.md。**最初に刷るのは min（最小の一式）。**残りの 6 組は、min で見込みが立ってから:

  min       最初に刷る最小の一式: 穴 3 つの枠（穴を 0.1 ずつ広げる）＋キャップ 3 個＋板。ノギスで測る所つき（外寸 10 の塊・内寸 10 の穴・つばと同じ厚さの段）。
            coupon_min_plate.stl は 3 つを 1 枚に並べた物（これだけ刷ればよい）
  a / b     3×3 の枠（19.05 ピッチ）。案 A（穴 16.5×16.0）と案 B（穴 17.05 角・リブ 2.0）。列ごとに穴を 0.1 ずつ広げる。板は共用（coupon_ab_base）
  standin   スイッチの代わりの台の高さ 3.2〜3.7（2×3）。浮き・がた・押し込みを触る。キャップは b の物を使う
  latch     掛かり方 6 通り（つば F・45° の足 C・平らな足 S × 0.4 / 0.6）
  wide      1.5u・1.75u・2.25u（中心の台 1 個）。端を押したときの傾き
  strip     枠の半分の長さの帯（7.5u = 142.9）と柱。反りと、柱が全部平らな面に着くか

名前の約束: build/cckb-click/coupon_<組>_<frame|base|caps>.stl（**刷る向きで出す**。min の 4 個 ＋ あとで刷る 14 個）。
見分け方: 左手前の角が落としてある（向き）。枠の縁の点の数 = 列・番号。板の台の手前の点 = 台の番号。キャップの上面の点 = 掛かり方の番号。
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(HERE), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from build123d import Compound, Pos, export_stl  # noqa: E402

import click_parts as P  # noqa: E402
from foundry import paths  # noqa: E402
from foundry.layout import UNIT  # noqa: E402

S = P.S
OUT = paths.BUILD / HERE.name
# 掛かり方の試し: (形, つばの厚さ／首の高さ)。番号 = 並び順 ＋ 1（枠の縁とキャップの上面の点の数）
LATCH_VARIANTS = (("F", 0.4), ("F", 0.6), ("C", 0.4), ("C", 0.6), ("S", 0.4), ("S", 0.6))
COLORS = {"frame": "#9aa0a6", "base": "#2f7d32", "caps": "#e8c9a0"}
OTHER_GENERATOR = ("coupon_screw_", "coupon_corner_")   # ねじ・角の試し刷りは click_case.py が作る（本番の枠から切り出す）。ここでは消さない


@dataclass
class Coupon:
    cells: list
    wall: bool = True
    extra_u: float = 0.0
    has_base: bool = True
    bumps: dict = field(default_factory=dict)        # マスの番号 → 板の点の数
    cap_dots: dict = field(default_factory=dict)     # マスの番号 → キャップの点の数
    caps: bool = True
    base_stl: str | None = None                      # 板を刷る STL の名前。None = この組の名前。"" = 刷らない（ほかの組の板を使う）
    caps_stl: str | None = None                      # 同、キャップ
    gauge: bool = False                              # 測る所をつける（枠の右の空きに内寸の穴・キャップの列に外寸の塊）。1 枚に並べた STL（_plate）も出す


def coupons(s=S):
    """小片の一覧（名前 → Coupon）。**刷る時間を減らすために共用する物**（検査が同じ形だと確かめる）:
    a と b の板は同じ形（外形・台の高さが同じ）なので 1 枚（coupon_ab_base）。standin のキャップは b のキャップ（案 B の 1u）。"""
    nominal = s.SW_STEM_TOP

    def grid(hole):
        return [P.Cell(i * UNIT, j * UNIT, hole, step=st, standin=nominal,
                       dots=(i + 1 if j in (0, 2) else 0), back=(j == 2))
                for j in range(3) for i, st in enumerate(s.COUPON_HOLE_STEPS)]

    hs = s.COUPON_STANDIN_H
    half = len(hs) // 2
    standin = [P.Cell((k % half) * UNIT, (k // half) * UNIT, s.HOLE_B, standin=h, dots=k + 1, back=(k >= half))
               for k, h in enumerate(hs)]
    latch = [P.Cell(k * UNIT, 0.0, s.HOLE_B, latch=l, tab=t, standin=nominal, dots=k + 1)
             for k, (l, t) in enumerate(LATCH_VARIANTS)]
    wide = [P.Cell((w - 1.0) * UNIT / 2, j * UNIT, s.HOLE_B, w_u=w, standin=nominal)
            for j, w in enumerate(s.COUPON_WIDE)]
    n = int(s.COUPON_STRIP_U)
    strip = [P.Cell(k * UNIT, 0.0, s.HOLE_B) for k in range(n)]
    mini = [P.Cell(i * UNIT, 0.0, s.HOLE_B, step=st, standin=nominal, dots=i + 1) for i, st in enumerate(s.COUPON_HOLE_STEPS)]
    return {
        "min": Coupon(mini, extra_u=s.COUPON_GAUGE_EXTRA_U, gauge=True),
        "a": Coupon(grid(s.HOLE_A), base_stl="coupon_ab_base"),
        "b": Coupon(grid(s.HOLE_B), base_stl=""),
        "standin": Coupon(standin, bumps={k: k + 1 for k in range(len(hs))}, caps_stl=""),
        "latch": Coupon(latch, cap_dots={k: k + 1 for k in range(len(latch))}),
        "wide": Coupon(wide),
        "strip": Coupon(strip, wall=False, extra_u=s.COUPON_STRIP_U - n, has_base=False, caps=False),
    }


def rest_dz(c, s=S):
    """置いたときのキャップの位置（掛かった位置からの下がり。負）。台がステムの代わりに支える。
    台が押す面より高ければ 0（掛かった位置のまま = 押し込み。実物では枠が浮く）。"""
    if c.standin is None:
        return 0.0
    return min(0.0, c.standin - P.levels(s, c.latch, c.tab)["pad"])


def build(cp, s=S):
    """組んだ状態の立体（名前 → 立体。caps は [(マス, 立体)]・置いた位置）。"""
    out = {"frame": P.frame(cp.cells, s, wall=cp.wall, extra_u=cp.extra_u)}
    if cp.gauge:
        out["frame"] = (out["frame"] - P.gauge_slot(*gauge_slot_xy(cp, s), s)).clean()
    if cp.has_base:
        out["base"] = P.base(cp.cells, s, extra_u=cp.extra_u, bumps=cp.bumps)
    if cp.caps:
        out["caps"] = [(c, Pos(c.cx, c.cy, rest_dz(c, s)) * P.cap(c, s, dots=cp.cap_dots.get(i, 0)))
                       for i, c in enumerate(cp.cells)]
    return out


def gauge_slot_xy(cp, s=S):
    """測る穴の中心（枠の右の空きの真ん中）。"""
    b = P.key_bounds(cp.cells)
    return (b[2] + cp.extra_u * UNIT / 2, (b[1] + b[3]) / 2)


def lay_caps(cells_caps, s=S, gap=3.0):
    """キャップを刷る向きでベッドに並べる（左から。はみ出したら次の行）。"""
    placed, x, y, row = [], 0.0, 0.0, 0.0
    for c, part in cells_caps:
        k = P.cap_print_pose(c, Pos(-c.cx, -c.cy, 0) * part, s)
        size = k.bounding_box().size
        if x + size.X > s.PRINT_MAX:
            x, y, row = 0.0, y + row + gap, 0.0
        placed.append(Pos(x + size.X / 2, y + size.Y / 2, 0) * k)
        x += size.X + gap
        row = max(row, size.Y)
    return Compound(placed)


def print_parts(name, cp, built, s=S):
    """刷る物（STL の名前 → 刷る向きの立体）。枠は上面をベッドに。共用で刷らない物（base_stl / caps_stl が ""）は出さない。"""
    out = {f"coupon_{name}_frame": P.flip_to_bed(built["frame"])}
    if "base" in built and cp.base_stl != "":
        out[cp.base_stl or f"coupon_{name}_base"] = P.to_bed(built["base"])
    if "caps" in built and cp.caps_stl != "":
        caps = lay_caps(built["caps"], s)
        if cp.gauge:                                  # 測る塊をキャップの列の右に（同じ 1 層目・同じ高さの段を、同じ条件で刷る）
            bb = caps.bounding_box()
            block = Pos(bb.max.X + 3.0 + s.COUPON_GAUGE[0] / 2, (bb.min.Y + bb.max.Y) / 2, 0) * P.gauge_block(s)
            caps = Compound(list(caps.solids()) + [block])
        out[cp.caps_stl or f"coupon_{name}_caps"] = caps
    if cp.gauge:
        out[f"coupon_{name}_plate"] = Compound([p for _, p in plate_layout(out, name)])
    return out


def plate_layout(parts, name, gap=5.0):
    """1 枚に並べる: 手前から キャップ（＋測る塊）・枠・板。X は中心をそろえる。**長い辺と、穴を広げる向きが X**
    （A1 mini は X が頭・Y がベッド。測る塊と穴の X / Y が、そのまま機械の X / Y になる）。返り値 [(種類, 置いた立体)]。"""
    out, y = [], 0.0
    for kind in ("caps", "frame", "base"):
        part = parts[f"coupon_{name}_{kind}"]
        bb = part.bounding_box()
        out.append((kind, Pos(-(bb.min.X + bb.max.X) / 2, y - bb.min.Y, -bb.min.Z) * part))
        y += bb.size.Y + gap
    return out


def export(s=S, out=OUT):
    """全部の小片を作り、刷る STL と組んだ状態の STL（assembly/）を書く。**どの生成器も出さない coupon_*.stl は消す。**"""
    out.mkdir(parents=True, exist_ok=True)
    asm = out / "assembly"
    asm.mkdir(exist_ok=True)
    made, style, x = {}, {}, 0.0
    for old in asm.glob("*.stl"):
        old.unlink()
    for name, cp in coupons(s).items():
        built = build(cp, s)
        for stem, part in print_parts(name, cp, built, s).items():
            size = part.bounding_box().size
            assert max(size.X, size.Y) <= s.PRINT_MAX, f"{stem}: {size.X:.1f} × {size.Y:.1f} が A1 mini に置けない"
            export_stl(part, str(out / f"{stem}.stl"))
            made[stem] = (size.X, size.Y, size.Z)
        # 組んだ状態（.blend 用）。小片を左から並べる
        b = built["frame"].bounding_box()
        shift = Pos(x - b.min.X, 0, 0)
        for kind in ("frame", "base", "caps"):
            if kind not in built:
                continue
            part = Compound([p for _, p in built[kind]]) if kind == "caps" else built[kind]
            export_stl(shift * part, str(asm / f"{name}_{kind}.stl"))
            style[f"{name}_{kind}"] = (COLORS[kind], 0.6 if kind == "frame" else 1.0)
        x += b.size.X + 12.0
    (asm / "style.json").write_text(json.dumps(style))
    for old in out.glob("coupon_*.stl"):
        if old.stem not in made and not old.stem.startswith(OTHER_GENERATOR):
            old.unlink()
            print(f"消した（もう作らない）: {old.name}")
    return made, style


def export_blend(style, out=OUT):
    """組んだ状態を .blend にする。**Blender は失敗しても 0 を返す**ので「OK <数>」とできたファイルで判定する。"""
    if not Path(paths.BLENDER).exists():
        return None
    r = subprocess.run([paths.BLENDER, "-b", "-P", str(HERE / "tools" / "blend_coupons.py")],
                       capture_output=True, text=True, timeout=900)
    ok = [line for line in r.stdout.splitlines() if line.startswith("OK ")]
    n = int(ok[-1].split()[1]) if ok else 0
    blend, png = out / "assembly" / "cckb-click_coupons.blend", out / "assembly" / "cckb-click_coupons.png"
    assert n == len(style) and blend.exists() and png.exists(), r.stdout[-2000:] + r.stderr[-2000:]
    return blend, png


def main():
    import click_figs

    made, style = export()
    for stem, size in sorted(made.items()):
        print(f"OK {stem}.stl  {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}")
    for p in click_figs.render_all(OUT):
        print("絵", p)
    b = export_blend(style)
    print("Blender:", *(b or ["無い（BLENDER の場所: foundry/paths.py）"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
