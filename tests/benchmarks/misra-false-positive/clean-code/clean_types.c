/* Clean code — 无 MISRA 违规 */
#include <stdint.h>

static void clean_explicit_cast(void)
{
    int32_t  big = 1000;
    int16_t  small;
    uint32_t ua = 10U;
    int32_t  sb = -5;

    /* 显式窄化转换 */
    small = (int16_t)big;

    /* 有符号/无符号比较一律显式转换 */
    if (ua < (uint32_t)sb) {
        /* dead branch — sb cast to huge unsigned */
    }

    (void)small;
    (void)ua;
}
