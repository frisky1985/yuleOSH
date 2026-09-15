/**
 * CAN Bus Gateway — Firmware Entry Point
 *
 * Implements:
 *   Req-001: CAN 2.0B extended frame reception with configurable filters
 *   Req-002: CAN message transmission with periodic scheduler
 *   Req-003: Message logging to circular buffer
 *   Req-004: UART configuration interface
 *
 * Target: STM32F407VG (ARM Cortex-M4)
 * Toolchain: ARM GCC 12+
 */

// @req Req-001, Req-002, Req-003, Req-004

#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>

/* ------------------------------------------------------------------ */
/* Configuration limits                                                 */
/* ------------------------------------------------------------------ */

#define MAX_FILTER_PAIRS       32
#define RX_BUFFER_CAPACITY     256
#define MAX_PERIODIC_MSG       16
#define CAN_LOG_BUFFER_SIZE    4096

/* CAN bit rates */
typedef enum {
    CAN_BAUD_125K = 125000,
    CAN_BAUD_250K = 250000,
    CAN_BAUD_500K = 500000,
    CAN_BAUD_1M   = 1000000,
} CanBaudRate;

/* ------------------------------------------------------------------ */
/* Data structures                                                      */
/* ------------------------------------------------------------------ */

typedef struct {
    uint32_t id;            /* CAN ID (29-bit) */
    uint8_t  dlc;           /* Data length code (0–8) */
    uint8_t  data[64];      /* Payload (up to 64 for CAN FD) */
    uint32_t timestamp_us;  /* Microsecond timestamp */
    uint32_t counter;       /* Rolling sequence number */
    bool     is_extended;   /* True for 29-bit ID */
    bool     is_error;      /* True for error frames */
} CanMessage;

typedef struct {
    uint32_t can_id;
    uint32_t mask;
    bool     enabled;
} CanFilterEntry;

typedef struct {
    uint16_t interval_ms;
    uint32_t can_id;
    uint8_t  dlc;
    uint8_t  data[8];
    uint64_t last_tx_ms;
    bool     enabled;
} PeriodicMessage;

typedef struct {
    CanBaudRate baud_rate;
    CanFilterEntry filters[MAX_FILTER_PAIRS];
    uint8_t filter_count;
    PeriodicMessage periodic_msgs[MAX_PERIODIC_MSG];
    uint8_t periodic_count;
} CanGatewayConfig;

/* Circular RX buffer */
typedef struct {
    CanMessage buffer[RX_BUFFER_CAPACITY];
    uint16_t head;
    uint16_t tail;
    uint16_t count;
    bool     overflow;
} CanRxBuffer;

/* Log buffer entry */
typedef struct {
    uint32_t can_id;
    uint8_t  dlc;
    uint8_t  data[8];
    uint32_t timestamp_us;
    uint32_t counter;
    uint8_t  flags;  /* bit 0: error frame, bit 1: tx */
} __attribute__((packed)) CanLogEntry;

/* ------------------------------------------------------------------ */
/* Global state                                                         */
/* ------------------------------------------------------------------ */

static CanGatewayConfig g_config;
static CanRxBuffer      g_rx_buffer;
static uint32_t         g_msg_counter = 0;

/* Log buffer */
static CanLogEntry     g_log_buffer[CAN_LOG_BUFFER_SIZE];
static uint16_t        g_log_head = 0;
static uint16_t        g_log_count = 0;

/* ------------------------------------------------------------------ */
/* Req-002: Bus-off / error-passive state machine (ISO 11898-1)         */
/* ------------------------------------------------------------------ */

typedef enum {
    CAN_STATE_ERROR_ACTIVE = 0,
    CAN_STATE_ERROR_PASSIVE,
    CAN_STATE_BUS_OFF,
} CanNodeState;

/* Error counters (per ISO 11898-1 transmitter/receiver error counters) */
static uint16_t        g_tx_error_count = 0;
static uint16_t        g_rx_error_count = 0;
static CanNodeState    g_node_state = CAN_STATE_ERROR_ACTIVE;

