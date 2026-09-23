"""発注の門。**機種の open-gaps.md に「発注をせき止めているもの」が残っていれば閉じる。**

    .venv/bin/python3 -m foundry.gate <機種>      # 閉じていれば終了コード 1

規則（docs/templates/open-gaps.md の書式）:
  - `### ★ 発注をせき止めているもの` の表で、**取り消し線の無い行**が止めている項目
  - 解けないと結論した項目は `### 承知して発注する #N` の見出しを立て、誰が・いつ・
    駄目だったとき何を作り直すかを書く。**見出し（行頭）だけが門を開ける**——
    HHKB では門を説明する散文そのものが門を開けていた（2026-08-11）

HHKB の export_fab は #23（アンテナ）1 件の見出しを直に見ていた。ここでは表から読む。
"""

import re
import sys

BLOCKING = "### ★ 発注をせき止めているもの"


def blockers(doc):
    """止めている項目の番号（#N）。取り消し線の行は済み。"""
    m = re.search(rf"^{re.escape(BLOCKING)}\s*$(.*?)(?=^#{{1,3}} |\Z)", doc, re.M | re.S)
    if not m:
        return []
    out = []
    for row in re.findall(r"^\|(.*)$", m.group(1), re.M):
        first = row.split("|")[0].strip()
        if first.startswith("~~") or set(first) <= set("-: "):
            continue
        n = re.search(r"#(\d+[a-z]?)", first)
        if n:
            out.append(n.group(1))
    return out


def accepted(doc):
    return set(re.findall(r"^### 承知して発注する\s+#(\d+[a-z]?)\s*$", doc, re.M))


def is_gate_open(doc):
    return not (set(blockers(doc)) - accepted(doc))


def main(argv):
    from .project import load

    p = load(argv[0])
    doc = (p.root / "docs" / "open-gaps.md").read_text()
    left = sorted(set(blockers(doc)) - accepted(doc))
    if left:
        print(f"閉 {p.name}: 発注をせき止めているもの {['#' + n for n in left]}")
        return 1
    print(f"開 {p.name}: せき止めているものは無い"
          + (f"（承知して発注: {sorted(accepted(doc))}）" if accepted(doc) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
