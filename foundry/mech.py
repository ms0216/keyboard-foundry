"""スイッチ・スタビ・ソケットの規格値。**プレートと基板が共有する。**

スイッチの種類ごとの値は `Switch` 1 つにまとめ、機種は spec.py の `SWITCH` で
名指しする（**既定値で埋めない**。書いていない種類で黙って作らない）。
同じ寸法を 2 箇所に書かない（HHKB でネジ位置をプレートとケースで別々に持ち、
食い違わせた）。KiCad の Python（3.9）からも import されるので標準ライブラリだけ。
"""

from __future__ import annotations

from dataclasses import dataclass

# [記録のみ] ケースを設計するときの値（MX 規格）。いまの生成器は読まない
PLATE_TO_PCB = 3.5       # プレート下面から基板上面まで 5.0 − 1.5

# プレートのスタビ開口を規格の輪郭から外へ広げる量（片側）。
# swillkb のパス（kerf=0）は実物のハウジング（6.804）より片側 0.027 狭い。
# 刷ったプレートで実物に片側 0.1 空くように 0.1 + 0.05（HHKB #30 の実測）。
# Choc スタビの開口にも同じ値を使う（CHOC_STAB_OUTLINE の幅は隙間 0。Choc では未実測）。
# スタビは基板保持なので広げてよい。**スイッチの開口は広げてはいけない**（プレート保持）。
STAB_KERF = 0.15


@dataclass(frozen=True)
class Switch:
    """スイッチ 1 種類の規格値。

    fp          キー幅(u) → フットプリント名（lib/keyswitch.pretty）。**無い幅は落とす**
    value       基板の Value。JLC の部品照合に使われる（キー名を入れると BOM から漏れる）
    diode_offset / diode_angle  ダイオード（裏面）の置き場所。KiCad 座標（Y 下向き）で
                キー中心から
    stab_offset キー幅(u) → スタビ支点の半間隔。2u 未満は不要
    stab_fp     半間隔 → 基板のスタビのフットプリント（基板に穴の要らない種類は空）
    stab_kind   プレートのスタビ開口の形（plate.py が解釈する）。None は未定義
    """

    name: str
    cutout: float
    plate_t: float
    fp: dict
    value: str
    diode_offset: tuple
    diode_angle: int
    stab_offset: dict
    stab_fp: dict
    stab_kind: object
    # 最前列のキーのスタビを 180° 回すか（stab_flipped）。フットプリントの素の向きでワイヤが
    # 手前に来る種類（Cherry）だけ回す。**素の向きでワイヤが奥の種類（Choc V2 のねじ留め）は回さない**
    # （回すと最前列で爪の穴が基板の外へ出る）
    stab_turn_front_row: bool

    def footprint(self, w_u):
        if w_u not in self.fp:
            raise RuntimeError(f"{self.name}: {w_u}u のフットプリントが無い。"
                               "近い幅で代用しない（mech.py の fp に足す）")
        return self.fp[w_u]

    def stab_offset_for(self, w_u):
        """幅 w_u のキーに要るスタビ半間隔。2u 未満は不要で None。"""
        if w_u < 2.0:
            return None
        if w_u not in self.stab_offset:
            raise ValueError(f"{self.name}: {w_u}u のスタビ間隔が未定義。"
                             "プレートと基板の両方に効くので mech.py に足す")
        return self.stab_offset[w_u]


# MX 互換・Kailh ホットスワップ（CPG151101S11-2）。HHKB で発注済みの値。
# スタビ半間隔は Cherry 規格（0.47in = 11.938 / 0.75in = 19.05）。
# **2〜2.75u は同じ 2u スタビ**。3u は国内で買えなかった（HHKB・2026-08-31）。
# ダイオード: 縦置きにしてソケットの端子 2（+5.842, −5.08）と同じ x に並べると
# スイッチ → ダイオードが L 字 2 本で済む。x 7.3 は位置決めポスト（外周 5.955）と
# 禁止域 ±1.15 を避ける値。y 2.0 は中央ポスト（φ4）を避け、行のバスを y 3.65 に通せる
MX_HOTSWAP = Switch(
    name="mx_hotswap",
    cutout=14.0,            # MX 標準のプレート開口
    plate_t=1.5,            # MX のプレート厚（FR4 1.6 でも成立）
    fp={1.0: "SW_Hotswap_Kailh_MX_1.00u", 1.5: "SW_Hotswap_Kailh_MX_1.50u",
        1.75: "SW_Hotswap_Kailh_MX_1.75u", 2.25: "SW_Hotswap_Kailh_MX_2.25u",
        2.75: "SW_Hotswap_Kailh_MX_2.75u", 3.0: "SW_Hotswap_Kailh_MX_3.00u"},
    value="CPG151101S11-2",
    diode_offset=(7.3, 2.0),
    diode_angle=90,
    stab_offset={2.0: 11.938, 2.25: 11.938, 2.5: 11.938, 2.75: 11.938,
                 3.0: 19.05, 6.25: 50.0, 7.0: 57.15},
    stab_fp={11.938: "Stabilizer_Cherry_MX_2.00u", 19.05: "Stabilizer_Cherry_MX_3.00u"},
    stab_kind="cherry",
    stab_turn_front_row=True,
)

