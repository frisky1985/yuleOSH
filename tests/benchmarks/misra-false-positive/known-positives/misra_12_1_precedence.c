// expected: misra-c2023-12.1
// description: 运算符优先级不明确
#include <stdint.h>

static void test_precedence(void)
{
    int32_t a = 1;
    int32_t b = 2;
    int32_t c = 3;

    /* MISRA 12.1: 缺少括号，位运算和比较运算优先级易混淆 */
    if (a & b == c) {
        /* ambiguous: (a & (b == c)) or ((a & b) == c) */
    }

    (void)a;
    (void)b;
    (void)c;
}
