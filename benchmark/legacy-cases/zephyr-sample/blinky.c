/*
 * Zephyr 代表性样例（脱敏 stand-in，非真实仓库代码）。
 * 许可证：Apache-2.0（与上游 Zephyr project 一致）。
 * 目的：为 C AST 扫描器冒烟/准确率门禁提供 Zephyr 典型惯用法样本
 *       （线程栈宏、GPIO 回调 ISR、volatile 全局、条件编译选板）。
 */
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

/* 函数式宏：线程栈定义（低置信度 entity 候选） */
#define STACK_SIZE 512
#define THREAD_PRIORITY 5
#define K_THREAD_STACK_DEFINE(name, size) static K_KERNEL_STACK_DEFINE(name, size)

/* 对象宏：板级 GPIO 规格（带值，高置信度） */
#define LED0_NODE DT_ALIAS(led0)
#define SLEEP_MS 500

/* volatile 全局：跨线程共享状态 */
volatile int g_blink_count = 0;
static const struct device *g_led_dev;

/* GPIO 中断回调（命名不含 isr/irq，但由 IRQ_CONNECT 注册 → 向量表/回调式 ISR 候选） */
void button_pressed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    g_blink_count += 1;
    k_msleep(SLEEP_MS);
}

/* 线程入口函数（函数定义） */
void blink_thread(void *p1, void *p2, void *p3)
{
    int ret;
    while (1) {
        ret = gpio_pin_toggle(g_led_dev, 0);
        if (ret != 0) {
            return;
        }
        g_blink_count += 1;
        k_msleep(SLEEP_MS);
    }
}

/* 初始化：条件编译按板选择不同 GPIO 规格 */
#ifdef CONFIG_BOARD_NATIVE_POSIX
static int board_init_native(void)
{
    g_led_dev = DEVICE_DT_GET(LED0_NODE);
    return 0;
}
#else
static int board_init_real(void)
{
    g_led_dev = DEVICE_DT_GET(LED0_NODE);
    return gpio_pin_configure(g_led_dev, 0, GPIO_OUTPUT_ACTIVE);
}
#endif

int main(void)
{
    int rc = board_init_real();
    if (rc != 0) {
        return rc;
    }
    blink_thread(NULL, NULL, NULL);
    return 0;
}
