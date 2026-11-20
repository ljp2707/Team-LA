# Production checklist

Work through this before NMU staff and partners rely on the app, and again after any big
change to accounts or settings. Each line says where to do it. Details are in the linked docs.

## Accounts (all owned by NMU, with 2-step verification)

- [ ] GitHub repository in an NMU organization; maintainers have their own accounts.
- [ ] Railway project on an NMU account with billing.
- [ ] Google Cloud project owned by an NMU Google account; the app is **In production** on the
      Audience page (otherwise the Gmail authorization expires every 7 days).
- [ ] Gmail sender is an NMU address (for example launches@).
- [ ] Airtable token made from an NMU-owned Airtable account.
- [ ] In NMU's Google Workspace, 2-Step Verification is enforced for staff.

## Railway: web service variables

- [ ] `ENV=production`.
- [ ] `APP_URL` and `FRONTEND_URL` are the `https://` address (the app refuses `http://`).
- [ ] `SESSION_SECRET`: a new random value of 48+ characters, used nowhere else.
- [ ] `AIRTABLE_TOKEN`: scopes `data.records:read` and `data.records:write` only, this base only.
- [ ] `AIRTABLE_MIGRATION_TOKEN` is **not** set (the app refuses to start with it).
- [ ] `DEV_LOGIN_EMAIL` is not set; `DEV_ALLOW_VIEW_SWITCH` is `false` or not set.
- [ ] `CSP_MODE` is not set (enforced is the default). Remove `CSP_MODE=report-only` if present.
- [ ] `REMINDERS_DRY_RUN=false` only once the Gmail settings are all set and the test email works.
- [ ] `BOOTSTRAP_ADMIN_EMAILS`: set only for the first sign-in, then removed (the log shows
      `bootstrap_admins_still_set` until it is).
- [ ] `ALLOWED_EMAIL_DOMAIN`: set if every user is on one Google Workspace domain; leave blank if
      partners use other addresses.
- [ ] `ORG_NAME`, `CONTACT_EMAIL` (an inbox someone reads), `ORG_ADDRESS`.

## Railway: cron service variables

- [ ] Only the variables listed in the README's cron section, with its **own**
      `SESSION_SECRET`.

## Google Cloud

- [ ] The sign-in client's authorized redirect URI is exactly
      `https://YOUR-APP-DOMAIN/auth/callback`; old and localhost URIs removed from the
      production client.
- [ ] Gmail authorized with `jobs.authorize_gmail` (send-only).

## GitHub

- [ ] **Settings > Branches**: `main` protected, pull request required, the six CI checks
      required.
- [ ] **Settings > Actions > General**: workflow permissions read-only; actions must be pinned
      to a full commit SHA.
- [ ] **Settings > Code security**: Dependabot alerts and security updates, secret scanning,
      push protection, private vulnerability reporting.

## Airtable

- [ ] The **Session Version** field on Users and the **Audit Log** table exist (they do in the
      current base; for a new base run `jobs.migrate_airtable` with a migration token).
- [ ] Only the people who look after the app are collaborators on the base.
- [ ] A manual snapshot taken before go-live (`backups.md`).

## Monitoring

- [ ] The alerts in `monitoring.md` are set up, sending to an inbox someone reads.
- [ ] A log drain to NMU-controlled storage, if NMU wants logs kept longer than Railway does.

## After deploying: check

Replace `APP` with the live address.

- [ ] `curl -s -D - -o /dev/null https://APP/` shows `Strict-Transport-Security`, `Content-Security-Policy`
      (not `-Report-Only`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
      `Cross-Origin-Opener-Policy`, and no `Server` header.
- [ ] `curl -s https://APP/api/health` answers `{"status":"ok"}`.
- [ ] `curl -s https://APP/openapi.json | head -c 15` shows `<!doctype html>` (the website's
      page), not JSON: the API description is off in production.
- [ ] `curl -s -o /dev/null -w "%{http_code}" https://APP/api/projects` gives `401`.
- [ ] `curl -s -o /dev/null -w "%{http_code}" -X POST -H "Origin: https://evil.example" https://APP/auth/logout`
      gives `403`.
- [ ] Sign in with Google works; the cookie in the browser's dev tools is named
      `__Host-nmu_session`, Secure and HttpOnly.
- [ ] As an admin, `/api/health/airtable` shows `connected: true`, and the log has no
      `airtable_token_too_broad`.
- [ ] The **Audit** page shows the sign-in day's admin actions.
- [ ] A test reminder email arrives.
- [ ] Everyone signs in again once (the cookie name changed in F29).

## Every year

- [ ] Rotate `SESSION_SECRET`, the Airtable token and the Google client secrets
      (`secrets-runbook.md`).
- [ ] Practise a restore (`backups.md`).
- [ ] Review who has access to GitHub, Railway, Google Cloud and Airtable.
- [ ] Re-read `asvs-checklist.md` and close what you can of its open items.
