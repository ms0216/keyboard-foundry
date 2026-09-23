# tests/fixtures/seeed_xiao（出典とライセンス）

| ファイル | 出典 | 改変 |
|---|---|---|
| `XIAO-nRF52840-SMD.kicad_mod` | Seeed Studio「OPL_Kicad_Library」の `Seeed Studio XIAO Series Library/XIAO-nRF52840-SMD.kicad_mod`（<https://github.com/Seeed-Studio/OPL_Kicad_Library>・commit `3be8215d3db652e2f62269913cb1fddd5e737d38`） | **なし**（上の commit の中身と sha256 `bea5909c…d7c7e2` が一致することを 2026-09-24 に GitHub API で確かめた） |
| `pins.json` | 同じライブラリの記号 `XIAO-nRF52840-SMD`（`Seeed_Studio_XIAO_Series.kicad_sym`・commit `b0035c51eb0348bb3e165fdb2f2765fa3d1d17bd`）から、パッドの番号とピンの名前の対応だけを書き写したもの | 自分で書いた対応表（出典は `source` に書いてある） |

**ライセンス**: OPL_Kicad_Library は **CC-BY-SA-4.0**（リポジトリの `LICENSE`。GitHub API の
`repos/Seeed-Studio/OPL_Kicad_Library/license` が `CC-BY-SA-4.0` と返すことを 2026-09-24 に確かめた）。
上の `.kicad_mod` は同じ CC-BY-SA-4.0 のもとで、改変せずに再配布している。
© Seeed Studio。ライセンスの全文: <https://creativecommons.org/licenses/by-sa/4.0/>

使い道: tests/test_cckb_pcb.py が、CCKB の基板の XIAO のパッドを Seeed のフットプリントと突き合わせる
（自分のフットプリントを自分で書いた値と比べない。CLAUDE.md 検証の作法 3）。