# Kailh Choc V1（PG1350）を基板に**直付け**（設計書 D2・D3）。
# 開口 13.8・プレート 1.2 は Kailh の図面 CPG135001D01（tests/test_choc.py が照合）。
# 1.2mm は Choc のスタビがプレートに留まる厚さでもある。
# fp は全幅で同じ（パッドが同一。幅つきは 18×17 ピッチのキャップ外形を描くので使わない）。
# value は部品表の照合用。スイッチは JLCPCB に在庫が無く利用者が手はんだする（D3）。
# ダイオードの位置: (7.6, -1.0)・90°。Task 6 で決めた。**スタビの逃げ穴が入るまでの暫定**
# （基板にまだ逃げ穴が無い。スタビのキー 4 つではパッドが x 8.2・コートヤードが 8.75 まで
# 来て、逃げ穴の始まる x 8.85 まで約 0.65mm しかない。計画 3 で穴を入れて DRC をやり直す。
# open-gaps の「まだ決めていない判断」）。
# 3 条件（tests/test_cckb.py の DRC 検査・diode_offset を 5.0 に壊すと 248 件の
# 穴クリアランス違反で落ちることを確認済み）:
#  1. DRC 違反 0（kicad-cli pcb drc、未配線板。警告は silk_edge_clearance 17 件のみ
#     記録して見逃さない。隣キーの端子・穴・ダイオードとの衝突は違反 0 で確認）
#  2. アノード側パッド（D の pad2、ダイオード中心から局所 (0,-1.65)）が
#     スイッチ端子 2（(5,-3.8)）と x 2.6mm 差で L 字 2 本（横→縦）で結べる位置
#  3. ダイオード中心・両パッドとも枠 ±9.525 の内側。ボス φ1.9 (±5.5,0) まで
#     最短 2.2mm、中心穴 φ3.45 まで最短 7.6mm（いずれもパッド半径を引いても
#     0.3mm を大きく超える）。pcbnew でワールド座標を読んで検算（本コメントの根拠）
# Choc スタビ（2u・プレートマウント）の右側の開口。**支点を原点**・Y 上向き・奥が +y。
# 出典: Keebio-Parts.pretty の Kailh-PG1350-Stab-Cutout.kicad_mod（2 つめの出典の
# Kailh 系製造図のハウジング 6.30×6.60・突起 3.20 に、奥行 +0.25・切り欠き +0.4 の隙間）。
# 左側は x を反転。切り欠き（y > 0）がワイヤの側で、**常に奥**に置く。
# 保存: projects/cckb/docs/references/。照合: tests/test_choc.py
# **幅は隙間 0。**輪郭の幅 6.30 は図面のハウジング 6.30（+0.02/−0.05）そのもので、
# 刷った PLA の穴は締まる。だからプレートでは Cherry と同じ STAB_KERF（片側 0.15・
# HHKB #30 の実測）だけ外へ広げて開ける（plate.build_plate）。この値は元の出典の
# 値として変えない。Choc での嵌め合いは**未実測**（open-gaps の試し刷り）。
CHOC_STAB_OUTLINE = ((-3.15, -3.05), (-3.15, 3.8), (-1.8, 3.8), (-1.8, 8.45),
                     (1.8, 8.45), (1.8, 3.8), (3.15, 3.8), (3.15, -3.05))

# スタビは CHOC_STAB_OUTLINE（出典 2 つ）。基板の逃げ穴は pcb.py ではなく計画 3 の
# pcb_extra で開ける（大きさは組み立てモデルで決める）。
CHOC_V1 = Switch(
    name="choc_v1",
    cutout=13.8,
    plate_t=1.2,
    fp={w: "SW_Kailh_Choc_V1" for w in (1.0, 1.5, 1.75, 2.25)},
    value="PG1350",
    diode_offset=(7.6, -1.0),
    diode_angle=90,
    stab_offset={2.0: 12.0, 2.25: 12.0},
    stab_fp={},
    stab_kind="choc",
    stab_turn_front_row=False,        # 基板に穴の要るスタビが無い（stab_fp が空）ので効かない
)

