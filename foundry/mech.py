"""MX 互換スイッチ・スタビ・ホットスワップの規格値。**プレートと基板が共有する。**

同じ寸法を 2 箇所に書かない（HHKB でネジ位置をプレートとケースで別々に持ち、
食い違わせた）。KiCad の Python（3.9）からも import されるので標準ライブラリだけ。
"""

from __future__ import annotations

SWITCH_CUTOUT = 14.0     # MX 標準のプレート開口
PLATE_T = 1.5            # MX のプレート厚（FR4 1.6 でも成立）
# [記録のみ] ケースを設計するときの値（MX 規格）。いまの生成器は読まない
PLATE_TO_PCB = 3.5       # プレート下面から基板上面まで 5.0 − 1.5

# キー中心からスタビ支点までの半間隔（Cherry 規格。0.47in = 11.938 / 0.75in = 19.05）。
# **2〜2.75u は同じ 2u スタビ**。3u は国内で買えなかった（HHKB・2026-08-31）ので
# 配列を決める前に入手性を確かめること（docs/knowledge/parts.md）。
STAB_OFFSET = {2.0: 11.938, 2.25: 11.938, 2.5: 11.938, 2.75: 11.938,
               3.0: 19.05, 6.25: 50.0, 7.0: 57.15}

# プレートのスタビ開口を規格の輪郭から外へ広げる量（片側）。
# swillkb のパス（kerf=0）は実物のハウジング（6.804）より片側 0.027 狭い。
# 刷ったプレートで実物に片側 0.1 空くように 0.1 + 0.05（HHKB #30 の実測）。
# スタビは基板保持なので広げてよい。**スイッチの開口は広げてはいけない**（プレート保持）。
STAB_KERF = 0.15


def stab_offset_for(w_u):
    """幅 w_u のキーに要るスタビ半間隔。2u 未満は不要で None。"""
    if w_u < 2.0:
        return None
    if w_u not in STAB_OFFSET:
        raise ValueError(f"{w_u}u のスタビ間隔が未定義。プレートと基板の両方に効くので mech.py に足す")
    return STAB_OFFSET[w_u]


def stab_flipped(key, keys):
    """スタビを 180° 回す（ワイヤを奥へ）か。**最前列のキーだけ回す。**

    素の向きだと大穴 φ3.988 が手前に来る。HHKB のスペースでは基板前縁まで
    0.381mm しか残らず、外形公差 ±0.2 で 0.18mm の橋になった（#53）。
    回すと 2.14mm。市販基板でもスペースのスタビはワイヤ奥が普通。
    """
    return round(key.y_mm, 2) == max(round(k.y_mm, 2) for k in keys)


# キー幅 → ホットスワップのフットプリント（lib/keyswitch.pretty・kiswitch 由来）
# **無い幅は落とす。**近い幅で代用するとシルクのキャップ外形が嘘になる。
# 足すときは kiswitch（perigoso）上流から取り、パッドと穴が 1u と一致するか確かめる
SWITCH_FP = {1.0: "SW_Hotswap_Kailh_MX_1.00u", 1.5: "SW_Hotswap_Kailh_MX_1.50u",
             1.75: "SW_Hotswap_Kailh_MX_1.75u", 2.25: "SW_Hotswap_Kailh_MX_2.25u",
             2.75: "SW_Hotswap_Kailh_MX_2.75u", 3.0: "SW_Hotswap_Kailh_MX_3.00u"}
STAB_FP = {11.938: "Stabilizer_Cherry_MX_2.00u", 19.05: "Stabilizer_Cherry_MX_3.00u"}

# ダイオード（SOD-123・裏面）の置き場所。KiCad 座標（Y 下向き）でキー中心から。
# 縦置きにしてソケットの端子 2（+5.842, −5.08）と同じ x に並べると、
# スイッチ → ダイオードが L 字 2 本で済む。x 7.3 は位置決めポスト（外周 5.955）と
# 禁止域 ±1.15 を避ける値。y 2.0 は中央ポスト（φ4）を避け、行のバスを y 3.65 に通せる
DIODE_OFFSET = (7.3, 2.0)
DIODE_ANGLE = 90
