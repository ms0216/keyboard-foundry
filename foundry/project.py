"""機種（projects/<名前>/）を読む。

1 機種は `spec.py`（寸法・部品・行列の決定）と `layout.json`（KLE）で決まる。
`spec.py` は **Python のまま**にしてある。値ごとに「なぜその値か」をコメントで
残せること、KiCad の Python（3.9・tomllib 無し）からも読めることが理由。

    from foundry.project import load
    p = load("my_board")            # projects/my_board/
    for piece, keys in p.pieces().items(): ...

KiCad の Python からも import されるので標準ライブラリだけで書く。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from . import paths
from .layout import islands, load_layout
from .matrix import assignments

# spec.py が持たなければならない名前。**既定値で埋めない**——黙って既定値が
# 効くと、その機種で決めていない寸法が決まったことになる。
REQUIRED = ("NAME", "LAYOUT", "PIECES", "SWITCH", "PLATE_MARGIN_X", "PLATE_MARGIN_Y",
            "CORNER_R", "PCB_INSET_X", "PCB_INSET_Y", "MOUNTS", "PLATE_OPENINGS")


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        path = self.root / "spec.py"
        s = importlib.util.spec_from_file_location(f"spec_{self.root.name}", path)
        self.spec = importlib.util.module_from_spec(s)
        s.loader.exec_module(self.spec)
        missing = [n for n in REQUIRED if not hasattr(self.spec, n)]
        if missing:
            raise AttributeError(f"{path}: {missing} が無い")

    @property
    def name(self):
        return self.spec.NAME

    @property
    def build(self):
        return paths.BUILD / self.root.name

    def keys(self):
        return load_layout(self.root / self.spec.LAYOUT)

    def pieces(self):
        """部品名 → その島のキー。島の数と PIECES の数が違えば落とす。"""
        found = islands(self.keys(), getattr(self.spec, "ISLAND_GAP_U", 1.0))
        if len(found) != len(self.spec.PIECES):
            raise ValueError(f"{self.name}: 配列の島は {len(found)} 個、"
                             f"PIECES は {self.spec.PIECES}")
        return dict(zip(self.spec.PIECES, found))

    def matrix(self, piece):
        """(キーマップ順のキー, 各キーの (row, col))。MATRIX_OVERRIDE を適用する。"""
        keys, rc = assignments(self.pieces()[piece],
                               getattr(self.spec, "MATRIX_COLUMNS", "physical"))
        for i, v in getattr(self.spec, "MATRIX_OVERRIDE", {}).get(piece, {}).items():
            rc[i] = tuple(v)
        if len(set(rc)) != len(rc):
            raise ValueError(f"{self.name}/{piece}: 同じ (row, col) に 2 つのキーがある")
        return keys, rc

    def diode_override(self, piece):
        """spec.DIODE_OVERRIDE[piece]（キー番号 → (dx, dy, 角度)）。無ければ {}。

        **綴り違いを黙って無視しない**: 無い部品名・キー番号（1〜キーの数）を書いたら落とす。
        前は効かないまま DRC 0 で通った（最終レビュー M2）。
        """
        over = getattr(self.spec, "DIODE_OVERRIDE", {})
        extra = set(over) - set(self.spec.PIECES)
        if extra:
            raise ValueError(f"{self.name}: DIODE_OVERRIDE の部品 {sorted(extra)} は PIECES {self.spec.PIECES} に無い")
        n = len(self.pieces()[piece])
        bad = sorted(set(over.get(piece, {})) - set(range(1, n + 1)), key=str)
        if bad:
            raise ValueError(f"{self.name}/{piece}: DIODE_OVERRIDE のキー番号 {bad} は 1〜{n} に無い")
        return over.get(piece, {})


def load(name_or_path):
    p = Path(name_or_path)
    return Project(p if (p / "spec.py").exists() else paths.PROJECTS / name_or_path)


def all_projects():
    return [Project(d) for d in sorted(paths.PROJECTS.glob("*/")) if (d / "spec.py").exists()]