# ---------------------------------------------------------------------------
# Kailh Choc V2（PG1353）直付け。**静音（PG1353S）も同じ足跡で受ける**（CCKB の cckb-v2 の枝）
# ---------------------------------------------------------------------------
# 出典（どれも keyboardio/keyswitch_documentation に保存された Kailh の図面・tests/test_choc_v2.py が照合）:
#   CPG135301D01      PG1353 赤（標準・2019-10-25「临时版」）
#   CPG1353S01D01-01  PG1353 静音 赤（リニア 43gf・全行程 2.8。2023-05-12「临时版」）
#   CPG1353S01D02-01  PG1353 静音 茶（タクタイル 45gf/55gf・全行程 2.8。2024-01-23「临时版」。
#                     表題「配1.2铝板」= 1.2mm のアルミのプレート用）
# 3 枚とも: 端子 φ1.20 ×2 の位置・中心 φ5.00・下のハウジング 13.95±0.05 角・つば 15.00・
#   ステムはプレートの上面から 6.40・足 3.00±0.2・中心の突起 φ4.80 × 3.30 が同じ。
# 違うのは 2 つ:
#   1. 位置決め穴: 標準は φ1.60。静音は **長円 2.0 × 1.5**（図の注「此孔开成此形状便于所有此系列轴共用」
#      = この系列のどの軸にも共用できるようにこの形で開ける）。静音の底面図は位置決めの足を中心から
#      5.15 と 5.50 の 2 か所に描いている（版で違う）。**両方を受ける和（長円 1.6 × 2.0）で開ける**
#      → lib/keyswitch.pretty/SW_Kailh_Choc_V2_Slot（kiswitch の SW_Kailh_Choc_V2 から位置決め穴だけ替えた物）
#   2. つばの下面から爪の先までの隙（プレートが入る所）: 標準 1.65・静音 **1.35**（下の plate_t）
CHOC_V2_FP = "SW_Kailh_Choc_V2_Slot"

# Choc V2 用のねじ留めスタビ（遊舎工房 A050001-01-1「Choc v2用スタビライザー 2U スクリュータイプ」）の
# 基板の穴。**支点を原点・X は外向き（キーの中心から遠ざかる向き）・Y はワイヤの側が +**（CAD。ワイヤは
# 常に奥に置くので +Y = 奥）。出典は 2 つで、どちらも公式ではない:
#   drawing    販売者が仕入れ先から取って公開した図（サリチル酸さんの記事 chocv2-stab-guide の
#              「Recommended PCB Layout・PCB-H=1.6mm」。2026-05-16。支点の間 24.00）
#   salicylic  サリチル酸さんの足跡 kbd_Stabilizer.pretty/Choc_v2_PCBMountStab_2u（実物を測った物・
#              commit 9ade20b。支点 ±11.9 = 23.8）
# **支点の間が 24.0 と 23.8 で 0.2 食い違う。**基板の穴は 2 つの出典の和で開け（どちらの実物でも入る）、
# 支点の位置そのもの（キャップの脚の位置）は届いた実物で測って決める（決定記録 2026-09-25-choc-v2 §8 の 3）。
# 各出典の形（支点からの位置・大きさ）。box は (X 幅, Y 幅) の矩形・screw/claw は (中心 y, X 幅, Y 幅) の長円
CHOC_V2_STAB_SOURCES = {
    # part = 箱そのもの（図の上面図 5.80 × 7.30）。推奨の穴 8.00 の y は採らない（下の CHOC_V2_STAB_HOLES）
    "drawing": dict(pivot=12.0, box=(6.00, 8.00), screw=(-6.20, 3.00, 3.00), claw=(8.50, 4.00, 4.00),
                    part=(5.80, 7.30)),
    "salicylic": dict(pivot=11.9, box=(6.0, 7.5), screw=(-6.2, 3.2, 3.4), claw=(8.24, 3.0, 4.0)),
}
# 開ける穴（支点 CHOC_V2.stab_offset = 12.0 から。X は外向き）。上の 2 つを含む最小に近い形を手で決め、
# tests/test_choc_v2.py が「両方の出典の形を含む」ことと「フットプリントと同じ」ことを確かめる。
#   box    箱（基板の下へ 3.30 出る）の穴。Edge.Cuts で抜く（interface.stab_reliefs が
#          spec.STAB_RELIEF_MARGIN を足す）。(x0, y0, x1, y1)。**y は ±3.75（サリチル酸さんの 7.5）で、図の
#          推奨 8.00 は採らない**: ねじの穴（長円 3.4・上端は支点から 4.5）との間の基板の橋が、図の 8.00 だと
#          0.5、それに外形の余裕を足すと 0.2 まで細る（1 回目の板で 0.2 になった・2026-09-25）。7.5 なら 0.75
#          （サリチル酸さんの足跡と同じ・実物で組まれている）。箱（図の 7.30）との y の隙は片側 0.1
#   screw  ねじの穴（非めっきの長円）。((中心 x, 中心 y), (X 幅, Y 幅))
#   claw   ワイヤの側の爪の穴（同）
CHOC_V2_STAB_HOLES = dict(box=(-3.1, -3.75, 3.0, 3.75),
                          screw=((-0.1, -6.2), (3.2, 3.4)),
                          claw=((-0.05, 8.37), (4.2, 4.4)))
