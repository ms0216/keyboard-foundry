"""蓋の別案 S（横ずらしで掛ける蓋）の絵（build/cckb-click/）。**作った立体そのものを切って描く**（寸法から描き直さない）。数は click_cover_slide の
numbers()・stresses()・wiggle()。

  cover_slide.png               しくみ（上から・断面・手前から）・閉め方／開け方・1 回の擦りで開かない理由・見える隙間・数
  coupon_cover_slide_howto.png  刷り上がった板・蓋の見分け方・組み方・手で見る所・教えてほしいこと

    .venv/bin/python3 projects/cckb-click/click_cover_slide.py   が呼ぶ
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import Pos  # noqa: E402

import click_case as C  # noqa: E402
import click_case_figs as CF  # noqa: E402
import click_cover_slide as K  # noqa: E402
import click_figs as F  # noqa: E402

LAY, S = C.LAY, C.S
COL = CF.COL
RED, BLUE, LEAF = "#c00000", "#1f5fbf", "#3f8fd8"


def _note(ax, text, size=10.5):
    ax.axis("off")
    ax.text(0.0, 1.0, text, fontsize=size, va="top", ha="left", linespacing=1.55, transform=ax.transAxes)


def _plain(ax):
    ax.set_xticks([])
    ax.set_yticks([])


def scene(variant=2, dx=0.0, dz=0.0, leaf=0.0, cover=True, clip=True):
    """組んだ試し刷り [(色, 立体)]。dx・dz = 蓋を掛けた位置から動かす量・leaf = 板ばねの先を奥へ押した量。"""
    cc = C.corner_coupon()
    out = [(COL["pcb"], cc["base"]), (COL["frame"], K.frame_body(True)), (LEAF, K.leaf(leaf)), (COL["bat"], cc["cell"])]
    if clip:
        out.append((COL["clip"], C.clip_solid()))
    if cover:
        out.append((COL["cover"], K.posed(K.cover(variant, True), dx=dx, dz=dz)))
    return out


def _draw(ax, sc, cut, lim, title, size=10.5):
    for color, part in sc:
        try:
            F.fill(ax, cut(part), color, lw=0.5)
        except Exception:                                    # 切る面がその立体を通らない
            pass
    ax.set_xlim(lim[0], lim[1])
    ax.set_ylim(lim[2], lim[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=size)
    ax.tick_params(labelsize=7)


def _arrow(ax, tip, tail, text, color=RED, size=9.5, **kw):
    ax.annotate(text, tip, tail, fontsize=size, color=color, arrowprops=dict(arrowstyle="->", color=color, lw=1.1),
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.0) if text else None, **kw)


def cover_slide(out, num=None, rise=None):
    num = num or K.numbers()
    st = K.stresses()
    ln = num["leaf"]
    if rise is None:
        rise = K.wiggle(K.cover(3, False, max(K.VARIANTS.values()) + K.PRINT_ERR), K.obstacles(0.0))[0]
    top = (107.0, 145.0, K.Y0 - 1.6, K.YC + 2.6)
    fig = plt.figure(figsize=(21, 15.5))
    gs = fig.add_gridspec(4, 6, height_ratios=[0.5, 0.5, 0.8, 1.05], hspace=0.22, wspace=0.16, left=0.03, right=0.99, top=0.95, bottom=0.005)

    # --- 上から 3 枚
    ax = fig.add_subplot(gs[0, :3])
    _draw(ax, scene(dx=K.SLIDE, leaf=ln["insert"] - K.CL), lambda p: F.xy(p, 4.6), top,
          f"① 蓋を、掛ける位置より {K.SLIDE} 右で上から落とした所（上面の少し下 z 4.6 で切った図。下が手前）")
    _arrow(ax, (K.XTIP + 0.4, K.LEAF_Y[0] + 0.6), (118.0, K.YC + 1.3), "蓋の右端の「当て」が、枠の板ばね（青）の先の鼻を奥へ押しのけている", va="center")
    _arrow(ax, (118.0, K.YF + 1.0), (124.0, K.YF + 1.0), "", size=1)
    ax.text(121.0, K.YF + 1.5, f"左へ {K.SLIDE} ずらす", fontsize=11, color=RED, ha="center")
    ax = fig.add_subplot(gs[0, 3:])
    _draw(ax, scene(), lambda p: F.xy(p, 4.6), top, "② 左へ寄せ切った所 = 掛けた位置（板ばねが戻って、当ての端の後ろに鼻が入る = カチッ）")
    _arrow(ax, (K.XTIP + 0.3, (K.NOSE_Y + K.LEAF_Y[0]) / 2), (119.0, K.YC + 1.9), "鼻が当ての端面と直角に突き合う → 蓋は右へ戻れない", va="center")
    _arrow(ax, ((K.XR + K.A1) / 2, K.Y0 + 0.5), (108.0, K.Y0 - 1.1), f"見える隙間 1: 手前の面の右に 幅 {num['recess'][0]:.2f}・奥行き {num['recess'][1]:.2f} のくぼみ（奥は耳の面）", va="center")
    _arrow(ax, (K.XTIP + K.NOSE[0] + 1.3, (K.TRENCH[0] + K.LEAF_Y[0]) / 2), (136.0, K.Y0 - 1.1), "爪を入れる溝（幅 1.0）", va="center")
    _arrow(ax, (K.HEAD[0] - 0.9, (K.YH + K.YC) / 2), (124.0, K.YC + 0.9), "見える隙間 2: 上面の穴", va="center")
    _arrow(ax, (K.XLANE + 2.0, K.LEAF_Y[1] + 0.4), (134.0, K.YC + 0.9), "見える隙間 3: 板ばねのまわりの溝", va="center")

    ax = fig.add_subplot(gs[1, :3])
    _draw(ax, scene(), lambda p: F.xy(p, 2.0), top, "③ 掛けた位置を、基板の上 2.0 で切った図: 左右の耳が、口の縁（枠の手前の壁）の裏に掛かっている")
    _arrow(ax, ((K.XLE + K.A0) / 2, K.YLL + 0.3), (107.3, K.Y0 - 1.1), f"左の耳: 縁の裏に {num['engage']['lip_left']:.1f}", va="center")
    _arrow(ax, ((K.A1 + K.XRE) / 2, K.YLR + 0.4), (133.0, K.Y0 - 1.1), f"右の耳: 縁の裏に {num['engage']['lip_right']:.1f}", va="center")
    _arrow(ax, (122.0, LAY.cell()[0][1] - LAY.cell()[1] - 0.1), (116.5, K.Y0 - 1.1), "電池は、蓋の真ん中に当たる（隙 0.2）", va="center")
    ax.annotate("", (122.0, K.YF + 0.2), (122.0, LAY.cell()[0][1] - 5.0), arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=2.0))
    ax = fig.add_subplot(gs[1, 3:])
    _draw(ax, scene(), lambda p: F.xz(p, K.YF + 0.4), (107.0, 145.0, -2.0, 6.2), "④ 手前から見た所（蓋の手前の面のすぐ奥で切った図）")
    _arrow(ax, ((K.XR + K.A1) / 2, 2.5), (K.A1 + 2.0, 5.6), f"くぼみ 幅 {num['recess'][0]:.2f}（上から下まで）", va="center")
    ax.text((K.XL + K.XR) / 2, 2.4, "蓋（切れ目なし）", fontsize=10, ha="center")

    # --- 断面 3 枚 ＋ 留めの拡大 2 枚
    win = (K.Y0 - 0.8, K.YC + 2.6, -2.0, 6.0)
    for i, (x, title) in enumerate((((K.XLE + K.P0) / 2, "⑤ 左の出っ張りの所（縦に切った図。左が手前）"),
                                    (122.0, "⑥ 電池の真ん中"), ((K.HEAD[0] + K.HEAD[1]) / 2 - 0.2, "⑦ 右の出っ張りの所"))):
        ax = fig.add_subplot(gs[2, i])
        _draw(ax, scene(), lambda p, x=x: CF.yz(p, x), win if i != 1 else (K.Y0 - 0.8, K.YC + 6.0, -2.0, 6.0), title, 10)
        if i == 0:
            _arrow(ax, ((K.YH + K.YT) / 2, K.roof_z((K.YH + K.YT) / 2) - 0.05), (K.Y0 - 0.6, -1.3), "45° の斜面（枠の屋根の下に、蓋の出っ張り）", size=8.5, va="center")
            ax.text(K.Y0 + 0.1, 5.3, "縁", fontsize=8.5)
    ax = fig.add_subplot(gs[2, 3])
    zoom = (K.A1 - 0.5, K.XLANE + 1.0, K.TRENCH[0] - 0.9, K.TRENCH[1] + 0.5)
    _draw(ax, scene(), lambda p: F.xy(p, 4.3), zoom, "⑧ 留めの所を上から（z 4.3）: 掛けた位置", 10)
    ax.text(K.XTIP + K.NOSE[0] + 0.3, (K.TRENCH[0] + K.LEAF_Y[0]) / 2, "← ここに爪の先", fontsize=9, color=RED, va="center")
    ax = fig.add_subplot(gs[2, 4])
    _draw(ax, scene(dx=0.8, leaf=ln["release"]), lambda p: F.xy(p, 4.3), zoom, f"⑨ 板ばねを奥へ {ln['release']:.2f} 押して、蓋を右へ 0.8", 10)
    ax = fig.add_subplot(gs[2, 5])
    _draw(ax, scene(), lambda p: F.xz(p, (K.RIB_Y[0] + K.RIB_Y[1]) / 2), (K.A1 - 0.5, K.XLANE + 1.0, -2.0, 6.0), "⑩ 当てと鼻を通る面で、手前から", 10)
    _arrow(ax, (K.XTIP + 3.0, K.TRENCH_Z - 0.1), (K.A1 - 0.3, -1.3), f"板ばねの溝の底（刷るとき橋）。ねじ H15 の下穴の上 {num['h15_cap']:.1f}", size=8.5, va="center")

    # --- 文
    fits = num["fits"]
    _note(fig.add_subplot(gs[3, :2]),
          "閉め方（道具なし）\n"
          f"1. 蓋を、右へ {K.SLIDE} 寄せた位置で、上からまっすぐ押し下げる\n"
          "   （当ての下の縁が、板ばねの鼻を奥へ押しのける）\n"
          "2. 上面が枠と揃ったら、蓋を左へ寄せ切る。最後の 0.9 で少し固くなる\n"
          "   （つぶれる筋に乗る）。寄せ切ると、板ばねがカチッと戻る\n\n"
          "開け方（3 つの別の向き）\n"
          "1. 右の溝に爪の先を入れ、板ばねを**奥へ**押す\n"
          f"   （{ln['release_seated']:.2f}〜{ln['release']:.2f} mm・{ln['force_release_seated']:.1f}〜{ln['force_release']:.1f} N）\n"
          "2. 押したまま、もう 1 本の指で、蓋を**右へ**ずらす\n"
          "   （爪の方へ。0.3 動けば、爪を離してよい）\n"
          f"3. 右へ {K.SLIDE} 寄せ切ってから、蓋を**上へ**つまみ上げる\n\n"
          "電池の替え方: 蓋を外す → 電池の上面を爪で押し下げながら\n"
          "手前へ引き出す → 新しい電池を奥の止めまで押し込む → 蓋", size=11)
    _note(fig.add_subplot(gs[3, 2:4]),
          "なぜ、ひとりでに開かないか（形で決まること）\n"
          "・上へ: 蓋の出っ張りが、枠の屋根と出っ張りの下にいる（樹脂の塊。\n"
          f"  ばねを通らない）。掛かりは左右とも {num['engage']['left']:.2f}。蓋をどう動かしても、\n"
          f"  四隅は {rise:.2f} より上がらない（筋なし・いちばん緩い蓋で探した）\n"
          "・板ばねを押しただけ・板ばねが折れただけでは、開かない:\n"
          "  蓋を右へ 1.45 ずらすまで、上へ抜けない\n"
          "・蓋を右へ押しただけでは、動かない: 0.25 で板ばねの鼻に当たる\n"
          "・1 回の擦りで開かない理由: 板ばねを押せる所は、蓋の右の外の\n"
          "  溝の中（幅 1.0）。そこの物が蓋を押せる向きは**左（閉まる向き）**だけ。\n"
          "  開くには、溝の中で奥へ押す物と、蓋を右へ動かす物が、別に要る\n"
          "・電池の力（手前向き）は、蓋を開ける向き（右・上）に働かない\n\n"
          "形では決まらないこと（刷って見る）\n"
          f"・板ばねを押す力は小さい（{ln['force_release']:.1f} N）。細い物が溝に入り、同時に\n"
          "  別の物が蓋を右へ擦れば、開く\n"
          "・つぶれる筋の固さ・板ばねが溝の底（橋）に付かずに刷れるか", size=11)
    _note(fig.add_subplot(gs[3, 4:]),
          "数（立体から測った物と、TDS の値での計算。刷った物の値ではない）\n"
          f"・電池が 1500 G で押す力 {num['cell_force']:.1f} N を、蓋の真ん中で受ける\n"
          f"  蓋の胴: 引っ張り {st['body']['tension']:.1f} MPa（強さ {S.PLA_TENSILE:.0f} の 1/{S.PLA_TENSILE / st['body']['tension']:.1f}）・\n"
          f"  圧縮 {st['body']['compression']:.1f} MPa（{S.PLA_BEND:.0f} の 1/{S.PLA_BEND / st['body']['compression']:.1f}）= **本番の蓋より悪い**\n"
          f"  耳の首 {st['neck_right_root']['stress']:.1f}・枠の縁 {st['lip_right']['stress']:.1f} MPa\n"
          f"・板ばね: 厚さ 1.0 × 高さ {K.TOP - K.LEAF_Z:.1f} × 長さ {K.LEAF_L}。重なり {ln['overlap_seated']:.2f}〜{ln['overlap']:.2f}\n"
          f"  ひずみ {ln['strain_release']:.2f} %（上限 {ln['strain_use']:.2f} %）・止めで {ln['strain_stop']:.2f} %\n"
          f"  落下 1500 G で先が揺れる量 {ln['drop']:.2f}（重なりの 1/{ln['overlap_seated'] / ln['drop']:.0f}）\n"
          f"  蓋が右へ押す力 {num['cover_force']:.1f} N に対し、座屈 {ln['buckle_free']:.1f} N（先が自由と見て）\n"
          "・がた取り（筋のしめしろ。蓋が座ったとき）:\n"
          + "".join(f"  蓋 {n}: 名目 {fits[n]['interference']:+.2f}（刷りの誤差で {fits[n]['loose']:+.2f}〜{fits[n]['tight']:+.2f}）\n" for n in sorted(fits))
          + f"・右の空洞から、ねじ H15 の下穴まで {num['h15_wall']:.2f}\n\n"
          "見える隙間（正直に）: 手前の面の右のくぼみ（1）・上面の右に、\n"
          f"穴 {num['slot_top'][0][0]:.2f} × {num['slot_top'][0][1]:.2f} と {num['slot_top'][1][0]:.2f} × {num['slot_top'][1][1]:.2f}（2）・板ばねのまわりの溝\n"
          f"幅 {K.TRENCH[1] - K.LEAF_Y[0] + K.LEAF_SLIT:.1f}〜{K.TRENCH[1] - K.TRENCH[0]:.1f} × 長さ {K.XTIP + K.LEAF_L - K.CAV[1]:.1f}（3。爪の溝を含む）", size=11)
    fig.suptitle("電池の蓋の別案 S（横ずらしで掛ける蓋）: 上から落とす → 左へずらす → 枠の板ばねがカチッ　　橙 = 蓋・灰 = 枠・青 = 枠の板ばね・"
                 "紫 = クリップ・緑 = 基板の代わり　　**試し刷りの候補。本番の蓋は変えていない**", fontsize=13)
    p = out / "cover_slide.png"
    fig.savefig(p, dpi=92)
    plt.close(fig)
    return p


def howto(out, num=None):
    num = num or K.numbers()
    ln = num["leaf"]
    fig = plt.figure(figsize=(17, 14.6))
    gs = fig.add_gridspec(3, 6, height_ratios=[1.0, 0.42, 1.5], hspace=0.12, wspace=0.08, left=0.02, right=0.985, top=0.945, bottom=0.005)
    ax = fig.add_subplot(gs[0, :3])
    label = {"cell": "電池の代わり", "base": "当て板（基板の代わり）", "frame": "枠の切れ端（S の口）", "cover1": "蓋 1", "cover2": "蓋 2", "cover3": "蓋 3"}
    for name, part, _ in K.plate_layout():
        bb = part.bounding_box()
        F.fill(ax, F.xy(part, min(0.5, bb.max.Z / 2)), COL["cover"] if name.startswith("cover") else "#d8d8d8", lw=0.5)
        small = bb.size.Y < 9.0
        ax.text((bb.min.X + bb.max.X) / 2, bb.min.Y - 2.6 if small else (bb.min.Y + bb.max.Y) / 2, label[name], fontsize=9.5, ha="center", va="center",
                color=RED, bbox=dict(fc="white", ec=RED, lw=0.6, pad=1.5))
    pb = K.plate().bounding_box()
    ax.set_xlim(pb.min.X - 8, pb.max.X + 8)
    ax.set_ylim(pb.min.Y - 6.5, pb.max.Y + 3)
    ax.set_aspect("equal")
    ax.set_title("0. 刷り上がった板を上から（6 個・サポート無し・向きはそのまま）。蓋も枠も、上面を下にして刷る", fontsize=11)
    _plain(ax)
    ax = fig.add_subplot(gs[0, 3:])
    for i, n in enumerate(sorted(K.VARIANTS)):
        part = Pos(0, 5.6 * (i - 1), 0) * K.cover(n, True)
        F.fill(ax, F.xy(part, 4.65), COL["cover"], lw=0.6)
        y = (K.YF + K.YT) / 2 + 5.6 * (i - 1)
        ax.text(K.XLE - 1.0, y, f"蓋 {n}", fontsize=11, ha="right", va="center", color=RED)
        f = num["fits"][n]
        ax.text(K.XRE + K.SLIDE + 1.0, y, f"切り欠き {n} 個: 斜面の隙 {f['gap']:.2f}\n（筋のしめしろ {f['interference']:+.2f}）", fontsize=9.5, ha="left", va="center")
    ax.set_xlim(K.XLE - 6, K.XRE + 22)
    ax.set_ylim(K.YF - 7.5, K.YT + 7.5)
    ax.set_aspect("equal")
    ax.set_title("蓋の見分け方（上から見た所。上の板の奥の縁の、右寄りの切り欠きの数）。1 = きつい・3 = 緩い", fontsize=11)
    _plain(ax)
    lim = (106.0, 146.5, K.Y0 - 3.0, K.YC + 5.0)
    ax = fig.add_subplot(gs[1, :2])
    _draw(ax, scene(cover=False, clip=False), lambda p: F.xy(p, 4.6), lim, "① 当て板に電池の代わりを置き、枠をかぶせた所（蓋なし）")
    _arrow(ax, (K.XTIP + 2.5, (K.LEAF_Y[0] + K.LEAF_Y[1]) / 2), (108.0, K.YC + 3.0), "枠の板ばね（青）。まず爪で奥へ押して、動くか・戻るかを見る", va="center")
    _plain(ax)
    ax = fig.add_subplot(gs[1, 2:4])
    _draw(ax, scene(dx=K.SLIDE, leaf=ln["insert"] - K.CL, clip=False), lambda p: F.xy(p, 4.6), lim, f"② 蓋を、右へ {K.SLIDE} 寄せた位置で上から押し下げた所")
    ax.annotate("", (114.0, K.Y0 - 1.5), (121.0, K.Y0 - 1.5), arrowprops=dict(arrowstyle="->", color=RED, lw=2.0))
    ax.text(122.0, K.Y0 - 1.5, "次に、左へ寄せ切る", fontsize=9.5, color=RED, ha="left", va="center")
    _plain(ax)
    ax = fig.add_subplot(gs[1, 4:])
    _draw(ax, scene(clip=False), lambda p: F.xy(p, 4.6), lim, "③ 掛けた所（カチッ）。蓋の上面が枠と揃う")
    _arrow(ax, (K.XTIP + K.NOSE[0] + 1.0, (K.TRENCH[0] + K.LEAF_Y[0]) / 2), (118.0, K.Y0 - 1.6), "開けるとき: この溝に爪の先", va="center")
    _plain(ax)
    _note(fig.add_subplot(gs[2, :3]),
          "組み方\n"
          "0. **刷り上がったら、まず枠の板ばねを見る**: 爪の先で、先（左の端）を奥へ押す。\n"
          "   0.8 ほど動いて、離すと戻るか。動かない = 溝の底に付いている（教えてください）\n"
          "1. 当て板を、平らな面を下にして置く\n"
          "2. 電池の代わり（丸い板）を、当て板の真ん中の止めに当てて置く\n"
          "3. 枠の切れ端を、平らな面（刷ったときの下の面）を上にしてかぶせる。\n"
          "   左と奥の当てに突き当てる\n"
          "4. 裏返して、角の近くの穴 1 つに M2×4 を締める（枠が当て板に留まる）\n"
          "   ※ 電池の左右の穴 2 つは使わない\n"
          f"5. 表に返す。蓋を、切り欠きのある縁を奥・細い板（当て）の出た側を右にして、\n"
          f"   **右へ {K.SLIDE} 寄せた位置**で、上からまっすぐ押し下げる（図 ②）\n"
          "6. 上面が枠と揃ったら、左へ寄せ切る。カチッと鳴って、右へ戻らなければ掛かった\n"
          "7. 蓋 3 → 2 → 1 の順に試す（3 = 緩い・1 = きつい）。\n"
          "   **いちばんきつくて、手で左へ寄せ切れる物**が、その刷りに合う蓋\n\n"
          "開け方\n"
          "1. 右の溝に爪の先を入れて、青い板ばねを奥へ押す\n"
          "2. 押したまま、もう 1 本の指で蓋を右へずらす（0.3 動いたら、爪は離してよい）\n"
          "3. 右へ寄せ切ってから、上へつまみ上げる\n\n"
          "いまの蓋（落とし込み式）の試し刷り coupon_corner_plate と、並べて比べてください。\n"
          "当て板と電池の代わりは同じ物なので、枠と蓋だけ取り替えても試せます", size=10.3)
    _note(fig.add_subplot(gs[2, 3:]),
          "手で見る所（蓋 1・2・3 のそれぞれで。結果を教えてください）\n"
          "a. 落として、左へ寄せ切れるか・カチッと鳴るか・固すぎないか\n"
          "b. がたつかないか（上下・前後・左右に揺する）。上面と手前の面が、枠と段なく揃うか\n"
          "c. 【電池を押す】裏返して、当て板の長い穴から、つまようじを電池の代わりの穴に\n"
          "   差し、手前（蓋の方）へ強く押す。蓋が動かないか・白くならないか\n"
          "d. 【振る】全体を上下・前後・左右に強く 10 回ずつ。裏返して同じ\n"
          "e. 【落とす】机の高さ（70 cm）から、板の間か硬い床へ、向きを変えて 5 回。\n"
          "   蓋は付いたままか・右へずれていないか（布団の上では試しにならない）\n"
          "f. 【擦る】ペンの先か、USB の端子の角で、手前の面と上面を、上下・左右・斜めの\n"
          "   どの向きにも強く擦る。右の溝の中もなぞる。蓋が動かないか・開かないか\n"
          "g. 【板ばねだけ押す】溝に爪を入れて板ばねを奥へ押し切り、蓋には触れない。\n"
          "   その状態で、蓋を上へこじる（左の端・右の端・真ん中）。抜けないか\n"
          "h. 【押さずにずらす】板ばねに触れずに、蓋を右へ強く押す。動かないか\n"
          "   （0.25 のがたの先で止まるはず）\n"
          "i. 【上へこじる】掛けたまま、上の縁を爪で上へこじる。どこまで浮くか（mm）\n"
          "j. 開け閉めを 20 回。板ばねが白くならないか・戻りが悪くならないか・\n"
          "   つぶれる筋が削れて、がたが出てこないか\n"
          "k. 蓋を外して、電池の代わりが爪で出し入れできるか\n"
          "l. 見た目: 手前の面の右のくぼみ（幅 1.75）と、上面の右の穴・溝は、許せるか\n\n"
          "教えてほしいこと\n"
          "・3 つのうち、どれがよいか（または全部だめか）と、a〜l でだめだった項目\n"
          "・外れた・ずれた・浮いた場合は、どの動きでか\n"
          "・いまの蓋（落とし込み式）と比べて、どちらが「しっかり・わざとだけ」に近いか", size=10.3)
    fig.suptitle("蓋の別案 S の試し刷り（coupon_cover_slide_plate_n04.gcode.3mf・A1 mini・0.4 ノズル・サポート無し）の組み方と見る所　　"
                 "緑 = 当て板・橙 = 蓋・青 = 枠の板ばね", fontsize=13)
    p = out / "coupon_cover_slide_howto.png"
    fig.savefig(p, dpi=96)
    plt.close(fig)
    return p


def render_all(out):
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    num = K.numbers()
    return [cover_slide(out, num), howto(out, num)]
