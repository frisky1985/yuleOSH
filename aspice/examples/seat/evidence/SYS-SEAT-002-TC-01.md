---
artifact: SYS-SEAT-002-TC-01__round1
stage: test
verdict: PASS
fills:
  - ENG_测试规范::SYS-SEAT-002-TC-01::实际结果
  - ENG_测试规范::SYS-SEAT-002-TC-01::测试日志链接
  - ENG_测试规范::SYS-SEAT-002-TC-01::判定结论
---

# 示例数据 · 不得作为项目证据

# SYS-SEAT-002-TC-01 第 1 轮测试执行记录

- 被测项：位置记忆与调用
- 期望结果：3 组均可保存/调用，重复调用偏差 ≤5 mm
- 实际结果：3 组位置保存成功，断电 10min 后调用偏差 2.1/1.8/2.4mm
- 测试日志链接：logs/SYS-SEAT-002-TC-01.log（示例占位）
- 判定结论：PASS

> 本文件模拟 pipeline test 阶段输出：stage 自声明 fills 槽位，
> 由 evidence_check.py 校验闭合与哈希。
