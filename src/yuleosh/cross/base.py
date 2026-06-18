"""
yuleOSH — Flash Abstraction Layer shared types.

Provides ``FlashResult``, ``FlashError``, and the ``FlashTool`` abstract
base class used by all backend modules.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class FlashResult:
    """Result of a flash operation.

    Attributes
    ----------
    passed : bool
        ``True`` if flashing succeeded.
    log : str
        Full stdout/stderr output from the flash tool.
    tool : str
        The flash tool used (e.g. ``"openocd"``, ``"jlink"``).
    elapsed : float
        Wall-clock duration in seconds.
    error : str | None
        Error message on failure.
    """

    passed: bool = True
    log: str = ""
    tool: str = ""
    elapsed: float = 0.0
    error: str | None = None


class FlashError(RuntimeError):
    """Raised when no suitable flash tool is available, or when a
    flash operation fails irrecoverably."""
    pass


class FlashTool(ABC):
    """Abstract base for all flash tool implementations.

    Subclasses must implement :meth:`name` and :meth:`write`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier (e.g. ``"openocd"``, ``"jlink"``)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this tool is installed on the system."""
        ...

    @abstractmethod
    def write(self, firmware: str, config: Any) -> FlashResult:
        """Flash *firmware* to the target described by *config*."""
        ...

    @abstractmethod
    def erase(self, config: Any) -> FlashResult:
        """Erase the target device flash memory."""
        ...

    def verify(self, firmware: str, config: Any) -> FlashResult:
        """Verify the flashed firmware matches the source file."""
        return FlashResult(
            passed=False,
            log="Verify not supported by this tool",
            tool=self.name,
            error="Verify not supported",
        )
