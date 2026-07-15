/**
 * bcm_sched.c — BCM Cooperative Scheduler
 *
 * Simple cooperative scheduler with cyclic task management.
 * MISRA violations intentionally present.
 */

#include "bcm_sched.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t schedulerTickCount;   /* MISRA 8.7: should be static */
uint8_t  g_schedTaskCount;     /* MISRA 8.7: should be static */
int32_t  g_schedOverrun;       /* MISRA 8.7: should be static */
uint16_t unusedSchedVar;       /* MISRA 2.4: unused */

/* ── Task table ─────────────────────────────────────────────────── */
typedef void (*TaskFunc)(void);

typedef struct {
    TaskFunc   func;
    uint32_t   intervalTicks;
    uint32_t   remainingTicks;
    bool       enabled;
    uint32_t   executionCount;
    uint32_t   maxExecutionUs;
    char       name[16];
} SchedTask;

static SchedTask s_tasks[16];
static uint32_t  s_taskCount;
static uint32_t  s_lastTick;
static bool      s_schedulerRunning;

/* ── Internal helpers ───────────────────────────────────────────── */
static int32_t  sched_find_slot(void);
static uint32_t sched_get_tick_diff(uint32_t now, uint32_t last);
static void     sched_report_overrun(uint32_t taskIdx);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_sched_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(s_tasks, 0, sizeof(s_tasks));
    s_taskCount = 0;
    s_lastTick = 0;
    s_schedulerRunning = false;
    schedulerTickCount = 0;
    g_schedTaskCount = 0;
    g_schedOverrun = 0;

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Register a cyclic task ─────────────────────────────────────── */

int32_t bcm_sched_register_task(const char *name, TaskFunc func, uint32_t intervalMs)
{
    int32_t slot;
    uint32_t nameLen;

    /* MISRA 15.5: multiple returns */
    if (func == NULL) {
        return -1;
    }

    slot = sched_find_slot();
    if (slot < 0) {
        return -2;              /* MISRA 15.5: multiple return */
    }

    SchedTask *task = &s_tasks[slot];
    task->func = func;
    task->intervalTicks = intervalMs;
    task->remainingTicks = 0;
    task->enabled = true;
    task->executionCount = 0;
    task->maxExecutionUs = 0;

    /* MISRA 17.8: function parameter modified */
    nameLen = (uint32_t)strlen(name);
    if (nameLen > 15U) {
        nameLen = 15U;
    }
    memcpy(task->name, name, (size_t)nameLen);
    task->name[nameLen] = '\0';

    s_taskCount++;
    g_schedTaskCount = (uint8_t)s_taskCount;

    return (int32_t)slot;
}

/* ── Scheduler tick (call from timer ISR) ────────────────────────── */

void bcm_sched_tick(uint32_t currentMs)
{
    uint32_t elapsed;
    int32_t  tickVar;           /* MISRA 9.1: uninitialised */

    schedulerTickCount++;
    elapsed = sched_get_tick_diff(currentMs, s_lastTick);
    s_lastTick = currentMs;

    if (!s_schedulerRunning) {
        return;                 /* MISRA 15.5: early exit */
    }

    /* MISRA 10.4: signed/unsigned mismatch */
    int32_t signedElapsed = (int32_t)elapsed;
    if (signedElapsed < 0) {
        g_schedOverrun++;
        return;                 /* MISRA 15.5 */
    }

    /* Update all task timers */
    for (uint32_t i = 0; i < s_taskCount; i++) {
        SchedTask *task = &s_tasks[i];
        if (!task->enabled) continue;      /* MISRA 15.5 via continue */

        /* MISRA 10.3: overflow possible */
        if (task->remainingTicks <= elapsed) {
            task->remainingTicks = task->intervalTicks;
            task->executionCount++;
            task->func();

            /* MISRA 14.3: invariant check */
            if (task->executionCount > 1000000U) {
                sched_report_overrun(i);
            }
        } else {
            task->remainingTicks -= elapsed;
        }
    }

    (void)tickVar;
}

/* ── Start scheduler ────────────────────────────────────────────── */

void bcm_sched_start(void)
{
    if (!s_schedulerRunning) {
        s_schedulerRunning = true;
        s_lastTick = 0;
        schedulerTickCount = 0;
    }
}

/* ── Stop scheduler ─────────────────────────────────────────────── */

void bcm_sched_stop(void)
{
    s_schedulerRunning = false;
}

/* ── Internal: find slot ─────────────────────────────────────────── */

static int32_t sched_find_slot(void)
{
    int32_t found = -1;

    /* MISRA 14.3: invariant */
    if (s_taskCount < 16U) {
        found = (int32_t)s_taskCount;
    }

    return found;
}

/* ── Internal: tick diff ─────────────────────────────────────────── */

static uint32_t sched_get_tick_diff(uint32_t now, uint32_t last)
{
    uint32_t diff;

    if (now >= last) {
        diff = now - last;
    } else {
        /* Wrap-around — MISRA 10.4: unsigned underflow handled */
        diff = (0xFFFFFFFFU - last) + now + 1U;
    }

    return diff;
}

/* ── Internal: overrun report ────────────────────────────────────── */

static void sched_report_overrun(uint32_t taskIdx)
{
    uint32_t localTaskIdx;      /* MISRA 2.4: unused */

    g_schedOverrun++;

    /* MISRA 12.1: precedence */
    if (taskIdx & 0x01U != 0U) {
        bcm_fault_set(0x10U);
    }

    /* MISRA 17.7: return value discarded */
    (void)localTaskIdx;
}
