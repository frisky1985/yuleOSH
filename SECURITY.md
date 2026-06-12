# Security Policy

## Supported Versions

We actively provide security patches for the following versions:

| Version | Supported |
|:--------|:----------|
| 1.0.x   | ✅ Active |
| 0.3.x   | ✅ Security patches only |
| < 0.3   | ❌ End of life |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability in yuleOSH, please **do not** open a public GitHub issue.

Instead, report it privately via one of these channels:

### Option 1: GitHub Private Vulnerability Reporting

Go to [github.com/frisky1985/yuleOSH/security/advisories](https://github.com/frisky1985/yuleOSH/security/advisories) and click **"New draft security advisory"** to submit a private report.

### Option 2: Security Contact

If GitHub's advisory system is unavailable, email the maintainers directly. The PGP key for encrypted communication can be found in the repository's security advisories page.

## What to Include

To help us triage and fix the issue quickly, please provide:

- **Type of vulnerability** (e.g., buffer overflow, SQL injection, XSS, auth bypass)
- **Affected versions** — which versions of yuleOSH are affected
- **Steps to reproduce** — minimal, complete, and verifiable
- **Impact** — what an attacker could achieve
- **Suggested fix** (optional but appreciated)

## Process

After you submit a report:

1. **Acknowledgement** (within 48 hours) — we confirm receipt
2. **Triage** (within 5 business days) — we assess severity and scope
3. **Fix development** — we develop a patch and test it
4. **Release** — we ship a patched version and publish the advisory
5. **Disclosure** — we credit the reporter (unless they request anonymity)

## Disclosure Timeline

| Severity | Target time to patch |
|:---------|:---------------------|
| 🔴 Critical | 7 days |
| 🟠 High | 14 days |
| 🟡 Medium | 30 days |
| 🟢 Low | 90 days |

## Scope

This security policy covers:

- The yuleOSH Python package (`yuleosh` on PyPI)
- The yuleOSH web dashboard (Next.js frontend + HTTP server)
- The yuleOSH CLI tool
- Official Docker images

**Out of scope:**

- Third-party dependencies (report those to their maintainers)
- Generated firmware code (treat as user code)
- Plugins written by third parties

## Security Best Practices for Users

- Always use the latest version: `pip install --upgrade yuleosh`
- Set a strong `YULEOSH_API_KEY` in production deployments
- Keep your deployment behind a firewall or VPN
- Use HTTPS in production (the built-in server does not terminate TLS)
- Regularly rotate API keys
- Audit plugin code before installing

## Thanks

We appreciate the security research community helping us keep yuleOSH safe. ❤️
