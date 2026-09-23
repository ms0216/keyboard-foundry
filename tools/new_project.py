"""新しい機種を始める。

    .venv/bin/python3 tools/new_project.py <名前> <KLE の JSON> [--pieces left,right]

作るもの:
  projects/<名前>/spec.py            設計値（docs/templates/spec.py.tmpl から）
  projects/<名前>/layout.json        KLE の写し
  projects/<名前>/docs/              台帳の雛形（open-gaps・暫定値・発注前・部品・引き継ぎ）
  config/boards/shields/<名前>/      ZMK シールドの雛形と行列表（build.yaml にも足す）

**既にあるものは上書きしない。**島の数から部品名を推す（1 つなら main、2 つなら
left/right）。3 つ以上は --pieces で名付ける。
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from foundry import paths, zmk                      # noqa: E402
from foundry.layout import islands, load_layout     # noqa: E402
from foundry.project import load                    # noqa: E402

TEMPLATES = ROOT / "docs" / "templates"
PROJECT_DOCS = ("open-gaps.md", "provisional-values.md", "fab-checklist.md",
                "parts-audit.md", "handover.md")


def create(name, layout, pieces=None, projects=paths.PROJECTS):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise SystemExit(f"名前は英小文字・数字・_（ZMK のシールド名になる）: {name!r}")
    d = projects / name
    if d.exists():
        raise SystemExit(f"{d} は既にある。上書きしない")
    n = len(islands(load_layout(layout)))
    if pieces is None:
        if n > 2:
            raise SystemExit(f"配列の島が {n} 個ある。--pieces で名付ける")
        pieces = ("main",) if n == 1 else ("left", "right")
    if len(pieces) != n:
        raise SystemExit(f"配列の島は {n} 個、--pieces は {pieces}")
    (d / "docs" / "decisions").mkdir(parents=True)
    (d / "pcb").mkdir()
    shutil.copy(layout, d / "layout.json")
    sub = dict(NAME=name, PIECES=repr(tuple(pieces)), SHIELD=name)
    (d / "spec.py").write_text(Template((TEMPLATES / "spec.py.tmpl").read_text()).substitute(sub))
    for f in PROJECT_DOCS:
        (d / "docs" / f).write_text(Template((TEMPLATES / f).read_text()).safe_substitute(sub))
    (d / "docs" / "decisions" / "README.md").write_text(
        "# 決定の記録\n\n1 件 1 ファイル `YYYY-MM-DD-slug.md`。雛形は docs/templates/decision.md。\n"
        "覆す前に読む。前提が動いたら読み直す。\n")
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("layout", type=Path)
    ap.add_argument("--pieces", type=lambda s: tuple(s.split(",")))
    a = ap.parse_args()
    d = create(a.name, a.layout, a.pieces)
    p = load(d)
    made, unknown = zmk.scaffold(p)
    zmk.write_transform(p)
    zmk.add_to_build_yaml(p)
    print(f"作った {d.relative_to(ROOT)}/")
    for f in made:
        print(f"作った {f.relative_to(ROOT)}")
    if unknown:
        print(f"⚠ キーマップで &none にした刻印: {unknown}")
    print(f"""
次にやること（CLAUDE.md「新しい機種を始める」）:
  1. projects/{a.name}/spec.py の値を決める（なぜその値かをコメントに）
  2. tools/kb {a.name} plate   → build/{a.name}/plate_*.png を自分の目で見る
  3. tools/kb {a.name} pcb     → tools/kb {a.name} render で絵を見る
  4. spec.ZMK["pins"] を書いて python -m foundry.zmk {a.name}（#error が消えるまでビルドは止まる）
  5. .venv/bin/pytest tests -q""")


if __name__ == "__main__":
    main()
