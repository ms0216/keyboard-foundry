"""cckb-click の本番の組み立ての絵。**作った立体そのものを切って描く**（寸法から描き直さない）。縦横は実寸比。

  main_sections.png   断面 6 枚: キー 2 個（置いたとき・押し切り）／外周のねじ／XIAO と USB の切り欠き／電池の口と指の切り欠き／電源スイッチのつまみ
  main_top.png        上から（枠の上面の高さで切る）と、枠の下（基板の上 1.5）で切った図。柱・壁・部品・ねじ・継ぎ目
  main_tilt.png       2.25u と 1u の縁を押し切った傾き（公差の端）と、その下の部品
  coupon_screw.png    ねじの試し刷り（本番の枠から切り出した壁と当て板）

    .venv/bin/python3 projects/cckb-click/click_case.py   が呼ぶ
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import Compound, Plane, Pos  # noqa: E402

import click_case as C  # noqa: E402
import click_figs as F  # noqa: E402
import click_parts as P  # noqa: E402

LAY, S = C.LAY, C.S
COL = {"frame": "#c8c8c8", "frame2": "#b4bcc6", "cap": "#f2b0b0", "pcb": "#7fb686", "sw": "#555555", "part": "#b98a55",
       "xiao": "#6f8fd0", "bat": "#d9d9d9", "screw": "#e0b020", "sheet": "#404040", "plug": "#9a9a9a"}


def yz(part, x):
    return F.section(part, Plane.YZ.offset(x), "Y", "Z")


def _scene(stem=None, mode="rest", keys=None):
    """[(色, 立体)]。mode = rest（ステムに載る）/ pressed / 傾き（"+x" など。keys に効く）。"""
    halves = C.frame_halves()
    rest = min(0.0, (S.SW_STEM_TOP if stem is None else stem) - P.levels(S)["pad"])
    caps = []
    for k in LAY.keys:
        if keys is not None and k.i in keys and mode != "rest":
            caps.append(C.cap_pose(k, mode))
        else:
            caps.append(Pos(0, 0, rest) * C.cap_pose(k, "latched"))
    bp = C.board_parts()
    sw_stem = None if mode == "rest" else S.SW_BODY_H + 0.1
    sws = C.switch_solids(LAY, stem)
    if keys is not None and mode != "rest":
        low = C.switch_solids(LAY, sw_stem)
        sws = {n: (low[n] if n in {f"SW{i}" for i in keys} else v) for n, v in sws.items()}
    return [(COL["sheet"], C.sheet_solid()), (COL["pcb"], C.pcb_solid()),
            (COL["screw"], Compound(list(C.screw_solids().values()))),
            (COL["sw"], Compound(list(sws.values()))),
            (COL["part"], Compound([v for n, v in bp.items() if n not in ("U_MCU", "BT1")])),
            (COL["xiao"], bp["U_MCU"]), (COL["bat"], Compound([bp["BT1"], C.cell_solid()])),
            (COL["frame"], halves["left"]), (COL["frame2"], halves["right"]),
            (COL["cap"], Compound(caps))]


def _draw(ax, scene, cut, lim, title, levels=()):
    for color, part in scene:
        F.fill(ax, cut(part), color, lw=0.5)
    for z, text in levels:
        ax.plot(lim[:2], [z, z], ":", color="#555", lw=0.5)
        ax.text(lim[1] - 0.1, z + 0.04, text, fontsize=7, ha="right", va="bottom", color="#222")
    ax.set_xlim(lim[0], lim[1])
    ax.set_ylim(lim[2], lim[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)


def sections(out):
    z = LAY.z()
    lv = [(0.0, "基板の上面 0"), (z["frame_under"], "枠の下面 3.0"), (z["frame_top"], "枠の上面 5.0"),
          (z["cap_top"], "キャップの上面 6.0"), (z["desk"], f"机 {z['desk']:.1f}")]
    rest = _scene()
    k = next(k for k in LAY.keys if k.label == "G")
    pressed = _scene(mode="pressed", keys={k.i, k.i + 1})
    fig, axs = plt.subplots(3, 2, figsize=(17, 13))
    zl = (-2.6, 6.6)
    _draw(axs[0][0], rest, lambda p: F.xz(p, k.y), (k.x - 12, k.x + 31, *zl), f"キー 2 個（{k.label} と右隣）・置いたとき（ステム 3.4 に載る）", lv)
    _draw(axs[0][1], pressed, lambda p: F.xz(p, k.y), (k.x - 12, k.x + 31, *zl), "同じ所・2 個とも押し切り（公差の端: 1.0 沈む）", lv)
    sx = S.SCREWS_PERIMETER[3][0]
    _draw(axs[1][0], rest, lambda p: yz(p, sx), (24, 52, *zl), f"奥の壁のねじ（x {sx}）: 基板の下から M2×4・頭はシートの厚さの中", lv)
    _draw(axs[1][1], rest, lambda p: F.xz(p, S.XIAO_AT[1]), (-148, -112, *zl), "左の角: XIAO と USB の切り欠き（y は XIAO の中心）", lv)
    cx = S.CLIP_AT[0]
    _draw(axs[2][0], rest, lambda p: yz(p, cx), (-52, -26, *zl), "右の角: 電池クリップ・電池の口（手前の壁）・指の切り欠き（x は電池の中心）", lv)
    _draw(axs[2][1], rest, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_ON * S.PSW_TRAVEL / 2), (128, 148, *zl),
          "右の縁: 電源スイッチ（つまみが入の位置の y）", lv)
    fig.suptitle("cckb-click の断面（作った立体を切った物。灰 = 枠・赤 = キャップ・緑 = 基板・黒 = スイッチ・茶 = 部品・黄 = ねじ）", fontsize=12)
    fig.tight_layout()
    p = out / "main_sections.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


def top(out):
    scene = _scene()
    f = LAY.frame
    fig, axs = plt.subplots(2, 1, figsize=(20, 14.5))
    lim = (f[0] - 2, f[2] + 2, f[1] - 2, f[3] + 2)
    _draw(axs[0], scene, lambda p: F.xy(p, 4.5), lim, "枠の上面の少し下（z 4.5）で切った図: 枠（左右で色を分けた）・キャップ・角の屋根・USB と電池の切り欠き")
    _draw(axs[1], scene, lambda p: F.xy(p, 1.0), lim, "基板の上 1.0 で切った図: 外周の壁・柱・ねじの所の厚い壁・スイッチ・ダイオード・XIAO・電池クリップ・電源スイッチ")
    for ax in axs:
        xs, ys = zip(*LAY.seam_path())
        ax.plot(xs, ys, "--", color="#d00000", lw=0.8)
    for ref, c, kind in LAY.screws():
        axs[1].plot(*c, "o", ms=5, mfc="none", mec="#b06000" if kind == "perimeter" else "#888888")
    fig.tight_layout()
    p = out / "main_top.png"
    fig.savefig(p, dpi=85)
    plt.close(fig)
    return p


def tilt(out):
    z = LAY.z()
    lv = [(0.0, "基板の上面 0"), (z["frame_under"], "枠の下面 3.0"), (z["frame_top"], "枠の上面 5.0")]
    wide = next(k for k in LAY.keys if k.label == "Enter")
    one = next(k for k in LAY.keys if k.label == "G")
    fig, axs = plt.subplots(2, 2, figsize=(18, 8))
    for row, (k, modes) in enumerate(((wide, ("+x", "-x")), (one, ("+x", "+y")))):
        for col, m in enumerate(modes):
            scene = _scene(mode=m, keys={k.i})
            half = k.w * 19.05 / 2 + 6
            if m[1] == "x":
                _draw(axs[row][col], scene, lambda p: F.xz(p, k.y - 5.6), (k.x - half, k.x + half, -2.4, 6.6),
                      f"{k.label}（{k.w}u）の {m} の縁を押し切り・ダイオードを通る面（y = キーの中心 − 5.6）", lv)
            else:
                _draw(axs[row][col], scene, lambda p: yz(p, k.x + 1.2), (k.y - 14, k.y + 14, -2.4, 6.6),
                      f"{k.label}（{k.w}u）の {m} の縁を押し切り・ダイオードを通る面（x = キーの中心 ＋ 1.2）", lv)
    fig.suptitle("縁を押し切った傾き（公差の端: 真ん中が 1.0 沈むまで。真ん中のスイッチの本体は無いものとして回した = 実物より深い）", fontsize=11)
    fig.tight_layout()
    p = out / "main_tilt.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


def screw_coupon(out):
    """ねじの試し刷り: 上から（基板の上 1.0 で切る）と、ねじを通る断面（ふつうの壁・厚くした壁・左の壁）。"""
    sc = C.screw_coupon()
    boxes = C.screw_coupon_boxes()
    d, depth = LAY.pilot()
    fig, axs = plt.subplots(2, 3, figsize=(18, 9))
    axs[0][0].remove()
    axs[0][1].remove()
    scene = lambda n: [(COL["pcb"], sc[f"base_{n}"]), (COL["frame"], sc[f"frame_{n}"])]      # noqa: E731
    bb, screws, thick = boxes["back"]
    ax = plt.subplot2grid((2, 3), (0, 0), colspan=2, fig=fig)
    _draw(ax, scene("back"), lambda p: F.xy(p, 1.0), (bb[0] - 2, bb[2] + 2, bb[1] - 2, bb[3] + 2),
          "奥の壁の切れ端（基板の上 1.0 で切った図）: ねじ 3 本。右の 1 本だけ壁を穴の中へ 0.5 厚くした（その側の端の角を落としてある）")
    for i, (x, y) in enumerate(screws):
        ax.text(x, bb[1] - 1.2, f"{i + 1} {'厚い（内の肉 1.2）' if (x, y) == thick else 'ふつう（内の肉 0.7）'}", ha="center", fontsize=9)
    sb, (sscrew,), _ = boxes["side"]
    _draw(axs[0][2], scene("side"), lambda p: F.xy(p, 1.0), (sb[0] - 2, sb[2] + 2, sb[1] - 2, sb[3] + 2),
          "左の壁の切れ端: ねじ 1 本（壁を厚くする幅が狭い所。斜めの肉 0.49）")
    axs[0][2].text(sscrew[0] + 4.5, sscrew[1], "4", fontsize=9)
    zl = (-2.2, 5.6)
    lv = [(0.0, "当て板の上面 0（基板の上面）"), (depth, f"下穴の底 {depth}"), (S.SCREW_L - S.PCB_T, f"M2×4 の先 {S.SCREW_L - S.PCB_T:.1f}")]
    _draw(axs[1][0], scene("back"), lambda p: yz(p, screws[0][0]), (bb[1] - 1, bb[3] + 1, *zl), "1 のねじを通る断面（ふつう）", lv)
    _draw(axs[1][1], scene("back"), lambda p: yz(p, thick[0]), (bb[1] - 1, bb[3] + 1, *zl), "3 のねじを通る断面（厚くした壁）", lv)
    _draw(axs[1][2], scene("side"), lambda p: F.xz(p, sscrew[1]), (sb[0] - 1, sb[2] + 1, *zl), "4 のねじを通る断面（左の壁）", lv)
    fig.suptitle("ねじの試し刷り coupon_screw（本番の枠から切り出した壁 ＋ 厚さ 1.6 の当て板。灰 = 枠・緑 = 当て板）", fontsize=12)
    fig.tight_layout()
    p = out / "coupon_screw.png"
    fig.savefig(p, dpi=85)
    plt.close(fig)
    return p


def render_all(out):
    return [sections(out), top(out), tilt(out), screw_coupon(out)]
