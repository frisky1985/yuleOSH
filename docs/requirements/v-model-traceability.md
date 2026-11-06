# V 模型追溯策略

> 本文件是受控的追溯声明，不是推断结果。`chain` 只按此表生成 `derive` 边，
> 未匹配到上游的需求不会被强行归类。
> 下游按章节前缀最长匹配；上游可写需求 ID 或章节前缀，并可逗号分隔多个。

| 下游章节前缀 | 上游需求 | 关系 |
|:-------------|:---------|:-----|
| RS-005 | STAKE-002, STAKE-003 | derive |
| RS-007 | STAKE-004 | derive |
| RS-012 | STAKE-004 | derive |
| RS-014 | STAKE-004 | derive |
| RS- | STAKE-001 | derive |
| NFR- | STAKE-001 | derive |
| CR- | STAKE-004 | derive |
| SYSARCH-001 | RS-001 | derive |
| SYSARCH-002 | RS-002 | derive |
| SYSARCH-003 | RS-003 | derive |
| SYSARCH-004 | RS-004, RS-008, RS-009 | derive |
| SYSARCH-005 | RS-005 | derive |
| SYSARCH-006 | RS-007, RS-012, RS-014 | derive |
| SYSARCH-007 | RS-006, RS-011, RS-013 | derive |
| SYSARCH-008 | RS-015 | derive |
| SWR-001 | SYSARCH-001 | derive |
| SWR-002 | SYSARCH-002 | derive |
| SWR-003 | SYSARCH-003 | derive |
| SWR-004 | SYSARCH-004 | derive |
| SWR-008 | SYSARCH-004 | derive |
| SWR-009 | SYSARCH-004 | derive |
| SWR-012 | SYSARCH-006 | derive |
| SWR-013 | SYSARCH-006 | derive |
| SWR-014 | SYSARCH-006 | derive |
| SWR- | SYSARCH-001 | derive |
| REQ-001 | SYSARCH-001 | derive |
| REQ-002 | SYSARCH-002 | derive |
| REQ-003 | SYSARCH-003 | derive |
| REQ-004 | SYSARCH-004 | derive |
| REQ-005 | SYSARCH-005 | derive |
| REQ-006 | SYSARCH-007 | derive |
| REQ-007 | SYSARCH-006 | derive |
| REQ-008 | SYSARCH-004 | derive |
| REQ-009 | SYSARCH-004 | derive |
| REQ-010 | SYSARCH-004 | derive |
| REQ-011 | SYSARCH-007 | derive |
| REQ-012 | SYSARCH-007 | derive |
| REQ-013 | SYSARCH-007 | derive |
| REQ-NFR-001 | SYSARCH-004 | derive |
| REQ-NFR-002 | SYSARCH-002 | derive |
| KG- | SYSARCH-008 | derive |
| TG- | SYSARCH-007 | derive |
| Scenario: | SYSARCH-004 | derive |
| SWARCH-001 | REQ-001 | derive |
| SWARCH-002 | REQ-002 | derive |
| SWARCH-003 | REQ-003 | derive |
| SWARCH-004 | REQ-004, REQ-008, REQ-009 | derive |
| SWARCH-005 | REQ-005 | derive |
| SWARCH-006 | REQ-007, REQ-012 | derive |
| SWARCH-007 | REQ-006, REQ-011, REQ-013 | derive |
| SWARCH-008 | KG-001 | derive |
| DD-001 | SWARCH-001 | derive |
| DD-002 | SWARCH-002 | derive |
| DD-003 | SWARCH-003 | derive |
| DD-004 | SWARCH-004 | derive |
| DD-005 | SWARCH-005 | derive |
| DD-006 | SWARCH-006 | derive |
| DD-007 | SWARCH-007 | derive |
| DD-008 | SWARCH-008 | derive |
