/* Clean code — 无 MISRA 违规 */
#include <stdint.h>

static int32_t calc(int32_t a, int32_t b)
{
    return a + b;
}

static void clean_basic(void)
{
    int32_t x = 10;
    int32_t y = 20;
    int32_t result;

    result = calc(x, y);

    if (result > 0) {
        /* do nothing */
    }

    (void)result;
}
