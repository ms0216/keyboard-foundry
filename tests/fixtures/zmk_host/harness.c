/*
 * low_battery_off.c の判定を、ZMK の電池の測り方（app/src/battery.c）を真似た代役の上で回す。
 *
 * 代役の残量計: sensor_sample_fetch_chan() で「いまの電圧」（now_mv）を測ってキャッシュに入れ、
 * sensor_channel_get() はキャッシュを返す（foundry の battery_alkaline.c と同じ）。
 * ZMK はアクティブの間だけ 60 秒ごとに fetch し、アイドル（キーを 30 秒押さない）で止める。
 *
 * 出力: 場面ごとに 1 行「名前 soft_off=<回数> fetch=<回数>」。判定は tests/test_firmware.py。
 */
#include <stdio.h>

#include "../../../firmware/src/low_battery_off.c"

const struct device host_battery;
static uint32_t cache_mv, now_mv;
static int fetches, soft_offs;
static bool usb;

int sensor_sample_fetch_chan(const struct device *dev, enum sensor_channel chan) {
    (void)dev;
    (void)chan;
    cache_mv = now_mv;
    fetches++;
    return 0;
}

int sensor_channel_get(const struct device *dev, enum sensor_channel chan, struct sensor_value *v) {
    (void)dev;
    (void)chan;
    v->val1 = (int32_t)(cache_mv / 1000);
    v->val2 = (int32_t)(cache_mv % 1000) * 1000;
    return 0;
}

void k_timer_start(struct k_timer *t, int delay, int period) {
    (void)t;
    (void)delay;
    (void)period;
}
int k_work_submit_to_queue(struct k_work_q *q, struct k_work *w) {
    (void)q;
    w->handler(w);
    return 0;
}
int zmk_pm_soft_off(void) {
    soft_offs++;
    return 0;
}
struct k_work_q *zmk_workqueue_lowprio_work_q(void) {
    return 0;
}
bool zmk_usb_is_powered(void) {
    return usb;
}

/* ZMK が最後に測った値 last_mv がキャッシュに残ったまま、アイドルで ZMK の測定が止まっている。
 * いまの電圧は now。low_battery_off のタイマーが ticks 回まわる。 */
static void scene(const char *name, uint32_t last_mv, uint32_t now, bool on_usb, int ticks) {
    cache_mv = last_mv;
    now_mv = now;
    usb = on_usb;
    fetches = soft_offs = 0;
    for (int k = 0; k < ticks; k++) {
        low_battery_tick(&low_battery_timer);
    }
    printf("%s soft_off=%d fetch=%d\n", name, soft_offs, fetches);
    /* 場面をまたいで数を持ち越さない（高い読みで 0 に戻す） */
    now_mv = cache_mv = HOST_EMPTY_MV + 500;
    usb = false;
    low_battery_tick(&low_battery_timer);
}

int main(void) {
    int (*init)(void) = host_init_low_battery_init;
    init();
    /* 送信中の一時的な降下を 1 回だけ測ってアイドルに入った（いまの電圧は十分）→ 止まらない */
    scene("stale_low", HOST_EMPTY_MV - 100, HOST_EMPTY_MV + 300, false, 3);
    /* 本当に尽きている → 2 回目で止まる。1 回では止まらない */
    scene("empty_once", HOST_EMPTY_MV - 100, HOST_EMPTY_MV - 100, false, 1);
    scene("empty_twice", HOST_EMPTY_MV - 100, HOST_EMPTY_MV - 100, false, 2);
    /* 最後の測定は高いまま、アイドルの間に電池が尽きた → 気づいて止まる */
    scene("drained_idle", HOST_EMPTY_MV + 300, HOST_EMPTY_MV - 100, false, 2);
    /* USB 給電中は数えない */
    scene("usb", HOST_EMPTY_MV - 100, HOST_EMPTY_MV - 100, true, 3);
    return 0;
}
