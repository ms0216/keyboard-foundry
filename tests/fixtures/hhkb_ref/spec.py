"""HHKB 分割機（../2608042258_HHKB_devided）を foundry で作り直すための値。

**検査の基準であって、製品ではない。**foundry の生成器が、発注済みの
HHKB の基板（tests/fixtures/hhkb_boards.json に抜き出した実物）と同じ位置・
同じ結線を出すかを tests/test_regression_hhkb.py が数える。

値は HHKB の tools/interface.py（e7a35cd 時点）から写した。
"""

NAME = "HHKB-REF"
LAYOUT = "layout.json"
PIECES = ("left", "right")
SWITCH = "mx_hotswap"        # HHKB は MX 互換＋Kailh ホットスワップ
PLATE_MARGIN_X = 3.125
PLATE_MARGIN_Y = 6.375
CORNER_R = 3.0
PCB_INSET_X = 3.0
PCB_INSET_Y = 5.3
# HHKB の interface.pcb_mount_positions（基板をプレート裏の柱へ締める M2）
MOUNTS = {
    "left": [(2.5, -9.0), (-65.0, 27.0), (64.0, -30.0), (-41.5, -38.0),
             (35.5, 28.0), (-21.5, 28.0)],
    "right": [(0.0, 28.0), (76.0, -29.0), (-82.4, 26.5), (81.0, 28.0),
              (-81.0, -38.0), (-6.0, -38.0), (38.0, 28.0), (-38.0, 28.0)],
}
PLATE_OPENINGS = {"left": [], "right": []}
# 利用者の決定（HHKB open-gaps #46）: 段の中の順番＝列番号。最下段だけ例外
MATRIX_COLUMNS = "ordinal"
MATRIX_OVERRIDE = {"left": {26: (4, 3)}, "right": {32: (4, 3), 33: (4, 4)}}
