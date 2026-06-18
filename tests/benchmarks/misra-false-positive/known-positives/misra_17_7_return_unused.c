// expected: misra-c2023-17.7
// description: 函数返回值未使用
#include <stdint.h>

static int32_t compute(int32_t a, int32_t b)
{
    return a + b;
}

static void test_unused_return(void)
{
    int32_t x = 10;
    int32_t y = 20;

    /* MISRA 17.7: 返回值必须被使用 */
    compute(x, y);

    (void)x;
    (void)y;
}
