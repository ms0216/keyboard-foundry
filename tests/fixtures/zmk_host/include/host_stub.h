/*
 * firmware/src/low_battery_off.c をホスト（cc）でコンパイルするための最小の代役。
 * Zephyr / ZMK の API のうち、あのファイルが使う物の**形だけ**を置く。動きは harness.c が決める。
 * tests/test_firmware.py の test_low_battery_off_counts_only_fresh_samples が使う。
 */
#ifndef HOST_STUB_H
#define HOST_STUB_H

#include <stdbool.h>
#include <stdint.h>

#define IS_ENABLED(x) (x)
#define BUILD_ASSERT(c, ...) _Static_assert(c, "BUILD_ASSERT")

/* devicetree: chosen zmk,battery の empty-millivolts だけ */
#define DT_CHOSEN(x) 0
#define DT_NODE_HAS_PROP(node, prop) 1
#define DT_PROP(node, prop) HOST_EMPTY_MV
#define DEVICE_DT_GET(node) (&host_battery)

struct device { int unused; };
extern const struct device host_battery;

/* sensor */
enum sensor_channel { SENSOR_CHAN_GAUGE_VOLTAGE, SENSOR_CHAN_GAUGE_STATE_OF_CHARGE };
struct sensor_value { int32_t val1; int32_t val2; };
int sensor_sample_fetch_chan(const struct device *dev, enum sensor_channel chan);
int sensor_channel_get(const struct device *dev, enum sensor_channel chan, struct sensor_value *val);

/* kernel */
struct k_work { void (*handler)(struct k_work *); };
struct k_timer { void (*expiry)(struct k_timer *); };
struct k_work_q { int unused; };
#define K_WORK_DEFINE(name, fn) struct k_work name = {fn}
#define K_TIMER_DEFINE(name, fn, stop) struct k_timer name = {fn}
#define K_SECONDS(s) (s)
void k_timer_start(struct k_timer *t, int delay, int period);
int k_work_submit_to_queue(struct k_work_q *q, struct k_work *w);

/* logging・init */
#define LOG_MODULE_DECLARE(...)
#define LOG_WRN(...) ((void)0)
#define LOG_ERR(...) ((void)0)
#define SYS_INIT(fn, level, prio) int (*const host_init_##fn)(void) = fn

/* zmk */
int zmk_pm_soft_off(void);
struct k_work_q *zmk_workqueue_lowprio_work_q(void);
bool zmk_usb_is_powered(void);

#endif
