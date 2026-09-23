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
)

SWITCHES = {s.name: s for s in (MX_HOTSWAP, CHOC_V1)}


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