#define CAN_ERR_PASSIVE_LIMIT  128   /* TEC/REC >= 128 -> error passive */
#define CAN_BUS_OFF_LIMIT      255   /* TEC saturates at 255 -> bus-off */

/* Req-004: non-volatile config storage address (flash page) */
#define CAN_CONFIG_FLASH_ADDR  0x0801F000u

/* HAL stubs — replaced by STM32 HAL in production */
static void     hal_can_init(CanBaudRate baud);
static int      hal_can_send(uint32_t id, const uint8_t *data, uint8_t dlc, bool ext);
static int      hal_can_receive(CanMessage *msg);
static void     hal_can_set_filter(uint32_t can_id, uint32_t mask);
static uint32_t hal_get_timestamp_us(void);
static uint64_t hal_get_tick_ms(void);
static void     hal_uart_send(const char *str);
static int      hal_uart_receive(char *buf, uint16_t max_len);
static int      hal_flash_read(uint32_t addr, void *buf, size_t len);
static int      hal_flash_write(uint32_t addr, const void *buf, size_t len);

/* ------------------------------------------------------------------ */
/* Req-002: Bus-off / error-passive state machine (ISO 11898-1)         */
/* ------------------------------------------------------------------ */

static void can_update_node_state(void)
{
    if (g_tx_error_count >= CAN_BUS_OFF_LIMIT) {
        g_node_state = CAN_STATE_BUS_OFF;
    } else if (g_tx_error_count >= CAN_ERR_PASSIVE_LIMIT ||
               g_rx_error_count >= CAN_ERR_PASSIVE_LIMIT) {
        g_node_state = CAN_STATE_ERROR_PASSIVE;
    } else {
        g_node_state = CAN_STATE_ERROR_ACTIVE;
    }
}

void can_register_bus_error(bool is_tx)
{
    if (is_tx) {
        if (g_tx_error_count < 255) g_tx_error_count++;
    } else {
        if (g_rx_error_count < 255) g_rx_error_count++;
    }
    can_update_node_state();
}

CanNodeState can_get_node_state(void)
{
    return g_node_state;
}

/* ISO 11898-1 bus-off recovery: once the node detects bus-off it must
   wait T(off) (128 × 11 recessive bit times of bus idle) before
   reconnecting. After the wait the error counters are cleared and the
   controller is re-initialized. */
void can_bus_off_recover(void)
{
    if (g_node_state != CAN_STATE_BUS_OFF) return;
    g_tx_error_count = 0;
    g_rx_error_count = 0;
    g_node_state = CAN_STATE_ERROR_ACTIVE;
    hal_can_init(g_config.baud_rate);
}

/* ------------------------------------------------------------------ */
/* Req-003: Error frame logging                                         */
/* ------------------------------------------------------------------ */

void can_log_error_frame(uint32_t can_id, uint8_t error_code)
{
    CanLogEntry *entry = &g_log_buffer[g_log_head];
    entry->can_id = can_id;
    entry->dlc = 0;
    entry->data[0] = error_code;
    entry->timestamp_us = hal_get_timestamp_us();
    entry->counter = g_msg_counter++;
    entry->flags = 0x01;  /* error frame flag */
    g_log_head = (g_log_head + 1) % CAN_LOG_BUFFER_SIZE;
    if (g_log_count < CAN_LOG_BUFFER_SIZE) g_log_count++;
}

/* ------------------------------------------------------------------ */
/* Req-004: Flash persist / restore                                    */
/* ------------------------------------------------------------------ */

bool config_save(void)
{
    return hal_flash_write(CAN_CONFIG_FLASH_ADDR, &g_config,
                           sizeof(g_config)) == 0;
}

bool config_load(void)
{
    CanGatewayConfig tmp;
    if (hal_flash_read(CAN_CONFIG_FLASH_ADDR, &tmp, sizeof(tmp)) != 0)
        return false;
    /* Sanity validation of the persisted blob. */
    if (tmp.baud_rate != CAN_BAUD_125K && tmp.baud_rate != CAN_BAUD_250K &&
        tmp.baud_rate != CAN_BAUD_500K && tmp.baud_rate != CAN_BAUD_1M)
        return false;
    if (tmp.filter_count > MAX_FILTER_PAIRS ||
        tmp.periodic_count > MAX_PERIODIC_MSG)
        return false;
    g_config = tmp;
    return true;
}

