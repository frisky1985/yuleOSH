# yuleOSH Cybersecurity Baseline — ISA/IEC 62443 对齐

> **Version**: 2.5.0 | **状态**: 正式发布  
> **参考标准**: ISA/IEC 62443-3-3 (系统安全要求), ISA/IEC 62443-4-1 (产品开发), ISO 26262:2018  
> **安全等级 (SL)**: SL-2 (Target)  
> **审查人**: 小马 🐴 (质量架构师)

---

## 1. 概述

本文档定义 yuleOSH 网络安全基线，对齐 ISA/IEC 62443 标准要求。基线覆盖以下安全域：

| 域 | SL 等级 | 参考标准 |
|:---|:-------:|:---------|
| IAC (Identification and Authentication Control) | SL-2 | 62443-3-3 SR 1.1–1.9 |
| UC (Use Control) | SL-2 | 62443-3-3 SR 2.1–2.12 |
| SI (System Integrity) | SL-2 | 62443-3-3 SR 3.1–3.9 |
| DC (Data Confidentiality) | SL-2 | 62443-3-3 SR 4.1–4.3 |
| RDF (Restricted Data Flow) | SL-2 | 62443-3-3 SR 5.1–5.4 |
| TIM (Timely Response to Events) | SL-2 | 62443-3-3 SR 6.1–6.2 |
| RA (Resource Availability) | SL-2 | 62443-3-3 SR 7.1–7.5 |

---

## 2. IAC — Identification and Authentication Control

### CR-001: JWT Token 鉴权 (SR 1.1)
- The system SHALL require valid JWT bearer tokens for all sensitive API endpoints
- The system SHALL reject requests with expired, revoked, or malformed tokens (HTTP 401)
- The system SHALL log all authentication failures with IP address, timestamp, and attempted resource
- The system SHALL support token refresh with configurable expiry (default 24h)

### CR-002: 密码策略 (SR 1.2–1.3)
- The system SHALL store user passwords using bcrypt with minimum 12 salt rounds
- The system SHALL enforce minimum password length (8 characters)
- The system SHALL NOT log plaintext credentials or API keys

### CR-003: 身份验证失败处理 (SR 1.8)
- The system SHALL implement rate limiting for login endpoints (max 10 attempts per 5 min per IP)
- Exceeding the rate limit SHALL return HTTP 429
- The system SHALL extend lockout duration on repeated violations

---

## 3. UC — Use Control

### CR-004: 基于角色的访问控制 (SR 2.1)
- The system SHALL enforce RBAC (admin/member/viewer) for all operations
- Admin roles SHALL have full system access
- Member roles SHALL have read/write access within their scope
- Viewer roles SHALL have read-only access
- The system SHALL deny write operations for read-only roles
- The system SHALL deny admin operations for non-admin roles

### CR-005: 权限审查 (SR 2.4)
- The system SHALL verify authorization on every API request
- The system SHALL deny access by default (whitelist approach)
- The system SHALL support permission audit at user and role level

### CR-006: 会话管理 (SR 2.6)
- The system SHALL support session timeout with automatic logout
- The system SHALL invalidate sessions on password change
- The system SHALL reject requests with expired tokens

---

## 4. SI — System Integrity

### CR-007: 输入验证 (SR 3.1)
- The system SHALL validate and sanitize all user inputs before processing
- The system SHALL reject spec files containing embedded scripts or control characters
- The system SHALL apply path normalization to prevent directory traversal attacks
- The system SHALL use parameterized queries for all database operations (SQL injection prevention)
- The system SHALL sanitize HTML/JS input to prevent XSS attacks

### CR-008: 安全更新 (SR 3.2)
- The system SHALL verify firmware binary checksum (SHA-256) before flashing to target hardware
- The system SHALL NOT flash firmware with unresolved safety violations
- The system SHALL support signed OTA package verification

### CR-009: 完整性校验 (SR 3.4)
- The system SHALL verify artifact SHA-256 checksums after each pipeline stage
- The system SHALL abort the pipeline on any artifact integrity check failure
- The system SHALL include SHA-256 manifest in evidence packs
- The system SHALL verify evidence pack integrity on download (manifest checksums)

### CR-010: 恶意代码防护 (SR 3.5)
- The system SHALL reject spec files exceeding configurable maximum size (default 10 MB)
- The system SHALL limit ZIP uploads to 50 MB; reject with HTTP 413 on excess
- The system SHALL limit cloned repos to 200 MB
- The system SHALL scan extracted files for supported extensions only

---

## 5. DC — Data Confidentiality

### CR-011: 传输加密 (SR 4.1)
- The system SHALL encrypt all database connections using TLS (minimum TLS 1.2)
- The system SHALL support HTTPS for all web and API traffic
- The system SHALL encrypt sensitive configuration (API keys, tokens) at rest
- The system SHALL use secure environment variables for secret management

