/* Clean code — 无 MISRA 违规 */
#include <stdint.h>

static void clean_loop(void)
{
    int32_t i;
    int32_t sum = 0;

    for (i = 0; i < 10; i++) {
        sum += i;
    }

    (void)sum;
}
