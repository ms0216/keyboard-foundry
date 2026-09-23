"""基板の DRC を走らせ、結果を**基板の指紋つきで**記録する。

    .venv/bin/python3 -m foundry.drc <板.kicad_pcb>...     # 指定した板
    .venv/bin/python3 -m foundry.drc --all                # projects/*/pcb/*.kicad_pcb（未配線は除く）

記録は板の隣の `<板>.drc.json`。CI には KiCad が無いので DRC 自体は走らないが、
**記録が今の板から作られたか**は tests/test_pcb_records.py が指紋で見る。
これが無いと「板を直したが DRC をかけ直していない」まま発注する（HHKB で実際に
DRC は手で叩いたときしか走っていなかった）。

⚠️ **`--severity-error` を渡さない。**渡していた間、HHKB は「違反 0」と言いながら
警告 72 件（実害候補の hole_to_hole を含む）を構造的に隠していた。
警告は合否に入れないが、**種類ごとに数えて必ず出す**（0 のときも「警告 0」と書く）。
重大度の無いものはエラー扱い（分からないものを軽い方へ倒すと見えなくなる）。
"""

import json
import subprocess
import sys
from pathlib import Path

from .boardhash import fingerprint
from .paths import KICAD_CLI, PROJECTS


def report_path(board):
    return Path(str(board)[:-len(".kicad_pcb")] + ".drc.json")


def run(board):
    board = Path(board)
    raw_path = board.with_suffix(".drc-raw.json")
    # **隣の .kicad_pro ごと**読ませる（規則はそこにある）。板だけを別の場所で
    # 回すと別物に見える（HHKB #50）。stderr を捨てない
    r = subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "-o", str(raw_path),
                        str(board)], capture_output=True, text=True)
    if r.returncode not in (0, 5) or not raw_path.exists():   # 5 = 違反あり
        raise RuntimeError(f"kicad-cli が失敗（{r.returncode}）: {r.stderr.strip()[-400:]}")
    raw = json.loads(raw_path.read_text())
    raw_path.unlink()

    def split(items):
        return ([v for v in items if v.get("severity") != "warning"],
                [v for v in items if v.get("severity") == "warning"])

    v_err, v_warn = split(raw.get("violations", []))
    u_err, u_warn = split(raw.get("unconnected_items", []))
    kinds = {}
    for w in v_warn + u_warn:
        kinds[w.get("type", "?")] = kinds.get(w.get("type", "?"), 0) + 1
    record = {
        "board": board.name,
        "fingerprint": fingerprint(board),
        "violations": len(v_err),
        "unconnected": len(u_err),
        "warnings": len(v_warn) + len(u_warn),
        "warning_kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
        "violation_kinds": sorted({v.get("type", "?") for v in v_err}),
        "details": [v.get("description", "") for v in v_err][:20],
    }
    report_path(board).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def main(argv):
    boards = ([b for b in sorted(PROJECTS.glob("*/pcb/*.kicad_pcb"))] if "--all" in argv
              else [Path(a) for a in argv])
    if not boards:
        raise SystemExit("板を指すか --all")
    bad = 0
    for b in boards:
        r = run(b)
        ok = r["violations"] == 0 and r["unconnected"] == 0
        bad += not ok
        print(f"{'OK' if ok else 'NG'} {b.name}  違反 {r['violations']} / 未配線 {r['unconnected']}"
              f" / 警告 {r['warnings']}")
        for d in r["details"]:
            print(f"      {d}")
        for kind, n in r["warning_kinds"].items():
            print(f"      ⚠ {kind} {n} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
