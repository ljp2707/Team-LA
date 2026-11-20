# Security

NMU Programs holds the names, work emails and task notes of No More Under staff and partners.
This page says how to report a problem and where the security documentation lives.

## Reporting a vulnerability

Please do not open a public GitHub issue for a security problem.

- Use GitHub's **private vulnerability reporting**: the repository's **Security** tab, then
  **Report a vulnerability**. (A maintainer turns this on under **Settings > Code security**.)
- Or email No More Under's contact inbox, the address on the app's **Privacy** page.

Include what you found, how to reproduce it and what an attacker could do with it. Please do
not access other people's data, change data or degrade the service while testing; a test
account on a test base is fine. We aim to reply within 5 working days and to fix confirmed
issues within 30 days, sooner for anything serious, and will say when it is fixed.

## Supported versions

Only the version on the `main` branch, which is what runs in production, gets fixes.

## How the app is protected, in short

- **Sign in** only with Google; the Airtable Users table decides who gets in. Sessions are a
  signed `__Host-` cookie that ends after 24 idle hours or 7 days, and can be ended on every
  device at once.
- **Every API route checks permissions on the server**: by access level, by program for
  partners, and by object. An automated access matrix tests every route for every role.
- **Browser protection**: an enforced Content-Security-Policy (tested in a real browser),
  Origin checks on every change, cross-origin isolation headers, no third-party scripts.
- **Limits** on request sizes, uploads, request rates and reminder emails.
- **An append-only audit trail** of every admin action, and JSON security logs.
- **Least privilege** for every credential, and production refuses to start with unsafe
  settings.
- **CI** runs the tests, the browser test, dependency audits, secret scanning, Semgrep and
  Trivy on every change; dependencies are pinned and hash-locked; Dependabot proposes updates.

## Documentation

| Document | What it covers |
|---|---|
| [`docs/security/threat-model.md`](docs/security/threat-model.md) | What we protect, from whom, and every route with its access rule |
| [`docs/security/findings.md`](docs/security/findings.md) | Every security finding (F1 onward): problem, fix, tests, commit |
| [`docs/security/asvs-checklist.md`](docs/security/asvs-checklist.md) | OWASP ASVS 5.0 Level 2 and the API Security Top 10, requirement by requirement |
| [`docs/security/production-checklist.md`](docs/security/production-checklist.md) | Everything to set and check before and after going live |
| [`docs/security/secrets-runbook.md`](docs/security/secrets-runbook.md) | Every secret: where it lives, who owns it, how to rotate it |
| [`docs/security/incident-response.md`](docs/security/incident-response.md) | What to do when something goes wrong |
| [`docs/security/monitoring.md`](docs/security/monitoring.md) | Logs, security events, alerts and the audit trail review |
| [`docs/security/backups.md`](docs/security/backups.md) | Backing up and restoring the data |
