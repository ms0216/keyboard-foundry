"""cckb-click の試し刷りの絵。**作った立体そのものを切って描く**（寸法から描き直さない）。縦横は実寸比。

  section_main.png    本番の形（つば F・0.4）の断面。キーの中心／つばを通る面 × 置いたとき／押し切り
  section_latch.png   掛かり方 6 通りの、つばのまわりの拡大（置いたとき／押し切り）
  wide_end_press.png  2.25u の端を押したとき（剛体で回した断面）
  coupons_top.png     あとで刷る小片 6 組を上から（穴・くぼみ・柱・台・番号）
  min_set.png         最初に刷る最小の一式（ベッドに置く向き・組んだ所を上から・断面）

    .venv/bin/python3 projects/cckb-click/click_coupons.py   が呼ぶ
"""

from __future__ import annotations

import math
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import GeomType, Plane, Pos  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.patches import Polygon as MPoly  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402

import click_coupons as CC  # noqa: E402
import click_parts as P  # noqa: E402
from foundry.layout import UNIT  # noqa: E402

plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
S = P.S
GREY, RED, GREEN, DARK = "#c8c8c8", "#f2b0b0", "#7fb686", "#6b6b6b"


def _wire_pts(wire):
    """輪郭の点列（辺を端でつないで順に。直線は端だけ、曲線は細かく）。"""
    segs = []
    for e in wire.edges():
        n = 1 if e.geom_type == GeomType.LINE else 16
        segs.append([e.position_at(t / n) for t in range(n + 1)])
    out = segs.pop(0)
    while segs:
        tail = out[-1]
        k = min(range(len(segs)), key=lambda i: min((segs[i][0] - tail).length, (segs[i][-1] - tail).length))
        seg = segs.pop(k)
        if (seg[-1] - tail).length < (seg[0] - tail).length:
            seg.reverse()
        out += seg[1:]
    return out


def _faces(shape):
    if shape is None:
        return []
    return list(shape.faces()) if hasattr(shape, "faces") else [f for s in shape for f in s.faces()]


def section(part, plane, ux, uy):
    """立体を平面で切った面 [(外の輪郭, [穴の輪郭])]。座標は (ux, uy) の成分。"""
    out = []
    for f in _faces(part.intersect(plane)):
        outer = [(getattr(p, ux), getattr(p, uy)) for p in _wire_pts(f.outer_wire())]
        inner = [[(getattr(p, ux), getattr(p, uy)) for p in _wire_pts(w)] for w in f.inner_wires()]
        out.append((outer, inner))
    return out


def xz(part, y):
    return section(part, Plane.XZ.offset(-y), "X", "Z")


def xy(part, z):
    return section(part, Plane.XY.offset(z), "X", "Y")


def fill(ax, polys, fc, ec="k", lw=0.7, alpha=1.0, move=None, ls="-"):
    """面を塗る。**穴は抜く**（白で塗りつぶさない——下に描いた物を隠して、柱が消えて見えた）。"""
    for outer, inner in polys:
        verts, codes = [], []
        for ring in [outer] + list(inner):
            pts = [move(p) for p in ring] if move else list(ring)
            verts += pts + [pts[0]]
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 1) + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), fc=fc, ec=ec, lw=lw, alpha=alpha, ls=ls))


def one_key(latch, tab, standin=None, s=S, w_u=1.0):
    """1 マスの組（枠・板・キャップ。マスの中心が原点）。"""
    c = P.Cell(0.0, 0.0, s.HOLE_B, w_u=w_u, latch=latch, tab=tab, standin=s.SW_STEM_TOP if standin is None else standin)
    return c, P.frame([c], s), P.base([c], s), P.cap(c, s)


def tab_plane_y(c):
    """つばを通る面（穴の手前の縁から 1.0 内側）。"""
    return -P.hole_size(c)[1] / 2 + 1.0


