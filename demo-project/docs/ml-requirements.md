# 机器学习需求分析（MLE.1）

- 生成时间：2026-11-10T15:31:23+00:00
- 机器学习条目数：0

## 机器学习条目

| ID | 条目 | 类型 | 来源 | 状态 | 责任人 |
|:---|:---|:---|:---|:---|:---|
| — | （无条目：未检测到机器学习范围） | — | — | — | — |

## 范围与扫描来源

机器学习范围由以下客观信号识别（零命中亦如实记录）：

- `glob:**/*.onnx`
- `glob:**/*.pt`
- `glob:**/*.pth`
- `glob:**/*.h5`
- `glob:**/*.tflite`
- `glob:**/train*.py`
- `dir:models/`
- `dir:ml/`
- `dir:datasets/`

> 本次扫描未命中任何机器学习信号，判定为无机器学习范围；不做任何条目推断。若项目实际包含模型/训练/数据集，请补充上述信号文件或在登记文件中人工登记（origin: manual）。

## 可追溯性

- 登记文件：`docs/ml-item-register.yaml`（scan_sources 为扫描证据）。
- 方案见 `docs/ml-approach.md`（MLE.2）；评估结论见 `docs/ml-evaluation-report.md`（MLE.4）。
