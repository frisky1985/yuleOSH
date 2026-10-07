# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH AI 审查引擎（review 包）。

此前本目录是隐式命名空间包（无 __init__.py），现补为正规包并聚集公共 API。
生产代码实际调用入口为 `review.run.review_architecture`（见
`pipeline/step_handlers/review_arch.py`）。`FindingTracker` 与 resource_predictor
下的资源预估函数为配套工具库，目前仅被测试覆盖、尚未接入 Pipeline 运行时——
如要在评审步骤中持久化 findings 或做资源预估，应在此登记调用方。
"""

from yuleosh.review.run import review_architecture
from yuleosh.review.tracker import FindingTracker
from yuleosh.review.resource_predictor import (
    predict_resources,
    predict_all_in_project,
)

__all__ = [
    "review_architecture",
    "FindingTracker",
    "predict_resources",
    "predict_all_in_project",
]
