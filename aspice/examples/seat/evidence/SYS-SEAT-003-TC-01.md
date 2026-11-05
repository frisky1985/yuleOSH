---
artifact: SYS-SEAT-003-TC-01__round1
stage: test
verdict: PASS
fills:
  - ENG_测试规范::SYS-SEAT-003-TC-01::实际结果
  - ENG_测试规范::SYS-SEAT-003-TC-01::测试日志链接
  - ENG_测试规范::SYS-SEAT-003-TC-01::判定结论
---

# 示例数据 · 不得作为项目证据

# SYS-SEAT-003-TC-01 第 1 轮测试执行记录

- 被测项：座椅加热控制
- 期望结果：3 档稳态温度符合标定值，过温 5 s 内切断
- 实际结果：3 档稳态 38/42/46℃，注入 NTC 过温后 3.2s 切断
- 测试日志链接：logs/SYS-SEAT-003-TC-01.log（示例占位）
- 判定结论：PASS

> 本文件模拟 pipeline test 阶段输出：stage 自声明 fills 槽位，
> 由 evidence_check.py 校验闭合与哈希。
