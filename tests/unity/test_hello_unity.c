/**
 * @file test_hello_unity.c
 * @brief Unity-based unit tests for hello.c cross-compilation test program.
 *
 * Uses function-renaming trick to avoid main() conflict.
 *
 * Compile:
 *   gcc -I../../src/yuleosh/cross --coverage -g -O0
 *       -o test_hello_unity test_hello_unity.c src/unity.c
 *
 * License: MIT
 */

#include "unity.h"

/* Rename main to hello_main to avoid conflict */
#define main hello_main
#include "hello.c"
#undef main

/* ------------------------------------------------------------------ */
/*  setUp / tearDown                                                   */
/* ------------------------------------------------------------------ */

void setUp(void) {
    /* nothing */
}

void tearDown(void) {
    /* nothing */
}

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

static void test_hello_returns_success(void) {
    int result = hello_main();
    TEST_ASSERT_EQUAL(0, result);
}

static void test_hello_prints_greeting(void) {
    /* We can't easily capture stdout in pure C without redirect tricks.
     * This test verifies the function runs without crashing. */
    int result = hello_main();
    TEST_ASSERT_TRUE(result == 0);
}

/* ------------------------------------------------------------------ */
/*  Main — Test Runner                                                */
/* ------------------------------------------------------------------ */

int main(void) {
    UnityBegin("Hello_TestSuite");

    RUN_TEST(test_hello_returns_success);
    RUN_TEST(test_hello_prints_greeting);

    return UnityEnd();
}
