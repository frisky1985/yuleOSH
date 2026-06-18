// expected: misra-c2023-21.3
// description: 使用标准库内存管理函数（malloc/free）
#include <stdlib.h>
#include <stdint.h>

static void test_malloc_no_check(void)
{
    int32_t *p;

    /* MISRA 21.3: 不应使用标准库内存管理函数 */
    p = (int32_t*)malloc(sizeof(int32_t) * 10);

    /* MISRA 10.4: 整数到指针的隐式转换 */
    p[0] = 42;

    free(p);
}