### CR-012: 敏感数据处理 (SR 4.2)
- The system SHALL NOT log plaintext credentials, tokens, or API keys
- The system SHALL mask sensitive data in logs where applicable
- The system SHALL encrypt JWT tokens with RS256 or HS256 algorithm

---

## 6. RDF — Restricted Data Flow

### CR-013: 网络隔离 (SR 5.1)
- The system SHALL execute each pipeline stage in an isolated workspace
- The system SHALL clean the workspace between pipeline runs
- The system SHALL reject cross-stage file references that violate stage boundaries
- The system SHALL isolate each SIL test in its own QEMU process

### CR-014: 服务依赖检查 (SR 5.4)
- The system SHALL verify HIL target connectivity before attempting to flash
- The system SHALL verify flash integrity (checksum comparison) after programming
- The system SHALL NOT execute HIL tests without a verified serial connection

---

## 7. TIM — Timely Response to Events

### CR-015: 审计日志 (SR 6.1–6.2)
- The system SHALL record all security-relevant events to the audit log
- Audit log entries SHALL include: timestamp, event type, user ID, source IP, resource, action, result
- The system SHALL record every API request (method, path, status, IP, duration)
- The system SHALL record every pipeline execution with stage-level granularity
- The system SHALL record every CI gate result with pass/fail/error distinction
- The system SHALL record every authentication attempt (success/failure, IP, timestamp)

### CR-016: 审计日志保护
- The system SHALL NOT allow deletion of audit log entries
- The system SHALL NOT allow modification of audit log entries
- The system SHALL support audit log export in tamper-evident format
- The system SHALL retain audit logs for a minimum of 12 months
- The audit logging system SHALL operate independently of the main request handling

---

## 8. RA — Resource Availability

### CR-017: 资源限制 (SR 7.1–7.5)
- The system SHALL implement rate limiting for public API endpoints (demo: 10 req/min per IP)
- Unauthenticated users SHALL be limited to 3 preview assessments per 24 hours per IP
- Authenticated users SHALL have a limit of 20 preview assessments per 24 hours
- The system SHALL support configurable CI timeouts
- SIL tests SHALL have configurable timeout (default 30s)
- Clone timeout for git repos SHALL be 120 seconds; timeout returns HTTP 408

### CR-018: 异常处理 (SR 7.3)
- The system SHALL gracefully handle agent failures with retry (max 5 rounds)
- The SIL runner SHALL gracefully handle QEMU process crashes (report FAIL with crash log)
- Pipeline stage failure SHALL NOT leave resources in an inconsistent state
- The system SHALL clean up QEMU processes on test timeout or abort

---

## 9. 安全架构映射

### 9.1 安全模块映射

| 模块 | 安全域 | CR 引用 | 62443 SR | 实现状态 |
|:-----|:-------|:--------|:---------|:--------:|
| API 鉴权 (auth) | IAC | CR-001, CR-003 | 1.1–1.8 | ✅ |
| 密码管理 (auth) | IAC | CR-002 | 1.2–1.3 | ✅ |
| RBAC (auth) | UC | CR-004, CR-005 | 2.1–2.4 | ✅ |
| 会话管理 (auth) | UC | CR-006 | 2.6 | 📝 |
| 输入验证 (sanitize) | SI | CR-007 | 3.1 | ✅ |
| 参数化查询 (store) | SI | CR-007 | 3.1 | ✅ |
| XSS 防护 (sanitize) | SI | CR-007 | 3.1 | ✅ |
| 路径遍历防护 (path) | SI | CR-007 | 3.1 | ✅ |
| 固件校验 (fal) | SI | CR-008 | 3.2 | ✅ |
| SHA-256 校验 (pipeline) | SI | CR-009 | 3.4 | ✅ |
| 文件大小限制 (api) | SI | CR-010 | 3.5 | ✅ |
| TLS 加密 (api/store) | DC | CR-011 | 4.1 | 📝 |
| 密钥加密 (config) | DC | CR-012 | 4.2 | 📝 |
| 工作空间隔离 (pipeline) | RDF | CR-013 | 5.1 | ✅ |
| HIL 验证 (hil) | RDF | CR-014 | 5.4 | ✅ |
| 审计日志 (audit) | TIM | CR-015, CR-016 | 6.1–6.2 | ✅ |
| 速率限制 (api) | RA | CR-017 | 7.1 | ✅ |
| 超时控制 (ci/pipeline) | RA | CR-018 | 7.3 | ✅ |

### 9.2 待实现 (📝)

