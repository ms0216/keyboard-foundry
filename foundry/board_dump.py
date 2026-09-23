"""基板からキーまわりの部品（SW/ST/D/H）の位置・向き・面・結線を抜き出す。

pcbnew を使わず S 式のテキストとして読む（venv から走る・CI で走る）。
**正規表現は `re.fullmatch` で絞る**——接頭辞 `D`/`SW` で拾うと電源部
（D_PWR・SW_PWR）を巻き込む（HHKB で 4 回起きた）。
"""

import re

from .boardhash import _blocks

KEY_PART = re.compile(r"(SW|ST|D|H)\d+")
REF = re.compile(r'\(property "Reference" "([^"]+)"')
AT = re.compile(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)")
LAYER = re.compile(r'\n\t\t\(layer "([^"]+)"\)')
PAD_HEAD = re.compile(r'\(pad "([^"]*)"')
NET = re.compile(r'\(net (?:\d+ )?"([^"]*)"\)')


def _balanced(txt, i):
    """txt[i] の "(" に対応する ")" までを返す。"""
    depth = 0
    for j in range(i, len(txt)):
        depth += {"(": 1, ")": -1}.get(txt[j], 0)
        if depth == 0:
            return txt[i:j + 1]
    raise ValueError("括弧が閉じていない")


def pads(blk):
    r"""[(パッド番号, ネット名)]。**パッドを括弧の対応で切り出してから**ネットを探す。

    `(pad ...)[\s\S]{0,400}?(net ...)` のような窓で探すと、ネットの無いパッド
    （NPTH）から**隣のパッドのネットへ滑る**（HHKB で 1 回、ここでも初版で 1 回）。
    """
    out = []
    for m in PAD_HEAD.finditer(blk):
        n = NET.search(_balanced(blk, m.start()))
        out.append((m.group(1), n.group(1) if n else ""))
    return out


def key_parts(text, origin=(150.0, 100.0)):
    """参照名 → dict(x, y, rot, back, fp, pads)。座標は origin からの差（KiCad の向き）。"""
    out = {}
    for name, blk in _blocks(text):
        r = REF.search(blk)
        if not r or not KEY_PART.fullmatch(r.group(1)):
            continue
        a = AT.search(blk)
        out[r.group(1)] = dict(
            x=round(float(a.group(1)) - origin[0], 4), y=round(float(a.group(2)) - origin[1], 4),
            rot=round(float(a.group(3) or 0) % 360, 2),
            back=LAYER.search(blk).group(1) == "B.Cu",
            fp=name.split(":")[-1],
            pads={num: net for num, net in pads(blk) if num})
    return out
