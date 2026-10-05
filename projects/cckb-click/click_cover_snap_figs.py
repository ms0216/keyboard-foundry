"""蓋の別案 B（左右のばねの腕で掛ける蓋）の絵（build/cckb-click/）。**作った立体そのものを切って描く**（寸法から描き直さない）。数は click_cover_snap の
numbers()・arm_numbers()・stresses()。

  cover_snap.png               しくみ（上から切った図・手前から・横から）・閉め方／開け方・何が電池を止めるか・弱い所・数
  coupon_cover_snap_howto.png  刷り上がった板・蓋の見分け方・組み方・手で見る所・教えてほしいこと

    .venv/bin/python3 projects/cckb-click/click_cover_snap.py   が呼ぶ
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import Plane  # noqa: E402

import click_case as C  # noqa: E402
import click_case_figs as CF  # noqa: E402
import click_cover_snap as B  # noqa: E402
import click_figs as F  # noqa: E402

LAY, S = C.LAY, C.S
COL = CF.COL
RED, BLUE = "#c00000", "#1f5fbf"


def _note(ax, text, size=10.5):
    ax.axis("off")
    ax.text(0.0, 1.0, text, fontsize=size, va="top", ha="left", linespacing=1.55, transform=ax.transAxes)


def scene(variant=B.MAIN, dl=None, dr=None, dy=0.0, cover=True, clip=True):
    """組んだ試し刷り [(色, 立体)]。dl・dr = 腕の先を内へ動かした量（既定 = 掛けた形）・dy = 蓋を奥へ動かした量（手前へ抜くと負）。"""
    out = [(COL["pcb"], B.base()), (COL["frame"], B.frame()), (COL["bat"], B.cell())]
    if clip:
        out.append((COL["clip"], C.clip_solid()))
    if cover:
        out.append((COL["cover"], B.posed(B.cover(variant, True, dl, dr), dy=dy)))
    return out


def yz(part, x):
    return F.section(part, Plane.YZ.offset(x), "Y", "Z")


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


def cover_snap(out, num=None, moves=None):
    """moves = 検査と同じ探し方で測った数 dict(forward, up, side, one_arm, cell)。渡さなければ、その行は「検査を見る」と書く。"""
    num = num or B.numbers()
    arm = num["arms"][B.MAIN]
    rel = arm["release"]
    full = (99.5, 146.5, -51.6, -34.4)
    fig = plt.figure(figsize=(23, 17.5))
    gs = fig.add_gridspec(4, 6, height_ratios=[0.8, 0.8, 0.9, 1.35], hspace=0.22, wspace=0.25, top=0.95, bottom=0.02)
    fig.suptitle("電池の蓋の別案 B（左右のばねの腕で掛ける蓋）: 手前からまっすぐ押し込む → 左右がカチッ。外すときは、左右のつまみを爪でつまんで引く"
                 "        橙 = 蓋・灰 = 枠・紫 = クリップ・緑 = 基板の代わり        **試し刷りの候補。本番の蓋・枠・基板は変えていない**",
                 fontsize=13, y=0.985)

    ax = fig.add_subplot(gs[0, :3])
    _draw(ax, scene(), lambda p: F.xy(p, 1.5), full, "① 掛けた所（基板の上 1.5 で切った図。下が手前）")
    _arrow(ax, (B.XLIP - 0.5, B.YS + 0.3), (100.3, -42.0), f"かぎ（出 {arm['hook']:.2f}）が\n口の縁の裏に掛かる")
    _arrow(ax, (B.XLIP + 0.5, -43.0), (101.0, -38.5), "ばねの腕（奥で付いて、\n手前へ戻る）")
    _arrow(ax, (B.XLIP + 0.5, B.YF + 0.4), (108.5, -51.35), "つまみ（腕の先）", va="center")
    _arrow(ax, (B.CX - 4.1, B.YB - 0.1), (114.0, -44.6), "電池は、くぼみの\n左右の角で当たる（隙 0.2）")
    _arrow(ax, (B.H15_NEW[0], B.H15_NEW[1]), (139.0, -44.0), "ねじ H15 を\nここへ動かす（提案）", color=BLUE)
    _arrow(ax, (B.mx(B.XRO) + 0.7, B.YJ + 0.5), (139.6, -36.2), "案内と奥の壁（枠）", va="center")
    ax = fig.add_subplot(gs[0, 3:])
    _draw(ax, scene(dl=rel, dr=rel, dy=-4.0), lambda p: F.xy(p, 1.5), full, "② 左右のつまみを内へつまんで（かぎが縁から外れる）、手前へ 4 引いた所")
    _arrow(ax, (B.XLIP + 1.6, B.YF - 3.6), (B.XLIP - 5.5, B.YF - 0.6), "つまむ", va="center")
    _arrow(ax, (B.mx(B.XLIP) - 1.6, B.YF - 3.6), (B.mx(B.XLIP) + 3.2, B.YF - 0.6), "つまむ", va="center")

    ax = fig.add_subplot(gs[1, :3])
    _draw(ax, scene(), lambda p: F.xy(p, 4.6), full, "③ 上から見える物（上面のすぐ下 4.6 で切った図）: 蓋の真ん中だけ。腕は枠の下に隠れる")
    ax = fig.add_subplot(gs[1, 3:])
    _draw(ax, scene(clip=False), lambda p: F.xz(p, B.YF + 0.35), (99.5, 146.5, -2.0, 6.0), "④ 手前から見た所（蓋の手前の面のすぐ奥で切った図）")
    _arrow(ax, (B.XLIP + arm["t"] + arm["front_gap"] / 2, 1.5), (104.0, -1.5), f"見える隙間: 幅 {arm['front_gap']:.1f} × 高さ {B.ZW:.0f}（左右）", va="center")
    _arrow(ax, ((B.XLIP + B.A0) / 2, 4.0), (101.0, 5.6), "枠の手前の壁は、上の 2.0 が残る", va="center")

    zoom = (103.5, 114.5, -51.3, -44.2)
    ax = fig.add_subplot(gs[2, 0:2])
    _draw(ax, scene(), lambda p: F.xy(p, 1.5), zoom, "⑤ 左のかぎ（掛けた所）")
    _arrow(ax, (B.XLIP - arm["hook"] / 2, B.YL - 0.05), (104.0, -44.9), "電池が蓋を手前へ押すと、\nここで止まる（直角の面）")
    _arrow(ax, (B.XLIP - 0.35, B.Y0 + 0.45), (104.0, -51.05), "爪の入る所", va="center")
    ax = fig.add_subplot(gs[2, 2:4])
    _draw(ax, scene(dl=rel, dr=rel), lambda p: F.xy(p, 1.5), zoom, f"⑥ つまんだ所（先を {rel - arm['pre']:.1f} 内へ）")
    _arrow(ax, (B.XLIP + 0.3, B.YL + 0.3), (104.0, -45.2), "かぎが縁から外れた\n→ 手前へ引ける")
    ax = fig.add_subplot(gs[2, 4:])
    _draw(ax, scene(), lambda p: yz(p, B.CX), (-52.0, -44.5, -2.0, 6.0), "⑦ 横から（電池の真ん中で切った図。左が手前）")
    _arrow(ax, (B.YF + 0.6, 2.0), (-51.9, -1.4), "蓋の板（ここが薄い）", va="center")
    _arrow(ax, ((B.YF + B.YB) / 2, 4.2), (-47.6, 5.6), "電池の上に渡る帯", va="center")

    st20 = num["stress"][next(k for k in num["stress"] if "指" in k)]
    rows = []
    for k, v in num["stress"].items():
        rows.append(f"   {k}（{v['force']:.1f} N）: 板 {v['plate']['tension']:.0f}／{v['plate']['compression']:.0f}・柱 {v['stem']['stress']:.0f}・腕 {v['arm']['stress']:.0f}")
    mv = moves or {}
    held = (f"・掛けた蓋の動ける量（立体を動かして測った）:\n"
            f"  手前 {mv['forward']:.2f}・奥 {mv['back']:.2f}・上 {mv['up']:.2f}・左右 {mv['side']:.2f}\n"
            f"・片方のつまみだけ押しても、その側が出てくるのは {mv['one_arm']:.1f} まで（立体は固いと見て）\n"
            f"・電池の代わりは、手前へ {mv['cell']:.2f} で蓋に当たる\n") if mv else "・掛けた蓋の動ける量は、検査（tests/test_cckb_click_cover_snap.py）が立体を動かして測る\n"
    ax = fig.add_subplot(gs[3, 0:2])
    _note(ax, "閉め方（道具なし）\n"
              "1. 蓋を、上の板を上・腕を奥にして、口の手前に置く\n"
              "2. まっすぐ奥へ押し込む。かぎの斜めの面が口の縁に乗り、\n"
              "   腕が内へ逃げる。押し切ると、左右がカチッと戻る\n"
              "3. 手前の面が枠と揃う。引っ張って、抜けないことを確かめる\n\n"
              "開け方（指 2 本）\n"
              "1. 親指と人差し指の爪を、左右の口の縁の角（斜めに落として\n"
              "   ある所）から、つまみの外の面に掛ける\n"
              f"2. 内へつまむ（片側 {rel - arm['pre']:.1f} mm・約 {arm['pinch']:.1f} N = {arm['pinch'] * 102:.0f} g ずつ）\n"
              "3. つまんだまま、手前へ引き抜く\n\n"
              "電池の替え方: 蓋を外す → 電池の上面を爪で押し下げながら\n"
              "手前へ引き出す（口の真ん中は上まで開いている）→ 新しい電池を\n"
              "奥の止めまで押し込む → 蓋")
    ax = fig.add_subplot(gs[3, 2:4])
    _note(ax, "何が電池を止めるか\n"
              "・電池 → 蓋のくぼみの左右の角 → 蓋の板 → 左右の柱（引っ張り）\n"
              "  → 腕（押し縮め）→ かぎ → 口の縁の裏（枠）\n"
              "・電池が押すと、かぎは外へ開く向きに押される（外は口の縁が\n"
              "  止める）= 押されるほど掛かる。かぎの面は直角\n"
              "・上へは枠の屋根・下は基板。蓋は奥行き 14 の間、屋根の下にいる\n"
              "  ので、内へ倒れない\n"
              + held +
              "\n**A・S より弱い所（正直な所）**\n"
              "・**電池の力が、ばねの腕とかぎを通る**（A・S は通らない）\n"
              f"・左右のかぎが {num['hook_span']:.0f} mm 離れている（腕が長く要るので、\n"
              f"  クリップのランドの外を通した）。その間を、厚さ {num['pocket']['plate_t']:.2f} の板が\n"
              "  梁になって受ける = **板の曲げがいちばん苦しい**\n"
              f"・計算では、{num['force_at_strength']:.0f} N で板の手前の縁が TDS の強さに届く\n"
              "・片方ずつ 2 回に分ければ開く（片方をつまんで少し引くと、\n"
              "  その側は外れたままになる）\n"
              f"・**基板を変える**: ねじ H15 を x = {B.H15_OLD[0]:.1f} → {B.H15_NEW[0]:.1f}（+{num['h15_move']:.1f}）")
    ax = fig.add_subplot(gs[3, 4:])
    _note(ax, "数（立体から測った物と、TDS の値での計算。刷った物の値ではない）\n"
              f"・腕: 厚さ {arm['t']:.2f} × 高さ {B.HS:.1f} × 長さ {arm['length']:.1f}・かぎの出 {arm['hook']:.2f}\n"
              f"  （誤差と遊びを全部悪い側に取って {arm['engage_worst']:.2f}）\n"
              f"・外すときの付け根のひずみ {arm['strain_release']:.2f} %（上限 {arm['strain_use']:.2f} %）\n"
              f"  入れるとき {arm['strain_insert']:.2f} %・胴に当たって止まるとき {arm['strain_stop']:.2f} %\n"
              f"・掛けた後、腕が縁を押す力 {arm['hold']:.2f} N（がた取り。蓋は {num['mass']:.2f} g）\n"
              f"・落下 {S.DROP_G:.0f} G（仮定）で、かぎが自分の重さで揺れる量 {arm['drop']:.2f}\n"
              f"  （外れるのは {arm['pre'] + arm['hook']:.2f} = {arm['drop_margin']:.1f} 倍）\n"
              "・電池が押す力と応力 [MPa]（板は 手前の縁の引っ張り／奥の縁の圧縮）\n"
              + "\n".join(rows) + "\n"
              f"  強さ（TDS）: 引っ張り {S.PLA_TENSILE:.0f}・曲げ {S.PLA_BEND:.0f}。**どの力も仮定**\n"
              f"  （20 N は指で強く押す力・{S.DROP_G:.0f} G は携帯機器の規格から借りた値）\n"
              f"  電池が角でなく真ん中で当たると、20 N で {st20['plate_center_hit']['tension']:.0f}／{st20['plate_center_hit']['compression']:.0f}\n"
              f"・腕の座屈 {st20['arm']['buckle']:.0f} N（1 本）・かぎのせん断 {st20['hook']:.1f}・縁の面圧 {st20['lip']:.1f} MPa（20 N）\n"
              f"・ねじの下穴から、かぎの空洞まで {num['h14_wall']:.1f}（H14・動かした H15）")
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def howto(out, num=None):
    num = num or B.numbers()
    arm = num["arms"]
    fig = plt.figure(figsize=(22, 15))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 1.0], hspace=0.2, wspace=0.12)
    fig.suptitle("蓋の別案 B の試し刷り（coupon_cover_snap_plate_n04.gcode.3mf）: 組み方と、手で見る所", fontsize=14, y=0.995)
    ax = fig.add_subplot(gs[0, 0])
    names = {"cell": "電池の代わり", "cover1": "蓋 1", "cover2": "蓋 2", "cover3": "蓋 3", "base": "当て板（基板の代わり）", "frame": "枠の角（上面が下）"}
    cols = {"cell": COL["bat"], "base": COL["pcb"], "frame": COL["frame"]}
    for name, part, _ in B.plate_layout():
        bb = part.bounding_box()
        F.fill(ax, F.xy(part, min(0.6, bb.max.Z / 2)), cols.get(name, COL["cover"]), lw=0.5)
        ax.text((bb.min.X + bb.max.X) / 2, bb.max.Y + 0.6, names[name], fontsize=9, ha="center", va="bottom")
    pb = B.plate().bounding_box()
    ax.set_xlim(pb.min.X - 2, pb.max.X + 2)
    ax.set_ylim(pb.min.Y - 2, pb.max.Y + 4)
    ax.set_aspect("equal")
    ax.set_title("刷り上がった板（上から。下が手前）", fontsize=11)
    ax.tick_params(labelsize=7)
    ax = fig.add_subplot(gs[0, 1:])
    import click_cover_snap_figs as me

    me._draw(ax, me.scene(), lambda p: F.xy(p, 1.5), (99.5, 146.5, -51.6, -27.5), "組んだ所（基板の上 1.5 で切った図。下が手前）")
    _arrow(ax, (B.CX, B.CY - 3.0), (B.CX + 3.0, -30.0), "電池の代わりを、裏の長い穴から\n細い棒で手前へ押す", va="center")
    _arrow(ax, (B.XLIP + 0.4, B.YF + 0.3), (100.2, -51.3), "つまみ", va="center")
    _arrow(ax, (B.mx(B.XLIP) - 0.4, B.YF + 0.3), (141.5, -51.3), "つまみ", va="center")
    ax = fig.add_subplot(gs[1, 0])
    _note(ax, "蓋の見分け方（上の板の奥の縁の切り欠きの数）\n"
              + "".join(f"  蓋 {n}（切り欠き {n} つ）: 腕の厚さ {a['t']:.2f}・かぎの出 {a['hook']:.2f}・\n"
                        f"      つまむ力 約 {a['pinch']:.1f} N ずつ・ひずみ {a['strain_release']:.2f} %\n" for n, a in arm.items())
              + "  蓋 1 = やわらかい腕 / 蓋 2 = 本番の候補 / 蓋 3 = 固い腕・少し小さいかぎ\n\n"
              "組み方\n"
              "1. 蓋の腕を、爪で内へ 2 mm ほど押して、戻ることを見る\n"
              "   （胴に付いて刷れていたら、そこで教えてください）\n"
              "2. 当て板に、枠の角を載せる（左と奥の当てに寄せる。\n"
              "   M2 のねじがあれば、裏から 2 本で留められる）\n"
              "3. 電池の代わりを、口から奥の止めまで入れる\n"
              "4. 蓋を、手前からまっすぐ押し込む（左右がカチッ）\n\n"
              "**この試し刷りは、ねじ H15 を右へ 3.5 動かした基板の形**\n"
              "（いまの基板のままでは、右の腕の通り道に H15 の下穴がある）。\n"
              "当て板に、クリップの板（電池の上の金属）の代わりは無い", size=10.5)
    ax = fig.add_subplot(gs[1, 1])
    _note(ax, "手で見る所（蓋 1・2・3 のそれぞれで）\n"
              "a. 入るか・カチッと 2 回（左右）鳴るか・押し込む固さ\n"
              "b. 手前の面が枠と揃うか（出っ張らないか・引っ込みすぎないか）\n"
              "c. 蓋をつまんで揺すって、がたつくか（前後・左右・上下）\n"
              "d. **電池の代わりを、裏から棒で強く押す**: 蓋が外れないか・\n"
              "   蓋の真ん中が手前へふくらむか・白くなるか・戻るか\n"
              "   （計算では、ここがいちばん弱い）\n"
              "e. 振る（電池の代わりを入れたまま、強く）: 外れないか・音\n"
              "f. 机の高さから、硬い床へ落とす（向きを変えて 5 回）:\n"
              "   蓋・電池の代わりが飛ばないか\n"
              "g. 鞄の中のように、手前の面を布・鍵・ペンの先で擦る・押す:\n"
              "   開かないか\n"
              "h. **片方のつまみだけ**を爪で内へ押して引く: その側が\n"
              "   どこまで出るか・手を離すと戻るか・電池の代わりが出るか\n"
              "i. 両方をつまんで引く: 爪が掛かるか・力・痛くないか\n"
              "j. 20 回 開け閉めする: かぎ・腕が白くなる・ゆるくなる・折れる\n"
              "k. 蓋を外して、電池の代わりを爪で出せるか\n"
              "l. 口の縁（枠の、かぎが掛かる所）が欠けないか", size=10.5)
    ax = fig.add_subplot(gs[1, 2])
    _note(ax, "教えてほしいこと\n"
              "・a〜l で、駄目だった物と、どの蓋か\n"
              "・3 つのうち、いちばん良かった蓋\n"
              "・d で、どのくらい押したら何が起きたか（外れた・ふくらんだ・\n"
              "  白くなった・何も起きない）\n"
              "・h で、片側が出た量（目で見て）\n"
              "・見た目: 手前の面の左右の隙間が気になるか\n"
              "・A（落とし込み）・S（横ずらし）と比べて、どれが良いか\n\n"
              "この試し刷りで分からないこと\n"
              "・本物のクリップと電池での固さ（電池はクリップの舌で\n"
              "  押さえられている。代わりは、ただの円板）\n"
              "・基板のねじ H15 を動かしてよいか（基板の配線の見直しが要る）\n"
              "・長く使ったときの、腕のへたり（予圧が抜ける）", size=10.5)
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def render_all(out, moves=None):
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    num = B.numbers()
    return [cover_snap(out / "cover_snap.png", num, moves), howto(out / "coupon_cover_snap_howto.png", num)]
