// expected: misra-c2023-10.3
// description: 隐式窄化转换
#include <stdint.h>

static void test_narrowing(void)
{
    int32_t big = 100000;
    int16_t small;

    /* MISRA 10.3: 从宽类型赋值给窄类型需要显式转换 */
    small = big;

    (void)small;
}