CHOC_V2_STAB_FP = "Stab_Kailh_Choc_V2_Screw_2u"
# プレートの開口（片側・**キーの中心を原点**・X は外向き・+Y = ワイヤ = 奥）。軸に平行な辺だけ。
# 出典: サリチル酸さんの kbd_SW_Hole.pretty/Stab_Hole_Choc_v2_PCBMount_2u（commit 9ade20b。支点 11.9）
#   羽（スタビ本体が通る）x 8.875〜14.9375・y −9.45（半円の頂）〜10.85
#   ワイヤの帯: **スイッチの開口の上辺からそのまま y 9.85 まで**（|x| < 8.375）。開口・帯・羽が 1 つの U 字の穴で、
#   スイッチの開口と羽の間の桟（x 7.05〜8.875・y 7.14375 より下）だけが残る
# 変えた所（どれも穴を広げる向き。狭めない）:
#   - 支点 12.0（図）でも入るよう、羽の外の辺を +0.1（14.9375 → 15.0375）
#   - 半円・角の丸みは外接する矩形にした（軸に平行な辺だけにする。穴は大きくなる）
#   - 羽の内の辺は左右で 8.87125 / 8.875 と 0.004 違うので、内側の 8.87 に揃えた
# **1 回目は帯を y 9.85〜10.85 と読み違え、スイッチの開口と帯の間に板の島（13.5 × 2.7）が 4 つ浮いた**
# （tests/test_cckb_case.py の「1 つの立体」で見つけた・2026-09-25）。tests/test_cckb.py が島の無いことを見る
# プレートでは STAB_KERF だけ外へ広げて開ける（plate.build_plate）
CHOC_V2_STAB_PLATE = ((0.0, 6.64375), (7.55, 6.64375), (7.55, 7.14375), (8.375, 7.14375), (8.375, 6.64375),
                      (8.87, 6.64375), (8.87, -9.45), (15.0375, -9.45), (15.0375, 10.85), (8.375, 10.85),
                      (8.375, 9.85), (0.0, 9.85))

