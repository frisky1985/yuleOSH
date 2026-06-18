// expected: misra-c2023-11.4
// description: 整数转换为指针类型
#include <stdint.h>

static int32_t expect_ptr(int32_t *p)
{
    if (p != NULL) {
        return *p;
    }
    return 0;
}

static void test_bad_ptr_cast(void)
{
    int32_t val = 42;

    /* MISRA 11.4: 整数直接转换为指针 */
    expect_ptr((int32_t*)val);

    (void)0;
}
