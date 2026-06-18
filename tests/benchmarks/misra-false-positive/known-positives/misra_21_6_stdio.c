// expected: misra-c2023-21.6
// description: 使用标准库输入/输出函数
#include <stdio.h>

static void test_stdio(void)
{
    /* MISRA 21.6: 禁止使用标准 I/O 函数 */
    printf("Hello, World!\n");
}

static int32_t get_value(void)
{
    int32_t val;

    /* MISRA 21.6: scanf 也属于 I/O 函数 */
    scanf("%d", &val);
    return val;
}
