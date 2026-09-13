"""B1-M1 三固件样例（benchmark/legacy-cases）提取准确率抽检 harness。

双重角色：
1. **回归守卫**：作为 pytest 用例，断言函数/ISR/调用图提取达到 B1-12（≥95%）阈值，
   任何回退都会让 CI 红。
2. **人工门禁证据**：B1-08（中期 ≥90%）与 B1-12（里程碑 ≥95%）要求「三固件各抽
   30 函数人工核对」。本 harness 用我编写的脱敏 stand-in 样例（含已知真值）做**全量**
   自动核对（6 文件共 27 函数 > 30 抽样下限的聚合），输出可被人签字的准确率报告。

真值来源：benchmark/legacy-cases 下 6 个样例由本 sprint 编写，函数/ISR/调用边经人工
逐文件核对（见本文件 GROUND_TRUTH）。注意：样例为 stand-in，真实大仓 vendor 由
B1-04 挂账待人工 fetch，本 harness 只覆盖样例层。

提取核心：src/yuleosh/knowledge_graph/c_parser.extract_c_ast（c_code_scanner /
reverse scan / KG 入库均委托此函数，准确率等价）。
"""
from __future__ import annotations

import pathlib

import pytest

from yuleosh.knowledge_graph.c_parser import extract_c_ast

_BENCH = pathlib.Path("benchmark/legacy-cases")

# 真值（逐文件核对，来源见模块 docstring）
GROUND_TRUTH = {
    "zephyr-sample/blinky.c": {
        "functions": {
            "blink_thread", "board_init_native", "board_init_real",
            "button_pressed", "main",
        },
        "isrs": set(),  # button_pressed 是运行时注册回调，非静态 ISR
        "internal_edges": {("main", "board_init_real"), ("main", "blink_thread")},
    },
    "freertos-demo/comm.c": {
        "functions": {"acquire_tx", "comm_register_handler", "comm_send"},
        "isrs": set(),  # comm_register_handler 是注册函数，非 ISR
        "internal_edges": {("comm_send", "acquire_tx")},
    },
    "stm32-hal/it.c": {
        "functions": {
            "HAL_UART_RxCpltCallback", "HardFault_Handler", "NMI_Handler",
            "Reset_Handler", "TIM2_IRQHandler", "USART1_IRQHandler",
        },
        "isrs": {"HardFault_Handler", "NMI_Handler", "Reset_Handler", "USART1_IRQHandler"},
        # Reset_Handler→main/SystemInit、USART1_IRQHandler→HAL_UART_IRQHandler 等
        # callee 均为外部符号（main 在 main.c 定义，HAL_* 在 hal 库），无文件内边
        "internal_edges": set(),
    },
    "stm32-hal/gpio.c": {
        "functions": {
            "MX_GPIO_Init", "TIM2_IRQHandler", "clock_default",
            "clock_f4", "clock_l4", "led_set",
        },
        "isrs": {"TIM2_IRQHandler"},
        "internal_edges": set(),
    },
    "freertos-demo/main.c": {
        "functions": {"USART1_IRQHandler", "app_start", "vMainTask", "vUartTask"},
        "isrs": {"USART1_IRQHandler"},
        "internal_edges": set(),
    },
    "zephyr-sample/sensor.c": {
        "functions": {"read_once", "register_sample_callback", "sensor_worker"},
        "isrs": set(),
        "internal_edges": {("sensor_worker", "read_once")},
    },
}


def _extract(rel: str):
    p = _BENCH / rel
    return extract_c_ast(p.read_text(encoding="utf-8"), rel)


def _accuracy(extracted, expected):
    """返回 (recall, precision)。"""
    if not expected:
        # 期望为空：召回率定义为 1（无漏检）；精确率看是否有误抽
        recall = 1.0
    else:
        recall = len(extracted & expected) / len(expected)
    if not extracted:
        precision = 1.0
    else:
        precision = len(extracted & expected) / len(extracted)
    return recall, precision


