"""蓋の別案 B5（左右のばねの腕で掛ける蓋）の絵（build/cckb-click/）。**作った立体そのものを切って描く**（寸法から描き直さない）。数は click_cover_snap の
numbers()・arm_numbers()・stresses()・measure_moves()・cell_access()。

  cover_snap.png               しくみ（上から切った図・手前から・横から）・閉め方／開け方／電池の出し方・蓋 3 つの違い・B2 から直した所・基板の提案・数
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


def scene(variant=B.MAIN, dl=None, dr=None, cover=True, clip=True, **pose):
    """組んだ試し刷り [(色, 立体)]。dl・dr = 腕の先を、座った形から内へ動かした量・pose = 蓋を動かす量（click_cover_snap.posed の引数）。"""
    out = [(COL["pcb"], B.base()), (COL["frame"], B.frame()), (COL["bat"], B.cell())]
    if clip:
        out.append((COL["clip"], B.clip()))
    if cover:
        out.append((COL["cover"], B.posed(B.cover(variant, True, dl, dr), **pose)))
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
    """moves = click_cover_snap.measure_moves()（検査と同じ探し方で測った数）。"""
    num = num or B.numbers()
    moves = moves or B.measure_moves()
    arm = num["arms"][B.MAIN]
    acc, tg, ej = num["cell_access"], num["target"], moves["eject"]
    e2 = ej[B.MAIN]
    full = (99.5, 146.5, -53.6, -29.8)
    fig = plt.figure(figsize=(23, 21))
    gs = fig.add_gridspec(4, 6, height_ratios=[1.0, 0.7, 0.95, 1.6], hspace=0.2, wspace=0.25, top=0.955, bottom=0.01)
    fig.suptitle("電池の蓋の別案 B5: 手前からまっすぐ押し込む → カチッ。外すときは、**左右のつまみを内へつまむだけ → 蓋が出てくる → 取る**"
                 "        橙 = 蓋・灰 = 枠・紫 = クリップ・緑 = 基板の代わり        **試し刷りの候補。本番の蓋・枠・基板は変えていない**",
                 fontsize=13, y=0.985)

    ax = fig.add_subplot(gs[0, :3])
    _draw(ax, scene(), lambda p: F.xy(p, 1.5), full, "① 掛けた所（基板の上 1.5 で切った図。下が手前）。クリップと電池は、いまより 2.0 奥")
    _arrow(ax, (B.XLIP - 0.5, B.YS + 0.3), (100.3, -42.5), f"かぎ（掛かり {arm['engage']:.1f}）が\n口の縁の裏に掛かる")
    _arrow(ax, (B.XN + 0.4, -41.0), (100.3, -39.0), "ばねの腕（奥で付いて、\n手前へ戻る）")
    _arrow(ax, (B.XN + 1.0, B.YF + 1.0), (108.3, -52.6), "つまみ（腕の先の塊。上面は、指で滑らせる面）", va="center")
    _arrow(ax, (B.XLIP - 1.5, B.Y0 + 0.2), (100.0, -52.6), f"指の入るくぼみ（幅 {tg['scoop'][0]:.0f}）", va="center")
    _arrow(ax, (B.CX, B.YF + 1.5), (118.5, -52.6), f"手前の板 {num['pocket']['plate_t']:.1f}", va="center")
    _arrow(ax, (B.H15_NEW[0], B.H15_NEW[1]), (139.2, -44.5), "ねじ H15 を\nここへ動かす（提案）", color=BLUE)
    _arrow(ax, (B.CX + 5.0, B.CY + 6.5), (131.0, -31.0), f"クリップと電池を 奥へ {B.DBACK:.1f}（提案）", color=BLUE, va="center")
    ax = fig.add_subplot(gs[0, 3:])
    d_end, y_end = e2["path"][-1][1], e2["rest"]
    _draw(ax, scene(dl=d_end, dr=d_end, dy=-y_end), lambda p: F.xy(p, 1.5), full,
          f"② 左右をつまんで、指を離した後（引いていない）: 蓋は {y_end:.1f} 出て止まる → 指でつまんで取る")
    ax.annotate("", (B.CX, B.YF - y_end - 1.6), (B.CX, B.YF - 0.2), arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.8))

    ax = fig.add_subplot(gs[1, :3])
    for color, part, z in [(COL["pcb"], B.base(), 1.0), (COL["bat"], B.cell(), 3.0), (COL["frame"], B.frame(), 4.0)]:
        F.fill(ax, F.xy(part, z), color, lw=0.5)
    ax.set_xlim(99.5, 146.5)
    ax.set_ylim(-51.6, -41.5)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_title("③ 蓋を外して、上から見た所（枠は 4.0・電池は 3.0 で切った図）: 口の真ん中は、手前と上へ開いた箱", fontsize=10.5)
    front = B.CY - B.CELL_R
    _arrow(ax, (B.CX, front + acc["top_nominal"] / 2), (132.5, -44.6),
           f"上から見える電池: 奥行き {acc['top_nominal']:.2f} × 幅 {acc['top'][1]:.1f}\nここを爪で下へ押しながら、手前へ引く", va="center")
    ax.annotate("", (B.CX, B.Y0 - 0.6), (B.CX, front + 0.3), arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.6))
    ax = fig.add_subplot(gs[1, 3:])
    _draw(ax, scene(clip=False), lambda p: F.xz(p, B.YF + 0.25), (99.5, 146.5, -2.0, 6.0), "④ 手前から見た所（蓋の手前の面のすぐ奥で切った図）")
    _arrow(ax, (B.XN + 1.0, 4.4), (100.2, 5.6), f"つまみ: 上面は枠の上面の 0.05 下（筋 {tg['ridges'][0]} 本）", va="center")
    _arrow(ax, (B.XN + B.TAB_W + arm["front_gap"] / 2, 1.5), (104.0, -1.5), f"見える隙間: 幅 {arm['front_gap']:.1f}（左右。上へも開いている）", va="center")

    zoom = (103.2, 113.2, -52.9, -46.4)
    shots = [("⑤ 掛けた所（上面の少し下 4.0 で切った図）", dict(), None),
             (f"⑥ 両方をつまみ切る（腕は付け根まわりに曲がり、つまみは {tg['tilt']:.0f}° 回る）→ 斜めの面が、蓋を {e2['cam']:.2f} 押し出す",
              dict(dl=B.D_MAX, dr=B.D_MAX, dy=-e2["cam"]), "cam"),
             (f"⑦ 指を離す → かぎは縁の裏へ戻れず、腕のばねが さらに押し出す → {y_end:.1f} で止まる", dict(dl=d_end, dr=d_end, dy=-y_end), "rest")]
    for k, (title, kw, tag) in enumerate(shots):
        ax = fig.add_subplot(gs[2, 2 * k:2 * k + 2])
        _draw(ax, scene(**kw), lambda p: F.xy(p, 4.0), zoom, title, size=9.5)
        if tag is None:
            _arrow(ax, (B.XN + 1.0, B.YF + 1.3), (103.4, -52.3), f"滑らせる面（幅 {tg['pad'][0]:.2f} × 奥行き {tg['pad'][1]:.1f}）\n指の腹を載せて、内へずらす", va="center")
            _arrow(ax, (B.cam_line(B.S0[1] - B.CAM_F / 2) + 0.05, B.S0[1] - B.CAM_F / 2), (108.6, -52.3), "斜めの面（1 本の線。奥に、\nまっすぐな壁は無い）", va="center")
            _arrow(ax, (B.XN + B.TAB_W - 0.05, B.YK), (104.0, -46.8), "つまみの出っ張り K", va="center")
        elif tag == "cam":
            _arrow(ax, (B.XN + 2.6, B.YF - e2["cam"] + 1.0), (103.4, -52.3), f"内へ {tg['travel']:.1f}・{arm['pinch']:.1f} N ずつ", va="center")

    st = num["stress"][True]
    sf = num["strength"]
    names = dict(plate_tension="板の引っ張り", plate_compression="板の圧縮", stem="柱", arm="腕", buckle="腕の座屈", hook="かぎのせん断", lip="縁の面圧")
    a1 = num["arms"][1]
    ax = fig.add_subplot(gs[3, 0:2])
    _note(ax, "閉め方（道具なし）\n"
              "1. 蓋を、上の板を上・腕を奥にして、口の手前に置く\n"
              f"2. まっすぐ奥へ押し込む（約 {arm['insert_force']:.0f} N）→ 左右がカチッ\n\n"
              "**開け方（どちらでも）**\n"
              "A. 指の腹を、左右のつまみの上面（筋のある面）に載せて、\n"
              f"   内へずらす（片側 {tg['travel']:.1f} mm・横へ {arm['pinch']:.1f} N。押し下げる力は {arm['slide']:.0f} N ほど）\n"
              "B. 指の先・爪の横で、手前のくぼみから、つまみを内へ押す\n"
              f"→ つまみ切ると、蓋が手前へ {e2['cam']:.2f} 押し出される（⑥）\n"
              f"→ 指を離すと、さらに出て {y_end:.1f} で止まる（⑦）→ 取る\n"
              "**出てこなくても、B4 と同じに、つまんだまま手で引けば抜ける**\n"
              "（斜めの面は、引く動きの邪魔をしない）\n\n"
              "つまむ所の大きさ（実際に取れた寸法）\n"
              f"・上面の滑らせる面: 幅 {tg['pad'][0]:.2f} × 奥行き {tg['pad'][1]:.1f}（× 2 つ）。筋 {tg['ridges'][0]} 本・高さ {tg['ridges'][1]}\n"
              "  **5 × 3 には届かない**（外は口の縁・内は、つまむ量 1.6 と、斜めの面を\n"
              "  付ける壁の残り 1.3 が要る。奥は、縁の裏のかぎの空洞の屋根）\n"
              f"・手前のくぼみ: 幅 {tg['scoop'][0]:.0f} × 奥行き {tg['scoop'][1]:.1f}（上まで開いている）\n"
              f"・内へ押す面: 奥行き {tg['face'][0]:.1f} × 高さ {tg['face'][1]:.2f}\n\n"
              "電池の出し方（蓋を外した後・③）: 見えている上面と手前の縁を、爪か\n"
              "指の先で下へ押しながら手前へ引く。**本物のクリップの固さは、\n"
              "試し刷りでは分からない**")
    ax = fig.add_subplot(gs[3, 2:4])
    _note(ax, "B4 から直した所（利用者: 手で引けば抜ける・出てはこない・遊びがある）\n"
              "・**腕の曲がり方の計算を直した**: B4 は、腕を横へずらすだけで形を作っていた。\n"
              "  本当は付け根まわりに曲がって、先が回る。直した計算で B4 をたどると、\n"
              "  つまみの角が、斜めの面の奥の「まっすぐな壁」に当たって止まる\n"
              "  （= 利用者の「出てこない」と合う）\n"
              f"・斜めの面: まっすぐな壁を無くして 1 本の線に・比 3 → {B.CAM_R:.0f}（摩擦 {num['cam']['lock_mu']:.1f} まで滑る）・\n"
              "  切り欠きの奥の壁を 0.275 → 0.9 離した\n"
              f"・つまみ: 上面を、指の腹で滑らせる面に（幅 {tg['pad'][0]:.2f} × 奥行き {tg['pad'][1]:.1f}・筋付き）\n"
              f"・腕: 0.65 長く・付け根の側を 0.85 に（かぎの近くは 1.0）・付け根の丸み 0.4\n"
              f"  → つまみ切って {a1['strain_pinch']:.2f} %（B4 は 1.51 %）。0.1 厚く刷れても {a1['strain_fat']:.2f} %\n"
              f"  つまむ力 {a1['pinch']:.1f} N（B4 は 1.2 N）= B4 より外しにくくしていない\n"
              "・腕の付け根と柱の隙を、1 層目だけ 0.7 に\n\n"
              "蓋 3 つ = きつさ（かぎの掛かり 1.1・腕・つまみは同じ）\n"
              + "".join(f"  蓋 {n}: 案内の隙 {num['arms'][n]['guide']:.2f}・予圧 {num['arms'][n]['pre']:.2f}・真ん中の溝との隙 {B.VARIANTS[n]['cl']:.2f}\n" for n in sorted(B.VARIANTS))
              + "  蓋 1 = B4 のいちばんきつい蓋と同じ嵌め（基準）\n"
              "  蓋 2 = 回る・左右の遊びを詰め、腕が蓋を手前へ押す力を戻した\n"
              f"      （座る力 {num['arms'][2]['seat_y'][0]:.2f}〜{num['arms'][2]['seat_y'][1]:.2f} N。蓋 1 は {a1['seat_y'][0]:.2f}〜{a1['seat_y'][1]:.2f} N）\n"
              "  蓋 3 = さらに、真ん中の左右の遊びも詰めた（きつくて入らなければ不合格）\n"
              "  前後の遊び 0.15 は、3 つとも同じ（つまむと、かぎの先が手前へ回る分、\n"
              "  蓋が奥へ 0.1 逃げる場所が要る。これ以上は詰められない）\n\n"
              f"片方だけつまむと: つまんだ側が {moves['one_arm'][0]:.2f} 出て止まる。もう片方は {moves['one_arm_other']:.2f}\n\n"
              "**基板の変更の提案（B2 から同じ。いまは何も変えていない）**\n"
              f"・クリップ BT1 を奥へ {B.DBACK:.1f}・ねじ H15 を x {B.H15_OLD[0]:.1f} → {B.H15_NEW[0]:.1f}・\n"
              "  使っていない穴 H30・H31 を消す")
    ax = fig.add_subplot(gs[3, 4:])
    _note(ax, "数（立体から測った物と、TDS の値での計算。刷った物の値ではない）\n"
              f"・腕: 厚さ {B.T_ROOT:.2f}〜{B.T_TIP:.2f} × 高さ {B.HS:.1f} × 長さ {arm['length']:.1f}\n"
              f"・ひずみ（蓋 {B.MAIN}）: つまみ切って {arm['strain_pinch']:.2f} %（上限 {arm['strain_use']:.2f} %）・胴に当たって {arm['strain_stop']:.2f} %・\n"
              f"  0.1 厚く刷れて {arm['strain_fat']:.2f} %。付け根の丸み 0.4 での集中は入れていない\n"
              f"・つまむ力 {arm['pinch']:.1f} N（0.1 厚く刷れて {arm['pinch_fat']:.1f} N）・押し込む力 {arm['insert_force']:.1f} N\n"
              f"・つまむ動きを 0.1 ずつたどった結果（蓋 {B.MAIN}）: 止まる所 {'あり' if e2['stuck'] else 'なし'}・\n"
              f"  蓋が押し出される量は 1 歩で最大 {e2['jump']:.2f}（急な段が無い）・つまみ切って {e2['cam']:.2f}\n"
              f"  かぎが外れるまでの間、蓋が前後に動ける幅は いちばん狭い所で {e2['room']:.2f}\n"
              f"・指を離して止まる所 {y_end:.1f}（摩擦を見ない。腕が押す力 平均 {e2['force']:.1f} N）\n"
              f"・つまみの重さ {arm['tab_mass'] * 1000:.0f} mg を入れた、落下 {S.DROP_G:.0f} G（借りた仮定）: かぎの揺れ {arm['drop']:.2f}\n"
              f"  （外れるのは {arm['pre'] + arm['engage']:.2f} = {arm['drop_margin']:.2f} 倍。**余裕は無い**: {arm['drop_g']:.0f} G で片方のかぎが外れる計算。\n"
              "  もう片方は、掛かる向きに揺れる）\n"
              f"・電池が 20 N（指で強く押す・仮定）で、真ん中に当たるとき [MPa]\n"
              f"  板 {st['plate']['tension']:.0f}／{st['plate']['compression']:.0f}・柱 {st['stem']['stress']:.0f}・腕 {st['arm']['stress']:.0f}"
              f"（強さ: 引っ張り {S.PLA_TENSILE:.0f}・曲げ {S.PLA_BEND:.0f} → 半分以内）\n"
              "・強さに届く力 [N]: "
              + "・".join(f"{names[k]} {v:.0f}" for k, v in sorted(sf.items(), key=lambda q: q[1])[:3]) + "\n"
              f"・掛けた蓋の動ける量: 手前 {moves['forward']:.2f}・上 {moves['up']:.2f}・胴の遊び 奥 {moves['back']:.2f}・左右 {moves['side']:.2f}\n"
              f"・ベッドに着く面積 {num['cam']['footprint']:.0f} mm2（B4 は 172。つまみが大きくなり、胴の手前が細くなった）\n"
              "・上から見える物: 蓋の真ん中・左右のつまみの上面・その内と奥の隙間・指のくぼみ。\n"
              "  蓋を付けた状態で、枠の外面・上面より出る物は無い")
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def howto(out, num=None, moves=None):
    num = num or B.numbers()
    moves = moves or B.measure_moves()
    arm, ej = num["arms"], moves["eject"]
    acc = num["cell_access"]
    fig = plt.figure(figsize=(22, 16.5))
    gs = fig.add_gridspec(2, 3, height_ratios=[0.85, 1.15], hspace=0.16, wspace=0.12)
    fig.suptitle("蓋の別案 B5 の試し刷り（coupon_cover_snap_plate_n04.gcode.3mf）: 刷り方・組み方・手で見る所", fontsize=14, y=0.995)
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
    ax.set_title("刷り上がった板（上から。下が手前）。蓋は、板の真ん中の列", fontsize=11)
    ax.tick_params(labelsize=7)
    ax = fig.add_subplot(gs[0, 1:])
    _draw(ax, scene(), lambda p: F.xy(p, 4.0), (99.5, 146.5, -53.0, -40.5), "組んだ所を、上面の少し下（4.0）で切った図。下が手前")
    _arrow(ax, (B.XN + 0.6, B.YF + 0.8), (101.0, -52.3), "つまみ（左）", va="center")
    _arrow(ax, (B.mx(B.XN) - 0.6, B.YF + 0.8), (140.5, -52.3), "つまみ（右）", va="center")
    ax.annotate("", (B.XN + 2.6, B.YF + 0.9), (B.XLIP - 2.6, B.YF + 0.9), arrowprops=dict(arrowstyle="->", color=BLUE, lw=2.0))
    ax.annotate("", (B.mx(B.XN) - 2.6, B.YF + 0.9), (B.mx(B.XLIP) + 2.6, B.YF + 0.9), arrowprops=dict(arrowstyle="->", color=BLUE, lw=2.0))
    ax.text(B.CX, -52.3, "外し方: 左右のつまみを、内へ押すだけ（青い矢印）→ 蓋が出てくる → 取る", fontsize=11, color=BLUE, ha="center", va="center")
    ax = fig.add_subplot(gs[1, 0])
    _note(ax, "刷る前に\n"
              "・ベッドの板を洗う（食器用の洗剤と水で洗って、よく乾かす）\n"
              "・渡したファイルは、1 層目を遅く（外周 20・中 30 mm/s）、2 層目から上の\n"
              "  内の壁と中も遅く（80・100 mm/s）してある。縁取り（brim）は付けていない\n\n"
              "**使う前に見る所**\n"
              "・腕の付け根と、その内の柱の間の隙が、底まで開いているか\n"
              "  （底で膜になって付いていたら、薄い刃で切り離す。付いたままだと、\n"
              "  腕が短く働いて、付け根が白くなる）\n"
              "・開け閉めのたびに、**腕の付け根が白くなっていないか**\n\n"
              "蓋の見分け方（上の板の奥の縁の切り欠きの数）= **きつさ**\n"
              + "".join(f"  蓋 {n}（切り欠き {n} つ）: 案内の隙 {arm[n]['guide']:.2f}・予圧 {arm[n]['pre']:.2f}・真ん中の隙 {B.VARIANTS[n]['cl']:.2f}\n" for n in arm)
              + "  蓋 1 = 前回のいちばんきつい蓋と同じ嵌め（比べる基準）\n"
              "  蓋 2 = 回る向き・左右の遊びを詰めた ＋ 腕が蓋を手前へ押す\n"
              "      → 蓋 1 より、揺すったときの回り・左右のがたが減るはず。\n"
              "        指で奥へ押して離すと、手前へ戻るはず\n"
              "  蓋 3 = 蓋 2 ＋ 真ん中の左右の隙も詰めた → 左右のがたが、さらに減るはず\n"
              "  前後（奥へ押し込める量 0.15）と上下（0.2）は、3 つとも同じ\n\n"
              "組み方\n"
              "1. 当て板に、枠の角を載せる（左と奥の当てに寄せる）\n"
              "2. 電池の代わりを、口から奥の止めまで入れる\n"
              f"3. 蓋を、手前からまっすぐ押し込む（約 {arm[B.MAIN]['insert_force']:.0f} N。左右がカチッ）\n\n"
              f"**この試し刷りは、クリップと電池を奥へ {B.DBACK:.1f}・ねじ H15 を右へ 3.5\n"
              "動かした基板の形**（いまの基板には合わない）", size=10.5)
    ax = fig.add_subplot(gs[1, 1])
    _note(ax, "手で見る所（蓋 1・2・3 のそれぞれで）\n"
              "a. 入るか・カチッと鳴るか（蓋 3 がきつくて入らなければ、不合格）\n"
              "b. 手前の面・上面が枠と揃うか（出っ張る物が無いか）\n"
              "c. **がた**: 蓋をつまんで揺する（回す・左右・前後・上下）。蓋 1 と比べて、\n"
              "   蓋 2・3 で何が減ったか・まだ気になるのは、どの向きか\n"
              "d. **外す（A）: 指の腹を左右のつまみの上面に載せて、内へずらす**\n"
              "   外す（B）: 指の先・爪の横で、手前から内へ押す\n"
              "   ・つまむだけで蓋が出てくるか（つまんで "
              f"{ej[B.MAIN]['cam']:.2f}・離して {ej[B.MAIN]['rest']:.1f} の計算）\n"
              "   ・出てこなくても、前回と同じに手で引けるか（前回より悪くないか）\n"
              "   **出てこないときは、次を見て教えてください**\n"
              "   ・つまみが、どこまで入って止まるか（目で。計算は 1.6）\n"
              "   ・つまんでいる間に、蓋が少しでも手前へ動くか\n"
              "   ・つまんだまま、指を手前へ 0.3 ほどずらすと抜けるか\n"
              "   ・0.6〜1.0 つまんだあたりで、急に固くなる所があるか\n"
              "e. 片方のつまみだけを押す: 蓋が出てこないこと\n"
              "f. **電池の代わりを、裏から棒で強く押す**: 蓋が外れないか・\n"
              "   蓋の真ん中がふくらむか・白くなるか\n"
              "g. 振る・机の高さから硬い床へ落とす（向きを変えて 5 回。\n"
              "   **横向きに落としたときに、蓋が外れないか**: つまみが重くなった）\n"
              "h. 鞄の中のように、手前の面と上面を布・鍵・ペンの先で擦る・押す\n"
              "   （つまみは、上面から指で動かせるようになった）\n"
              "i. 20 回 開け閉めする: 腕の付け根・かぎ・つまみが白くなる・欠ける\n"
              f"j. 電池の出し方: 見えている上面（奥行き {acc['top_nominal']:.1f}）と手前の縁を、爪か指の先で\n"
              "   下へ押しながら手前へ引く（本物のクリップの固さは、再現できない）", size=10.5)
    ax = fig.add_subplot(gs[1, 2])
    _note(ax, "教えてほしいこと\n"
              "・**c: どの蓋のきつさが良いか・まだ遊ぶ向き**\n"
              "・**d: つまむだけで出てきたか**。出てこなければ、上の 4 つ\n"
              "・指の腹で、上面を滑らせて動かせたか（A）・爪が要ったか（B）\n"
              "・前回（B4）より、外しやすいか・外しにくいか\n"
              "・f・g で、何が起きたか\n"
              "・刷っている途中で剥がれた物があれば、どれが・どこから\n"
              "・見た目: 上面に見える、つまみと隙間が気になるか\n\n"
              "この試し刷りで分からないこと\n"
              "・本物のクリップと電池での固さ → 電池を出すのに要る力\n"
              "・基板を変えてよいか（クリップを奥へ 2.0・H15 を右へ 3.5・\n"
              "  H30 と H31 を消す。配線と検査の見直しが要る）\n"
              "・長く使ったときの、腕のへたり", size=10.5)
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def render_all(out, moves=None):
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    num = B.numbers()
    moves = moves or B.measure_moves()
    return [cover_snap(out / "cover_snap.png", num, moves), howto(out / "coupon_cover_snap_howto.png", num, moves)]
