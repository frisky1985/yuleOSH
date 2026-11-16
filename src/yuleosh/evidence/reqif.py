#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""ReqIF 1.2 导出（AUD-ASPICE-001 NC-08）。

ASPICE 评估方通常用 DOORS / Polarion 等需求管理工具，交付物必须可导入。
本模块把 spec 中的需求（按 SHALL 语句展开）导出为 ReqIF 1.2 XML，并提供
``parse_reqif`` 自检解析器 —— 生成后立即回读，确保"能导出"不是只靠肉眼。

导出粒度：每条 SHALL → 一个 ``SPEC-OBJECT``（ID ``<REQ-ID>#<n>``），
父需求标题作为层级容器 ``SPEC-HIERARCHY``，保留 V 模型追溯所需的父子关系。
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

REQIF_XMLNS = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
SCHEMA = "ReqIF 1.2"


def _ident(seed: str) -> str:
    """稳定 IDENTIFIER：同内容重复导出得到同样的 ID。"""
    return "YOSH-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:24].upper()


def _collect(spec_path) -> list[dict]:
    """解析 spec：每条 SHALL 一条需求。"""
    from yuleosh.spec.validate import parse_spec

    try:
        doc = parse_spec(str(spec_path))
    except Exception:  # noqa: BLE001 — 解析失败按空集导出，由调用方判空
        return []

    entries: list[dict] = []
    for req in doc.requirements:
        rid = req.req_id or req.name or "REQ"
        statements = req.shall or req.should or req.may or []
        if not statements:
            entries.append({
                "id": rid,
                "parent": "",
                "title": req.name,
                "text": req.reason or req.name,
                "status": req.status,
            })
            continue
        for idx, statement in enumerate(statements, start=1):
            entries.append({
                "id": f"{rid}#{idx}",
                "parent": rid,
                "title": req.name,
                "text": statement,
                "status": req.status,
            })
    return entries