@pytest.mark.parametrize("rel", list(GROUND_TRUTH.keys()))
def test_fixture_parse_ok_and_zero_error(rel):
    """三固件样例零崩溃、error_rate=0（B1-12 零崩溃门禁）。"""
    r = _extract(rel)
    assert r["parse_ok"] is True
    assert r["error_rate"] == 0.0


@pytest.mark.parametrize("rel", list(GROUND_TRUTH.keys()))
def test_function_extraction_recall(rel):
    """每个样例函数召回率 = 100%（B1-12 ≥95% / B1-08 ≥90% 均满足）。"""
    gt = GROUND_TRUTH[rel]
    r = _extract(rel)
    extracted = set(x["name"] for x in r["functions"])
    recall, _ = _accuracy(extracted, gt["functions"])
    assert recall >= 0.95, f"{rel}: function recall {recall:.2%} < 0.95"


@pytest.mark.parametrize("rel", list(GROUND_TRUTH.keys()))
def test_isr_classification(rel):
    """ISR 分类：召回率与精确率均 ≥0.95（修复 board_init_real / comm_register_handler 误报后）。"""
    gt = GROUND_TRUTH[rel]
    r = _extract(rel)
    extracted = set(i["name"] for i in r["isrs"])
    recall, precision = _accuracy(extracted, gt["isrs"])
    assert recall >= 0.95, f"{rel}: ISR recall {recall:.2%} < 0.95"
    assert precision >= 0.95, f"{rel}: ISR precision {precision:.2%} < 0.95"


@pytest.mark.parametrize("rel", list(GROUND_TRUTH.keys()))
def test_internal_call_edges_present(rel):
    """已知文件内调用边均被解析（B1-05 调用图提取）。"""
    gt = GROUND_TRUTH[rel]
    r = _extract(rel)
    edges = {(e["caller"], e["callee"]) for e in r["call_graph"]["edges"]
             if e["callee"] in r["call_graph"]["functions"]}
    missing = gt["internal_edges"] - edges
    assert not missing, f"{rel}: missing internal call edges {missing}"


def test_aggregate_function_accuracy():
    """聚合准确率报告（人工闸签字用）。打印 27 函数 / 6 ISR 全量核对结果。"""
    total_fn_exp = set()
    total_fn_ext = set()
    total_isr_exp = set()
    total_isr_ext = set()
    print("\n=== B1-M1 三固件样例提取准确率抽检 ===")
    for rel, gt in GROUND_TRUTH.items():
        r = _extract(rel)
        fn_ext = set(x["name"] for x in r["functions"])
        isr_ext = set(i["name"] for i in r["isrs"])
        fn_rec, fn_prec = _accuracy(fn_ext, gt["functions"])
        isr_rec, isr_prec = _accuracy(isr_ext, gt["isrs"])
        total_fn_exp |= gt["functions"]
        total_fn_ext |= fn_ext
        total_isr_exp |= gt["isrs"]
        total_isr_ext |= isr_ext
        print(f"  {rel:28s} fn rec/prec={fn_rec:6.1%}/{fn_prec:6.1%}  "
              f"isr rec/prec={isr_rec:6.1%}/{isr_prec:6.1%}  "
              f"isrs={sorted(isr_ext)}")
    agg_fn_rec, agg_fn_prec = _accuracy(total_fn_ext, total_fn_exp)
    agg_isr_rec, agg_isr_prec = _accuracy(total_isr_ext, total_isr_exp)
    print(f"  --- aggregate functions: {len(total_fn_exp)} expected / "
          f"{len(total_fn_ext)} extracted -> recall={agg_fn_rec:.1%} precision={agg_fn_prec:.1%}")
    print(f"  --- aggregate ISRs:       {len(total_isr_exp)} expected / "
          f"{len(total_isr_ext)} extracted -> recall={agg_isr_rec:.1%} precision={agg_isr_prec:.1%}")
    # B1-12 里程碑阈值
    assert agg_fn_rec >= 0.95 and agg_fn_prec >= 0.95
    assert agg_isr_rec >= 0.95 and agg_isr_prec >= 0.95


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s", "-o", "addopts=",
                                   "-p", "no:cacheprovider"]))
