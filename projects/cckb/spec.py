"""CCKB（Completely Compact KeyBoard）の設計値。**寸法・部品・行列の決定はここに集める。**

持ち運び用の HHKB 英語配列準拠キーボード。設計書: docs/superpowers/specs/2026-09-23-cckb-design.md
要求（HHKB 準拠）は tests/test_cckb.py が HHKB の実物の KLE と突き合わせる。
値ごとに**なぜその値か**を書く。`[暫定]` は docs/provisional-values.md に同じ数値で載せる。
"""

NAME = "CCKB"                # 基板に刷る名前（他社の商標 HHKB は刷らない）
LAYOUT = "layout.json"       # HHKB 英語配列のスペースを 2.25+1.5+2.25u に分けたもの
PIECES = ("main",)           # 一体型（設計書 D1）
SWITCH = "choc_v1"           # Kailh Choc V1 直付け（設計書 D2・D3）

# キー領域からプレート外形までの余白（片側）。ケースの上枠がプレートの縁を押さえる
# 形は計画 2 で決める。それまでキー領域ちょうど（外周のキーの開口の外に 2.625mm の桟）
PLATE_MARGIN_X = 0.0         # [暫定] 計画 2（ケース）で決める
PLATE_MARGIN_Y = 0.0         # [暫定] 計画 2（ケース）で決める
CORNER_R = 1.0               # [暫定] 計画 2（ケース）で決める
# 基板はキー領域いっぱい。角（XIAO・電池）もキー領域の外接矩形の中にある
PCB_INSET_X = 0.0            # [暫定] 計画 2（ケース）で決める
PCB_INSET_Y = 0.0            # [暫定] 計画 2（ケース）で決める

# 取付ネジ（計画 2 で 5 条件を同時に満たす位置を決める。設計書 O4）
MOUNTS = {"main": []}

MATRIX_COLUMNS = "physical"

ZMK = {
    "shield": "cckb",
    "board": "xiao_ble//zmk",
}
