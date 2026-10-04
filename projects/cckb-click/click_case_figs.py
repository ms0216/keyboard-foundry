"""cckb-click の本番の組み立ての絵。**作った立体そのものを切って描く**（寸法から描き直さない）。縦横は実寸比。

  main_sections.png   断面 6 枚: キー 2 個（置いたとき・押し切り）／外周のねじ／XIAO と USB の切り欠き／電池の口と指の切り欠き／電源スイッチのつまみ
  main_top.png        上から（枠の上面の高さで切る）と、枠の下（基板の上 1.5）で切った図。柱・壁・部品・ねじ・継ぎ目
  main_tilt.png       2.25u と 1u の縁を押し切った傾き（公差の端）と、その下の部品
  coupon_screw.png    ねじの試し刷り（本番の枠から切り出した壁と当て板）
  main_corner.png     右手前の角: つまみの切り欠き・電池の口・落とし込み式の蓋を、上から・断面で
  coupon_corner.png   角の試し刷り（枠の切れ端・当て板・つまみと電池の代わり・蓋）
  cover_latch.png     **電池の蓋（落とし込み式）の説明**: 上から・棒の高さで切った図・手前から・断面・開け方／閉め方／電池の替え方
  coupon_cover_howto.png  蓋の試し刷り（角の試し刷り・蓋 3 つ）の組み方と、手で見る所・教えてほしいこと

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
       "knob": "#111111", "clip": "#7a5cc0"}
RED = "#c00000"


def yz(part, x):
    return F.section(part, Plane.YZ.offset(x), "Y", "Z")


def _scene(stem=None, mode="rest", keys=None, cover=True):
    """[(色, 立体)]。mode = rest（ステムに載る）/ pressed / 傾き（"+x" など。keys に効く）。cover=False で電池の蓋を外す。"""
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
    _draw(axs[2][0], rest, lambda p: yz(p, cx), (-52, -26, *zl), "右の角: 電池クリップ・電池の口（手前の壁）・蓋（橙。x は電池の中心）", lv)
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
    """右手前の角: 上から（蓋あり・なし）・棒の高さで切った図・断面 3 枚（電池の中心／蓋の足／つまみ）。"""
    z = LAY.z()
    f = LAY.frame
    cv = LAY.cover()
    lv = [(0.0, "基板の上面 0"), (z["frame_under"], "枠の下面 3.0"), (z["frame_top"], "枠の上面 5.0")]
    with_c, without = _scene(), _scene(cover=False)
    clip = [(COL["clip"], C.clip_solid())]
    knobs = [(COL["knob"], C.knob_solid(1)), ("#888888", C.knob_solid(-1))]
    fig, axs = plt.subplots(2, 3, figsize=(20, 11))
    lim = (106, f[2] + 1.5, f[1] - 1.5, -29)
    _draw(axs[0][0], with_c, lambda p: F.xy(p, 4.65), lim, "上から（z 4.65）・蓋（橙）を付けた図。上面は枠と面一・左右の角に枠の歯")
    _draw(axs[0][1], without, lambda p: F.xy(p, 4.65), lim, "同じ・蓋を外した図（電池の上面が口から見える。口の左右に耳の溝）")
    za = sum(cv["band"]["A"]) / 2
    _draw(axs[0][2], with_c + knobs, lambda p: F.xy(p, za), lim, f"基板の上 {za:.1f}（下の棒の高さ）で切った図。蓋の足・耳・棒／つまみ（黒 = 入・灰 = 切）")
    for ax in axs[0]:
        ax.plot([f[2], f[2]], [lim[2], lim[3]], ":", color="#d00000", lw=0.6)
        ax.plot([lim[0], lim[1]], [f[1], f[1]], ":", color="#d00000", lw=0.6)
    zl = (-2.4, 6.0)
    _draw(axs[1][0], with_c, lambda p: yz(p, S.CLIP_AT[0]), (-52, -40, *zl), "断面（電池の中心 x）: 手前の板に棒 2 本・上の板", lv)
    xf = cv["block"][0][0] + 1.5
    _draw(axs[1][1], [s for s in with_c if s[0] != COL["bat"]] + [(COL["bat"], C.cell_solid())] + clip, lambda p: yz(p, xf),
          (-52, -40, *zl), f"断面（蓋の足 x {xf:.1f}）: 足は基板に立ち、クリップの板（紫・図面）の手前で終わる（板の下へは入れない）", lv)
    on = _scene() + [(COL["knob"], C.knob_solid(1))]
    _draw(axs[1][2], on, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_ON * S.PSW_TRAVEL / 2), (136, 148, *zl),
          f"断面（つまみが入の y）: つまみの先は枠の外面（赤の点線）の {f[2] - LAY.psw_knob(1)[2]:.2f} 内側・内側の上の縁は斜め", lv)
    axs[1][2].plot([f[2], f[2]], zl, ":", color="#d00000", lw=0.6)
    fig.suptitle("右手前の角（作った立体を切った物）: 電源スイッチのつまみの切り欠きと、電池の口・落とし込み式の蓋（橙）", fontsize=12)
    fig.tight_layout()
    p = out / "main_corner.png"
    fig.savefig(p, dpi=80)
    plt.close(fig)
    return p


def _coupon_scene(cc, n=None, lift=0.0, deflect=0.0):
    """角の試し刷りを組んだ [(色, 立体)]。n = 付ける蓋の番号（None で蓋なし）。"""
    out = [(COL["pcb"], cc["base"]), (COL["frame"], cc["frame"]), (COL["bat"], cc["cell"]), (COL["knob"], cc["knob"])]
    if n is not None:
        out.append((COL["cover"], Pos(0, 0, lift) * C.cover_solid(n, deflect, True)))
    return out


def corner_coupon(out):
    """角の試し刷り: 上から（2 つの高さ）と断面 2 枚。"""
    cc = C.corner_coupon()
    box = C.corner_coupon_box()
    cv = LAY.cover()
    scene = _coupon_scene(cc, S.COVER_MAIN)
    fig, axs = plt.subplots(2, 2, figsize=(17, 11))
    lim = (box[0] - 3, box[2] + 1.5, box[1] - 1.5, box[3] + 3)
    _draw(axs[0][0], scene, lambda p: F.xy(p, 4.65), lim, "上から（z 4.65）: 枠の切れ端（灰）・蓋（橙）")
    za = sum(cv["band"]["A"]) / 2
    _draw(axs[0][1], scene, lambda p: F.xy(p, za), lim, f"当て板の上 {za:.1f}: 蓋の足・耳・下の棒／スイッチの本体の代わり・クリップの代わり（止めと案内）・電池の代わり")
    zl = (-2.2, 5.6)
    lv = [(0.0, "当て板の上面 0（基板の上面）"), (5.0, "枠の上面 5.0")]
    _draw(axs[1][0], scene, lambda p: yz(p, cv["block"][0][0] + 1.5), (box[1] - 1, box[3] + 3, *zl), "断面（蓋の足）", lv)
    _draw(axs[1][1], scene, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_TRAVEL / 2), (box[0] - 3, box[2] + 1, *zl), "断面（つまみが入の y）", lv)
    fig.suptitle("角の試し刷り coupon_corner = 蓋の試し刷り（本番の枠から切り出した右手前の角 ＋ 当て板。緑 = 当て板と代わりの物・橙 = 蓋・黒 = つまみの小片）", fontsize=12)
    fig.tight_layout()
    p = out / "coupon_corner.png"
    fig.savefig(p, dpi=85)
    plt.close(fig)
    return p


def _plain(ax):
    ax.set_xticks([])
    ax.set_yticks([])


def _note(ax, text, size=10.5):
    ax.axis("off")
    ax.text(0.0, 1.0, text, fontsize=size, va="top", ha="left", linespacing=1.6, transform=ax.transAxes)


def _label(ax, text, at, to, color="#222"):
    ax.annotate(text, at, to, fontsize=9.5, color=color, ha="center", va="center",
                arrowprops=dict(arrowstyle="->", color=color, lw=0.9), bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.85))


def _corner_scene(frame, cover=True, lift=0.0, deflect=0.0, cell=True, clip=True):
    """右手前の角の [(色, 立体)]。lift = 蓋を上へ持ち上げた量・deflect = 棒の先を押し込んだ量。"""
    out = [(COL["sheet"], C.sheet_solid()), (COL["pcb"], C.pcb_solid()), (COL["frame"], frame)]
    if cell:
        out.append((COL["bat"], C.cell_solid()))
    if clip:
        out.append((COL["clip"], C.clip_solid()))
    if cover:
        out.append((COL["cover"], Pos(0, 0, lift) * C.cover_solid(None, deflect)))
    return out


def cover_latch(out):
    """電池の蓋の説明（利用者に見せる絵）。作った立体を切って描く。数は立体・spec から。"""
    cv = LAY.cover()
    f = LAY.frame
    frame = C.frame_halves()["right"] & C._box((104.0, f[1] - 1.0, 140.0, -30.0), -1.0, 6.0)
    (cx, cy), r = LAY.cell()
    num = C.cover_numbers()
    za, zb = sum(cv["band"]["A"]) / 2, sum(cv["band"]["B"]) / 2
    fig = plt.figure(figsize=(17, 17.5))
    gs = fig.add_gridspec(4, 6, height_ratios=[0.95, 0.95, 0.95, 1.05], hspace=0.2, wspace=0.12, left=0.02, right=0.985, top=0.95, bottom=0.01)
    full = _corner_scene(frame)
    lim = (cv["x0"] - 5.5, cv["x1"] + 5.5, f[1] - 2.4, -41.5)

    ax = fig.add_subplot(gs[0, :3])
    _draw(ax, full, lambda p: F.xy(p, 4.65), lim, "① 上から見た所（蓋を付けた所。下が手前）")
    ax.text(cx, (cv["yf"] + cv["y1"]) / 2, "蓋（上面は枠と同じ高さ）", fontsize=10.5, ha="center", va="center", color="white")
    _label(ax, "歯（枠）", (cv["x0"] + 0.5, f[1] + 0.5), (cv["x0"] - 3.2, f[1] - 1.6), RED)
    _label(ax, "歯（枠）", (cv["x1"] - 0.5, f[1] + 0.5), (cv["x1"] + 3.2, f[1] - 1.6), RED)
    _label(ax, "耳（蓋）が\n枠の溝に入っている", (cv["x0"] - 0.9, cv["y_ear"][1] - 0.5), (cv["x0"] - 3.4, -43.6), RED)
    _plain(ax)
    ax = fig.add_subplot(gs[0, 3:])
    off = _corner_scene(frame, cover=False)
    _draw(ax, off, lambda p: F.xy(p, 4.65), lim, "② 蓋を外した所（電池が見える。左右に耳の溝と、手前の角の歯）")
    ax.annotate("", (cx, f[1] - 2.0), (cx, cy - r + 1.5), arrowprops=dict(arrowstyle="->", color=RED, lw=1.8))
    ax.text(cx + 1.0, f[1] - 1.5, "電池は手前へ出す", fontsize=9.5, color=RED)
    _plain(ax)

    ax = fig.add_subplot(gs[1, :3])
    _draw(ax, full, lambda p: F.xy(p, za), lim, f"③ 基板の上 {za:.1f} で切った図（下の棒の高さ）")
    _label(ax, "下の棒（左の足から右へ）\n先が右の歯の下に入る", (cx + 2.0, cv["yf"] + 0.5), (cx + 2.5, f[1] - 1.5), RED)
    _label(ax, "足（電池を止める）", (cv["block"][0][0] + 2.6, -48.0), (cv["x0"] - 1.5, f[1] - 1.7), RED)
    _label(ax, "耳の斜めの面\n（電池に押されても、ここで止まる）", (cv["x1"] + 1.0, cv["y_ear"][0] + 0.9), (cv["x1"] + 0.6, f[1] - 1.5), RED)
    ax.text(cx, -44.5, "電池", fontsize=10, ha="center", color="#444")
    _plain(ax)
    ax = fig.add_subplot(gs[1, 3:])
    pushed = _corner_scene(frame, deflect=num["release_seated"])
    _draw(ax, pushed, lambda p: F.xy(p, za), lim, f"④ 同じ高さ・棒を押し込んだ所（先が {num['release_seated']:.1f} 奥へ逃げて、歯の下から外れる）")
    ax.annotate("", (cx, cv["yf"] + 0.4), (cx, f[1] - 2.0), arrowprops=dict(arrowstyle="->", color=RED, lw=2.0))
    ax.text(cx + 0.8, f[1] - 1.7, "指で押す", fontsize=10, color=RED)
    _label(ax, "先が歯の下から\n外れた", (cv["x1"] - 0.9, cv["yf"] + 1.5), (cv["x1"] + 3.0, f[1] - 1.2), RED)
    _plain(ax)

    xl = (cv["x0"] - 5.5, cv["x1"] + 5.5, -2.6, 6.2)
    ax = fig.add_subplot(gs[2, :3])
    _draw(ax, full, lambda p: F.xz(p, cv["yf"] + 0.45), xl, "⑤ 手前から見た所（手前の面のすぐ内で切った図）")
    _label(ax, "上の棒 → 左の歯の下", (cx - 3.0, zb), (cx - 3.0, 5.75), RED)
    _label(ax, "下の棒 → 右の歯の下", (cx + 3.0, za), (cx + 3.0, -1.7), RED)
    _label(ax, "歯（枠）", (cv["x0"] + 0.5, 4.5), (cv["x0"] - 3.3, 5.7), RED)
    _label(ax, "歯（枠）", (cv["x1"] - 0.5, 3.8), (cv["x1"] + 3.3, 5.7), RED)
    _label(ax, "2 本にまたがって押す（爪の先）", (cx, (za + zb) / 2), (cx - 0.5, -2.1))
    _plain(ax)
    ax = fig.add_subplot(gs[2, 3:5])
    lifted = _corner_scene(frame, lift=2.6, deflect=num["release_seated"])
    _draw(ax, lifted, lambda p: F.xz(p, cv["yf"] + 0.45 + 0.3), (xl[0], xl[1], -2.6, 9.4), "⑥ 棒を押したまま持ち上げた所（まっすぐ上へ抜ける）")
    ax.annotate("", (cx, 9.2), (cx, 7.8), arrowprops=dict(arrowstyle="->", color=RED, lw=2.0))
    _plain(ax)
    ax = fig.add_subplot(gs[2, 5:])
    _draw(ax, full, lambda p: yz(p, cx), (-52.4, -44.5, -2.6, 6.2), "⑦ 横から（電池の真ん中）")
    _label(ax, "棒", (cv["yf"] + 0.5, zb), (-51.6, 5.6), RED)
    _plain(ax)

    beam = C.cover_beam()
    _note(fig.add_subplot(gs[3, :2]),
          "開け方（道具は要らない。爪を使う）\n"
          "1. 手前の面の、上下に並んだ 2 本の棒を、爪の先で\n"
          f"   2 本いっしょに押し込む（真ん中で {num['mid_push']:.1f} mm・約 {num['mid_force'] * 102:.0f} g の力）\n"
          "   ※ 1 本だけ押しても開かない（片側が 1 mm ほど浮くだけ）\n"
          "2. 押したまま、爪を上へずらして蓋を持ち上げる\n"
          "   → 蓋が上へ出てくる。つまんで抜く\n\n"
          "閉め方\n"
          "1. 蓋を、上の板を上・棒を手前にして、口の真上に置く\n"
          "2. まっすぐ下へ押す。上面が枠と揃うまで\n"
          "   （少し固い: 左右の耳の裏の細い筋が、がたつきを取る）\n"
          "3. パチッと 2 回（左右）。上へこじって、抜けないことを確かめる")
    _note(fig.add_subplot(gs[3, 2:4]),
          "電池の替え方\n"
          "1. 蓋を開ける（左）\n"
          "2. 電池の上面を爪で押さえながら、手前へ引き出す\n"
          "3. 新しい電池を、＋ を上にして奥まで押し込む\n"
          "4. 蓋を閉める（左）\n\n"
          "蓋は必ず付ける。\n"
          "電池を手前へ止めている物は、この蓋だけ\n"
          "（金具は電池を上から押さえているだけ）\n\n"
          "蓋は小さい（0.2 g）。予備を 1 つ一緒に刷ってある")
    _note(fig.add_subplot(gs[3, 4:]),
          "外れにくさ（正直な所）\n"
          "・電池が蓋を手前へ押す力は、左右の耳が枠の溝の斜めの面に\n"
          "  当たって止まる。ばねは使っていない\n"
          "・上へは、2 本の棒の先が枠の歯の下に当たる（直角の面）\n"
          "・開くのは「2 本とも押し込む ＋ 持ち上げる」とき。\n"
          "  ただし爪 1 つでできる = 細い物が 2 本にまたがって\n"
          "  押しながら上へ擦れば、開きうる。力も小さい\n\n"
          "数（計算と立体から。刷った物の値ではない）\n"
          f"・落下 {S.DROP_G:.0f} G で電池が押す力 {num['cell_force']:.0f} N → 蓋の胴の引っ張り {beam['tension']:.0f} MPa\n"
          f"  （強さ {S.PLA_TENSILE:.0f} の {beam['tension'] / S.PLA_TENSILE:.2f} 倍）\n"
          f"・棒の付け根のひずみ {num['mid_strain']:.1f} %（上限 {num['strain_use']:.1f} %）\n"
          f"・同じ落下で、棒が自分の重さで揺れる量 {num['drop_tip']:.2f}\n"
          f"  （外れるのは {num['release_seated'] - 0.1:.2f} から = 余裕 {(num['release_seated'] - 0.1) / num['drop_tip']:.1f} 倍）")
    fig.suptitle("電池の蓋（道具なし・上から落とし込む）　　橙 = 蓋・緑 = 基板・灰 = 枠と電池・紫 = 電池クリップ・黒 = 底のシート。基板は変えない（穴 H30・H31 は使わない）",
                 fontsize=13)
    p = out / "cover_latch.png"
    fig.savefig(p, dpi=92)
    plt.close(fig)
    return p


def coupon_cover_howto(out):
    """蓋の試し刷り（角の試し刷り）の、刷ったあとの組み方と手で見る所。"""
    cc = C.corner_coupon()
    box = C.corner_coupon_box()
    cv = LAY.cover()
    (cx, cy), r = LAY.cell()
    fig = plt.figure(figsize=(16, 16.5))
    gs = fig.add_gridspec(3, 6, height_ratios=[1.05, 1.0, 1.15], hspace=0.14, wspace=0.12, left=0.02, right=0.985, top=0.95, bottom=0.01)
    ax = fig.add_subplot(gs[0, :3])
    label = {"cell": "電池の代わり", "knob": "つまみの\n代わり", "base": "当て板（基板の代わり）", "frame": "枠の切れ端",
             "cover1": "蓋 1", "cover2": "蓋 2", "cover3": "蓋 3"}
    for name, part in C.corner_coupon_layout():
        bb = part.bounding_box()
        F.fill(ax, F.xy(part, min(0.5, bb.max.Z / 2)), COL["cover"] if name.startswith("cover") else "#d8d8d8", lw=0.5)
        small = bb.size.Y < 9.0
        ax.text((bb.min.X + bb.max.X) / 2, bb.min.Y - 2.6 if small else (bb.min.Y + bb.max.Y) / 2, label[name], fontsize=9.5, ha="center", va="center",
                color=RED, bbox=dict(fc="white", ec=RED, lw=0.6, pad=1.5))
    pb = C.corner_coupon_plate().bounding_box()
    ax.set_xlim(pb.min.X - 8, pb.max.X + 8)
    ax.set_ylim(pb.min.Y - 6.5, pb.max.Y + 3)
    ax.set_aspect("equal")
    ax.set_title("0. 刷り上がった板を上から（7 個・サポート無し・向きはそのまま）。蓋は手前の面を下にして立っている", fontsize=11)
    _plain(ax)
    ax = fig.add_subplot(gs[0, 3:])
    for i, n in enumerate(sorted(S.COVER_VARIANTS)):
        v = S.COVER_VARIANTS[n]
        part = Pos(0, 3.4 * i - 3.4, 0) * C.cover_solid(n, 0.0, True)
        F.fill(ax, F.xy(part, 4.65), COL["cover"], lw=0.6)
        ax.text(cv["x0"] - 1.0, cv["y1"] - 1.6 + 3.4 * i - 3.4, f"蓋 {n}", fontsize=11, ha="right", va="center", color=RED)
        ax.text(cv["x1"] + 1.0, cv["y1"] - 1.6 + 3.4 * i - 3.4, f"切り欠き {n} 個: 歯との隙 {v['gap']:.1f}・筋 {v['rib']:.2f}", fontsize=10, ha="left", va="center")
    ax.set_xlim(cv["x0"] - 7, cv["x1"] + 24)
    ax.set_ylim(cv["yf"] - 4.6, cv["y1"] + 4.2)
    ax.set_aspect("equal")
    ax.set_title("蓋の見分け方（上から見た所。上の板の奥の縁の、右寄りの切り欠きの数）", fontsize=11)
    _plain(ax)
    lim = (box[0] - 3, box[2] + 1.5, box[1] - 3.0, box[3] + 3)
    za = sum(cv["band"]["A"]) / 2
    ax = fig.add_subplot(gs[1, :2])
    _draw(ax, _coupon_scene(cc), lambda p: F.xy(p, 1.0), lim, "① 当て板に電池の代わりを置き、枠をかぶせた所（蓋なし）")
    _plain(ax)
    ax = fig.add_subplot(gs[1, 2:4])
    _draw(ax, _coupon_scene(cc, S.COVER_MAIN), lambda p: F.xy(p, za), lim, "② 蓋を上から落とした所（下の棒の高さで切った図）")
    ax.annotate("", (cx, cv["yf"] + 0.4), (cx, box[1] - 2.6), arrowprops=dict(arrowstyle="->", color=RED, lw=2.0))
    ax.text(cx + 1.0, box[1] - 2.3, "開けるときは、ここを押しながら上へ", fontsize=9.5, color=RED)
    _plain(ax)
    ax = fig.add_subplot(gs[1, 4:])
    _draw(ax, _coupon_scene(cc, S.COVER_MAIN), lambda p: F.xy(p, 4.65), lim, "③ 上から見た所（蓋の上面が枠と揃う）")
    _plain(ax)
    _note(fig.add_subplot(gs[2, :3]),
          "組み方\n"
          "1. 当て板を平らな面を下にして置く。つまみの代わりを溝に落とす\n"
          "2. 電池の代わり（丸い板）を、当て板の真ん中の止めに当てて置く\n"
          "3. 枠の切れ端を、平らな面（刷ったときの下の面）を上にしてかぶせる\n"
          "   左と奥の当てに突き当てる\n"
          "4. 裏返して、角の近くの穴 1 つに M2×4 を締める（枠が当て板に留まる）\n"
          "   ※ 電池の左右の穴 2 つは使わない（何も入れない）\n"
          "5. 表に返し、蓋を、上の板を上・棒を手前にして、口へまっすぐ押し下げる\n"
          "   上面が枠と揃って、パチッと 2 回（左右）鳴れば入っている\n"
          "6. 蓋 1 → 2 → 3 の順に、同じことを試す\n"
          "   （1 = 歯との隙が狭い・筋が低い／3 = 隙が広い・筋が高い）\n\n"
          "開け方: 手前の面の、上下に並んだ 2 本の棒を、爪の先で 2 本いっしょに\n"
          "        押し込み、押したまま爪を上へずらす。蓋が上へ出てきたら、つまんで抜く", size=10)
    _note(fig.add_subplot(gs[2, 3:]),
          "手で見る所（蓋 1・2・3 のそれぞれで。結果を教えてください）\n"
          "a. 押し下げるだけで入るか・左右ともパチッと留まるか・固すぎないか\n"
          "b. 入れた後、上の縁を爪で上へこじっても抜けないか（左の端・右の端・真ん中）\n"
          "c. 蓋ががたつかないか・上面と手前の面が枠と段なく揃うか\n"
          "d. 【片方だけ押す】右の端の近くで、下の棒だけを押し込み、右の端を上へこじる。\n"
          "   どこまで浮くか（mm）・指を離すと戻るか・浮いたままか。左（上の棒）でも同じ\n"
          "e. 【擦る】ペンの先か、USB の端子の角で、手前の面を下から上へ強く擦る。\n"
          "   棒の上・端の近く・真ん中。蓋が浮かないか・開かないか\n"
          "f. 【振る】全体を上下・前後・左右に強く 10 回ずつ。裏返して同じ。\n"
          "   d で片方が浮いたままになるなら、その状態からも振る\n"
          "g. 【電池を押す】裏返して、当て板の長い穴から、つまようじを電池の代わりの穴に\n"
          "   差し、手前（蓋の方）へ強く押す。蓋が動かないか。耳の付け根が白くならないか\n"
          "h. 【落とす】机の高さ（70 cm）から、板の間か机の上へ、向きを変えて 5 回。\n"
          "   蓋は付いたままか・片方が浮いていないか（布団の上では試しにならない）\n"
          "i. 開けられるか: 爪 1 つでできるか・固さ。開け閉めを 20 回して、棒が白く\n"
          "   ならないか・戻りが悪くならないか\n"
          "j. 蓋を外して、電池の代わりが爪で出し入れできるか\n\n"
          "教えてほしいこと: 3 つのうち、どれがよいか（または全部だめか）と、\n"
          "a〜j でだめだった項目。外れた・浮いた場合は、どの動きでか", size=10)
    fig.suptitle("蓋の試し刷り（coupon_corner_plate_n04.gcode.3mf・A1 mini・0.4 ノズル・サポート無し）の組み方と見る所　　緑 = 当て板・橙 = 蓋",
                 fontsize=13)
    p = out / "coupon_cover_howto.png"
    fig.savefig(p, dpi=96)
    plt.close(fig)
    return p


def render_all(out):
    for old in ("cover_spring.png", "cover_screw.png"):             # 前の蓋（ばね・ねじ）の絵。古い絵を、いまの蓋の絵と見間違えない
        (out / old).unlink(missing_ok=True)
    return [sections(out), top(out), tilt(out), screw_coupon(out), corner(out), corner_coupon(out), cover_latch(out), coupon_cover_howto(out)]
