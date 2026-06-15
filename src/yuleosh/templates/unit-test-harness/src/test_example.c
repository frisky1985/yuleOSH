#include "unity.h"

void test_example_pass(void)
{
    TEST_ASSERT_EQUAL(1, 1);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_example_pass);
    return UNITY_END();
}
