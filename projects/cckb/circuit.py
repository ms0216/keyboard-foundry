"""CCKB の回路を**データとして**宣言する。**ここが回路の唯一の出どころ。**

    PART = (参照名, 種類, {ピン名: ネット名})      種類は foundry/pinmap.py の PINS のキー

- ピンは**名前で**書き、パッド番号は pinmap.resolve で引く（引けなければ落ちる。
  握り潰すとネットの無いパッドが DRC 0 のまま残る。HHKB で 595 が丸ごと消えていた）
- **繋がないピンは "NC" と書く。**書き忘れと区別する（検査は「宣言に無いピン」も落とす）
- 基板（pcb_extra.py）はここを読んでネットを張り、tests/test_cckb_pcb.py は
  **配線して塗った板**のパッドのネットをここと端から端まで突き合わせる

回路（設計書 §4・docs/knowledge/power.md）:

    CR1632 ＋ → 電源スイッチ（② 共通 → ③）→ VBAT_SW ┬ 1MΩ → VBAT_SENSE（D0）→ 1MΩ → GND
                                                   └ B5819W A→K → V3V3（XIAO の 3V3 ピン）
    CR1632 − → GND。**XIAO の BAT には何も繋がない**（LiPo の充電回路に直結。USB を挿すと
    一次電池を充電する）
    行 5 本 ROW0..4 → XIAO D2..D6（入力・プルダウンはファーム）
    列 15 本 ← 74LVC595 ×2 の数珠つなぎ（SPI: SCK=D8・MOSI=D10・CS=D7。D9 は MISO に確保）
      U1: DS=MOSI・SH_CP=SCK・ST_CP=CS・MR→3V3・OE→GND・Q7S→U2 の DS。QA..QH = COL0..7
      U2: SH_CP・ST_CP は共有。QA..QG = COL8..14。QH・Q7S は NC
      ファームの &shifter n = COLn（ZMK gpio_595: 最下位バイトが鎖の先頭 U1、&shifter 0 = U1 の QA、
      &shifter 8 = U2 の QA。docs/knowledge/zmk-and-xiao.md・config/boards/shields/cckb/cckb.overlay）
    キーごとに BAT46W（col2row: COL → スイッチ → A→K → ROW）
    パスコン 0.1µF を各 595 の直近に 1 個（XIAO は 3V3 に内蔵 2.2µF×5）

KiCad の Python（3.9）からも読むので標準ライブラリだけ。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NC = "NC"

# XIAO のピン → ネット。**overlay（config/boards/shields/cckb/cckb.overlay）と同じ**:
# row-gpios = xiao_d 2..6、cs-gpios = xiao_d 7、xiao_spi（SCK=D8・MOSI=D10）、adc 0 = D0
XIAO_PINS = {
    "GND": "GND", "3V3": "V3V3", "5V": NC, "BAT": NC,
    "D0": "VBAT_SENSE", "D1": NC,
    "D2": "ROW0", "D3": "ROW1", "D4": "ROW2", "D5": "ROW3", "D6": "ROW4",
    "D7": "CS", "D8": "SPI_SCK", "D9": NC, "D10": "SPI_MOSI",
}

_Q = ["Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]     # QA..QH（pinmap の NXP 名）


def _595(ref, first_col, n_cols, ds, q7s):
    pins = {"VCC": "V3V3", "GND": "GND",
            "MR": "V3V3",          # マスタリセット（Low で消える）。浮かせない
            "OE": "GND",           # 出力許可（Low で有効）。浮かせると全列が High-Z
            "DS": ds, "SH_CP": "SPI_SCK", "ST_CP": "CS", "Q7S": q7s}
    for i, q in enumerate(_Q):
        pins[q] = f"COL{first_col + i}" if i < n_cols else NC
    return (ref, "74LVC595", pins)


def electronics():
    """キー以外の部品。[(参照名, 種類, {ピン: ネット})]。"""
    return [
        ("U_MCU", "xiao_nrf52840", dict(XIAO_PINS)),
        _595("U1", 0, 8, "SPI_MOSI", "U1_U2"),
        _595("U2", 8, 7, "U1_U2", NC),
        ("C_U1", "cap_100n", {"1": "V3V3", "2": "GND"}),
        ("C_U2", "cap_100n", {"1": "V3V3", "2": "GND"}),
        ("BT1", "coin_holder_bs16", {"+": "VBAT_IN", "-": "GND"}),
        # ② 共通・③ が入。① は空き。図面の上面図はつまみを ① の側に描き、回路図は ①② を
        # 繋いで描く → つまみを ③ の側へ寄せると入（**図の読み。実物をテスターで確かめる**）
        ("SW_PWR", "slide_mk12c02", {"1": NC, "2": "VBAT_IN", "3": "VBAT_SW",
                                     "EAR1": NC, "EAR2": NC, "EAR3": NC, "EAR4": NC}),
        ("R_HI", "res_1M", {"1": "VBAT_SW", "2": "VBAT_SENSE"}),
        ("R_LO", "res_1M", {"1": "VBAT_SENSE", "2": "GND"}),
        ("D_PWR", "schottky", {"A": "VBAT_SW", "K": "V3V3"}),
    ]


def matrix(project=None):
    """キーのスイッチとダイオード。**行列は foundry.matrix（ファームと同じ出どころ）から。**"""
    if project is None:
        from foundry.project import load
        project = load(Path(__file__).resolve().parent)
    _, rc = project.matrix("main")
    out = []
    for i, (r, c) in enumerate(rc, start=1):
        out.append((f"SW{i}", "keyswitch", {"1": f"COL{c}", "2": f"SW{i}_D"}))
        out.append((f"D{i}", "diode", {"A": f"SW{i}_D", "K": f"ROW{r}"}))
    return out


def netlist(project=None):
    return electronics() + matrix(project)


# 基板に載るが回路に入らないもの（穴）。**名前を列挙する**（接頭辞で除外しない）
def mechanical_refs(project=None):
    if project is None:
        from foundry.project import load
        project = load(Path(__file__).resolve().parent)
    return {f"H{i}" for i in range(len(project.spec.MOUNTS["main"]))} | {"H_LID"}


def expected_pad_nets(project=None):
    """{参照名: {パッド番号: ネット名（NC は ""）}}。pinmap を通して引く（引けなければ落ちる）。

    同じパッド番号を 2 つのピンが共有することはない（あれば落とす）。基板に出ないピン
    （XIAO の BAT）はここに現れない（pinmap が None を返す）。
    """
    from foundry import pinmap

    out = {}
    for ref, kind, pins in netlist(project):
        if set(pins) != set(pinmap.PINS[kind]):
            raise ValueError(f"{ref}（{kind}）の宣言が pinmap と違う: "
                             f"無い {sorted(set(pinmap.PINS[kind]) - set(pins))} / "
                             f"余分 {sorted(set(pins) - set(pinmap.PINS[kind]))}")
        pads = {}
        for pin, net in pins.items():
            num = pinmap.resolve(kind, pin)
            if num is None:
                continue
            if num in pads:
                raise ValueError(f"{ref} のパッド {num} に 2 つのピン")
            pads[num] = "" if net == NC else net
        out[ref] = pads
    return out


def nets():
    return sorted({n for _, _, pins in netlist() for n in pins.values() if n != NC})


# 太く引くネット（pcb_extra.py がネットクラス POWER にする）
POWER_NETS = ("GND", "V3V3", "VBAT_IN", "VBAT_SW")
