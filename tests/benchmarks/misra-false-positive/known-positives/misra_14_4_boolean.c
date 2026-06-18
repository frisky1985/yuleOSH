// expected: misra-c2023-14.4
// description: 控制表达式非布尔类型
#include <stdint.h>

static void test_ctrl_expr(int32_t flag)
{
    /* MISRA 14.4: 控制表达式应本质上是布尔类型 */
    if (flag) {
        /* should be if (flag != 0) */
    }
}
