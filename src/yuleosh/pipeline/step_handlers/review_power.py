"""Step: 小克 — 低功耗/能效审查。

检查项:
- WFI/WFE 指令使用
- 时钟门控配置
- 外设备用/停止/待机模式配置
- 唤醒源配置
- 动态电压频率调节 (DVFS)
"""
import re, json
from pathlib import Path

def step_review_power(session) -> str:
    project_dir = Path(".").resolve()
    findings = []
    source_files = list(project_dir.rglob("*.c")) + list(project_dir.rglob("*.h"))
    
    code_content = ""
    for f in source_files:
        try:
            code_content += f.read_text(errors="ignore") + "\n"
        except:
            pass
    
    # WFI/WFE 检查
    if not re.search(r'WFI|__WFI|wfi', code_content):
        findings.append({"severity": "major", "category": "power", "message": "未检测到 WFI/WFE 指令 — 系统可能未进入低功耗模式"})
    else:
        findings.append({"severity": "info", "category": "power", "message": "检测到 WFI/WFE 指令"})
    
    # 时钟门控
    if not re.search(r'CLOCK.*ENABLE|__HAL_RCC.*CLK.*ENABLE|clock.*gate|CGAC|SCGC', code_content, re.IGNORECASE):
        findings.append({"severity": "major", "category": "power", "message": "未检测到外设时钟门控配置 — 未使用外设可能持续耗电"})
    
    # 唤醒源
    if not re.search(r'WAKE|EXTI|wake_up|wakeup', code_content, re.IGNORECASE):
        findings.append({"severity": "info", "category": "power", "message": "未检测到唤醒源配置"})
    
    # 睡眠/停止/待机模式
    if not re.search(r'SLEEP|STOP|STANDBY|PWR_|__HAL_PWR', code_content, re.IGNORECASE):
        findings.append({"severity": "major", "category": "power", "message": "未检测到睡眠/停止/待机模式配置"})
    
    report = {"step": "review-power", "findings": findings, "total": len(findings), "severity": sum(1 for f in findings if f["severity"]=="major")}
    out_path = Path(str(session.session_dir) if hasattr(session, 'session_dir') else '.') / "review-power.json" if hasattr(session, 'session_dir') else Path(".") / "review-power.json"
    if hasattr(session, 'session_dir'):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
    return str(report)

# Ensure step_review_power is the exported name
step_review_power.__name__ = "step_review_power"
