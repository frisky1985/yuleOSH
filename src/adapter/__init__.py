"""
yuleOSH Adapter Module — Vector CANoe / dSPACE等总线仿真工具适配器。

Adapter Pattern 实现，将Pipeline产出的测试用例转化为各平台可执行格式。
与核心Pipeline完全解耦，可独立使用和扩展。
"""

from .vector_adapter import VectorCANoeAdapter
from .dspace_adapter import DSAPCEAdapter

__all__ = [
    "VectorCANoeAdapter",
    "DSAPCEAdapter",
]
