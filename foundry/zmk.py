"""ZMK のシールドを配列から作る。

    .venv/bin/python3 -m foundry.zmk <機種>              # 行列表（transform）だけ作り直す
    .venv/bin/python3 -m foundry.zmk <機種> --scaffold   # 無いファイルを雛形から作る

**生成器が持つのは `<shield>-transform.dtsi` だけ。**毎回上書きする（手で直さない）。
基板（pcb.py）と同じ `project.matrix` から作るので、キーの行列が基板とずれない。
それ以外（kscan のピン・.conf・keymap）は雛形を 1 回だけ置き、あとは人が持つ。
**上書きしない**——キーマップを直したあとで消えると困る。

行列とファームの一致は tests/test_zmk.py が見る（transform・col-offset・キーマップの
キー数）。HHKB では transform を唯一の出所にし、基板がそれを読んでいた。ここでは
配列から transform も基板も作るので、向きが逆になっている。
"""

from __future__ import annotations

import re
import sys

from . import paths

SHIELDS = paths.ROOT / "config" / "boards" / "shields"

# KLE の刻印 → ZMK のキーコード。**分からないものは &none にして一覧に出す**
# （黙って別のキーにしない）。
_KEYCODES = {
    **{c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    **{str(d): f"N{d}" for d in range(10)},
    "`": "GRAVE", "~": "GRAVE", "-": "MINUS", "=": "EQUAL", "[": "LBKT", "]": "RBKT",
    "\\": "BSLH", "|": "BSLH", ";": "SEMI", "'": "SQT", ",": "COMMA", ".": "DOT",
    "/": "FSLH", "Esc": "ESC", "Tab": "TAB", "Enter": "RET", "Return": "RET",
    "Space": "SPACE", "L-Space": "SPACE", "R-Space": "SPACE", "BS": "BSPC",
    "Bksp": "BSPC", "Backspace": "BSPC", "Del": "DEL", "Delete": "DEL",
    "Ctrl": "LCTRL", "Control": "LCTRL", "Shift": "LSHFT", "Alt": "LALT", "Opt": "LALT",
    "Meta": "LGUI", "Cmd": "LGUI", "Win": "LGUI", "GUI": "LGUI", "Caps": "CAPS",
    "Up": "UP", "Down": "DOWN", "Left": "LEFT", "Right": "RIGHT",
}


def binding(label):
    """刻印 → キーマップの 1 項目。Fn は &mo 1。"""
    if label == "Fn":
        return "&mo 1"
    code = _KEYCODES.get(label) or _KEYCODES.get(label.upper())
    return f"&kp {code}" if code else "&none"


def shield_name(project):
    return getattr(project.spec, "ZMK", {}).get("shield", project.root.name)


def piece_shields(project):
    """部品名 → シールド名。一体型ならシールド名そのもの。"""
    s = shield_name(project)
    pieces = project.spec.PIECES
    return {p: (s if len(pieces) == 1 else f"{s}_{p}") for p in pieces}


def layout(project):
    """[(部品, キー, (row, 全体の col))] をキーマップの並び順で。部品ごとの col-offset も返す。"""
    rows, offsets, off = [], {}, 0
    for piece in project.spec.PIECES:
        keys, rc = project.matrix(piece)
        offsets[piece] = off
        rows += [(piece, k, (r, c + off)) for k, (r, c) in zip(keys, rc)]
        off += max(c for _, c in rc) + 1
    return rows, offsets


def transform_dtsi(project):
    rows, offsets = layout(project)
    n_rows = max(r for _, _, (r, _) in rows) + 1
    n_cols = max(c for _, _, (_, c) in rows) + 1
    lines = []
    for piece in project.spec.PIECES:
        rc = [f"RC({r},{c})" for p, _, (r, c) in rows if p == piece]
        lines.append(f"\t\t\t/* {piece}（col-offset {offsets[piece]}） */")
        lines += ["\t\t\t" + " ".join(rc[i:i + 8]) for i in range(0, len(rc), 8)]
    body = "\n".join(lines)
    return f"""/*
 * **生成物。手で直さない。** python -m foundry.zmk {project.root.name}
 * 配列（{project.spec.LAYOUT}）と spec.py の行列設定から作る。基板と同じ割り当て。
 * 並び順はキーマップと同じ（部品を左から、部品の中は上の段から左→右）。
 */

#include <dt-bindings/zmk/matrix_transform.h>

/ {{
\tchosen {{
\t\tzmk,matrix-transform = &default_transform;
\t}};

\tdefault_transform: keymap_transform_0 {{
\t\tcompatible = "zmk,matrix-transform";
\t\tcolumns = <{n_cols}>;
\t\trows = <{n_rows}>;
\t\tmap = <
{body}
\t\t>;
\t}};
}};
"""


def _write_once(path, text, made):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        made.append(path)


def scaffold(project):
    """無いファイルだけ雛形から作る。作ったファイルと、&none にした刻印を返す。"""
    s = shield_name(project)
    d = SHIELDS / s
    made = []
    rows, offsets = layout(project)
    zmk = getattr(project.spec, "ZMK", {})
    split = len(project.spec.PIECES) > 1
    kconfig = "".join(
        f"config SHIELD_{ps.upper()}\n\tdef_bool $(shields_list_contains,{ps})\n\n"
        for ps in piece_shields(project).values())
    _write_once(d / "Kconfig.shield", kconfig, made)
    for i, (piece, ps) in enumerate(piece_shields(project).items()):
        pins = zmk.get("pins", {}).get(piece)
        if pins:
            # 行は MCU 直結の入力（割り込みで起きられる＝常時スキャンしない）。
            # 並び順が行番号。列は GPIO でも 595 の出力（&shifter N）でもよい
            rows_ = "\n\t\t, ".join(f"<{p} (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>" for p in pins["rows"])
            cols_ = "\n\t\t, ".join(f"<{p} GPIO_ACTIVE_HIGH>" for p in pins["cols"])
            kscan = f"\trow-gpios\n\t\t= {rows_}\n\t\t;\n\tcol-gpios\n\t\t= {cols_}\n\t\t;\n"
        else:
            kscan = ('#error "行・列のピンが未定。回路を決めたら row-gpios / col-gpios を書き、'
                     'この行を消す（spec.ZMK[\\"pins\\"] を書いてから --scaffold し直してもよい）"\n')
        offset = (f"\n&default_transform {{\n\tcol-offset = <{offsets[piece]}>;\n}};\n"
                  if split and offsets[piece] else "")
        _write_once(d / f"{ps}.overlay", f"""/* {project.name} {piece}。雛形から作った。以後は人が持つ。 */

#include "{s}-transform.dtsi"

/ {{
\tchosen {{
\t\tzmk,kscan = &kscan0;
\t}};

\tkscan0: kscan_0 {{
\t\tcompatible = "zmk,kscan-gpio-matrix";
\t\twakeup-source;
\t\tdiode-direction = "col2row";
\t}};
}};

&kscan0 {{
{kscan}}};
{offset}""", made)
        central = split and i == 0
        _write_once(d / f"{ps}.conf", f"""# {project.name} {piece}。雛形から作った。以後は人が持つ。
# 各行の理由は docs/knowledge/zmk-and-xiao.md。
CONFIG_ZMK_KEYBOARD_NAME="{project.name}"
{"CONFIG_ZMK_SPLIT=y" if split else ""}
{"CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y" if central else ""}
# 既定は n。乾電池では桁が変わる（スリープ 2〜3µA）
CONFIG_ZMK_SLEEP=y
CONFIG_ZMK_IDLE_SLEEP_TIMEOUT=1800000
CONFIG_ZMK_KSCAN_DEBOUNCE_PRESS_MS=3
CONFIG_ZMK_KSCAN_DEBOUNCE_RELEASE_MS=5
# macOS は ZMK 既定（min 7.5ms）を Apple §58.6 違反として要求ごと捨てる。
# 適合する設定で 0.63 → 0.43mA（HHKB の実測）
CONFIG_BT_PERIPHERAL_PREF_MIN_INT=12
CONFIG_BT_PERIPHERAL_PREF_MAX_INT=12
CONFIG_BT_PERIPHERAL_PREF_LATENCY=30
CONFIG_BT_PERIPHERAL_PREF_TIMEOUT=600
""".replace("\n\n\n", "\n"), made)
    unknown = sorted({k.label for _, k, _ in rows if binding(k.label) == "&none"})
    base = "\n".join(f"\t\t\t\t{binding(k.label):<12}  // {k.label}" for _, k, _ in rows)
    fn = "\n".join(f"\t\t\t\t{'&trans':<12}  // {k.label}" for _, k, _ in rows)
    _write_once(d / f"{s}.keymap", f"""/* {project.name}。雛形から作った。以後は人が持つ。
 * 並びは {s}-transform.dtsi の map と同じ。&none は刻印から推せなかったキー。
 * **&bootloader と &bt BT_CLR を必ずどこかに置く**（ケースを開けずに復旧できるように）。
 */

#include <behaviors.dtsi>
#include <dt-bindings/zmk/keys.h>
#include <dt-bindings/zmk/bt.h>

/ {{
\tkeymap {{
\t\tcompatible = "zmk,keymap";

\t\tbase {{
\t\t\tbindings = <
{base}
\t\t\t>;
\t\t}};

\t\tfn {{
\t\t\tbindings = <
{fn}
\t\t\t>;
\t\t}};
\t}};
}};
""", made)
    return made, unknown


def write_transform(project):
    path = SHIELDS / shield_name(project) / f"{shield_name(project)}-transform.dtsi"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transform_dtsi(project))
    return path


def add_to_build_yaml(project, board="xiao_ble//zmk"):
    """build.yaml に各部品のシールドを足す（既にあれば何もしない）。"""
    y = paths.ROOT / "build.yaml"
    text = y.read_text()
    for ps in piece_shields(project).values():
        if not re.search(rf"shield:\s*{re.escape(ps)}\s*$", text, re.M):
            text = text.rstrip() + f"\n  - board: {board}\n    shield: {ps}\n"
    y.write_text(text)


def main(argv):
    from .project import load

    p = load(argv[0])
    if "--scaffold" in argv:
        made, unknown = scaffold(p)
        for f in made:
            print(f"作った {f.relative_to(paths.ROOT)}")
        if unknown:
            print(f"⚠ 刻印からキーコードを推せず &none にした: {unknown}")
        add_to_build_yaml(p, getattr(p.spec, "ZMK", {}).get("board", "xiao_ble//zmk"))
    print(f"書いた {write_transform(p).relative_to(paths.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