| 项目 | 优先级 | 预计工作量 | 备注 |
|:-----|:------:|:----------:|:-----|
| TLS 加密自动配置 | P2 | 2天 | 需生成/配置 SSL 证书 |
| 密钥加密存储 | P2 | 1天 | 使用 Fernet / AWS KMS |
| 会话超时自动退出 | P2 | 1天 | 前端 + 后端联动 |
| 审计日志 12 月保留策略 | P2 | 1天 | 日志轮转 + 归档 |
| OTA 签名验证 | P3 | 3天 | 固件签名流程 |

---

## 10. 安全测试要求

### 10.1 自动化测试

所有 CR SHALL 语句 SHALL 有对应的自动化测试：

| 测试 ID | CR | 描述 | 测试位置 |
|:--------|:---|:-----|:---------|
| TC-CR-001 | CR-001 | JWT 鉴权：无 token → 401 | `tests/test_security.py` |
| TC-CR-002 | CR-002 | bcrypt 密码存储验证 | `tests/test_security.py` |
| TC-CR-003 | CR-003 | 登录速率限制验证 | `tests/test_security.py` |
| TC-CR-004 | CR-004 | RBAC 权限验证 | `tests/test_security.py` |
| TC-CR-005 | CR-007 | SQL 注入防护验证 | `tests/test_security.py` |
| TC-CR-006 | CR-007 | 路径遍历防护验证 | `tests/test_security.py` |
| TC-CR-007 | CR-007 | XSS 输入清理验证 | `tests/test_security.py` |
| TC-CR-008 | CR-010 | 文件大小限制验证 | `tests/test_security.py` |
| TC-CR-009 | CR-015 | 审计日志完整性验证 | `tests/test_security.py` |
| TC-CR-010 | CR-017 | 速率限制验证 | `tests/test_security.py` |

### 10.2 渗透测试

| 项目 | 频率 | 方法 |
|:-----|:----:|:-----|
| JWT 签名绕过 | 每次发布 | 尝试伪造 JWT 签名 |
| SQL 注入 | 每次发布 | 使用 sqlmap 工具 |
| 路径遍历 | 每次发布 | 手动模糊测试 |
| XSS | 每次发布 | OWASP ZAP 扫描 |
| 速率限制绕过 | 每季度 | 多 IP 分布式测试 |

---

## 11. 合规检查清单

### 11.1 ISA/IEC 62443-3-3 检查

| SR ID | 名称 | 状态 | 备注 |
|:------|:-----|:----:|:-----|
| SR 1.1 | Human user identification | ✅ | JWT + RBAC |
| SR 1.2 | Software process identification | ✅ | Pipeline steps have unique IDs |
| SR 1.3 | Account management | ✅ | Registration, update, password management |
| SR 1.4 | Identifier management | ✅ | UUID-based identifiers |
| SR 1.5 | Authenticator management | ✅ | bcrypt hashing, JWT rotation |
| SR 1.6 | Wireless access management | N/A | No wireless interfaces |
| SR 1.7 | Strength of password-based authentication | ✅ | Min 8 chars, bcrypt 12 rounds |
| SR 1.8 | Public key authentication | ✅ | JWT RS256 support |
| SR 1.9 | Account lockout | ✅ | Rate limiting |
| SR 2.1 | Authorization enforcement | ✅ | RBAC |
| SR 2.4 | Non-repudiation | ✅ | Audit log |
| SR 3.1 | Input validation | ✅ | Sanitize + parameterized queries |
| SR 3.2 | Malicious code protection | ✅ | Size limits + extension filtering |
| SR 3.4 | System integrity monitoring | ✅ | SHA-256 artifact verification |
| SR 4.1 | Communication integrity | 📝 | TLS pending |
| SR 4.2 | Communication confidentiality | 📝 | TLS pending |
| SR 6.1 | Audit log accessibility | ✅ | Export + tamper-evident format |
| SR 6.2 | Continuous monitoring | 📝 | Alerting pending |
| SR 7.1 | Denial of service protection | ✅ | Rate limiting + timeouts |
| SR 7.7 | Resource management | ✅ | Memory limits, process cleanup |

---

## 12. 参考文档

- ISA/IEC 62443-3-3:2013 — System Security Requirements and Security Levels
- ISA/IEC 62443-4-1:2018 — Secure Product Development Lifecycle Requirements
- ISO 26262:2018 — Road Vehicles — Functional Safety
- OWASP Top 10 — Web Application Security Risks
- `docs/safety-concept.md` — yuleOSH ISO 26262 安全概念
- `docs/spec.md` — yuleOSH 规范文档（v2.5.0）
- `docs/acceptance-matrix.md` — 验收判定矩阵

---

*本文档使用 RFC 2119 规范语言。所有 CR-XXX 需求对应 docs/spec.md 中的第四部分（网络安全需求）。*
*最新更新: 2026-07-17 | 作者: 小马 🐴 (质量架构师)*
