# ZMK モジュール（foundry）

リポジトリ自身が ZMK のモジュール（`zephyr/module.yml`）。ZMK 公式の再利用ワークフローが
`zephyr/module.yml` を見つけると自動で読み込む（別リポジトリは要らない）。

| 機能 | Kconfig | 使い方 |
|---|---|---|
| 乾電池の残量計 | `FOUNDRY_BATTERY_ALKALINE`（DT にノードがあれば自動で y） | シールドに `compatible = "foundry,battery-alkaline"` のノードを置き `chosen { zmk,battery = &vbatt; }` |
| 打ち止めで自分から止まる | `FOUNDRY_LOW_BATTERY_SOFT_OFF`（上と `ZMK_PM_SOFT_OFF` で自動） | `.conf` に `CONFIG_ZMK_PM_SOFT_OFF=y` |
| XIAO の RGB LED で状態表示 | `FOUNDRY_STATUS_LED`（既定 n） | `.conf` に `=y`。led0/1/2 のエイリアスが要る |

## 出どころ

HHKB 分割機（`../2608042258_HHKB_devided`・GitHub ms0216/hhkb-split）で書いて
CI でビルドしたもの。**foundry に移すにあたって名前だけ変えた**（`hhkb,` → `foundry,`・
`HHKB_` → `FOUNDRY_`）。**名前を変えてからはまだビルドしていない**——最初の機種の
シールドを build.yaml に足した push で CI がビルドする。そこまでは「未ビルド」。

ソースの注記にある `open-gaps #N`・`docs/hardware/…`・`tools/circuit.py`・`Task C4/C5`
は HHKB のリポジトリの記録を指す（経緯を消さないために残した）。

## 実機での確認状況（HHKB 時点）

- 残量計・打ち止め停止: CI でビルド成功・**実機での使い切り試験は未実施**（HHKB Task C4/C5）
- 状態 LED: CI でビルド成功・実機で点灯確認は利用者側の残タスク

## 乾電池 2 本・XIAO nRF52840 の場合のシールドの書き方（HHKB の実物）

```dts
/ {
	vbatt: vbatt {
		compatible = "foundry,battery-alkaline";
		io-channels = <&adc 0>;          /* D0/AIN0。分圧はスイッチの後ろ・ショットキーの手前 */
		output-ohms = <1000000>;
		full-ohms = <2000000>;
		empty-millivolts = <2400>;       /* 回路が動かなくなる電圧（機種ごとに計算する） */
		full-millivolts = <3300>;        /* 新品アルカリの開路電圧 1.65V × 2 */
		/delete-property/ power-gpios;   /* 板の vbatt と合体する。P0.14 を毎回叩いて 10ms 待っていた */
	};
	chosen { zmk,battery = &vbatt; };
};
```
