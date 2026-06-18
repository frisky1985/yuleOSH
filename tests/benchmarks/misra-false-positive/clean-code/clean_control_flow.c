/* Clean code — 无 MISRA 违规 */
#include <stdint.h>

static void clean_switch(int32_t cmd)
{
    switch (cmd) {
        case 1:
            break;
        case 2:
            break;
        default:
            break;
    }
}

static void clean_if(int32_t val)
{
    if (val != 0) {
        clean_switch(val);
    }
}
