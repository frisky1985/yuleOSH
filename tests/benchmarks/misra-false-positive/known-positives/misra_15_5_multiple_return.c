// expected: misra-c2023-15.5
// description: 函数不应有多个 return 语句
#include <stdint.h>

static int32_t check_value(int32_t x)
{
    /* MISRA 15.5: 函数有多个 return 语句 */
    if (x > 0) {
        return 1;
    }
    if (x < 0) {
        return -1;
    }
    return 0;
}
