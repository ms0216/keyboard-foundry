# Choc スタビ（2u）の寸法は、製造図と Keebio の開口の 2 出典が一致した値を使う

- **日付:** 2026-09-23
- **状態:** 決定
- **決めた人:** Claude（利用者の指示のもとで作業）

## 1. なぜ決める必要が生じたか

CCKB は HHKB 英語配列のスペースを 2.25+1.5+2.25u に分けた配列（`projects/cckb/layout.json`）で、
Enter・左 Shift・スペース左右の計 4 キーが 2.25u 以上になりスタビが要る。プレートの開口と
基板の逃げ穴の寸法はスタビの寸法で決まるため、CHOC_V1（`foundry/mech.py`）の `stab_offset`・
`stab_kind` を埋める必要があった（Task 2 まではこれらが未定義で、2u 以上のキーで落ちる
状態にしてあった）。

## 2. 事実はどうか（測った・読んだもの。出所を書く）

- **Kailh 系製造図**（AliExpress の商品画像、中国語の工場図面。
  `projects/cckb/docs/references/kailh_choc_stab_drawing.png` に保存）。自分の目で読んだ値:
  - 2u ワイヤ: 24.00⁰₋₀.₀₅（端口切平）
  - ワイヤの脚: 10.00±0.1、曲げ R1.50/R0.50、90°
  - ワイヤ径: φ1.00⁰₋₀.₀₃/⁰₋₀.₀₅
  - 76.00±0.1 の長いワイヤ（同じ脚形状）も同シートに記載
  - ハウジング: 幅 6.30⁺⁰·⁰²₋₀·⁰⁵・奥行 6.60（図の 6.60⁻⁰·⁰³系の寸法）・突起 3.20⁺⁰·⁰⁸／⁰・
    高さ 4.30・全体の外包絡 7.60×7.30×12.80 系
  - この画像は WebP で配信されるため `sips -s format png` で PNG に変換して保存した
    （手順は task brief Step 1 の curl/sips コマンドのまま実行）
- **Keebio-Parts.pretty の `Kailh-PG1350-Stab-Cutout.kicad_mod`**
  （`projects/cckb/docs/references/` に保存。GitHub raw から取得）。
  開口の中心（支点）は x=±12.0 で、輪郭は右側（x>8）で
  (8.85,3.05)(8.85,−3.8)(10.2,−3.8)(10.2,−8.45)(13.8,−8.45)(13.8,−3.8)(15.15,−3.8)(15.15,3.05)
  （KiCad 座標・Y 下向き）。

両出典の支点間隔（製造図のワイヤ 24.00 ↔ Keebio の開口中心 ±12.0）が一致することを
`tests/test_choc.py::test_the_stab_half_span_is_the_drawings_wire` で照合している。

## 3. 効く条件（候補を並べる前に全部書く）

| # | 条件 | 実データ | 何で確かめたか（外 / 自分の生成物） |
|---|---|---|---|
| 1 | スタビ支点の間隔 | 24.0mm（半間隔 12.0） | 外：製造図のワイヤ寸法とKeebioの開口中心、2出典の一致 |
| 2 | プレートの開口輪郭 | Keebio の8点（右側）、左右対称 | 外：Keebio の kicad_mod（Kailh 系実装での実績） |
| 3 | 開口とハウジングの隙間 | 奥行 +0.25・切り欠き +0.4 | 外：Keebio の輪郭値と製造図のハウジング寸法の差分 |
| 4 | ワイヤの向き | 常に奥（切り欠きが奥側） | 外：製造図とKeebioの輪郭の対応（Chocでは最前列でも回さない） |
| 5 | スイッチ開口とスタビ開口の間の桟 | ≧1.6mm（0.4×4以上） | 自分の生成物（CHOC_STAB_OUTLINEとcutout=13.8の差分計算）。刷れる幅として検査で担保 |
| 6 | プレートの下に出る量 | 未確認（二次情報のみ 2.5〜3.5mm） | 未確認。基板の逃げ穴は組み立てモデルで決める（計画3のpcb_extra） |

## 4. 影響範囲（信号や力の流れに沿って端から端まで）

- `foundry/mech.py`: `CHOC_STAB_OUTLINE`（新規定数）・`CHOC_V1.stab_offset`・`stab_kind` を埋めた。
  `MX_HOTSWAP`（Cherry の分岐）には触れていない。
