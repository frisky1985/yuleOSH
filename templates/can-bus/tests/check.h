/**
 * yuleOSH shared C unit-test harness — "c-harness".
 *
 * 轻量、零依赖、宿主机可编译的 CHECK harness。所有 demo 模板的单元测试与
 * 系统合格性场景共用同一套断言宏, 使 spec §4b "custom-Check harness" 的宣称
 * 成为事实 (而非幻觉的 ctest/Unity)。
 *
 * 用法 (测试 .c 内 #include 本头, 并自带 main()):
 *   #include "check.h"
 *   int main(void) {
 *       CHECK(foo() == 1);
 *       CHECK_EQ(bar(), 2);
 *       return c_harness_report();   // 0 = 全过, 非0 = 失败数
 *   }
 *
 * 设计约束 (与 templates 的构建结构匹配):
 *   - 纯头文件, 计数全局量在 include 处定义一次 (include guard 保证单 TU 内唯一)。
 *   - demo 测试二进制均为单 TU (test_main.c #include "../src/main.c"), 故不会
 *     跨 TU 重复符号; 系统合格性场景 (scenario_test.c) 各自独立二进制同理。
 *   - 不依赖 ctest/CMake CTest; 由 `make test` / `make test-system` 直接运行。
 */
#ifndef YULEOSH_C_HARNESS_H
#define YULEOSH_C_HARNESS_H

#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 跨断言共享的计数 (单 TU 内由本头定义一次) */
int c_harness_checks = 0;
int c_harness_failures = 0;

/* CHECK(cond): 记录一次断言; 失败打印文件:行号并累加失败计数 (不中止)。 */
#define CHECK(cond)                                                          \
    do {                                                                     \
        c_harness_checks++;                                                  \
        if ((cond)) {                                                        \
            printf("  ok:   %s\n", #cond);                                   \
        } else {                                                             \
            printf("  FAIL: %s  (%s:%d)\n", #cond, __FILE__, __LINE__);      \
            c_harness_failures++;                                            \
        }                                                                     \
    } while (0)

/* CHECK_EQ(a, b): 数值相等断言, 失败时打印双方值。 */
#define CHECK_EQ(a, b)                                                       \
    do {                                                                     \
        c_harness_checks++;                                                  \
        long long _c_harness_va = (long long)(a);                            \
        long long _c_harness_vb = (long long)(b);                            \
        if (_c_harness_va == _c_harness_vb) {                               \
            printf("  ok:   %s == %s\n", #a, #b);                           \
        } else {                                                             \
            printf("  FAIL: %s (%lld) == %s (%lld)  (%s:%d)\n",             \
                   #a, _c_harness_va, #b, _c_harness_vb,                     \
                   __FILE__, __LINE__);                                      \
            c_harness_failures++;                                            \
        }                                                                     \
    } while (0)

/* 打印汇总并返回失败数 (0 = 全过)。作为 main 的返回值使 `make test` 正确判定。 */
static int c_harness_report(void)
{
    printf("\n[c-harness] %d checks, %d failures\n",
           c_harness_checks, c_harness_failures);
    return c_harness_failures;
}

#ifdef __cplusplus
}
#endif

#endif /* YULEOSH_C_HARNESS_H */
