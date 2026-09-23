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

SWITCHES = {s.name: s for s in (MX_HOTSWAP,)}


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