- `foundry/plate.py`: `build_plate` のスタビ分岐に `stab_kind == "choc"` の枝を足した
  （`choc_stab_polygons` を新規に追加）。`stab_kind == "cherry"` の経路（`stab_cutout_face`）は
  無変更（HHKB 回帰検査 `tests/test_regression_hhkb.py` で確認、バイト単位で挙動を変えていない）。
- プレートの開口が決まったことで、基板側の逃げ穴（`pcb_extra.py`）の設計が可能になる
  （こちらは計画 3 の範囲。本タスクでは未着手）。
- ケース側（プレートの下に出る量に応じた逃げ）は現時点で未確認のため、部品が届いてからの
  試し刷りで確かめる必要がある（下記「まだ決めていないこと」）。

## 5. 決めたこと

- `mech.CHOC_STAB_OUTLINE`: 右側の開口を **支点を原点・Y 上向き・奥が +y** で
  `((-3.15, -3.05), (-3.15, 3.8), (-1.8, 3.8), (-1.8, 8.45), (1.8, 8.45), (1.8, 3.8), (3.15, 3.8), (3.15, -3.05))`
  と定義した（Keebio の輪郭を Y 上向き・支点原点に変換した値と一致）。
- `CHOC_V1.stab_offset = {2.0: 12.0, 2.25: 12.0}`、`stab_kind = "choc"`。
- `plate.choc_stab_polygons(s, at)` で左右 2 つの開口の多角形を返し、`build_plate` はこれを
  build123d の `BuildSketch(mode=Mode.PRIVATE)` → `BuildLine` → `Polyline(close=True)` →
  `make_face()` → `add(..., mode=Mode.SUBTRACT)` の手順でプレートから引く。
  **kerf は 0**（Keebio の輪郭が既に隙間込みのため、Cherry のような `offset()` は行わない）。

## 検討して捨てた案

| 案 | 捨てた理由 |
|---|---|
| Keebio のスイッチ開口 14.0 を Choc にも流用 | Kailh の図面は 13.8（Task 2 で確認済み）。Keebio の 14.0 は MX と共用の値で Choc 固有ではない |
| Gemini Deep Research の報告のプレート厚許容 1.10〜1.30mm | 根拠となる一次資料が示されておらず、既に `plate_t=1.2`（Kailh 図面 CPG135001D01 由来、Task 2 で確定）と矛盾しない範囲の主張に過ぎないため採らない。裏取りできる出典がない |
| Gemini Deep Research の報告の「CFX（キーキャップ互換規格）適合」 | 二次情報 1 件のみで、かつ本プロジェクトはキーキャップを自分で刷る方針のため不要になった主張 |

## この決定が乗っている前提（動いたら読み直す）

- CCKB は Kailh Choc V1（PG1350）をプレートマウントで使う前提（`spec.SWITCH = "choc_v1"`）。
  スイッチの種類が変われば本決定全体を読み直す。
- スタビが要るキーは 2.0u・2.25u のみ（HHKB 英語配列のスペース分割・Enter・左 Shift）。
  レイアウトが変わり 2.75u 以上のキーが出た場合、`stab_offset` にそのキー幅を追加するかどうか
  再検討が要る（現状は未対応で `stab_offset_for` が例外を出す設計、`mech.py` 参照）。
- プレート厚 `plate_t=1.2` は Task 2 の決定に乗っている。プレート厚が変わると、本決定の
  「ハウジングがプレートの下に出る」という前提（4.30 > 1.2+1.0）も再計算が要る。

## 覆す前に読むこと

- `tests/test_choc.py` のスタビ関連テスト一式（`test_the_stab_half_span_is_the_drawings_wire`・
  `test_the_stab_outline_is_keebios`・`test_the_outline_leaves_a_web_to_the_switch_opening`・
  `test_the_plate_cuts_both_stab_openings`）。
- `projects/cckb/docs/references/kailh_choc_stab_drawing.png` と
  `Kailh-PG1350-Stab-Cutout.kicad_mod`（出典そのもの）。

## まだ決めていないこと

| 項目 | 決められない理由 |
|---|---|
| プレートの下に出る量の正確な値 | 製造図・Keebio ともに二次的にしか示されておらず（2.5〜3.5mm 相当の情報のみ）、一次資料での確証がない。部品が届いたら試し刷りの小片でスタビを押し込み、実測で確かめる |
| 基板の逃げ穴の大きさ・位置 | 組み立てモデル（3D）で決める。計画 3 の pcb_extra の範囲 |
