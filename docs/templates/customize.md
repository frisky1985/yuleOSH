# 自定义模板教程

> 如何基于现有模板定制自己的 yuleOSH ECU 模板

---

## 模板结构

ECU 模板存储在 `src/yuleosh/templates/ecus/<name>/` 目录下。
每个模板包含：

```
template.yaml         # 模板元数据 (名称/MCU/BSW 列表)
*.j2                  # Jinja2 模板文件 (条件渲染用 {{ }} )
其他文件              # 直接复制的静态文件
```

---

## 方法 1: 基于现有模板修改

### 1.1 复制模板

```bash
cd <yuleOSH-repo>/src/yuleosh/templates/ecus
cp -r bcm my-custom-bcm
```

### 1.2 修改 template.yaml

```yaml
name: my-custom-bcm
version: 1.0.0
description: 自定义车身控制器 — 增加天窗/雨量传感器
mcu: S32K312
asil: ASIL_B
bsw_modules:
  - Mcu
  - Dio
  - Port
  - Gpt
  - Can
  - ...  # 添加或删除模块
swcs:
  - Door_SWC
  - Light_SWC
  - Wiper_SWC
  - Power_SWC
  - Sunroof_SWC  # 新增
```

### 1.3 修改 spec.md.j2

在 Jinja2 模板中添加或修改 SHALL 需求。使用条件语法控制不同 ASIL 等级的差异：

```markdown
### REQ-XXX: 自定义需求
{% if asil == 'ASIL_D' %}
- The system SHALL implement redundant measurement for this function
{% else %}
- The system SHOULD implement measurement for this function
{% endif %}
```

### 1.4 使用自定义模板

```bash
yuleosh init --template my-custom-bcm --name my-project
```

---

## 方法 2: 从零创建模板

### 2.1 创建目录

```bash
mkdir -p src/yuleosh/templates/ecus/my-ecm/
mkdir -p src/yuleosh/templates/ecus/my-ecm/src/app
mkdir -p src/yuleosh/templates/ecus/my-ecm/src/bsw
mkdir -p src/yuleosh/templates/ecus/my-ecm/tests/unit
```

### 2.2 创建 template.yaml

```yaml
name: my-ecm
version: 1.0.0
description: Engine Control Module — 发动机控制
mcu: S32K312
asil: ASIL_D
bsw_modules:
  - Mcu
  - Dio
  - Can
  - Spi
  - Pwm
  - Adc
swcs:
  - Injection_SWC
  - Ignition_SWC
```

### 2.3 创建模板文件

使用 `.j2` 扩展名的文件会经过 Jinja2 渲染。可用变量：

| 变量 | 说明 | 示例值 |
|:-----|:-----|:-------|
| `{{ project_name }}` | 项目名称 | `my-ecm` |
| `{{ template_name }}` | 模板名称 | `my-ecm` |
| `{{ mcu }}` | MCU 型号 | `S32K312` |
| `{{ mcu_family }}` | MCU 系列 | `S32K3` |
| `{{ mcu_arch }}` | 架构 | `ARM Cortex-M7` |
| `{{ mcu_cores }}` | 核心数 | `1` |
| `{{ mcu_flash_kb }}` | Flash 大小 | `1024` |
| `{{ mcu_ram_kb }}` | RAM 大小 | `192` |
| `{{ asil }}` | ASIL 代码 | `ASIL_D` |
| `{{ asil_label }}` | ASIL 标签 | `ASIL D` |
| `{{ bsw_modules }}` | BSW 模块列表 | [...] |
| `{{ swc_list }}` | SWC 列表 | [...] |
| `{{ num_bsw_modules }}` | BSW 数量 | `6` |
| `{{ generated_at }}` | 生成时间 | `2026-07-26 23:53` |
| `{{ generated_by }}` | 生成工具 | `yuleOSH init` |

### 2.4 测试模板

```bash
# 重新安装包
pip install -e .

# 测试
yuleosh init --template my-ecm --name test-ecm --output /tmp

# 验证产出
ls -la /tmp/test-ecm/
cat /tmp/test-ecm/docs/spec.md
```

---

## 高级: 添加自定义 filter

在 `ecus/__init__.py` 中可添加 Jinja2 filter：

```python
env.filters["camel_case"] = lambda s: ...  # 你的转换逻辑
```

可在模板中使用：
```jinja2
{{ my_variable | camel_case }}
```

---

## 技巧与最佳实践

1. **模板文件不要太大** — 每个模板 20~30 条 SHALL 就足够
2. **使用条件渲染** — `{% if asil == 'ASIL_D' %}` 处理不同安全等级
3. **项目命名空间** — `{{ project_name }}` 用于 include guards 和 namespace
4. **CI 配置个性化** — 不同领域的安全要求不同，调整 `ci-config.yaml.j2` 中的覆盖率阈值
5. **测试骨架** — 为每个 SWC 提供基础测试用例
