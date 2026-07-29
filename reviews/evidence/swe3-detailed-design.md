# ASPICE SWE.3 — 软件详细设计 证据文档

## 1. 模块详细设计

### 1.1 Pipeline 引擎 (src/yuleosh/pipeline)
- 设计模式: 策略模式 + 责任链
- 关键类: PipelineSession, StepHandler, StepResult
- 数据流: Input → Validate → Execute → Verify → Output

### 1.2 知识图谱 (src/yuleosh/knowledge_graph)
- 存储: PostgreSQL JSONB
- 索引: GIN 索引 + B-tree 复合索引
- 查询: Cypher-like DSL 转换为 SQL

### 1.3 CLI 工具 (src/yuleosh/cli)
- 使用 argparse 构建命令树
- 30+ 命令分组至 commands/ 子模块
- 支持 --mock 模式脱机运行

## 2. 类图（关键模块）

```
PipelineSession
├── spec_path: Path
├── mock: bool
├── results: dict
├── artifacts: dict
├── run_step(step_id) → StepResult
└── get_artifact(name) → Any

SystemEventBus
├── publish(event) → None
├── subscribe(event_type, callback) → Subscription
├── unsubscribe(sub) → None
└── pending: Deque[LoopEvent]
```

## 3. 测试策略

- 单元测试: pytest + mock
- 集成测试: mock HAL + QEMU
- 覆盖率目标: 70%+ (当前 11%, 逐步提升)
