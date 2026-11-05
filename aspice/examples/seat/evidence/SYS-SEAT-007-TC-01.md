---
artifact: SYS-SEAT-007-TC-01__round1
stage: test
verdict: PASS
fills:
  - ENG_测试规范::SYS-SEAT-007-TC-01::实际结果
  - ENG_测试规范::SYS-SEAT-007-TC-01::测试日志链接
  - ENG_测试规范::SYS-SEAT-007-TC-01::判定结论
---

# 示例数据 · 不得作为项目证据

# SYS-SEAT-007-TC-01 第 1 轮测试执行记录

- 被测项：电源与环境适应性
- 期望结果：边界内功能正常，欠压 <8.5 V 停止，休眠 ≤1 mA
- 实际结果：9/12/16V × -40/25/85℃ 全组合功能正常，8.4V 停止，休眠 0.6mA
- 测试日志链接：logs/SYS-SEAT-007-TC-01.log（示例占位）
- 判定结论：PASS

> 本文件模拟 pipeline test 阶段输出：stage 自声明 fills 槽位，
> 由 evidence_check.py 校验闭合与哈希。
