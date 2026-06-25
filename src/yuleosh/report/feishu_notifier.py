#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Feishu Webhook Notifier — 将质量摘要卡片推送到飞书群聊。

通过调用 card_generator.generate_feishu_card_json() 获取飞书交互卡片 JSON，
然后通过 POST 请求发送到飞书 Webhook URL。

Usage:
    # Python API
    from yuleosh.report.feishu_notifier import post_quality_card_to_feishu
    success = post_quality_card_to_feishu(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        project_dir="/path/to/project",
    )

    # CLI
    python3 -m yuleosh.report.feishu_notifier \\
        --webhook-url https://open.feishu.cn/open-apis/bot/v2/hook/xxx \\
        --project-dir /path
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

log = logging.getLogger("report.feishu_notifier")

# 环境变量名称
ENV_FEISHU_WEBHOOK_URL = "FEISHU_WEBHOOK_URL"


def _post_json(url: str, payload: dict, timeout: int = 15) -> bool:
    """POST JSON 负载到指定 URL。

    Parameters
    ----------
    url : str
        目标 URL。
    payload : dict
        JSON 可序列化的负载。
    timeout : int
        超时秒数（默认 15s）。

    Returns
    -------
    bool
        HTTP 状态码为 2xx 时返回 True。
    """
    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urlopen(req, timeout=timeout)
        body = resp.read().decode("utf-8")
        log.info("Feishu webhook POST -> %s %s: %s", resp.status, resp.reason, body[:200])
        return 200 <= resp.status < 300
    except URLError as e:
        log.error("Feishu webhook POST failed (URL error): %s", e)
        return False
    except TimeoutError:
        log.error("Feishu webhook POST timed out after %ds", timeout)
        return False
    except Exception as e:
        log.error("Feishu webhook POST error: %s", e)
        return False


def post_quality_card_to_feishu(
    webhook_url: str,
    project_dir: str,
) -> bool:
    """将质量摘要卡片推送到飞书 Webhook。

    调用 card_generator.generate_feishu_card_json() 获取卡片 JSON，
    然后发送 POST 请求到飞书 Webhook URL。

    Parameters
    ----------
    webhook_url : str
        飞书 Webhook URL。
    project_dir : str
        项目根目录路径（传递给 card_generator 获取报告数据）。

    Returns
    -------
    bool
        推送成功返回 True，否则返回 False。
    """
    from yuleosh.report.card_generator import generate_feishu_card_json

    # 验证参数
    if not webhook_url:
        log.error("Feishu webhook URL is empty")
        return False

    project_path = Path(project_dir)
    if not project_path.is_dir():
        log.error("Project directory does not exist: %s", project_dir)
        return False

    # 生成飞书卡片 JSON
    try:
        card_json = generate_feishu_card_json(project_dir)
    except Exception as e:
        log.error("Failed to generate Feishu card JSON: %s", e)
        return False

    # 包装成飞书消息格式
    payload = {
        "msg_type": "interactive",
        "card": card_json,
    }

    # 发送
    return _post_json(webhook_url, payload)


def _resolve_webhook_url(cli_url: Optional[str] = None) -> Optional[str]:
    """解析 Webhook URL：优先 CLI 参数，其次环境变量。"""
    url = (cli_url or "").strip()
    if not url:
        url = os.environ.get(ENV_FEISHU_WEBHOOK_URL, "").strip()
    return url or None


# ------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="推送 yuleOSH 质量摘要卡片到飞书群聊",
    )
    parser.add_argument(
        "--webhook-url", "-w",
        default=None,
        help="飞书 Webhook URL。也可通过环境变量 %s 设置。" % ENV_FEISHU_WEBHOOK_URL,
    )
    parser.add_argument(
        "--project-dir", "-p",
        default=".",
        help="项目根目录路径（默认：当前目录）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细日志",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    webhook_url = _resolve_webhook_url(args.webhook_url)
    if not webhook_url:
        print("❌ 错误：未指定 Webhook URL。请使用 --webhook-url 或设置 %s 环境变量。" % ENV_FEISHU_WEBHOOK_URL)
        sys.exit(1)

    success = post_quality_card_to_feishu(
        webhook_url=webhook_url,
        project_dir=args.project_dir,
    )

    if success:
        print("✅ 质量摘要卡片已成功推送到飞书")
        sys.exit(0)
    else:
        print("❌ 推送飞书质量卡片失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
