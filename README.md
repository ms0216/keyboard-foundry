# keyboard foundry

自作キーボードを**現物になる前に機械で確かめながら**作るための作業場。
KLE の配列 1 本から、プレート（STL）・キーマトリクスの基板（KiCad・JLCPCB の規則入り）・
ZMK のシールドを作り、それらが食い違わないことを検査する。

HHKB 分割機（`../2608042258_HHKB_devided`）の開発で積み上げた道具・検査・知識・作法を
抜き出したもの。**核の生成器は、HHKB の発注済みの基板を再現できる**
（キーまわりの全 140 部品の位置・向き・面・フットプリントと、全 244 パッドの結線が一致。
tests/test_regression_hhkb.py）。

## 構成

```
foundry/          共通の核（Python）
  layout.py         KLE → キーの実寸座標。島（分割の左右）に分ける
  matrix.py         キー → (row, col)。基板とファームが同じものを読む
  project.py        機種（projects/<機種>/spec.py + layout.json）を読む
  mech.py           MX・スタビ・ホットスワップの規格値
  plate.py          プレート（build123d）
  pcb.py            未配線の基板（KiCad の Python）。スイッチ・ダイオード・スタビ・穴・JLC 規則
  zmk.py            ZMK シールドの雛形と行列表
  fab_fields.py     発注道具（Fabrication Toolkit）が読む LCSC・面・除外を板に焼く
  drc.py            DRC を指紋つきで記録（警告を隠さない）
  render_pcb.py     基板を絵にする（変わっていなければ描かない・動いた部品を拡大）
  verify.py         寸法・水密・干渉（結果の記憶つき）・図
  inspect_mesh.py / slice_check.py   印刷できるか（近似と、OrcaSlicer で実際にスライス）
  gate.py           発注の門（open-gaps の「せき止めているもの」）
  parts.py          HHKB で確かめた部品と選定理由
  pinmap.py         ピン名 → パッド番号（データシートで裏付け）
  mutate.py         定数を壊して検査が気づくかを測る
  jlcpcb_lookup.py  JLCPCB の API（区分・在庫・単価）
firmware/ zephyr/ ZMK モジュール（乾電池の残量計・打ち止めで停止・状態 LED）
config/ build.yaml ZMK の設定（機種を作ると足される）
lib/              フットプリント（kiswitch の MX ホットスワップ・スタビ、XIAO）
projects/<機種>/  spec.py・layout.json・docs/（台帳）・pcb/
tests/            検査。fixtures/ に HHKB の配列と発注済みの基板から抜き出した事実
tools/kb          機種ごとの操作の入口 / tools/new_project.py
docs/method/      失敗から出た規則
docs/knowledge/   部品・電源・基板・筐体・ZMK・アンテナ・測り方
docs/templates/   台帳の雛形
.claude/          基板が変わったら絵を出して「見ろ」と言う hook
```

## 始め方

```sh
python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests -q                              # 全部緑であること

.venv/bin/python3 tools/new_project.py mykb path/to/kle.json
tools/kb mykb plate        # build/mykb/plate_*.stl / .png
tools/kb mykb pcb          # projects/mykb/pcb/unrouted/*.kicad_pcb（KiCad 10 が要る）
```

次にやることは CLAUDE.md の「新しい機種を始める」。

## 要るもの

| 道具 | 何に | 場所の指定 |
|---|---|---|
| Python 3.13 + requirements-dev.txt | 核・検査 | — |
| KiCad 10（同梱の Python と kicad-cli） | 基板の生成・DRC・絵 | `KICAD_PYTHON` `KICAD_CLI` `KICAD_FOOTPRINTS` |
| pdftoppm（poppler） | 基板の絵 | PATH |
| OrcaSlicer | スライスの確認 | `ORCA_SLICER` |
| GitHub Actions | ZMK のビルド（手元に SDK は要らない） | — |

## まだ核に入っていないもの（HHKB を参照実装として読む）

| もの | 理由 | HHKB の場所 |
|---|---|---|
| ケース・組み立て検査（留め方・挿入経路・干渉） | 機種の意匠そのもの。2 台目で共通部分を抜き出す | tools/gen_case.py・gen_assembly.py・envelopes.py |
| MCU 子基板・電源回路・回路図と ERC | 構成が機種ごとに違う（pcb_extra.py で足す） | tools/gen_daughterboard.py・circuit.py・gen_sch.py |
| 配線の仕上げ（GND ビア・手配線の再現） | 配線の品質は手作業から来ていた | tools/finalize_pcb.py・gnd_fanout.py・export_matrix_routing.py |
| .blend での確認 | ケースと一緒に | tools/export_assembly.py・blend_assembly.py |
