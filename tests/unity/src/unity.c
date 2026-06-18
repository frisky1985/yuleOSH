/* =========================================================================
    Unity — A Test Framework for C
    ThrowTheSwitch.org
    MIT License — See unity.h for full license text.
    ========================================================================= */

#include "unity.h"
#include <string.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>

/* Internal state */
static jmp_buf _abort_frame;
static int     _test_failed;
static int     _test_passed;
static int     _test_ignored;
static int     _current_test_failed;
static const char *_current_test_name;

/* Forward declarations */
void setUp(void) { }
void tearDown(void) { }

/* ── Startup ────────────────────────────────────────────────────────── */

void UnityBegin(const char *name) {
    _test_passed = 0;
    _test_failed = 0;
    _test_ignored = 0;
    (void)name;
}

void UnityConcludeTest(void) {
    if (_current_test_failed) {
        ++_test_failed;
    } else {
        ++_test_passed;
    }
    _current_test_failed = 0;
}

int UnityEnd(void) {
    int total = _test_passed + _test_failed;
    printf("\n-----------------------\n");
    printf("%d Tests %d Failures %d Ignored\n",
           total, _test_failed, _test_ignored);
    return _test_failed;
}

/* ── Test fixture ───────────────────────────────────────────────────── */

void UnityDefaultTestRun(UnityTestFunction func, const char *name, int UNITY_LINE_TYPE line) {
    (void)line;
    _current_test_name = name;
    _current_test_failed = 0;

    if (setjmp(_abort_frame) == 0) {
        setUp();
        func();
        tearDown();
    }
    /* If we get here via longjmp, test already counted as failed */
    UnityConcludeTest();
}

/* ── Assert helpers ─────────────────────────────────────────────────── */

void UnityFail(const char *msg, int UNITY_LINE_TYPE line) {
    _current_test_failed = 1;
    printf("  FAIL: %s (%s:%d)\n", msg, __FILE__, line);
    longjmp(_abort_frame, 1);
}

void UnityIgnore(const char *msg, int UNITY_LINE_TYPE line) {
    ++_test_ignored;
    printf("  IGNORE: %s (%s:%d)\n", msg, __FILE__, line);
    longjmp(_abort_frame, 1);
}

void UnityAssertEqualNumber(const UNITY_INT expected, const UNITY_INT actual,
                            const char *msg, int UNITY_LINE_TYPE line,
                            const UNITY_DISPLAY_STYLE_T UNITY_DISPLAY_STYLE_UNUSED style) {
    if (expected != actual) {
        _current_test_failed = 1;
        printf("  FAIL: expected %d, got %d", (int)expected, (int)actual);
        if (msg && *msg) printf(" — %s", msg);
        printf(" (%s:%d)\n", __FILE__, line);
        longjmp(_abort_frame, 1);
    }
}

void UnityAssertEqualString(const char *expected, const char *actual,
                            const char *msg, int UNITY_LINE_TYPE line) {
    if (expected == NULL && actual == NULL) return;
    if (expected == NULL || actual == NULL || strcmp(expected, actual) != 0) {
        _current_test_failed = 1;
        printf("  FAIL: expected \"%s\", got \"%s\"",
               expected ? expected : "(null)",
               actual ? actual : "(null)");
        if (msg && *msg) printf(" — %s", msg);
        printf(" (%s:%d)\n", __FILE__, line);
        longjmp(_abort_frame, 1);
    }
}

void UnityAssertTrue(int condition, const char *msg, int UNITY_LINE_TYPE line) {
    if (!condition) {
        _current_test_failed = 1;
        printf("  FAIL: expected TRUE");
        if (msg && *msg) printf(" — %s", msg);
        printf(" (%s:%d)\n", __FILE__, line);
        longjmp(_abort_frame, 1);
    }
}

void UnityAssertFalse(int condition, const char *msg, int UNITY_LINE_TYPE line) {
    if (condition) {
        _current_test_failed = 1;
        printf("  FAIL: expected FALSE");
        if (msg && *msg) printf(" — %s", msg);
        printf(" (%s:%d)\n", __FILE__, line);
        longjmp(_abort_frame, 1);
    }
}

void UnityAssertIntArray(const UNITY_INT *expected, const UNITY_INT *actual,
                         const unsigned int num_elements, const char *msg,
                         int UNITY_LINE_TYPE line,
                         const UNITY_DISPLAY_STYLE_T UNITY_DISPLAY_STYLE_UNUSED style) {
    for (unsigned int i = 0; i < num_elements; ++i) {
        if (expected[i] != actual[i]) {
            _current_test_failed = 1;
            printf("  FAIL: array[%u] expected %d, got %d", i,
                   (int)expected[i], (int)actual[i]);
            if (msg && *msg) printf(" — %s", msg);
            printf(" (%s:%d)\n", __FILE__, line);
            longjmp(_abort_frame, 1);
        }
    }
}

void UnityAssertEqualMemory(const void *expected, const void *actual,
                            const unsigned int length, const char *msg,
                            int UNITY_LINE_TYPE line) {
    if (memcmp(expected, actual, length) != 0) {
        _current_test_failed = 1;
        printf("  FAIL: memory mismatch (%u bytes)", length);
        if (msg && *msg) printf(" — %s", msg);
        printf(" (%s:%d)\n", __FILE__, line);
        longjmp(_abort_frame, 1);
    }
}

void UnityAssertBits(const UNITY_INT mask, const UNITY_INT expected,
                     const UNITY_INT actual, const char *msg,
                     int UNITY_LINE_TYPE line) {
    if ((expected & mask) != (actual & mask)) {
        _current_test_failed = 1;
        printf("  FAIL: bitmask 0x%x: expected 0x%x, got 0x%x",
               (unsigned)mask, (unsigned)expected, (unsigned)actual);
        if (msg && *msg) printf(" — %s", msg);
        printf(" (%s:%d)\n", __FILE__, line);
        longjmp(_abort_frame, 1);
    }
}
