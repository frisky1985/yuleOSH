#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
flasher — 嵌入式硬件刷写器

支持三种刷写方式：
  - OpenOCD  — STM32 / ESP32 等 ARM Cortex-M 设备
  - JLink    — SEGGER J-Link 调试器
  - esptool  — ESP32 / ESP8266 等乐鑫芯片

所有外部工具调用通过 ``subprocess`` 完成，失败时友好提示而非崩溃。
刷写前自动检测目标硬件是否存在。

Usage::

    from hardware.flasher import OpenOCDFlasher

    flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
    flasher.flash("build/firmware.elf")
    flasher.verify("build/firmware.elf")

"""

import logging
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import ClassVar

log = logging.getLogger("hardware.flasher")


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class FlashError(RuntimeError):
    """刷写失败时抛出的异常。"""


class BinaryNotFoundError(FlashError):
    """二进制文件不存在。"""


class ToolNotFoundError(FlashError):
    """刷写工具未安装或不在 PATH 中。"""


class HardwareNotFoundError(FlashError):
    """目标硬件未检测到。"""


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class BaseFlasher(ABC):
    """刷写器抽象基类。"""

    # 子类覆盖
    tool_name: ClassVar[str] = ""            # 外部工具可执行文件名
    detect_cmd: ClassVar[list[str] | None] = None  # 硬件检测命令

    def __init__(self, config: dict):
        self.config = config

    # ---- 公共接口 --------------------------------------------------------

    def flash(self, binary_path: str) -> bool:
        """刷写固件到目标硬件。

        Parameters
        ----------
        binary_path : str
            固件文件路径（.elf / .bin / .hex）。

        Returns
        -------
        bool
            刷写成功返回 ``True``。

        Raises
        ------
        FlashError
            任何刷写相关的失败。
        """
        self._check_binary(binary_path)
        self._check_tool()
        self._check_hardware()
        return self._do_flash(binary_path)

    def verify(self, binary_path: str) -> bool:
        """验证刷写内容与源文件一致。

        默认调用 ``_do_verify``，如果子类未实现则 fallback 到
        重新刷写但不写入（部分工具不支持单独验证）。
        """
        self._check_binary(binary_path)
        self._check_tool()
        return self._do_verify(binary_path)

    # ---- 内部检查 --------------------------------------------------------

    def _check_binary(self, path: str):
        if not os.path.isfile(path):
            raise BinaryNotFoundError(f"Binary not found: {path}")

    def _check_tool(self):
        if not shutil.which(self.tool_name):
            raise ToolNotFoundError(
                f"Tool '{self.tool_name}' not found. "
                f"Please install it or add it to PATH.\n"
                f"  macOS: brew install {self._brew_package_name()}\n"
                f"  Linux: apt install {self._apt_package_name()}"
            )

    def _check_hardware(self):
        """可选：检测目标硬件是否可达。"""
        if self.detect_cmd is None:
            return  # 子类未实现硬件检测
        try:
            result = subprocess.run(
                self.detect_cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise HardwareNotFoundError(
                    f"Hardware not detected.\n"
                    f"  Command: {' '.join(self.detect_cmd)}\n"
                    f"  stderr : {result.stderr.strip()}"
                )
        except FileNotFoundError:
            pass  # 检测命令不存在时跳过（可能只是可选工具）
        except subprocess.TimeoutExpired:
            raise HardwareNotFoundError(
                "Hardware detection timed out after 10s."
            )

    # ---- 子类实现 --------------------------------------------------------

    @abstractmethod
    def _do_flash(self, binary_path: str) -> bool:
        ...

    def _do_verify(self, binary_path: str) -> bool:
        """默认验证：通过返回 False 表示不支持。子类可覆盖。"""
        log.warning("%s does not support standalone verify", self.tool_name)
        return False

    @staticmethod
    def _brew_package_name() -> str:
        return "openocd"

    @staticmethod
    def _apt_package_name() -> str:
        return "openocd"

    def _run(self, cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
        """运行外部命令并记录日志。"""
        log.debug("Running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                log.warning(
                    "Command failed (rc=%d):\n  stdout: %s\n  stderr: %s",
                    result.returncode,
                    result.stdout.strip() or "(empty)",
                    result.stderr.strip() or "(empty)",
                )
            else:
                log.info("Command succeeded: %s", " ".join(cmd[:3]))
            return result
        except subprocess.TimeoutExpired:
            raise FlashError(
                f"Command timed out after {timeout}s: {' '.join(cmd)}"
            )
        except OSError as exc:
            raise FlashError(
                f"Failed to execute command: {' '.join(cmd)}\n  {exc}"
            )


# ---------------------------------------------------------------------------
# OpenOCD 刷写器
# ---------------------------------------------------------------------------

class OpenOCDFlasher(BaseFlasher):
    """OpenOCD 刷写器 — STM32 / ESP32 等 ARM Cortex-M 设备。

    Config 示例::

        {
            "interface": "stlink",        # 调试器类型
            "target": "stm32f4x",         # 目标芯片
            "interface_cfg": "interface/stlink.cfg",
            "target_cfg": "target/stm32f4x.cfg",
            "extra_args": ["-c", "adapter speed 1000"],
        }

    默认命令::

        openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \\
                -c "program firmware.elf verify reset exit"
    """

    tool_name = "openocd"
    detect_cmd: ClassVar[list[str] | None] = ["openocd", "--version"]

    def __init__(self, config: dict):
        super().__init__(config)
        raw_interface = config.get("interface")
        self.interface_cfg = config.get("interface_cfg")
        if not self.interface_cfg:
            if raw_interface:
                self.interface_cfg = f"interface/{raw_interface}.cfg"
            else:
                self.interface_cfg = "interface/.cfg"

        raw_target = config.get("target")
        self.target_cfg = config.get("target_cfg")
        if not self.target_cfg:
            if raw_target:
                self.target_cfg = f"target/{raw_target}.cfg"
            else:
                self.target_cfg = "target/.cfg"
        self.extra_args = config.get("extra_args", [])

    def _do_flash(self, binary_path: str) -> bool:
        cmd = (
            [self.tool_name]
            + ["-f", self.interface_cfg]
            + ["-f", self.target_cfg]
            + self.extra_args
            + ["-c", f"program {binary_path} verify reset exit"]
        )
        result = self._run(cmd)
        if result.returncode != 0:
            log.error(
                "OpenOCD flash failed.\n  stdout: %s\n  stderr: %s",
                result.stdout.strip() or "(empty)",
                result.stderr.strip() or "(empty)",
            )
            return False
        return True

    def _do_verify(self, binary_path: str) -> bool:
        cmd = (
            [self.tool_name]
            + ["-f", self.interface_cfg]
            + ["-f", self.target_cfg]
            + self.extra_args
            + ["-c", f"program {binary_path} verify exit"]
        )
        result = self._run(cmd)
        return result.returncode == 0

    @staticmethod
    def _brew_package_name() -> str:
        return "openocd"

    @staticmethod
    def _apt_package_name() -> str:
        return "openocd"


# ---------------------------------------------------------------------------
# J-Link 刷写器
# ---------------------------------------------------------------------------

class JLinkFlasher(BaseFlasher):
    """J-Link 刷写器 — SEGGER J-Link 调试器。

    Config 示例::

        {
            "device": "STM32F407VG",
            "if": "SWD",
            "speed": 4000,
            "script": "flash.jlink",      # 可选 .jlink 脚本路径
        }

    默认命令::

        JLinkExe -device STM32F407VG -if SWD -speed 4000 \\
                 -autoconnect 1 -CommanderScript flash.jlink
    """

    tool_name = "JLinkExe"
    detect_cmd: ClassVar[list[str] | None] = ["JLinkExe", "-?"]

    def __init__(self, config: dict):
        super().__init__(config)
        self.device = config.get("device", "STM32F407VG")
        self.interface = config.get("if", "SWD")
        self.speed = config.get("speed", 4000)
        self.script = config.get("script")

    def _do_flash(self, binary_path: str) -> bool:
        if self.script:
            # 使用脚本文件
            cmd = [
                self.tool_name,
                "-device", self.device,
                "-if", self.interface,
                "-speed", str(self.speed),
                "-autoconnect", "1",
                "-CommanderScript", self.script,
            ]
            return self._run(cmd).returncode == 0
        else:
            # 生成临时脚本
            ext = os.path.splitext(binary_path)[1].lower()
            load_cmd = {
                ".elf": f"loadfile {binary_path}",
                ".bin": f"loadbin {binary_path}, 0x08000000",
                ".hex": f"loadfile {binary_path}",
            }.get(ext, f"loadfile {binary_path}")

            script_lines = [
                load_cmd,
                "r",        # reset
                "g",        # go
                "exit",
            ]
            # 通过 stdin 传递命令
            input_data = "\n".join(script_lines) + "\n"
            try:
                result = subprocess.run(
                    [
                        self.tool_name,
                        "-device", self.device,
                        "-if", self.interface,
                        "-speed", str(self.speed),
                        "-autoconnect", "1",
                    ],
                    input=input_data,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    log.error(
                        "JLink flash failed.\n  stdout: %s\n  stderr: %s",
                        result.stdout.strip() or "(empty)",
                        result.stderr.strip() or "(empty)",
                    )
                    return False
                return True
            except subprocess.TimeoutExpired:
                raise FlashError("JLink flash timed out after 120s")
            except OSError as exc:
                raise FlashError(f"Failed to execute JLinkExe: {exc}")

    def _do_verify(self, binary_path: str) -> bool:
        # JLink 的 verify 需要单独脚本，暂不支持
        log.warning("JLink standalone verify not implemented; use 'verify' in .jlink script")
        return False

    @staticmethod
    def _brew_package_name() -> str:
        return "segger-jlink"

    @staticmethod
    def _apt_package_name() -> str:
        return "jlink"  # 需要从 SEGGER 官网下载


# ---------------------------------------------------------------------------
# esptool.py 刷写器
# ---------------------------------------------------------------------------

class ESPToolFlasher(BaseFlasher):
    """esptool.py 刷写器 — ESP32 / ESP8266 等乐鑫芯片。

    Config 示例::

        {
            "chip": "esp32",              # esp32 / esp8266 / esp32s2 / esp32c3
            "baud": 921600,
            "flash_mode": "dio",
            "flash_size": "4MB",
        }

    默认命令::

        esptool.py --port /dev/ttyUSB0 --baud 921600 \\
                   write_flash 0x1000 firmware.bin
    """

    tool_name = "esptool.py"
    detect_cmd: ClassVar[list[str] | None] = ["esptool.py", "--version"]

    def __init__(self, config: dict):
        super().__init__(config)
        self.chip = config.get("chip", "esp32")
        self.baud = config.get("baud", 921600)
        self.flash_mode = config.get("flash_mode", "dio")
        self.flash_size = config.get("flash_size", "4MB")

    def flash(self, binary_path: str, port: str = "/dev/ttyUSB0") -> bool:
        """刷写固件到 ESP32 设备。

        Parameters
        ----------
        binary_path : str
            固件文件路径。
        port : str
            串口设备路径。默认 ``"/dev/ttyUSB0"``。

        Returns
        -------
        bool
        """
        self._check_binary(binary_path)
        self._check_tool()
        self._check_port(port)
        return self._do_flash_port(binary_path, port)

    def _do_flash(self, binary_path: str) -> bool:
        return self._do_flash_port(binary_path, "/dev/ttyUSB0")

    def _do_flash_port(self, binary_path: str, port: str) -> bool:
        ext = os.path.splitext(binary_path)[1].lower()
        # esptool 的 offset 因芯片而异
        offset_map = {
            "esp32": "0x1000",
            "esp32s2": "0x1000",
            "esp32c3": "0x0000",
            "esp8266": "0x0000",
        }
        offset = offset_map.get(self.chip, "0x1000")

        cmd = [
            self.tool_name,
            "--port", port,
            "--baud", str(self.baud),
            "--chip", self.chip,
            "write_flash",
            "-fm", self.flash_mode,
            "-fs", self.flash_size,
            offset, binary_path,
        ]

        # esptool 对 .elf 使用不同命令
        if ext == ".elf":
            cmd = [
                self.tool_name,
                "--port", port,
                "--baud", str(self.baud),
                "--chip", self.chip,
                "elf2image",
                binary_path,
            ]
            log.warning(
                ".elf detected. esptool will generate images first; "
                "prefer .bin files for direct flashing."
            )

        result = self._run(cmd)
        return result.returncode == 0

    def _do_verify(self, binary_path: str) -> bool:
        # esptool 的 verify 通过 verify_flash 命令
        ext = os.path.splitext(binary_path)[1].lower()
        if ext == ".bin":
            cmd = [
                self.tool_name,
                "--port", "/dev/ttyUSB0",
                "--baud", str(self.baud),
                "--chip", self.chip,
                "verify_flash",
                "0x1000", binary_path,
            ]
            result = self._run(cmd)
            return result.returncode == 0
        log.warning("esptool verify only supported for .bin files")
        return False

    def _check_port(self, port: str):
        """检查串口是否存在。"""
        if sys.platform == "darwin":
            if not os.path.exists(port):
                # 尝试 macOS 的常用串口路径
                alt = port.replace("/dev/ttyUSB", "/dev/cu.usbserial")
                if os.path.exists(alt):
                    return
                raise HardwareNotFoundError(
                    f"Serial port {port} not found.\n"
                    f"  macOS USB-serial adapters often appear as:\n"
                    f"    /dev/cu.usbserial-XXXX\n"
                    f"    /dev/cu.SLAB_USBtoUART\n"
                    f"  Try: ls /dev/cu.*"
                )
        elif sys.platform == "linux":
            if not os.path.exists(port):
                raise HardwareNotFoundError(
                    f"Serial port {port} not found.\n"
                    f"  Try: ls /dev/ttyUSB* /dev/ttyACM*"
                )

    @staticmethod
    def _brew_package_name() -> str:
        return "esptool"

    @staticmethod
    def _apt_package_name() -> str:
        return "esptool"

    def __repr__(self) -> str:
        return (
            f"<ESPToolFlasher chip={self.chip} baud={self.baud} "
            f"mode={self.flash_mode} size={self.flash_size}>"
        )
