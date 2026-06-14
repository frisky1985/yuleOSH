#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
monitor — 串口监视器

实时捕获嵌入式设备串口输出，支持后台线程运行、超时等待特定字符串、
历史日志捕获等功能。

Usage::

    from hardware.monitor import SerialMonitor

    mon = SerialMonitor("/dev/ttyUSB0", baud=115200)
    mon.start()           # 后台线程
    ...
    mon.wait_for_string("Boot OK", timeout=30)
    logs = mon.get_log()
    mon.stop()

"""

import logging
import threading
import time

log = logging.getLogger("hardware.monitor")


class SerialMonitorError(RuntimeError):
    """串口监视器相关错误。"""


class PortNotFoundError(SerialMonitorError):
    """串口设备不存在或不可用。"""


class SerialMonitor:
    """串口监视器 — 实时捕获嵌入式设备串口输出。

    通过后台线程持续读取串口数据，线程安全地存储历史日志。

    Parameters
    ----------
    port : str
        串口设备路径（例如 ``"/dev/ttyUSB0"``, ``"/dev/cu.usbserial-XXXX"``）。
    baud : int
        波特率，默认 115200。
    timeout : float
        读取超时秒数，默认 1.0。影响 ``wait_for_string`` 的检查间隔。
    """

    def __init__(self, port: str, baud: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baud = baud
        self.timeout = timeout

        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._serial = None  # 延迟导入 pyserial
        self._lock = threading.Lock()
        self._log: list[str] = []

    # ---- 生命周期 --------------------------------------------------------

    def start(self) -> threading.Thread:
        """启动后台监视线程。

        Returns
        -------
        threading.Thread
            后台线程句柄，可用于 ``join()`` 等操作。
        """
        if self._running.is_set():
            log.warning("Monitor already running on %s", self.port)
            return self._thread

        # 尝试打开串口
        self._open_serial()

        self._running.set()
        self._thread = threading.Thread(
            target=self._read_loop,
            name=f"SerialMonitor-{self.port}",
            daemon=True,
        )
        self._thread.start()
        log.info("Serial monitor thread started on %s @ %d baud", self.port, self.baud)
        return self._thread

    def stop(self):
        """停止后台监视线程并关闭串口。"""
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        self._close_serial()
        log.info("Serial monitor stopped on %s", self.port)

    # ---- 数据访问 --------------------------------------------------------

    def get_log(self) -> list[str]:
        """获取捕获的串口日志。

        Returns
        -------
        list[str]
            按时间顺序排列的日志行列表（线程安全快照）。
        """
        with self._lock:
            return list(self._log)

    def wait_for_string(self, s: str, timeout: int = 10) -> bool:
        """等待串口输出中出现特定字符串。

        轮询检查已捕获的日志行，适合少量数据场景。
        对于高吞吐场景建议使用基于回调的方式。

        Parameters
        ----------
        s : str
            要等待的字符串。
        timeout : int
            超时秒数，默认 10。

        Returns
        -------
        bool
            超时前找到返回 ``True``，否则 ``False``。
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._search_log(s):
                return True
            time.sleep(0.05)  # 50ms 检查间隔
        return False

    def clear_log(self):
        """清空已捕获的日志。"""
        with self._lock:
            self._log.clear()

    # ---- 内部实现 --------------------------------------------------------

    def _open_serial(self):
        """打开串口。

        延迟导入 ``serial`` 模块，避免未安装 pyserial 时直接报错。
        如果 pyserial 未安装，使用模拟串口进行测试。
        """
        if self._serial is not None:
            return
        try:
            import serial as pyserial_module
            self._serial = pyserial_module.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout,
            )
        except ImportError:
            log.warning(
                "pyserial not installed. Falling back to mock serial "
                "(for testing only).\n"
                "  Install: pip install pyserial"
            )
            self._serial = _MockSerial(self.port)
        except FileNotFoundError as exc:
            raise PortNotFoundError(
                f"Serial port not found: {self.port}\n"
                f"  Check connection with: ls {self.port.rsplit('/', 1)[0]}"
            ) from exc
        except OSError as exc:
            raise PortNotFoundError(
                f"Cannot open {self.port}: {exc}\n"
                f"  Try: sudo chmod 666 {self.port}"
                if "Permission denied" in str(exc) else str(exc)
            ) from exc

    def _close_serial(self):
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _read_loop(self):
        """后台线程的主循环。"""
        while self._running.is_set():
            try:
                line = self._read_line()
                if line:
                    line = line.rstrip("\r\n")
                    with self._lock:
                        self._log.append(line)
                    log.debug("SERIAL: %s", line)
            except Exception as exc:
                log.warning("Serial read error: %s", exc)
                time.sleep(0.1)

    def _read_line(self) -> str | None:
        """从串口读取一行数据。

        使用 pyserial 的 ``readline()`` 方法，超时由 ``self.timeout`` 控制。
        """
        if self._serial is None:
            return None
        try:
            data = self._serial.readline()
            if data:
                return data.decode("utf-8", errors="replace")
            return None
        except Exception:
            return None

    def _search_log(self, s: str) -> bool:
        """在线程安全快照中搜索字符串。"""
        with self._lock:
            for line in self._log:
                if s in line:
                    return True
        return False

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def __repr__(self) -> str:
        return (
            f"<SerialMonitor port={self.port} baud={self.baud} "
            f"running={self._running.is_set()}>"
        )


# ---------------------------------------------------------------------------
# Mock Serial — pyserial 未安装时的 fallback
# ---------------------------------------------------------------------------

class _MockSerial:
    """Mock pyserial Serial 类，用于测试环境。

    不依赖实际硬件，返回空数据。可通过 ``inject_data()`` 注入测试数据。
    """

    def __init__(self, port: str):
        self.port = port
        self._injected: list[bytes] = []
        self._closed = False

    def readline(self) -> bytes:
        if self._injected:
            return self._injected.pop(0)
        time.sleep(0.1)
        return b""

    def inject(self, data: str):
        """注入模拟串口数据。"""
        self._injected.append((data + "\n").encode("utf-8"))

    def close(self):
        self._closed = True

    @property
    def is_open(self) -> bool:
        return not self._closed
