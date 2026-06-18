// expected: misra-c2023-16.4
// description: switch 语句没有 default 分支
#include <stdint.h>

static void test_switch_no_default(int32_t cmd)
{
    switch (cmd) {
        case 1:
            break;
        case 2:
            break;
        /* MISRA 16.4: 没有 default 分支 */
    }
}