def draw_key(ax, c, fr, bs, cp, y, dz, title, s=S, xlim=None, zlim=(-2.0, 6.6), marks=True):
    lv = P.levels(s, c.latch, c.tab)
    fill(ax, xz(bs, y), GREEN)
    fill(ax, xz(fr, y), GREY)
    fill(ax, xz(Pos(0, 0, dz) * cp, y), RED, ec="#b00000")
    half = c.w_u * UNIT / 2 + s.PLATE_MARGIN_X + 2.5
    xlim = xlim or (-half, half)
    if marks:
        for z, t in ((0.0, "基板の上面 0"), (s.SW_BODY_H, f"スイッチの本体 {s.SW_BODY_H}"), (lv["frame_under"], f"枠の下面 {lv['frame_under']:.1f}"),
                     (lv["pad"] + dz, f"押す面 {lv['pad'] + dz:.1f}"), (lv["latch"], f"掛かる面 {lv['latch']:.1f}"),
                     (lv["frame_top"], f"枠の上面 {lv['frame_top']:.1f}"), (lv["cap_top"] + dz, f"キャップの上面 {lv['cap_top'] + dz:.1f}")):
            ax.plot(xlim, [z, z], ":", color="#555", lw=0.5)
            ax.text(xlim[1] - 0.1, z + 0.05, t, fontsize=7, ha="right", va="bottom", color="#333")
    ax.set_xlim(*xlim)
    ax.set_ylim(*zlim)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)


