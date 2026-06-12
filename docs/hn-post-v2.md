Show HN: yuleOSH – AI-Powered Embedded Development Pipeline, from Spec to Hardware

We built an open-source AI pipeline for embedded development. It converts natural language requirements into compiled, hardware-tested firmware — automatically.

What it does:
- Write requirements in plain language → yuleOSH generates OpenSpec (SHALL/SHOULD/MAY + GIVEN/WHEN/THEN)
- AI Code Review for embedded C: detects missing volatile, ISR race conditions, stack overflows, memory barrier issues, debug printf leftovers, watchdog misplacement
- Hardware-in-the-loop: compiles, flashes via OpenOCD/JLink/esptool, monitors serial output, iterates — all in one pipeline
- Exports to Vector CANoe and dSPACE AutomationDesk test formats
- Multi-tenant SaaS with PostgreSQL, JWT auth, usage metering
- Plugin marketplace and skill store (VS Code-style extensibility)

Tech stack: Python, Next.js 16, PostgreSQL, LLM (DeepSeek V4), OpenOCD/JLink

Why we built it:
dSPACE HIL hardware costs €30K-120K per setup. Vector CANoe costs €15K-30K per engineer per year. BootLoop (YC S25) does AI firmware generation but has no spec layer, no CI/CD, no test traceability. yuleOSH is MIT-licensed and starts at ¥299/month.

Pricing:
- Free: ¥0 (3 projects, AI Code Review, ESP32 templates)
- Pro: ¥299/mo (¥2,999/yr) — unlimited projects, HIL, all adapters
- Enterprise: ¥98,000/yr — on-prem, SAML, SOC 2, SLA

Code: https://github.com/frisky1985/yuleOSH
Pricing: https://frisky1985.github.io/yuleOSH/pricing.html

Happy to answer questions — especially from embedded engineers who've dealt with CANoe Options hell or dSPACE quote processes.
