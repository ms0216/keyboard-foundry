# ZMK と XIAO nRF52840

HHKB の `docs/hardware/task-c1〜c4-c5*.md`・`xiao-flash-recovery.md`・`config/` で確かめたこと。

## ビルド

- **手元に Zephyr SDK は無くてよい。**push → GitHub Actions（ZMK 公式の再利用ワークフロー）→
  Artifacts の `firmware` から `.uf2`。`config/` と `build.yaml` はリポジトリ直下（入れ子は
  "no west workspace found"）。build.yml は `paths:` で文書だけの push を除く——**足りないと
  変えたのに焼かれない**（HHKB で 2 週間ビルドされないまま放置された）
- ボードは `xiao_ble//zmk`（Zephyr 4.1 以降。`seeeduino_xiao_ble` でつまずいた）
- `Kconfig.shield` の `shields_list_contains` の引数がシールド名と違うと**黙って無視される**
  （`python -m foundry.check_zmk_config` が見る）
- リポジトリ自身を ZMK モジュールにできる（`zephyr/module.yml`）。モジュールから ZMK の
  ヘッダを使うには `zephyr_include_directories(${CMAKE_SOURCE_DIR}/include)`
  （`ZEPHYR_ZMK_MODULE_DIR` は空になる）
- 成果物 `<shield>-xiao_ble__zmk-zmk.uf2`。**BLE が入っているかは大きさで分かる**
  （左 約 470KB・ログ入り 約 570KB・115KB 級なら BLE が抜けている）
- 「CI でビルド成功」と「実機で確認」を分けて書く

## 書き込み・復旧

- RESET を素早く 2 回 → `XIAO-SENSE` ドライブ（通常版でもこの名前）
- macOS のエラー -36・`cp: Device not configured`・「ディスクの不正な取り出し」は正常
- **書き込みツールの「成功」を信用しない。**`CURRENT.UF2` を読み返す（UF2 は 512B ブロック・
  マジック 0x0A324655）。SoftDevice S140 7.3.0 が 0x1000〜0x27000
- SoftDevice が消えた XIAO の復旧: Adafruit_nRF52_Bootloader 0.11.0 の zip から SoftDevice
  だけを `adafruit-nrfutil dfu genpkg --dev-type 82 --sd-req 0xFFFE` → `dfu serial`。
  **`--singlebank` は付けない**（8% しか書けないのに「programmed」と言う）
- `settings_reset` を build.yaml に常に入れる。「一覧に出るのに繋がらない」は片方だけが相手を
  覚えている状態。**左・右・ホストの 3 者を全部消す**。焼いたら本来のファームを焼き直す
- 両方に左用を焼くと 2 台ともセントラルになる。マスキングテープで印を付ける
- キーマップに `&bootloader` と `&bt BT_CLR`（`dt-bindings/zmk/bt.h` が要る）を必ず置く
  （ケースを開けずに復旧できる）

## 設定の定石（HHKB の .conf）

| 設定 | 理由 |
|---|---|
| `CONFIG_ZMK_SLEEP=y`・`IDLE_SLEEP_TIMEOUT=1800000` | 既定は n。スリープ 2〜3µA。30 分で約 16 ヶ月、無しで約 5 ヶ月 |
| デバウンス 押し 3 / 離し 5ms | 同じ文字の重複は機械的バウンス（ゴーストなら違う文字が出る） |
| `BT_PERIPHERAL_PREF_MIN/MAX_INT=12`・`LATENCY=30`・`TIMEOUT=600` | **ZMK 既定（min 7.5ms）は Apple §58.6 違反で、macOS は要求ごと捨てる。**適合させて 0.63 → 0.43mA、遅延は増えない（latency は無料、間隔は有料） |
| `SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING/PROXY` | 右の残量も左から見える |
| 595 の `spi-max-frequency = <4000000>` | 200kHz では数珠つなぎで速い打鍵を取りこぼす報告がある。試験も本番と同じ周波数で |
| 残量計は `foundry,battery-alkaline`（firmware/） | ZMK 標準はリチウム曲線で 3.45V 以下が 0%。乾電池では常に 0% |
| `/delete-property/ power-gpios;` | 板の vbatt と合体し、XIAO 内蔵分圧の P0.14 を毎回叩いて 10ms 待っていた |

- `Apple §58.6`: latency ≤ 30・timeout 6〜18 秒・Min ≥ 15ms かつ 15ms の倍数・
  timeout ＞ Max × (lat+1) × 3。**規則違反で「通った」設定は採らない**（OS 更新で黙って戻る）
- ZMK の分割セントラルは、ペリフェラルが揃うまでスキャンをやめない（片側不在で 3.7mA）。
  Kconfig の入口は無い
- 分割間隔を伸ばすと右手だけ遅れる（左右差）。ホスト間隔は両手に等しく乗る
- 送信電力は既定の 0dBm が正解（+8dBm は +0.10mA、技適の 6.0mW を公称で超える可能性）
- `ZMK_BLE` は `select BT_PERIPHERAL` で、ホスト側 BLE だけを止めることはできない

## キーマップ・行列

- キーマップを解釈するのはセントラルだけ（右に焼いたキーマップは使われない）
- `&bootloader` は押された側で動く。`&bt` は常に左で動く
- conditional-layers は修飾キーを扱えない → Fn+Ctrl は FN 面の Ctrl の位置に `&mo SYS`
- 分割は transform を 1 つ共有し、右は overlay で `col-offset`。row-gpios は左右の overlay に置ける
  （左右で FFC の向きが違うなら行の並びも違ってよい。ファームで吸収し、配線をひねらない）
- ZMK の `gpio_595`: 最下位バイトが鎖の先頭・MSB first。`&shifter 0` が QA、`&shifter 8` は 2 個目の QA。
  待機中は全列 High（何も押さず QA が 3.3V なら 595 まで届いている）。STCP が外れていても
  `spi_write_dt()` は成功を返す
- 押した直後の 1 回目の走査だけ全列 High になる（ISR から SPI を使えず -EWOULDBLOCK が捨てられる）。
  デバウンスが吸収する。症状が出たら `CONFIG_ZMK_KSCAN_MATRIX_POLLING=y`

## XIAO のピン

- ピン間隔 0.6 インチ（15.24mm）。ブレッドボードでは d 行と h 行（外形 17.8 とは違う）
- USB を奥に向けて上から: 左列 D0〜D6、右列 5V・GND・3V3・D10・D9・D8・D7（**D7 が最下端**）。
  ピン番号のシルクは裏面だけ
- SPI: SCK=D8（P1.13）/ MOSI=D10（P1.15）/ **D9 は pinctrl が MISO に確保**。CS は D7
  （ZMK 公式サンプルの D9 は pinctrl と衝突しうる）
- ADC は D0〜D5 だけ（P0.02/03/28/29/04/05）
- UART ログ: `chosen { zephyr,console = &uart0; }`・`&uart0 { status = "okay"; }`・
  `CONFIG_ZMK_LOG_LEVEL_DBG=y`。**overlay に `&uart0` を置くだけで +0.46mA。**
  `CONFIG_BT_CONN_LOG_LEVEL_DBG` は禁止（ログが溢れて BLE 接続まで壊れた）
- `CONFIG_ZMK_USB=y` のファームは USB を抜いても掴んだまま → 電流を測る前に電池を入れ直す
- macOS: `ioreg -p IOUSB -w0` で `!registered` なら「アクセサリの接続を許可」。
  長押しのアクセント候補は `defaults write -g ApplePressAndHoldEnabled -bool false`
