/* =========================================================================
    Test Runner Template — yuleOSH Unity Test Suite

    This file is a template for running Unity-based C unit tests.
    Replace the example tests below with your actual module tests.

    Build & run:
        make -C tests/unity
    ========================================================================= */

#include "unity.h"

/* ── Example module to test (replace with your own headers) ──────────── */

/* Example: a simple function to test */
static int add(int a, int b) {
    return a + b;
}

/* ── setUp / tearDown ────────────────────────────────────────────────── */

void setUp(void) {
    /* Called before each test — initialize test fixtures here */
}

void tearDown(void) {
    /* Called after each test — clean up test fixtures here */
}

/* ── Test Cases ──────────────────────────────────────────────────────── */

static void test_add_positive_numbers(void) {
    TEST_ASSERT_EQUAL(5, add(2, 3));
    TEST_ASSERT_EQUAL(10, add(7, 3));
}

static void test_add_negative_numbers(void) {
    TEST_ASSERT_EQUAL(-1, add(2, -3));
    TEST_ASSERT_EQUAL(-5, add(-2, -3));
}

static void test_add_zero(void) {
    TEST_ASSERT_EQUAL(0, add(0, 0));
    TEST_ASSERT_EQUAL(5, add(5, 0));
    TEST_ASSERT_EQUAL(-3, add(0, -3));
}

/* ── Main — Test Runner Entry Point ──────────────────────────────────── */

int main(void) {
    UnityBegin("ExampleTestSuite");

    RUN_TEST(test_add_positive_numbers);
    RUN_TEST(test_add_negative_numbers);
    RUN_TEST(test_add_zero);

    return UnityEnd();
}
