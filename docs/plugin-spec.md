# yuleOSH Plugin Spec v0.1

> 插件市场规范文档 — 对标 VS Code 扩展市场模式，让社区贡献 Plugin 和 Skill。

---

## 1. Plugin 类型

| 类型 | 标识 | 用途 | 示例 |
|------|------|------|------|
| **Target Plugin** | `target` | MCU/平台支持 | `esp32`, `stm32`, `rp2040` |
| **Skill Plugin** | `skill` | AI Agent 能力扩展 | AUTOSAR 配置助手, 时序分析 |
| **Template Plugin** | `template` | 项目模板 | `freertos`, `zephyr`, `bare-metal` |
| **Tool Plugin** | `tool` | 外部工具集成 | `openocd`, `esptool`, `jlink` |

---

## 2. Plugin 目录结构

每个 Plugin 是一个规范化的目录，必须包含以下文件：

```
my-plugin/
├── manifest.json          # Plugin 元数据（必需）
├── main.py                # Sky 入口（可选，纯模板可省略）
├── assets/                # 图标 / 截图（可选）
│   ├── icon.png
│   └── screenshot-1.png
├── lib/                   # 内部依赖（可选）
│   └── helper.py
└── README.md              # 使用说明（推荐）
```

### manifest.json Schema

```json
{
  "$schema": "https://yuleai.app/schemas/plugin-manifest-v1.json",
  "name": "plugin-name",
  "version": "1.0.0",
  "type": "target",
  "description": "Short description of the plugin",
  "author": "Community Author",
  "entry": "main.py",
  "min_yuleosh_version": "0.4.0",
  "max_yuleosh_version": "0.5.0",
  "tags": ["esp32", "freertos"],
  "dependencies": {},
  "repository": {
    "type": "github",
    "url": "https://github.com/frisky1985/yuleOSH/plugins/plugin-name"
  },
  "license": "MIT",
  "icon": "assets/icon.png"
}
```

### 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 插件名称，kebab-case，全局唯一 |
| `version` | string | ✅ | SemVer 版本号 |
| `type` | string | ✅ | 插件类型：`target`/`skill`/`template`/`tool` |
| `description` | string | ✅ | 简短说明（≤120字符） |
| `author` | string | ✅ | 作者名或组织 |
| `entry` | string | 否 | 主入口文件（相对路径），纯模板可省略 |
| `min_yuleosh_version` | string | ✅ | 兼容的最低 yuleOSH 版本 |
| `max_yuleosh_version` | string | 否 | 兼容的最高 yuleOSH 版本 |
| `tags` | string[] | 否 | 搜索标签 |
| `dependencies` | object | 否 | 插件依赖 `{"plugin-name": ">=1.0.0"}` |
| `repository` | object | 否 | 源码仓库信息 |
| `license` | string | 否 | 许可证标识符（如 MIT, Apache-2.0） |
| `icon` | string | 否 | 图标文件路径（相对 manifest.json） |

---

## 3. Skill Manifest 扩展

Skill 是更高层次的 Plugin 组合，多个 Plugin 编排成一个工作流。Skill Manifest 在 Plugin Manifest 基础上扩展 `workflow` 字段。

```json
{
  "name": "autosar-config-helper",
  "version": "1.0.0",
  "type": "skill",
  "description": "AUTOSAR 配置助手 — 从 ARXML 生成代码",
  "author": "yuleAI",
  "entry": "main.py",
  "min_yuleosh_version": "0.4.0",
  "tags": ["autosar", "arxml", "codegen"],

  "workflow": {
    "version": "1",
    "steps": [
      {
        "id": "parse-arxml",
        "plugin": "arxml-parser",
        "inputs": {
          "file": "$.input.arxml_path"
        }
      },
      {
        "id": "generate-config",
        "plugin": "autosar-codegen",
        "depends_on": ["parse-arxml"],
        "inputs": {
          "model": "$steps.parse-arxml.output.model",
          "template": "$.input.template"
        }
      }
    ],
    "outputs": {
      "config": "$steps.generate-config.output"
    }
  }
}
```

### workflow.steps 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 步骤唯一标识 |
| `plugin` | string | 要调用的 Plugin 名称 |
| `inputs` | object | 输入参数，支持 JSONPath 引用 |
| `depends_on` | string[] | 依赖的步骤 ID 列表 |
| `condition` | string | 可选执行条件表达式 |

---

## 4. Plugin 生命周期

```
[开发] → [打包] → [发布] → [发现] → [安装] → [加载] → [执行] → [卸载]
```

1. **开发**: 按规范目录结构编写 Plugin
2. **打包**: `yuleosh plugin pack ./my-plugin` → 生成 `.yuleosh-plugin` 包
3. **发布**: 推送到 GitHub Releases 或 yuleOSH 注册表
4. **发现**: `yuleosh plugin search esp32` 从注册表搜索
5. **安装**: `yuleosh plugin install esp32-blink` 下载到本地
6. **加载**: PluginManager 读取 manifest.json 并动态导入入口
7. **执行**: PluginSandbox 提供沙箱执行环境
8. **卸载**: `yuleosh plugin uninstall esp32-blink` 移除文件

---

## 5. 安全约束

所有 Plugin 在沙箱中执行，受限策略：

| 维度 | 默认策略 | 可配置 |
|------|----------|--------|
| 文件系统 | 仅读写 Plugin 自己的目录 | 通过 manifest `permissions` 声明 |
| 网络 | 禁止出站连接 | 通过 manifest `permissions` 声明 |
| 系统调用 | 禁止子进程/exec | 通过 manifest `permissions` 声明 |
| 执行超时 | 30 秒 | 通过 manifest `timeout` 配置 |
| 内存限制 | 256 MB | 系统级限制 |

### manifest.json Permissions 声明示例

```json
{
  "permissions": {
    "filesystem": {
      "read": ["/tmp/", "./output/"],
      "write": ["./output/"]
    },
    "network": {
      "allow": ["api.github.com:443"]
    },
    "system": {
      "exec": false,
      "env_read": ["PATH", "HOME"]
    }
  },
  "timeout": 60
}
```

---

## 6. 版本兼容性检查

安装时执行版本检查：

1. `min_yuleosh_version` ≤ 当前 yuleOSH 版本 ≤ `max_yuleosh_version`（如有）
2. 所有 `dependencies` 中的插件已安装且版本满足约束
3. SemVer 版本匹配规则：`>=1.0.0`、`^1.2.0`、`~1.2.3`

---

## 7. 注册表源

| 源 | 协议 | 说明 |
|-----|------|------|
| GitHub Releases | HTTPS | 从 GitHub repo releases 下载 `.yuleosh-plugin` |
| yuleOSH Registry | HTTPS | 官方注册表，含审核机制 |
| 自定义源 | HTTPS | 自建私有注册表（企业场景） |

注册表索引格式：

```json
{
  "index_version": 1,
  "plugins": {
    "esp32-blink": {
      "name": "esp32-blink",
      "versions": {
        "1.0.0": {
          "download_url": "https://...",
          "sha256": "abc123...",
          "manifest": { "...": "..." }
        }
      }
    }
  }
}
```

---

## 8. Plugin 打包格式

`.yuleosh-plugin` 是 gzipped tar 包：

```
my-plugin-1.0.0.yuleosh-plugin
├── manifest.json
├── main.py
├── lib/
├── assets/
└── README.md
```

打包验证：
1. manifest.json 必须存在且符合 Schema
2. 如指定 `entry`，该文件必须存在
3. 版本号必须为有效的 SemVer
4. `min_yuleosh_version` 必须满足
