"""cckb-click の本番の組み立ての絵。**作った立体そのものを切って描く**（寸法から描き直さない）。縦横は実寸比。

  main_sections.png   断面 6 枚: キー 2 個（置いたとき・押し切り）／外周のねじ／XIAO と USB の切り欠き／電池の口と指の切り欠き／電源スイッチのつまみ
  main_top.png        上から（枠の上面の高さで切る）と、枠の下（基板の上 1.5）で切った図。柱・壁・部品・ねじ・継ぎ目
  main_tilt.png       2.25u と 1u の縁を押し切った傾き（公差の端）と、その下の部品
  coupon_screw.png    ねじの試し刷り（本番の枠から切り出した壁と当て板）
  main_corner.png     右手前の角: つまみの切り欠き・電池の口・前の蓋（考え直し中・刷らない）を、上から・断面で
  coupon_corner.png   角の試し刷り（枠の切れ端・当て板・つまみと電池の代わり・蓋）
  cover_spring.png    蓋の腕（ばね）を手前から見た断面: 山が壁の下面に当たる所と、ばねとして効く長さ（直す前の形と並べる）

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
       "xiao": "#6f8fd0", "bat": "#d9d9d9", "screw": "#e0b020", "sheet": "#404040", "plug": "#9a9a9a", "cover": "#e08a3c",
       "knob": "#111111"}


def yz(part, x):
    return F.section(part, Plane.YZ.offset(x), "Y", "Z")


def _scene(stem=None, mode="rest", keys=None, cover=False):
    """[(色, 立体)]。mode = rest（ステムに載る）/ pressed / 傾き（"+x" など。keys に効く）。cover=True で電池の蓋を入れる。"""
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
            (COL["cap"], Compound(caps))] + ([(COL["cover"], C.cover_solid())] if cover else [])


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
    _draw(axs[2][0], rest, lambda p: yz(p, cx), (-52, -26, *zl), "右の角: 電池クリップ・電池の口（手前の壁）・指の切り欠き（x は電池の中心・蓋なし）", lv)
    _draw(axs[2][1], rest, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_ON * S.PSW_TRAVEL / 2), (128, 148, *zl),
          "右の縁: 電源スイッチ（つまみが入の位置の y）。つまみは枠の外面の内側・壁は上まで切り欠き", lv)
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


def corner(out):
    """右手前の角: 上から（蓋あり・なし）・つまみの高さで切った図・断面 3 枚（電池の中心／蓋の山／つまみ）。"""
    z = LAY.z()
    f = LAY.frame
    cv = LAY.cover()
    lv = [(0.0, "基板の上面 0"), (z["frame_under"], "枠の下面 3.0"), (z["frame_top"], "枠の上面 5.0")]
    with_c, without = _scene(cover=True), _scene()
    knobs = [(COL["knob"], C.knob_solid(1)), ("#888888", C.knob_solid(-1))]
    fig, axs = plt.subplots(2, 3, figsize=(20, 11))
    lim = (106, f[2] + 1.5, f[1] - 1.5, -29)
    _draw(axs[0][0], with_c, lambda p: F.xy(p, 4.65), lim, "上から（z 4.65）・前の蓋（橙）を入れた図。**蓋は考え直し中・刷らない**")
    _draw(axs[0][1], without, lambda p: F.xy(p, 4.65), lim, "同じ・蓋なし（電池の上面が指の切り欠きから見える）")
    _draw(axs[0][2], without + knobs, lambda p: F.xy(p, 0.7), lim, "つまみの高さ（z 0.7）で切った図。黒 = 入（奥）・灰 = 切（手前）のつまみ")
    for ax in axs[0]:
        ax.plot([f[2], f[2]], [lim[2], lim[3]], ":", color="#d00000", lw=0.6)
        ax.plot([lim[0], lim[1]], [f[1], f[1]], ":", color="#d00000", lw=0.6)
    zl = (-2.4, 6.0)
    _draw(axs[1][0], with_c, lambda p: yz(p, S.CLIP_AT[0]), (-52, -40, *zl), "断面（電池の中心 x）・前の蓋（刷らない）: 手前の板と電池の隙 0.51", lv)
    _draw(axs[1][1], with_c, lambda p: yz(p, cv["bump"][0][0]), (-52, -44, *zl), "断面（前の蓋の山の x）: 枠の溝は残してある（蓋は留まらなかった）", lv)
    on = _scene() + [(COL["knob"], C.knob_solid(1))]
    _draw(axs[1][2], on, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_ON * S.PSW_TRAVEL / 2), (136, 148, *zl),
          f"断面（つまみが入の y）: つまみの先は枠の外面（赤の点線）の {f[2] - LAY.psw_knob(1)[2]:.2f} 内側・内側の上の縁は斜め", lv)
    axs[1][2].plot([f[2], f[2]], zl, ":", color="#d00000", lw=0.6)
    fig.suptitle("右手前の角（作った立体を切った物）: 電源スイッチのつまみの切り欠き（外へ広がる形）と、電池の口。蓋は考え直し中（橙 = 前の蓋・刷らない）", fontsize=12)
    fig.tight_layout()
    p = out / "main_corner.png"
    fig.savefig(p, dpi=80)
    plt.close(fig)
    return p


def corner_coupon(out):
    """角の試し刷り: 上から（2 つの高さ）と断面 2 枚。"""
    cc = C.corner_coupon()
    box = C.corner_coupon_box()
    cv = LAY.cover()
    scene = [(COL["pcb"], cc["base"]), (COL["frame"], cc["frame"]), (COL["bat"], cc["cell"]), (COL["knob"], cc["knob"]), (COL["cover"], cc["cover"])]
    fig, axs = plt.subplots(2, 2, figsize=(17, 11))
    lim = (box[0] - 3, box[2] + 1.5, box[1] - 1.5, box[3] + 3)
    _draw(axs[0][0], scene, lambda p: F.xy(p, 4.65), lim, "上から（z 4.65）: 枠の切れ端（灰）・蓋（橙）")
    _draw(axs[0][1], scene, lambda p: F.xy(p, 0.7), lim, "当て板の上 0.7: スイッチの本体の代わり（溝とつまみの小片）・クリップの代わり（止めと案内）・電池の代わり")
    zl = (-2.2, 5.6)
    lv = [(0.0, "当て板の上面 0（基板の上面）"), (5.0, "枠の上面 5.0")]
    _draw(axs[1][0], scene, lambda p: yz(p, S.CLIP_AT[0]), (box[1] - 1, box[3] + 3, *zl), "断面（電池の中心 x）", lv)
    _draw(axs[1][1], scene, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_TRAVEL / 2), (box[0] - 3, box[2] + 1, *zl), "断面（つまみが入の y）", lv)
    fig.suptitle("角の試し刷り coupon_corner（本番の枠から切り出した右手前の角 ＋ 当て板。緑 = 当て板と代わりの物・橙 = 蓋・黒 = つまみの小片）", fontsize=12)
    fig.tight_layout()
    p = out / "coupon_corner.png"
    fig.savefig(p, dpi=85)
    plt.close(fig)
    return p


def cover_spring(out):
    """蓋の腕（ばね）: 山の頂を通る面（y）で、枠の口のまわりと蓋を切って手前から見る。上 = 3 回目の監査の前の形・下 = いまの形。
    数（当たる所・効く長さ・ひずみ・力）は click_case.cover_spring が立体から測った物。"""
    cv = LAY.cover()
    frame = C._mouth_piece()
    y = cv["bump"][0][1]
    lim = (cv["x0"] - 1.5, cv["x1"] + 1.5, 1.6, 5.3)
    shapes = (("直す前（3 回目の監査の指摘）: 山が壁の下いっぱい・腕 5.5", C.cover_solid(True, (5.5, 0.7, 0.5), (0.25, 0.8, 99.0))),
              ("いま: 山は腕の先の 0.8 だけ・腕 6.3", C.cover_solid()))
    fig, axs = plt.subplots(2, 1, figsize=(17, 9))
    for ax, (name, cover) in zip(axs, shapes):
        sp = C.cover_spring(frame, cover)
        _draw(ax, [(COL["frame2"], frame), (COL["cover"], cover)], lambda q: F.xz(q, y), lim,
              f"{name} → 効く長さ {sp['lever']:.2f}・ひずみ {sp['strain'] * 100:.2f} %（許容 {S.PLA_STRAIN_LIMIT * 100:.1f} %）・"
              f"腕 1 本の力 {sp['force']:.2f} N・引き抜く力 約 {sp['hold']:.1f} N")
        for side, a in sp["arms"].items():
            xc = a["contact"][1] if side == "left" else a["contact"][0]
            root = xc + a["lever"] * (1 if side == "left" else -1)
            zt = cv["z_slot"] - S.COVER_CLEAR
            ax.plot([xc, xc], [zt - a["t"] - 0.35, zt + 0.45], "-", color="#d00000", lw=0.9)
            ax.plot([root, root], [zt - a["t"] - 0.35, zt + 0.45], "-", color="#0040c0", lw=0.9)
            ax.annotate("", (xc, zt - a["t"] - 0.25), (root, zt - a["t"] - 0.25), arrowprops=dict(arrowstyle="<->", color="#222", lw=0.8))
            ax.text((xc + root) / 2, zt - a["t"] - 0.42, f"効く長さ {a['lever']:.2f}", ha="center", va="top", fontsize=9)
        ax.text(lim[0] + 0.1, lim[3] - 0.1, "赤 = 壁の下面が最後まで当たる所（山の、付け根の側の端）・青 = 腕の付け根。山が溝に入った位置（y は山の頂）",
                fontsize=8, va="top")
    fig.suptitle("電池の蓋の腕（ばね）を手前から見た断面（作った立体を切った物。灰 = 枠・橙 = 蓋）", fontsize=12)
    fig.tight_layout()
    p = out / "cover_spring.png"
    fig.savefig(p, dpi=90)
    plt.close(fig)
    return p


def render_all(out):
    return [sections(out), top(out), tilt(out), screw_coupon(out), corner(out), corner_coupon(out), cover_spring(out)]