def render_reqif(entries: list[dict], title: str = "yuleOSH Requirements") -> str:
    """把需求条目渲染为 ReqIF 1.2 XML 文本。"""
    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<REQ-IF xmlns="{REQIF_XMLNS}">',
        "  <THE-HEADER>",
        f'    <REQ-IF-HEADER IDENTIFIER={quoteattr(_ident("header:" + title))}>',
        f"      <COMMENT>{escape(SCHEMA + ' export from yuleOSH')}</COMMENT>",
        f"      <CREATION-TIME>{now}</CREATION-TIME>",
        "      <REQ-IF-TOOL-ID>yuleOSH</REQ-IF-TOOL-ID>",
        "      <REQ-IF-VERSION>1.0</REQ-IF-VERSION>",
        "      <SOURCE-TOOL-ID>yuleOSH</SOURCE-TOOL-ID>",
        f"      <TITLE>{escape(title)}</TITLE>",
        "    </REQ-IF-HEADER>",
        "  </THE-HEADER>",
        "  <CORE-CONTENT>",
        "    <REQ-IF-CONTENT>",
        "      <SPEC-TYPES>",
        "        <DATATYPE-DEFINITIONS>",
        f'          <DATATYPE-DEFINITION-STRING IDENTIFIER={quoteattr(_ident("dt:string"))}',
        '                                   LONG-NAME="String">',
        "            <MAX-LENGTH>4096</MAX-LENGTH>",
        "          </DATATYPE-DEFINITION-STRING>",
        "        </DATATYPE-DEFINITIONS>",
        "        <SPECIFICATION-TYPES>",
        f'          <SPECIFICATION-TYPE IDENTIFIER={quoteattr(_ident("type:specification"))}',
        '                              LONG-NAME="Requirement Specification"/>',
        "        </SPECIFICATION-TYPES>",
        "        <SPEC-OBJECT-TYPES>",
        f'          <SPEC-OBJECT-TYPE IDENTIFIER={quoteattr(_ident("type:requirement"))}',
        '                            LONG-NAME="Requirement">',
        "            <SPEC-ATTRIBUTES>",
    ]
    for attr in ("ReqID", "Title", "Text", "Status"):
        lines += [
            f'              <ATTRIBUTE-DEFINITION-STRING IDENTIFIER={quoteattr(_ident("attr:" + attr))}',
            f'                                        LONG-NAME="{attr}">',
            "                <TYPE><DATATYPE-DEFINITION-STRING-REF>"
            f"{_ident('dt:string')}</DATATYPE-DEFINITION-STRING-REF></TYPE>",
            "              </ATTRIBUTE-DEFINITION-STRING>",
        ]
    lines += [
        "            </SPEC-ATTRIBUTES>",
        "          </SPEC-OBJECT-TYPE>",
        "        </SPEC-OBJECT-TYPES>",
        "      </SPEC-TYPES>",
        "      <SPEC-OBJECTS>",
    ]

    for entry in entries:
        obj_id = _ident("object:" + entry["id"])
        lines += [
            f'        <SPEC-OBJECT IDENTIFIER="{obj_id}" LAST-CHANGE="{now}">',
            "          <VALUES>",
        ]
        for attr, key in (("ReqID", "id"), ("Title", "title"),
                          ("Text", "text"), ("Status", "status")):
            value = str(entry.get(key, ""))
            lines += [
                f"            <ATTRIBUTE-VALUE-STRING THE-VALUE={quoteattr(value)}>",
                "              <DEFINITION>",
                "                <ATTRIBUTE-DEFINITION-STRING-REF>"
                f"{_ident('attr:' + attr)}</ATTRIBUTE-DEFINITION-STRING-REF>",
                "              </DEFINITION>",
                "            </ATTRIBUTE-VALUE-STRING>",
            ]
        lines += [
            "          </VALUES>",
            "          <TYPE><SPEC-OBJECT-TYPE-REF>"
            f"{_ident('type:requirement')}</SPEC-OBJECT-TYPE-REF></TYPE>",
            "        </SPEC-OBJECT>",
        ]

    lines += [
        "      </SPEC-OBJECTS>",
        "      <SPECIFICATIONS>",
        f'        <SPECIFICATION IDENTIFIER={quoteattr(_ident("spec:" + title))}',
        f'                       LAST-CHANGE="{now}">',
        "          <VALUES/>",
        "          <TYPE><SPECIFICATION-TYPE-REF>"
        f"{_ident('type:specification')}</SPECIFICATION-TYPE-REF></TYPE>",
        "          <CHILDREN>",
    ]
    for entry in entries:
        lines += [
            "            <SPEC-HIERARCHY>",
            "              <OBJECT>",
            "                <SPEC-OBJECT-REF>"
            f"{_ident('object:' + entry['id'])}</SPEC-OBJECT-REF>",
            "              </OBJECT>",
            "            </SPEC-HIERARCHY>",
        ]
    lines += [
        "          </CHILDREN>",
        "        </SPECIFICATION>",
        "      </SPECIFICATIONS>",
        "    </REQ-IF-CONTENT>",
        "  </CORE-CONTENT>",
        "</REQ-IF>",
    ]
    return "\n".join(lines) + "\n"


def export_reqif(spec_path, out_path) -> dict:
    """导出 ReqIF 并回读自检。

    Returns
    -------
    dict
        ``{"path": str, "objects": int, "valid": bool, "error": str}``
    """
    entries = _collect(spec_path)
    if not entries:
        return {"path": "", "objects": 0, "valid": False,
                "error": "no requirements parsed from spec"}

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    title = f"{Path(spec_path).stem} requirements"
    target.write_text(render_reqif(entries, title=title), encoding="utf-8")

    parsed = parse_reqif(target)
    return {
        "path": str(target),
        "objects": parsed["objects"],
        "valid": parsed["valid"],
        "error": parsed["error"],
    }


def parse_reqif(path) -> dict:
    """最小 ReqIF 自检解析器：XML 合法 + 有 SPEC-OBJECT + ID 唯一。"""
    try:
        root = ET.parse(str(path)).getroot()
    except (ET.ParseError, OSError) as exc:
        return {"valid": False, "objects": 0,
                "ids": [], "error": f"parse error: {exc}"}

    ns = {"r": REQIF_XMLNS}
    objects = root.findall(".//r:SPEC-OBJECT", ns)
    ids: list[str] = []
    for obj in objects:
        ident = obj.get("IDENTIFIER", "")
        if ident:
            ids.append(ident)
    if not objects:
        return {"valid": False, "objects": 0, "ids": [],
                "error": "no SPEC-OBJECT elements"}
    if len(ids) != len(set(ids)):
        return {"valid": False, "objects": len(objects), "ids": ids,
                "error": "duplicate SPEC-OBJECT IDENTIFIER"}
    return {"valid": True, "objects": len(objects), "ids": ids, "error": ""}