def section_main(out, s=S):
    c, fr, bs, cp = one_key("F", s.TAB_T, s=s)
    lv = P.levels(s, "F", s.TAB_T)
    rest = CC.rest_dz(c, s)
    fig, axs = plt.subplots(2, 2, figsize=(16, 9.6))
    ty = tab_plane_y(c)
    for row, (dz, state) in enumerate(((rest, f"置いたとき（ステム {c.standin} の上。浮き {-rest:.1f}）"),
                                       (-lv["descent_max"], f"押し切り（公差の端: {lv['descent_max']:.1f} 下がる）"))):
        draw_key(axs[row][0], c, fr, bs, cp, 0.0, dz, f"キーの中心を通る面・{state}", s)
        draw_key(axs[row][1], c, fr, bs, cp, ty, dz, f"つばを通る面（穴の縁から 1.0 内側）・{state}", s)
    fig.suptitle("cckb-click 本番の形（つば F・厚さ %.1f）の断面。灰 = 枠（柱つき）・赤 = キャップ・緑 = 基板の代わりの板とスイッチの代わりの台。"
                 "高さは基板の上面から [mm]・実寸比" % s.TAB_T, fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def section_latch(out, s=S):
    fig, axs = plt.subplots(3, 4, figsize=(16, 10.5))
    for k, (latch, tab) in enumerate(CC.LATCH_VARIANTS):
        c, fr, bs, cp = one_key(latch, tab, s=s)
        lv = P.levels(s, latch, tab)
        rest = CC.rest_dz(c, s)
        ty = tab_plane_y(c)
        name = {"F": "つば F", "C": "45° の足 C", "S": "平らな足 S"}[latch]
        for j, (dz, state) in enumerate(((rest, "置いたとき"), (-lv["descent_max"], "押し切り"))):
            ax = axs[k // 2][(k % 2) * 2 + j]
            draw_key(ax, c, fr, bs, cp, ty, dz, f"{k + 1}: {name} {tab}・{state}（押す面 {lv['pad'] + dz:.1f}）", s,
                     xlim=(4.6, 11.4), zlim=(-0.3, 6.3), marks=False)
            ax.grid(True, lw=0.2)
    fig.suptitle("掛かり方 6 通り（つばを通る面の拡大・1 目盛 1 mm）。番号 = 枠の縁とキャップの上面の点の数。"
                 "F は下面をベッドに、C・S は上面をベッドに刷る", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def wide_end_press(out, s=S):
    w_u = max(s.COUPON_WIDE)
    c, fr, bs, cp = one_key("F", s.TAB_T, s=s, w_u=w_u)
    lv = P.levels(s, "F", s.TAB_T)
    ep = P.end_press(c, s)
    th = math.radians(ep["angle"])
    px, pz = -ep["pivot"], lv["latch"]

    def rot(p):          # 遠い側（左）のつばの外の縁・掛かる面を支点に、右が下がる向きに回す
        dx, dz = p[0] - px, p[1] - pz
        return (px + dx * math.cos(th) + dz * math.sin(th), pz - dx * math.sin(th) + dz * math.cos(th))

    ty = tab_plane_y(c)
    fig, axs = plt.subplots(2, 1, figsize=(16, 7.6))
    for ax, y, t in ((axs[0], 0.0, "キーの中心を通る面"), (axs[1], ty, "つばを通る面")):
        fill(ax, xz(bs, y), GREEN)
        fill(ax, xz(fr, y), GREY)
        fill(ax, xz(cp, y), "none", ec="#888", ls="--")
        fill(ax, xz(cp, y), RED, ec="#b00000", move=rot)
        half = w_u * UNIT / 2 + 5
        ax.set_xlim(-half, half)
        ax.set_ylim(-2.0, 7.6)
        ax.set_aspect("equal")
        ax.set_title(f"{w_u}u の右端を押す・{t}。点線 = 掛かった位置。中心が {s.SW_TRAVEL + s.SW_TRAVEL_TOL:.1f} 沈むまで"
                     f"（傾き {ep['angle']:.2f}°・右の縁 {ep['near_drop']:.2f} 下がる・左の胴が枠の上面の高さで横へ {ep['shift']:.3f}・"
                     f"指の力はスイッチの {ep['force_ratio']:.2f} 倍）", fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def coupons_top(out, s=S):
    cps = {k: v for k, v in CC.coupons(s).items() if k != "min"}       # 最小の一式は min_set.png
    fig, axs = plt.subplots(2, 3, figsize=(16, 11.5))
    lv = P.levels(s)
    titles = {"a": "a: 案 A（穴 %.1f×%.1f）3×3" % s.HOLE_A, "b": "b: 案 B（穴 %.2f 角）3×3" % s.HOLE_B[0],
              "standin": "standin: 台の高さ", "latch": "latch: 掛かり方", "wide": "wide: 幅の広いキー",
              "strip": "strip: 半分の長さの帯（柱だけ・壁なし）"}
    for ax, (name, cp) in zip(axs.flat, cps.items()):
        built = CC.build(cp, s)
        fr = built["frame"]
        fill(ax, xy(fr, lv["frame_top"] - s.COUPON_DOT[1] / 2), GREY)
        fill(ax, xy(fr, 1.5), "#9db7e8", ec="#2040a0", lw=0.5, alpha=0.8)                 # 柱と壁（基板に着く所）
        for outer, inner in xy(fr, lv["frame_under"] + 0.5):                              # くぼみ（下から掘った範囲）
            for h in inner:
                ax.add_patch(MPoly(h, closed=True, fc="none", ec="#a05000", lw=0.6, ls="--"))
        for c, part in built.get("caps", []):
            fill(ax, xy(part, lv["cap_top"] + CC.rest_dz(c, s) - s.CAP_TOP_CHAMFER - 0.05), RED, ec="#b00000", alpha=0.55)
        for c in cp.cells:
            w, d = P.hole_size(c)
            lines = []
            if name in ("a", "b", "wide"):
                lines.append(f"穴 {w:.2f}×{d:.2f}")
            if c.standin is not None:
                ax.add_patch(plt.Rectangle((c.cx - s.SW_BODY / 2, c.cy - s.SW_BODY / 2), s.SW_BODY, s.SW_BODY, fc=DARK, ec="k", lw=0.5))
            if name == "standin":
                lines.append(f"台 {c.standin:.1f}")
            if name == "latch":
                lines.append(f"{c.latch} {c.tab}")
            if c.dots:
                lines.append(f"点 {c.dots}")
            ax.text(c.cx, c.cy + 5.8, "\n".join(lines), fontsize=6.5, ha="center", va="center")
        bb = fr.bounding_box()
        ax.set_xlim(bb.min.X - 5, bb.max.X + 5)
        ax.set_ylim(bb.min.Y - 5, bb.max.Y + 5)
        ax.set_aspect("equal")
        ax.set_title(f"{titles[name]}  {bb.size.X:.1f} × {bb.size.Y:.1f}", fontsize=10)
    fig.suptitle("試し刷りの小片（上から。手前が下・左手前の角が落としてある）。灰 = 枠・赤 = キャップ・青 = 柱と壁（板に着く所）・"
                 "茶の点線 = くぼみ・黒 = スイッチの代わりの台", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def min_set(out, s=S):
    """最初に刷る最小の一式。上 = ベッドに置く向き（coupon_min_plate.stl を上から）、中 = 組んだ所を上から、下 = 断面。"""
    cp = CC.coupons(s)["min"]
    built = CC.build(cp, s)
    lv = P.levels(s)
    parts = CC.print_parts("min", cp, built, s)
    fig, axs = plt.subplots(3, 1, figsize=(13, 16), gridspec_kw={"height_ratios": [3.4, 1.35, 0.75]})
    ax = axs[0]
    label = {"caps": "キャップ 3 個（同じ形）＋ 測る塊\n押す面（下面）がベッド", "frame": "枠\n上面がベッド（柱が上を向く）",
             "base": "板（基板の代わり）\n下面がベッド"}
    colour = {"caps": RED, "frame": GREY, "base": GREEN}
    for kind, part in CC.plate_layout(parts, "min"):
        for z, a in ((0.35, 0.45), (part.bounding_box().max.Z - 0.25, 1.0)):       # 薄く = ベッドのすぐ上、濃く = いちばん上
            fill(ax, xy(part, z), colour[kind], alpha=a, lw=0.5)
        bb = part.bounding_box()
        ax.text(bb.max.X + 2, (bb.min.Y + bb.max.Y) / 2, label[kind], fontsize=9, va="center")
    side, gh, ledge = s.COUPON_GAUGE
    ax.set_xlim(-45, 75)
    ax.set_ylim(-4, 82)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.2)
    ax.set_xlabel("X（A1 mini の頭が動く向き）")
    ax.set_ylabel("Y（ベッドが動く向き）")
    ax.set_title("ベッドに置く向き（coupon_min_plate.stl を上から。このまま回さずに刷る）。濃い色 = いちばん上の面", fontsize=11)

    ax = axs[1]
    fr = built["frame"]
    fill(ax, xy(fr, lv["frame_top"] - s.COUPON_DOT[1] / 2), GREY)
    for c, part in built["caps"]:
        fill(ax, xy(part, lv["cap_top"] + CC.rest_dz(c, s) - s.CAP_TOP_CHAMFER - 0.05), RED, ec="#b00000", alpha=0.55)
        w, _ = P.hole_size(c)
        ax.text(c.cx, c.cy, f"点 {c.dots}\n穴 {w:.2f} 角\n隙 片側 {P.side_gap(c, s)[0]:.2f}", fontsize=9, ha="center", va="center")
    gx, gy = CC.gauge_slot_xy(cp, s)
    ax.text(gx, gy, f"測る穴\n内寸 {side:.0f} 角", fontsize=8, ha="center", va="center")
    bb = fr.bounding_box()
    ax.set_xlim(bb.min.X - 4, bb.max.X + 4)
    ax.set_ylim(bb.min.Y - 3, bb.max.Y + 3)
    ax.set_aspect("equal")
    ax.set_title("組んだ所を上から（手前が下。左手前の角が落としてある。手前の縁の点の数 = 穴の番号。右へ行くほど穴が 0.1 ずつ広い）", fontsize=11)

    ax = axs[2]
    fill(ax, xz(built["base"], 0.0), GREEN)
    fill(ax, xz(fr, 0.0), GREY)
    for c, part in built["caps"]:
        fill(ax, xz(part, 0.0), RED, ec="#b00000")
    for z, tx in ((0.0, "板の上面 0"), (s.SW_STEM_TOP, f"台の上面 {s.SW_STEM_TOP}"), (lv["frame_top"], f"枠の上面 {lv['frame_top']:.1f}")):
        ax.plot([bb.min.X - 4, bb.max.X + 4], [z, z], ":", color="#555", lw=0.5)
        ax.text(bb.max.X + 3.8, z + 0.05, tx, fontsize=7, ha="right", va="bottom")
    ax.set_xlim(bb.min.X - 4, bb.max.X + 4)
    ax.set_ylim(-1.6, 6.6)
    ax.set_aspect("equal")
    ax.set_title(f"断面（キーの中心を通る面・実寸比）。キャップは台の上に載っている（浮き {lv['float_nominal']:.1f}）。右の空きが測る穴", fontsize=11)
    fig.suptitle(f"最初に刷る最小の一式（min）。測る塊: 外寸 {side:.0f} 角 × 高さ {gh:.0f}・右の段は厚さ {s.TAB_T}（つばと同じ）", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def render_all(out, s=S):
    out.mkdir(parents=True, exist_ok=True)
    return [section_main(out / "section_main.png", s), section_latch(out / "section_latch.png", s),
            wide_end_press(out / "wide_end_press.png", s), coupons_top(out / "coupons_top.png", s), min_set(out / "min_set.png", s)]