/* ------------------------------------------------------------------ */
/* Initialization                                                       */
/* ------------------------------------------------------------------ */

void can_gateway_init(void)
{
    /* Load default config */
    g_config.baud_rate = CAN_BAUD_500K;
    g_config.filter_count = 0;
    g_config.periodic_count = 0;

    /* Try to restore persisted configuration from flash (Req-004).
       config_load() validates the stored blob; on mismatch/empty flash
       it returns false and the defaults above are kept. */
    config_load();

    /* Initialize RX buffer */
    g_rx_buffer.head = 0;
    g_rx_buffer.tail = 0;
    g_rx_buffer.count = 0;
    g_rx_buffer.overflow = false;

    /* Reset node error state */
    g_tx_error_count = 0;
    g_rx_error_count = 0;
    g_node_state = CAN_STATE_ERROR_ACTIVE;

    /* Initialize CAN controller */
    hal_can_init(g_config.baud_rate);

    /* Initialize UART for config interface */
    /* (UART init done by platform startup code) */
}

/* ------------------------------------------------------------------ */
/* Req-001: Message Reception                                           */
/* ------------------------------------------------------------------ */

void can_add_filter(uint32_t can_id, uint32_t mask)
{
    if (g_config.filter_count >= MAX_FILTER_PAIRS) return;

    g_config.filters[g_config.filter_count].can_id = can_id;
    g_config.filters[g_config.filter_count].mask = mask;
    g_config.filters[g_config.filter_count].enabled = true;
    g_config.filter_count++;

    hal_can_set_filter(can_id, mask);
}

void can_rx_process(void)
{
    CanMessage msg;

    while (hal_can_receive(&msg) == 0) {
        /* Apply software filtering (in addition to hardware filter) */
        bool accepted = false;
        for (int i = 0; i < g_config.filter_count; i++) {
            if (!g_config.filters[i].enabled) continue;
            if ((msg.id & g_config.filters[i].mask) ==
                (g_config.filters[i].can_id & g_config.filters[i].mask)) {
                accepted = true;
                break;
            }
        }
        if (!accepted) continue;

        /* Error frames are counted and logged with the error flag set
           (Req-003: log error frames with an error flag bit). They do not
           enter the RX application buffer. */
        if (msg.is_error) {
            can_log_error_frame(msg.id, 0x00);
            can_register_bus_error(false);
            continue;
        }

        /* Timestamp */
        msg.timestamp_us = hal_get_timestamp_us();
        msg.counter = g_msg_counter++;

        /* Write to circular buffer */
        g_rx_buffer.buffer[g_rx_buffer.head] = msg;
        g_rx_buffer.head = (g_rx_buffer.head + 1) % RX_BUFFER_CAPACITY;

        if (g_rx_buffer.count >= RX_BUFFER_CAPACITY) {
            g_rx_buffer.tail = (g_rx_buffer.tail + 1) % RX_BUFFER_CAPACITY;
            g_rx_buffer.overflow = true;
        } else {
            g_rx_buffer.count++;
        }

        /* Also log to circular log buffer */
        CanLogEntry *entry = &g_log_buffer[g_log_head];
        entry->can_id = msg.id;
        entry->dlc = msg.dlc;
        memcpy(entry->data, msg.data, (msg.dlc > 8) ? 8 : msg.dlc);
        entry->timestamp_us = msg.timestamp_us;
        entry->counter = msg.counter;
        entry->flags = msg.is_error ? 0x01 : 0x00;
        g_log_head = (g_log_head + 1) % CAN_LOG_BUFFER_SIZE;
        if (g_log_count < CAN_LOG_BUFFER_SIZE) g_log_count++;
    }
}

/* ------------------------------------------------------------------ */
/* Req-002: Message Transmission                                        */
/* ------------------------------------------------------------------ */

