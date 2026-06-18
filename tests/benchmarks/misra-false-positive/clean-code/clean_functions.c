/* Clean code — 无 MISRA 违规 */
#include <stdint.h>

static int32_t multiply(int32_t a, int32_t b)
{
    return a * b;
}

static int32_t clean_calls(void)
{
    int32_t product;

    product = multiply(3, 4);

    return product;
}
