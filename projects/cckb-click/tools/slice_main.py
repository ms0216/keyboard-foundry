"""cckb-click の本番の刷る物（枠 2 枚・キャップの板 2 枚）を、精度優先の設定で**実際にスライスする**。

    .venv/bin/python3 projects/cckb-click/click_case.py                 # 先に STL を出す
    .venv/bin/python3 projects/cckb-click/tools/slice_main.py            # 0.4 ノズル・Bambu Studio
    .venv/bin/python3 projects/cckb-click/tools/slice_main.py orca       # OrcaSlicer で

スライスの仕方（設定の継承をたどる・ベッドの真ん中に回さず置く・G-code の設定の欄と突き合わせる）は、試し刷りと同じ
tools/slice_precise.py。出すのは時間・材料・層の数・効いた設定の数・警告。**出力を捨てない。**各行の頭に OK / NG。
結果は build/cckb-click/slice_main.json にも書く（文書の表はここから写す）。
"""

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import slice_precise as SP  # noqa: E402

STEMS = ("frame_left", "frame_right", "caps_1u", "caps_wide")
PLA = 1.24                  # g/cm3


def main(argv):
    only = next((a for a in argv if a in ("bambu", "orca")), "bambu")
    variant = next((a for a in argv if a in SP.S.PRINT_RECIPES), "n04")
    rc = SP.recipe(variant, SP.S, only)
    print(f"== {variant}・{only}: {rc['preset']['name']}（{rc['machine']['name']}・{rc['filament']['name']}）")
    newest = max(q.stat().st_mtime for q in SP.PROJECT.glob("*.py"))
    rows, bad = [], 0
    for stem in STEMS:
        stl = SP.BUILD / f"{stem}.stl"
        if not stl.exists() or stl.stat().st_mtime < newest:
            print(f"NG {stem}: STL が無いか、生成器より古い（click_case.py を回し直す）")
            bad += 1
            continue
        gcode, log = SP.slice_stl(rc, stl)
        if gcode is None:
            print(f"NG {stem}: スライスに失敗\n{log.strip()[-600:]}")
            bad += 1
            continue
        text = gcode.read_text(errors="replace")
        info = SP.summarize_gcode(gcode)
        total = re.search(r"total estimated time: ([^\n;]+)", text)
        used = re.search(r"; (?:total )?filament (?:used|length) \[mm\] ?[:=] ?([\d.]+)", text)
        cm3 = info.get("材料") or (f"{float(used.group(1)) * math.pi * 0.875 ** 2 / 1000:.2f}" if used else None)
        warns = sorted({ln.strip()[:160] for ln in log.splitlines() if re.search(r"warn|error|fail|cannot|invalid", ln, re.I)})
        problems, n = SP.applied_problems(rc, SP.gcode_config(text))
        bad += len(problems)
        grams = round(float(cm3) * PLA, 1) if cm3 else None
        print(f"{'NG' if problems else 'OK'} {stem}: 造形 {info.get('時間')}（準備込み {total.group(1).strip() if total else '?'}）・"
              f"材料 {cm3} cm3（約 {grams} g）・層 {info.get('層数')}・設定 {n} 個を G-code と突き合わせた・警告 {len(warns)}")
        for w in warns[:6]:
            print(f"     ! {w}")
        for q in problems:
            print(f"     NG {q}")
        rows.append(dict(name=stem, time=info.get("時間"), total=total.group(1).strip() if total else None, cm3=cm3, grams=grams,
                         layers=info.get("層数"), warnings=len(warns)))
    (SP.BUILD / "slice_main.json").write_text(json.dumps(dict(variant=variant, engine=only, rows=rows), ensure_ascii=False, indent=1) + "\n")
    print("NG" if bad else "OK", f"問題 {bad} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
