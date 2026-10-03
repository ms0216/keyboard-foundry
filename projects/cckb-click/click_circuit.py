"""cckb-click の回路を**データとして**宣言する。**ここが回路の唯一の出どころ。**

    PART = (参照名, 種類, {ピン名: ネット名})      種類は foundry/pinmap.py の PINS のキー

**電気の設計は CCKB と同じ**（projects/cckb/circuit.py。ピンも同じなので ZMK のシールドは同じ形）。違うのは部品だけ:

    CR1632 ＋（クリップ）→ 電源スイッチ MSK12C02（2 共通 → 3）→ VBAT_SW ┬ 1MΩ → VBAT_SENSE（D0）→ 1MΩ → GND
                                                                      └ D_PWR（BAT46W）A→K → V3V3（XIAO の 3V3）
    CR1632 − → 基板の裸の銅 → GND。**XIAO の BAT には何も繋がない**
    行 5 本 ROW0..4 → XIAO D2..D6。列 15 本 ← 74LVC595 ×2（SPI: SCK=D8・MOSI=D10・CS=D7）
    キーごとに BAT46W（col2row: COL → スイッチ → A→K → ROW）
    幅の広いキー 11 個は、真ん中のスイッチと**並列の空きランド**が左右にある（SWA{i}・SWB{i}。JLC は実装しない）
    電源スイッチの枠（4）は GND（図面の回路図）

- ピンは**名前で**書き、パッド番号は pinmap.resolve で引く（引けなければ落ちる）
- **繋がないピンは "NC" と書く**
- 基板（pcb_extra.py）はここを読んでネットを張り、tests/test_cckb_click_pcb.py は**配線して塗った板**のパッドのネットを
  ここと端から端まで突き合わせる

KiCad の Python（3.9）からも読むので標準ライブラリだけ。
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

NC = "NC"

# XIAO のピン → ネット。**overlay（config/boards/shields/cckb_click/cckb_click.overlay）と同じ**（CCKB と同じ割り当て）
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
        ("BT1", "coin_clip_my1632", {"+": "VBAT_IN", "-": "GND"}),
        # 2 が共通。3 は奥（+y）の端子で入、1（手前）は空き。つまみのある側の端子が共通とつながる（図面の回路図）ので、
        # つまみを奥へ寄せると入（spec.PSW_ON・枠の刻印）。**図の読み。基板が届いたらテスターで確かめる**
        ("SW_PWR", "slide_msk12c02", {"1": NC, "2": "VBAT_IN", "3": "VBAT_SW", "SHELL": "GND"}),
        ("R_HI", "res_1M", {"1": "VBAT_SW", "2": "VBAT_SENSE"}),
        ("R_LO", "res_1M", {"1": "VBAT_SENSE", "2": "GND"}),
        ("D_PWR", "schottky", {"A": "VBAT_SW", "K": "V3V3"}),
    ]


def _layout(project=None):
    import click_layout
    return click_layout.Layout(project)


def matrix(project=None):
    """キーのスイッチ・ダイオードと、幅の広いキーの空きランド。**行列は foundry.matrix（ファームと同じ出どころ）から。**"""
    lay = _layout(project)
    out = []
    for k in lay.keys:
        pins = {"1": f"COL{k.c}", "2": f"SW{k.i}_D"}
        out.append((f"SW{k.i}", "keyswitch", dict(pins)))
        out.append((f"D{k.i}", "diode", {"A": f"SW{k.i}_D", "K": f"ROW{k.r}"}))
        if lay.side_offset(k) is not None:
            out.append((f"SWA{k.i}", "keyswitch", dict(pins)))
            out.append((f"SWB{k.i}", "keyswitch", dict(pins)))
    return out


def netlist(project=None):
    return electronics() + matrix(project)


def mechanical_refs(project=None):
    """基板に載るが回路に入らないもの（ねじの穴）。**名前を列挙する**（接頭辞で除外しない）。"""
    return {ref for ref, _, _ in _layout(project).screws()}


def expected_pad_nets(project=None):
    """{参照名: {パッド番号: ネット名（NC は ""）}}。pinmap を通して引く（引けなければ落ちる）。"""
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


# 太く引くネット（pcb_extra.py がネットクラス POWER にする）
POWER_NETS = ("GND", "V3V3", "VBAT_IN", "VBAT_SW")
