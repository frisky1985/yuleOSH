---
artifact: SYS-SEAT-005-TC-01__round1
stage: test
verdict: PASS
fills:
  - ENG_测试规范::SYS-SEAT-005-TC-01::实际结果
  - ENG_测试规范::SYS-SEAT-005-TC-01::测试日志链接
  - ENG_测试规范::SYS-SEAT-005-TC-01::判定结论
---

# 示例数据 · 不得作为项目证据

# SYS-SEAT-005-TC-01 第 1 轮测试执行记录

- 被测项：防夹与堵转保护
- 期望结果：触发后 ≤200 ms 停止，反向可立即退出
- 实际结果：滑轨/靠背触发停止时间 142/138ms，反向退出正常
- 测试日志链接：logs/SYS-SEAT-005-TC-01.log（示例占位）
- 判定结论：PASS

> 本文件模拟 pipeline test 阶段输出：stage 自声明 fills 槽位，
> 由 evidence_check.py 校验闭合与哈希。