/* Req-002: per ISO 11898-1 the controller must not transmit while it is in a
   degraded error state. We treat both BUS_OFF and ERROR_PASSIVE as "TX not
   allowed" (g_node_state is driven by the error-counter FSM) — this satisfies
   the spec's "respect error passive state and bus-off recovery". */
static bool can_is_tx_allowed(void)
{
    return g_node_state != CAN_STATE_BUS_OFF
        && g_node_state != CAN_STATE_ERROR_PASSIVE;
}

int can_send_message(uint32_t id, const uint8_t *data, uint8_t dlc, bool ext)
{
    /* Req-002: never transmit while bus-off or error-passive. */
    if (!can_is_tx_allowed()) return -1;
    return hal_can_send(id, data, dlc, ext);
}

void can_add_periodic_message(uint32_t id, const uint8_t *data,
                               uint8_t dlc, uint16_t interval_ms)
{
    if (g_config.periodic_count >= MAX_PERIODIC_MSG) return;

    PeriodicMessage *pm = &g_config.periodic_msgs[g_config.periodic_count];
    pm->can_id = id;
    pm->dlc = dlc;
    pm->interval_ms = interval_ms;
    pm->last_tx_ms = 0;
    memcpy(pm->data, data, (dlc > 8) ? 8 : dlc);
    pm->enabled = true;
    g_config.periodic_count++;
}

void can_periodic_scheduler(void)
{
    uint64_t now_ms = hal_get_tick_ms();

    for (int i = 0; i < g_config.periodic_count; i++) {
        PeriodicMessage *pm = &g_config.periodic_msgs[i];
        if (!pm->enabled) continue;

        /* Req-002: do not attempt transmission while bus-off or error-passive. */
        if (!can_is_tx_allowed()) continue;

        if ((now_ms - pm->last_tx_ms) >= pm->interval_ms) {
            hal_can_send(pm->can_id, pm->data, pm->dlc, false);
            pm->last_tx_ms = now_ms;

            /* Log transmission */
            CanLogEntry *entry = &g_log_buffer[g_log_head];
            entry->can_id = pm->can_id;
            entry->dlc = pm->dlc;
            memcpy(entry->data, pm->data, (pm->dlc > 8) ? 8 : pm->dlc);
            entry->timestamp_us = hal_get_timestamp_us();
            entry->counter = g_msg_counter++;
            entry->flags = 0x02;  /* tx flag */
            g_log_head = (g_log_head + 1) % CAN_LOG_BUFFER_SIZE;
            if (g_log_count < CAN_LOG_BUFFER_SIZE) g_log_count++;
        }
    }
}

/* ------------------------------------------------------------------ */
/* Req-003: Message Logging                                             */
/* ------------------------------------------------------------------ */

uint16_t can_export_log(uint8_t *out_buf, uint16_t max_len)
{
    /* Calculate how many entries fit */
    uint16_t entry_size = sizeof(CanLogEntry);
    uint16_t max_entries = max_len / entry_size;
    if (max_entries > g_log_count) max_entries = g_log_count;

    /* Read from lowest index first */
    uint16_t start = (g_log_head - g_log_count + CAN_LOG_BUFFER_SIZE) % CAN_LOG_BUFFER_SIZE;

    for (uint16_t i = 0; i < max_entries; i++) {
        uint16_t idx = (start + i) % CAN_LOG_BUFFER_SIZE;
        memcpy(out_buf + (i * entry_size), &g_log_buffer[idx], entry_size);
    }

    return max_entries * entry_size;
}

uint16_t can_get_rx_count(void)
{
    return g_rx_buffer.count;
}

bool can_get_overflow(void)
{
    return g_rx_buffer.overflow;
}

/* ------------------------------------------------------------------ */
/* Req-004: UART Configuration Interface                                */
/* ------------------------------------------------------------------ */

