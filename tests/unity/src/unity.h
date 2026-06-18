/* =========================================================================
    Unity — A Test Framework for C
    ThrowTheSwitch.org
    MIT License
    ========================================================================= */

#ifndef UNITY_H_
#define UNITY_H_

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── Types ──────────────────────────────────────────────────────────── */

typedef int UNITY_INT;
typedef unsigned int UNITY_UINT;
typedef int UNITY_LINE_TYPE;
typedef enum {
    UNITY_DISPLAY_STYLE_INT,
    UNITY_DISPLAY_STYLE_UINT,
    UNITY_DISPLAY_STYLE_HEX,
} UNITY_DISPLAY_STYLE_T;

#define UNITY_DISPLAY_STYLE_UNUSED /* empty */

typedef void (*UnityTestFunction)(void);
typedef void (*UnityDefaultTestFunction)(UnityTestFunction, const char *, int);

/* ── Lifecycle ──────────────────────────────────────────────────────── */

void UnityBegin(const char *name);
int  UnityEnd(void);
void UnityDefaultTestRun(UnityTestFunction func, const char *name, int line);
void UnityConcludeTest(void);

/* ── Assertions ─────────────────────────────────────────────────────── */

void UnityFail(const char *msg, int line);
void UnityIgnore(const char *msg, int line);

void UnityAssertEqualNumber(UNITY_INT expected, UNITY_INT actual,
                            const char *msg, int line,
                            UNITY_DISPLAY_STYLE_T style);

void UnityAssertEqualString(const char *expected, const char *actual,
                            const char *msg, int line);

void UnityAssertTrue(int condition, const char *msg, int line);
void UnityAssertFalse(int condition, const char *msg, int line);

void UnityAssertIntArray(const UNITY_INT *expected, const UNITY_INT *actual,
                         unsigned int num_elements, const char *msg,
                         int line, UNITY_DISPLAY_STYLE_T style);

void UnityAssertEqualMemory(const void *expected, const void *actual,
                            unsigned int length, const char *msg, int line);

void UnityAssertBits(UNITY_INT mask, UNITY_INT expected, UNITY_INT actual,
                     const char *msg, int line);

/* ── Convenience Macros ─────────────────────────────────────────────── */

#define TEST_ASSERT_EQUAL(expected, actual) \
    UnityAssertEqualNumber((UNITY_INT)(expected), (UNITY_INT)(actual), \
                           NULL, __LINE__, UNITY_DISPLAY_STYLE_INT)

#define TEST_ASSERT_EQUAL_UINT(expected, actual) \
    UnityAssertEqualNumber((UNITY_INT)(expected), (UNITY_INT)(actual), \
                           NULL, __LINE__, UNITY_DISPLAY_STYLE_UINT)

#define TEST_ASSERT_EQUAL_HEX(expected, actual) \
    UnityAssertEqualNumber((UNITY_INT)(expected), (UNITY_INT)(actual), \
                           NULL, __LINE__, UNITY_DISPLAY_STYLE_HEX)

#define TEST_ASSERT_EQUAL_STRING(expected, actual) \
    UnityAssertEqualString((expected), (actual), NULL, __LINE__)

#define TEST_ASSERT_TRUE(condition) \
    UnityAssertTrue((condition), NULL, __LINE__)

#define TEST_ASSERT_FALSE(condition) \
    UnityAssertFalse((condition), NULL, __LINE__)

#define TEST_ASSERT_NULL(pointer) \
    UnityAssertEqualNumber((UNITY_INT)NULL, (UNITY_INT)(pointer), \
                           NULL, __LINE__, UNITY_DISPLAY_STYLE_INT)

#define TEST_ASSERT_NOT_NULL(pointer) \
    UnityAssertTrue((pointer) != NULL, NULL, __LINE__)

#define TEST_ASSERT_EQUAL_INT_ARRAY(expected, actual, num) \
    UnityAssertIntArray((expected), (actual), (num), NULL, \
                        __LINE__, UNITY_DISPLAY_STYLE_INT)

#define TEST_ASSERT_EQUAL_MEMORY(expected, actual, len) \
    UnityAssertEqualMemory((expected), (actual), (len), NULL, __LINE__)

#define TEST_ASSERT_BITS(mask, expected, actual) \
    UnityAssertBits((mask), (expected), (actual), NULL, __LINE__)

#define TEST_FAIL()    UnityFail("Forced failure", __LINE__)
#define TEST_IGNORE()  UnityIgnore("Test ignored", __LINE__)

/* ── Test Runner Macro ──────────────────────────────────────────────── */

#define RUN_TEST(func) \
    UnityDefaultTestRun(func, #func, __LINE__)

#ifdef __cplusplus
}
#endif

#endif /* UNITY_H_ */
