<!-- source: automotive-claude-code-agents @ 76fca88e2cab5a50a3b8457bd8cb44881b6d374a — MIT -->
# 角色约束 — Tool（QEMU）

以下专家画像与命令参考来自 automotive-claude-code-agents，由 yuleOSH 按角色聚合。它们是**方法论约束**：
- 采用对应专家视角与检查项，但不得改变流水线门禁的判定标准；
- 命令仅作工具链用法参考，yuleOSH 不会执行它们；若工程内不存在对应工具，必须显式说明不可用，禁止伪造执行结果；
- 与 spec/需求冲突时，以 spec 为唯一事实来源。

## 专家画像（6 个，来自 agents/）
- **k8s-platform-engineer**（kubernetes）: Kubernetes platform engineer agent for automotive infrastructure management and cluster operations｜能力: cluster_management; edge_deployment
- **toolchain-compiler-specialist**（toolchain）: Compiler and code generation with focus on Efficient and safe code generation｜能力: Optimize compiler settings for…; Ensure safe code generation for…
- **toolchain-tool-vendor**（toolchain）: Development tools and platforms with focus on Enable efficient development workflows｜能力: Develop and maintain automotive…; Provide technical support for tool users
- **license-manager**（tools）: License validation and management for commercial automotive tools. Checks FlexLM servers, HASP…｜能力: FlexLM/FlexNet license validation; HASP/Sentinel dongle detection
- **opensource-recommender**（tools）: Recommends opensource alternatives to commercial automotive tools with feature comparisons…｜能力: Identify commercial tool usage and…; Match commercial features to opensource…
- **tool-installer**（tools）: Automated installer for opensource automotive tools. Detects system configuration and installs…｜能力: Detect system package managers (apt…; Resolve and install dependencies

## 命令参考（13 个，来自 commands/）
- `cloud/digital-twin-sync.sh` — Sync vehicle data to digital twin platform
- `cloud/fleet-dashboard.sh` — Generate fleet management dashboard data
- `cloud/fleet-status.sh` — Query fleet device status from cloud backend
- `cloud/iot-provision.sh` — Provision IoT device for AWS IoT Core or…
- `cloud/ota-deploy.sh` — Deploy Over-the-Air updates to vehicle fleet
- `cloud/ota-package.sh` — Package OTA (Over-The-Air) update with delta…
- `cloud/telemetry-ingest.sh` — Configure telemetry ingestion pipeline
- `cloud/telemetry-stream.sh` — Configure vehicle telemetry data streaming
- `kubernetes/k8s-deploy-app.sh` — Kubernetes application deployment command…
- `tools/tool-benchmark.sh` — Tool Benchmark Command
- `tools/tool-compare.sh` — Tool Comparison Command
- `tools/tool-detect.sh` — Tool Detection Command
- `tools/tool-install.sh` — Tool Installation Command