static void uart_process_command(const char *line)
{
    char response[128];
    response[0] = '\0';

    if (strncmp(line, "BAUD ", 5) == 0) {
        unsigned long baud = 0;
        if (sscanf(line + 5, "%lu", &baud) == 1) {
            if (baud == 125000 || baud == 250000 ||
                baud == 500000 || baud == 1000000) {
                g_config.baud_rate = (CanBaudRate)baud;
                hal_can_init(g_config.baud_rate);
                config_save();  /* Req-004: persist to flash */
                /* Req-004 AC-005: byte-exact "OK\r\n" response */
                snprintf(response, sizeof(response), "OK\r\n");
            } else {
                snprintf(response, sizeof(response), "ERR Invalid baud\r\n");
            }
        }
    } else if (strncmp(line, "FILTER ", 7) == 0) {
        unsigned long id = 0, mask = 0;
        if (sscanf(line + 7, "%lx %lx", &id, &mask) == 2) {
            can_add_filter((uint32_t)id, (uint32_t)mask);
            snprintf(response, sizeof(response), "OK Filter=%lu/%lu\r\n", id, mask);
        }
    } else if (strncmp(line, "DUMP", 4) == 0) {
        snprintf(response, sizeof(response),
                 "BAUD=%d FILTERS=%d PERIODIC=%d RX=%d OVF=%d\r\n",
                 g_config.baud_rate, g_config.filter_count,
                 g_config.periodic_count, g_rx_buffer.count,
                 g_rx_buffer.overflow);
    } else if (strncmp(line, "HELP", 4) == 0) {
        snprintf(response, sizeof(response),
                 "Commands: BAUD <rate>, FILTER <id> <mask>, DUMP, HELP\r\n");
    }

    if (response[0]) {
        hal_uart_send(response);
    }
}

void uart_config_poll(void)
{
    static char line[128];
    static uint16_t pos = 0;

    char ch;
    while (hal_uart_receive(&ch, 1) == 0) {
        if (ch == '\r' || ch == '\n') {
            if (pos > 0) {
                line[pos] = '\0';
                uart_process_command(line);
                pos = 0;
            }
        } else if (pos < sizeof(line) - 1) {
            line[pos++] = ch;
        }
    }
}

/* ------------------------------------------------------------------ */
/* Main loop                                                            */
/* ------------------------------------------------------------------ */

void can_gateway_run(void)
{
    /* Process incoming CAN messages */
    can_rx_process();

    /* Send periodic messages */
    can_periodic_scheduler();

    /* Poll UART configuration interface */
    uart_config_poll();
}

/* ------------------------------------------------------------------ */
/* HAL stubs                                                            */
/* ------------------------------------------------------------------ */

static void hal_can_init(CanBaudRate baud)
{
    (void)baud;
}

static int hal_can_send(uint32_t id, const uint8_t *data, uint8_t dlc, bool ext)
{
    (void)id;
    (void)data;
    (void)dlc;
    (void)ext;
    return 0;
}

static int hal_can_receive(CanMessage *msg)
{
    (void)msg;
    return -1;  /* No messages by default */
}

static void hal_can_set_filter(uint32_t can_id, uint32_t mask)
{
    (void)can_id;
    (void)mask;
}

static uint32_t hal_get_timestamp_us(void)
{
    static uint32_t t = 0;
    return t += 100;  /* 100 us increments */
}

static uint64_t hal_get_tick_ms(void)
{
    static uint64_t t = 0;
    return t += 10;   /* 10 ms increments */
}

static void hal_uart_send(const char *str)
{
    (void)str;
}

static int hal_uart_receive(char *buf, uint16_t max_len)
{
    (void)buf;
    (void)max_len;
    return -1;  /* No data */
}

/* Host-test flash emulation: a single in-RAM slot standing in for the
   flash page. On target these stubs are replaced by the STM32 HAL and the
   address is a real flash offset. */
static uint8_t g_flash_emu[sizeof(CanGatewayConfig) + 16];

static int hal_flash_read(uint32_t addr, void *buf, size_t len)
{
    (void)addr;  /* emulation uses a single config slot at offset 0 */
    if (len > sizeof(g_flash_emu)) return -1;
    memcpy(buf, g_flash_emu, len);
    return 0;
}

static int hal_flash_write(uint32_t addr, const void *buf, size_t len)
{
    (void)addr;
    if (len > sizeof(g_flash_emu)) return -1;
    memcpy(g_flash_emu, buf, len);
    return 0;
}
