---
artifact: SYS-SEAT-006-TC-01__round1
stage: test
verdict: PASS
actual_result: 电机开路/NTC 开路/LIN 断线 DTC 均一致，掉电保持，0x14 清除后不重现
log_link: logs/SYS-SEAT-006-TC-01.log（示例占位）
fills:
  - ENG_测试规范::SYS-SEAT-006-TC-01::实际结果
  - ENG_测试规范::SYS-SEAT-006-TC-01::测试日志链接
  - ENG_测试规范::SYS-SEAT-006-TC-01::判定结论
---

# 示例数据 · 不得作为项目证据

# SYS-SEAT-006-TC-01 第 1 轮测试执行记录

- 被测项：故障诊断与 DTC
- 期望结果：DTC 与故障一致，掉电保持，清除后不再重现
- 实际结果：电机开路/NTC 开路/LIN 断线 DTC 均一致，掉电保持，0x14 清除后不重现
- 测试日志链接：logs/SYS-SEAT-006-TC-01.log（示例占位）
- 判定结论：PASS

> 本文件模拟 pipeline test 阶段输出：stage 自声明 fills 槽位，
> 由 evidence_check.py 校验闭合与哈希，evidence_render.py 回写 xlsx。
