// expected: misra-c2023-12.3
// description: 逗号运算符的使用
#include <stdint.h>

static void test_comma_operator(void)
{
    int32_t a, b, c;

    /* MISRA 12.3: 不应使用逗号运算符作为表达式 */
    a = 1, b = 2, c = 3;

    (void)a;
    (void)b;
    (void)c;
}