def choc_v2_stab_plate_polys(at=(0.0, 0.0), outline=None, web=0.0, kerf=0.0):
    """キーの中心 at の左右 2 つの開口（CHOC_V2_STAB_PLATE・CAD）。ワイヤは常に奥。

    outline（プレートの外形 (x0, y0, x1, y1)）を渡すと、kerf だけ広げた開口と外形の間が web 未満になる辺を
    外形の外まで伸ばす（**細い帯を残さない**。最下段のスペースでは羽の手前の端が外形から 0.225 だった）。
    返す点列は kerf を足す前の形（広げるのは使う側）。伸ばした辺は kerf を足しても外形の外にある。
    """
    ax, ay = at
    right = [(ax + x, ay + y) for x, y in CHOC_V2_STAB_PLATE]
    left = [(ax - x, ay + y) for x, y in reversed(CHOC_V2_STAB_PLATE)]
    polys = [left, right]
    if outline is None:
        return polys
    x0, y0, x1, y1 = outline
    out = []
    ys = [y for _, y in polys[1]]
    lo, hi = min(ys), max(ys)
    cut_lo, cut_hi = lo - kerf - y0 < web, y1 - (hi + kerf) < web
    for poly in polys:
        new = []
        for x, y in poly:
            if y == lo and cut_lo:
                y = y0 - 1.0
            elif y == hi and cut_hi:
                y = y1 + 1.0
            new.append((x, y))
        out.append(new)
    # 羽を外形の外まで伸ばすと、スイッチの開口の外形側の板と、開口と羽の間の桟が島になって落ちる。
    # **その島ごと抜く**: 左右の羽の内の辺のあいだを、外形の外から反対側の帯の始まりまで（桟も含めて）。
    # そのキーのスイッチの周りにはプレートが無くなる（スイッチは基板にはんだ付けで留まる。D11）
    edge = min(y for _, y in CHOC_V2_STAB_PLATE)                 # 羽の手前の端（相対）
    inner = min(x for x, y in CHOC_V2_STAB_PLATE if y == edge)   # 羽の内の辺
    # 帯のいちばん低い縁（桟の角の上。開口の縁 6.64 より上の最初の辺）。ここまで抜けば桟の角も残らない
    band = min(y for _, y in CHOC_V2_STAB_PLATE if y > min(y2 for x2, y2 in CHOC_V2_STAB_PLATE if x2 == 0.0))
    if cut_lo:
        out.append([(ax - inner, y0 - 1.0), (ax + inner, y0 - 1.0), (ax + inner, ay + band),
                    (ax - inner, ay + band)])
    if cut_hi:
        out.append([(ax - inner, ay - band), (ax + inner, ay - band), (ax + inner, y1 + 1.0),
                    (ax - inner, y1 + 1.0)])
    return out


CHOC_V2 = Switch(
    name="choc_v2",
    # [暫定] 下のハウジング 13.95±0.05（3 枚の図の底面図）。V1 と同じく図の名目の値を開口にする。
    # 刷ったプレートで 13.90 / 13.95 / 14.00 / 14.05 を試し刷りの小片で比べて決める
    cutout=13.95,
    # [暫定] プレートの厚さ。つばの下面から爪の先までの隙が標準 1.65・**静音 1.35**。静音の茶の図の表題は
    # 「配1.2铝板」（1.2mm のプレート用）。**両方に入る厚さは 1.35 以下** → 1.2（0.2 層で 6 層）。
    # 静音で遊び 0.15・標準で 0.45（標準ではプレートがカタつく。スイッチは基板にはんだ付けするので位置はずれない）。
    # 決定記録の下書きの 1.4 / 1.6 は標準だけを見た値で、静音には入らない
    plate_t=1.2,
    fp={w: CHOC_V2_FP for w in (1.0, 1.5, 1.75, 2.25)},
    value="PG1353",
    # ダイオード（裏・縦置き）。V1 の (7.6, −1.0) から 0.5 左: スタビのキーで、箱の穴の内の縁
    # （支点 12.0 − 3.1 − spec.STAB_RELIEF_MARGIN 0.3 = x 8.6）とコートヤード（x ±1.15 → 8.25）の間に
    # 0.35 残す（V1 はキー 4 つだけ DIODE_OVERRIDE で動かしていた。全部のキーで同じ位置にして上書きを無くした）。
    # 端子 2 (5, −3.8) からアノード（x 7.1）へ L 字 2 本。アノードのパッドと端子 2 のランドの間 0.55
    diode_offset=(7.1, -1.0),
    diode_angle=90,
    stab_offset={2.0: 12.0, 2.25: 12.0},
    stab_fp={12.0: CHOC_V2_STAB_FP},
    stab_kind="choc_v2_screw",
    stab_turn_front_row=False,        # フットプリントの素の向きでワイヤが奥。最前列（スペース）も回さない
)

SWITCHES = {s.name: s for s in (MX_HOTSWAP, CHOC_V1, CHOC_V2)}


def switch_of(spec):
    """spec.SWITCH の種類。**知らない名前は落とす。**"""
    if spec.SWITCH not in SWITCHES:
        raise ValueError(f"SWITCH = {spec.SWITCH!r} は mech.SWITCHES に無い: {sorted(SWITCHES)}")
    return SWITCHES[spec.SWITCH]


def stab_flipped(key, keys):
    """スタビを 180° 回す（ワイヤを奥へ）か。**最前列のキーだけ回す。**

    素の向きだと大穴 φ3.988 が手前に来る。HHKB のスペースでは基板前縁まで
    0.381mm しか残らず、外形公差 ±0.2 で 0.18mm の橋になった（#53）。
    回すと 2.14mm。市販基板でもスペースのスタビはワイヤ奥が普通。
    """
    return round(key.y_mm, 2) == max(round(k.y_mm, 2) for k in keys)
