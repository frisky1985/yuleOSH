// expected: misra-c2023-8.4
// description: 外部函数定义前不可见兼容声明
#include <stdint.h>

/* MISRA 8.4: test_no_proto 有外部链接但之前无可见声明 */
void test_no_proto(void)
{
    int32_t x = 0;
    (void)x;
}
