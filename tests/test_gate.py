"""発注の門。**散文では開かず、見出しでだけ開くこと。開くこともあること。**"""

from foundry.gate import blockers, is_gate_open

DOC = """# 実機とまだ違うところ

## いま残っているもの（2026-09-23 に棚卸し）

### ★ 発注をせき止めているもの

| # | 何 | 次の一手 |
|---|---|---|
| ~~**#3**~~ | ~~済んだもの~~ **✅ 決着** | **無し** |
| **#7** | アンテナが地板に挟まれている | 測る |

### 物を買う・刷るまで進まないもの

| # | 何 | 要るもの |
|---|---|---|
| #9 | 公差 | クーポン |
"""


def test_an_open_row_closes_the_gate():
    assert blockers(DOC) == ["7"]
    assert not is_gate_open(DOC)


def test_prose_that_quotes_the_heading_does_not_open_it():
    doc = DOC + "\n本文: 解けなければ「### 承知して発注する #7」を書く。\n"
    assert not is_gate_open(doc)


def test_the_acceptance_heading_opens_it():
    assert is_gate_open(DOC + "\n### 承知して発注する #7\n\n利用者が 2026-09-23 に承知。\n")


def test_striking_the_row_through_opens_it():
    assert is_gate_open(DOC.replace("| **#7** |", "| ~~**#7**~~ |"))


def test_rows_outside_the_blocking_table_do_not_count():
    assert "9" not in blockers(DOC)
