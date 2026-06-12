/**
 * @file main.c
 * @brief yuleOSH Blinky 示例 — GPIO + UART + Wi-Fi Scan + FreeRTOS
 *
 * 功能:
 *   - blink_task: GPIO2 LED 以 1s 周期闪烁
 *   - wifi_task: 扫描周围 Wi-Fi AP 并通过 UART 输出结果
 *   - UART: 115200 baud, 打印 Hello 及扫描结果
 *
 * 目标: ESP-IDF v5.x, ESP32 / ESP32-S3 / ESP32-C3
 */

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"

/* ── 常量 ──────────────────────────────────────────────────── */

#define BLINK_GPIO       CONFIG_BLINK_GPIO       /**< LED GPIO (默认 2) */
#define BLINK_PERIOD_MS  1000                    /**< 闪烁周期 (ms)    */
#define UART_BAUD        115200                  /**< UART 波特率      */
#define WIFI_SCAN_INTERVAL_SEC  30               /**< Wi-Fi 扫描间隔   */

static const char *TAG = "yuleOSH";

/* ── 函数声明 ──────────────────────────────────────────────── */

static void blink_task(void *arg);
static void wifi_task(void *arg);
static void wifi_scan(void);

/* ── app_main ──────────────────────────────────────────────── */

void app_main(void)
{
    ESP_LOGI(TAG, "yuleOSH Blinky 示例启动");
    ESP_LOGI(TAG, "UART 波特率: %d", UART_BAUD);
    ESP_LOGI(TAG, "LED GPIO: %d", BLINK_GPIO);

    /* 初始化 NVS (Wi-Fi 栈需要) */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* 初始化网络接口 (Wi-Fi 扫描需要事件循环) */
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    /* 创建 FreeRTOS 任务 */
    xTaskCreate(blink_task, "blink_task", 2048, NULL, 5, NULL);
    xTaskCreate(wifi_task,  "wifi_task",  4096, NULL, 5, NULL);

    ESP_LOGI(TAG, "任务已创建 — Hello from yuleOSH!");
}

/* ── blink_task ────────────────────────────────────────────── */

static void blink_task(void *arg)
{
    /* 配置 GPIO */
    gpio_reset_pin(BLINK_GPIO);
    gpio_set_direction(BLINK_GPIO, GPIO_MODE_OUTPUT);

    while (1) {
        gpio_set_level(BLINK_GPIO, 1);
        ESP_LOGI(TAG, "LED ON");
        vTaskDelay(pdMS_TO_TICKS(BLINK_PERIOD_MS / 2));

        gpio_set_level(BLINK_GPIO, 0);
        ESP_LOGI(TAG, "LED OFF");
        vTaskDelay(pdMS_TO_TICKS(BLINK_PERIOD_MS / 2));
    }
}

/* ── wifi_task ─────────────────────────────────────────────── */

static void wifi_task(void *arg)
{
    /* Wi-Fi 初始化 (station 模式，仅用于扫描) */
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    vTaskDelay(pdMS_TO_TICKS(2000)); /* 等 Wi-Fi 驱动就绪 */

    while (1) {
        ESP_LOGI(TAG, "开始 Wi-Fi 扫描...");
        wifi_scan();

        ESP_LOGI(TAG, "扫描完成，%d 秒后再次扫描",
                 WIFI_SCAN_INTERVAL_SEC);
        vTaskDelay(pdMS_TO_TICKS(WIFI_SCAN_INTERVAL_SEC * 1000));
    }
}

/* ── wifi_scan ─────────────────────────────────────────────── */

static void wifi_scan(void)
{
    uint16_t ap_count = 0;
    uint16_t max_aps  = 20;

    /* 分配扫描结果缓冲区 */
    wifi_ap_record_t *ap_records =
        (wifi_ap_record_t *)heap_caps_malloc(
            max_aps * sizeof(wifi_ap_record_t), MALLOC_CAP_DEFAULT);
    if (ap_records == NULL) {
        ESP_LOGE(TAG, "内存不足，无法分配扫描缓冲区");
        return;
    }
    memset(ap_records, 0, max_aps * sizeof(wifi_ap_record_t));

    /* 执行扫描 */
    esp_err_t err = esp_wifi_scan_start(NULL, true); /* block=true */
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Wi-Fi 扫描失败: %s", esp_err_to_name(err));
        free(ap_records);
        return;
    }

    err = esp_wifi_scan_get_ap_records(&max_aps, ap_records);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "获取扫描结果失败: %s", esp_err_to_name(err));
        free(ap_records);
        return;
    }

    err = esp_wifi_scan_get_ap_num(&ap_count);
    if (err != ESP_OK) {
        ap_count = max_aps;
    }

    ESP_LOGI(TAG, "发现 %d 个 AP:", ap_count);

    for (uint16_t i = 0; i < ap_count && i < max_aps; i++) {
        const wifi_ap_record_t *ap = &ap_records[i];

        char auth_str[32];
        switch (ap->authmode) {
            case WIFI_AUTH_OPEN:         snprintf(auth_str, sizeof(auth_str), "OPEN");        break;
            case WIFI_AUTH_WEP:          snprintf(auth_str, sizeof(auth_str), "WEP");         break;
            case WIFI_AUTH_WPA_PSK:      snprintf(auth_str, sizeof(auth_str), "WPA_PSK");     break;
            case WIFI_AUTH_WPA2_PSK:     snprintf(auth_str, sizeof(auth_str), "WPA2_PSK");    break;
            case WIFI_AUTH_WPA_WPA2_PSK: snprintf(auth_str, sizeof(auth_str), "WPA/WPA2");    break;
            case WIFI_AUTH_WPA3_PSK:     snprintf(auth_str, sizeof(auth_str), "WPA3_PSK");    break;
            default:                     snprintf(auth_str, sizeof(auth_str), "UNKNOWN");      break;
        }

        ESP_LOGI(TAG, "  [%2d] SSID: %-32s  RSSI: %-4d  CH: %-2d  %s",
                 i,
                 (const char *)ap->ssid,
                 ap->rssi,
                 ap->primary,
                 auth_str);
    }

    free(ap_records);
}
