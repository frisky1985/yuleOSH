// expected: misra-c2023-10.4
// description: 有符号/无符号表达式混用
#include <stdint.h>

static void test_mixed_sign(void)
{
    uint32_t ua = 10U;
    int32_t  sb = -5;

    /* MISRA 10.x: 有符号/无符号混用（无显式转换） */
    if (ua <= sb) {
        /* signed/unsigned comparison — triggers misra-c2012-10.4 */
    }

    (void)ua;
    (void)sb;
}
