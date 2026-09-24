/*
 * 打ち止め電圧を割ったら、自分から止まる（open-gaps #25b）。
 *
 * 何が起きるか:
 *   レールが 1.7V を割ると nRF52840 はブラウンアウトでリセットする。
 *   電池は負荷が消えると電圧が戻るので、リセット → 起動 → 広告 →
 *   電圧降下 → リセット を繰り返す。
 *     - 残り少ない電池を早く使い切る
 *     - 使う側からは故障に見える
 *     - **低電圧での flash 書き込みでペアリング情報が壊れうる**
 *       （nRF52840 の NVMC は VDD ≧ 1.7V が条件）
 *
 * どう止めるか:
 *   ZMK が電池を測る周期（ZMK_BATTERY_REPORT_INTERVAL・既定 60 秒）と
 *   同じ周期の自前タイマーで、**毎回自分で測ってから**電圧を読む。
 *   打ち止め（devicetree の empty-millivolts）を下回った状態が規定回数
 *   続いたら zmk_pm_soft_off() に入る。
 *
 *   ⚠️ 2026-09-25 まで driver のキャッシュを読むだけだった（「ZMK が同じ周期で
 *   fetch 済み」）。ZMK はアイドル（キーを 30 秒押さない）とスリープで測定の
 *   タイマーを止める（ZMK app/src/battery.c の battery_event_listener:
 *   ZMK_ACTIVITY_IDLE・SLEEP で k_timer_stop(&battery_timer)。main af96766 で確認）。
 *   そのためアイドル中は**最後の 1 回の測定**を何度も数え、送信中の一時的な
 *   降下 1 回で止まりえた（CCKB 4 回目の監査 F 重要 1）。起動直後にキーを
 *   押さなければ、起動の瞬間の 1 回を 2 回と数えていた。
 *   測る費用は 60 秒に 1 回の SAADC の変換（40µs × 4 の平均）。ZMK の測定と
 *   同じ低優先の work queue で回すので、fetch と channel_get の間に ZMK の
 *   fetch が割り込まない（battery_alkaline.c の alk_channel_get の注記）。
 *   検査: tests/test_firmware.py（ホストの代役の上でこのファイルを回す）。
 *
 *   ⚠️ 2026-09-03 まで zmk_battery_state_changed を待ち受けていたが、
 *   ZMK 本体（app/src/battery.c）はその事象を **% が変わったときしか
 *   出さない**（last_state_of_charge != val1）。% が 0 に張り付くと
 *   2 回目が来ず、止まらなかった。周期で読む形に直した。
 *
 *   USB 給電中は判定しない。電源スイッチ OFF＋USB のとき分圧の読みは電池の電圧では
 *   ない（0mV とは限らない: 3V3 からショットキーの逆向きの漏れ電流が 2MΩ の分圧に入り、
 *   数 V まで浮きうる。CCKB 監査 F-3・未実測）。0 付近に読めれば USB でつないだ瞬間に
 *   soft off し、浮けば残量の表示が狂うだけ。どちらにしても USB 給電中は数えない。
 *
 * 復帰:
 *   電池を替えれば、電源スイッチが電池を機械的に切り離しているので
 *   入れ直しで起動する。soft off の wake ピンには依存しない。
 *
 * ⚠️ **これはビルドが通っているだけで、実機では一度も動かしていない。**
 *    確かめるのは Task C4/C5（電池を実際に使い切る試験）。
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <zephyr/init.h>

#include <zmk/pm.h>
#include <zmk/workqueue.h>
#if IS_ENABLED(CONFIG_ZMK_USB)
#include <zmk/usb.h>
#endif

LOG_MODULE_DECLARE(foundry_battery, CONFIG_SENSOR_LOG_LEVEL);

#define BATTERY_NODE DT_CHOSEN(zmk_battery)

BUILD_ASSERT(DT_NODE_HAS_PROP(BATTERY_NODE, empty_millivolts),
             "chosen zmk,battery に empty-millivolts が無い。"
             "foundry,battery-alkaline を使うこと");

#define EMPTY_MV DT_PROP(BATTERY_NODE, empty_millivolts)

static const struct device *const battery = DEVICE_DT_GET(BATTERY_NODE);

static void low_battery_check(struct k_work *work) {
    static uint8_t consecutive;

#if IS_ENABLED(CONFIG_ZMK_USB)
    if (zmk_usb_is_powered()) {
        consecutive = 0;
        return;
    }
#endif

    /* **毎回測り直す。**キャッシュは ZMK がアイドルに入る前の古い測定のことがある
     * （冒頭のコメント）。数えるのは、いま測った値だけ。 */
    int rc = sensor_sample_fetch_chan(battery, SENSOR_CHAN_GAUGE_VOLTAGE);
    if (rc != 0) {
        LOG_WRN("電池電圧を測れない (%d)。判定を飛ばす", rc);
        return;
    }
    struct sensor_value voltage;
    rc = sensor_channel_get(battery, SENSOR_CHAN_GAUGE_VOLTAGE, &voltage);
    if (rc != 0) {
        LOG_WRN("電池電圧が読めない (%d)。判定を飛ばす", rc);
        return;
    }

    uint32_t mv = voltage.val1 * 1000U + voltage.val2 / 1000U;
    if (mv > EMPTY_MV) {
        consecutive = 0;
        return;
    }

    consecutive++;
    LOG_WRN("電池が打ち止め %u mV を下回った（%u mV・%u 回目）", (unsigned)EMPTY_MV,
            (unsigned)mv, (unsigned)consecutive);

    /* 1 回では止めない。BLE 送信中は電池の内部抵抗ぶん一時的に下がる。 */
    if (consecutive < CONFIG_FOUNDRY_LOW_BATTERY_SOFT_OFF_SAMPLES) {
        return;
    }

    LOG_ERR("電池が尽きた。soft off に入る（電池を替えて電源を入れ直すこと）");
    zmk_pm_soft_off();
}

K_WORK_DEFINE(low_battery_work, low_battery_check);

static void low_battery_tick(struct k_timer *timer) {
    k_work_submit_to_queue(zmk_workqueue_lowprio_work_q(), &low_battery_work);
}

K_TIMER_DEFINE(low_battery_timer, low_battery_tick, NULL);

static int low_battery_init(void) {
    /* 最初の 1 周は待つ（起動の瞬間は BLE の立ち上げと重なる。判定は起動の 65 秒後から）。 */
    k_timer_start(&low_battery_timer, K_SECONDS(CONFIG_ZMK_BATTERY_REPORT_INTERVAL + 5),
                  K_SECONDS(CONFIG_ZMK_BATTERY_REPORT_INTERVAL));
    return 0;
}

SYS_INIT(low_battery_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
