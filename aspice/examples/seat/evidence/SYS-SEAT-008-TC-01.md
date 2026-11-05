---
artifact: SYS-SEAT-008-TC-01__round1
stage: test
verdict: PASS
fills:
  - ENG_测试规范::SYS-SEAT-008-TC-01::实际结果
  - ENG_测试规范::SYS-SEAT-008-TC-01::测试日志链接
  - ENG_测试规范::SYS-SEAT-008-TC-01::判定结论
---

# 示例数据 · 不得作为项目证据

# SYS-SEAT-008-TC-01 第 1 轮测试执行记录

- 被测项：LIN 通信与信号超时
- 期望结果：命令正确执行，断线 200 ms 内停止所有执行器
- 实际结果：开关/中控命令全部正确执行，断线 186ms 停止全部执行器
- 测试日志链接：logs/SYS-SEAT-008-TC-01.log（示例占位）
- 判定结论：PASS

> 本文件模拟 pipeline test 阶段输出：stage 自声明 fills 槽位，
> 由 evidence_check.py 校验闭合与哈希。
