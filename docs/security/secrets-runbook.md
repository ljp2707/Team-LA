# Secrets runbook

Every secret NMU Programs uses: where it lives, who should own it, when to rotate it and how.
Rotate a secret **at once** if it may have leaked (pasted in a chat, committed, shown in a
screenshot, on a lost laptop) or when the person who made it leaves. Follow
`incident-response.md` if you think it was used.

General rules:
- Secrets live only in Railway **Variables** (production) and each developer's own `.env`
  (never committed; `.gitignore` covers it, and CI's gitleaks scan checks every commit).
- Never send a secret by email or chat. Paste it straight into Railway.
- Every account below should belong to NMU, not to a person. See the admin runbook's
  "Who owns what".
- After changing a Railway variable, redeploy the service if Railway asks.

## The list

| Secret | Where | Owner | Gives access to | Rotate |
|---|---|---|---|---|
| `SESSION_SECRET` (web) | Railway web service | NMU | Forging any sign-in, including Admin | Yearly, on leak, when a maintainer leaves |
| `SESSION_SECRET` (cron) | Railway cron service | NMU | Nothing (never signs a cookie) | Any time; it must differ from the web one |
| `AIRTABLE_TOKEN` | Both Railway services | NMU Airtable account | Read and write every record in the base | Yearly, on leak, when its owner leaves |
| `AIRTABLE_MIGRATION_TOKEN` | A laptop, only while migrating | Whoever migrates | Changing the base's structure | Delete right after each migration |
| `GOOGLE_CLIENT_SECRET` | Both Railway services | NMU Google Cloud project | With the client ID, impersonating the app's sign-in | Yearly, on leak |
| `GMAIL_CLIENT_SECRET` (if used) | Both Railway services | NMU Google Cloud project | As above, for the Gmail client | Yearly, on leak |
| `GMAIL_REFRESH_TOKEN` | Both Railway services | The sender account | Sending email as the sender (not reading it) | On leak, when the sender changes |
| Calendar feed tokens | Airtable Users > Calendar Feed Token | Each person | That person's task calendar | The person clicks **Reset link** |
| Railway, GitHub, Google Cloud, Airtable logins | Password managers | NMU | Everything | Use 2-step verification on all of them |

## How to rotate each one

### SESSION_SECRET

Changing it signs **everyone** out once; they sign in again with Google.

1. Make a new value: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Railway, web service, **Variables**: replace `SESSION_SECRET`. Redeploy.
3. Sign in to check. (For the cron service, use a different new value.)

### AIRTABLE_TOKEN

1. Signed in to Airtable as the NMU account, https://airtable.com/create/tokens, **Create
   token**: scopes `data.records:read` and `data.records:write` only, access to the NMU base only.
2. Put it in `AIRTABLE_TOKEN` on both Railway services. Redeploy both.
3. As an admin, open `https://YOUR-APP-DOMAIN/api/health/airtable`: `connected` must be `true`.
   The server log must **not** show `airtable_token_too_broad`.
4. Delete the old token in Airtable.

### AIRTABLE_MIGRATION_TOKEN

Make it only when running `jobs.migrate_airtable` or `jobs.dump_schema` (README, "Updating the
Airtable base"), keep it in your own `.env`, and delete it in Airtable when done. Production
refuses to start if it is ever set on Railway.

### GOOGLE_CLIENT_SECRET (and GMAIL_CLIENT_SECRET)

1. Google Cloud console, **Google Auth Platform > Clients**, open the client, **Add secret**.
2. Put the new secret on both Railway services. Redeploy both. Check sign in works.
3. Back in the client, **disable**, then delete, the old secret.
4. A Gmail refresh token made with this client keeps working; if email stops, re-authorize
   Gmail (below).

### GMAIL_REFRESH_TOKEN

1. Signed in as the sender, https://myaccount.google.com/connections: remove the app's access.
   This kills the old token at once.
2. Re-authorize as in the admin runbook, "Re-authorizing Gmail" (`python -m jobs.authorize_gmail`,
   which asks only for permission to send).
3. Put the new token on both Railway services. Redeploy. Send the test email.

### Calendar feed tokens

Each link is a secret: anyone with it can see that person's tasks. If one leaks, the person
clicks **Reset link** on their calendar feed card: the old link stops working at once and they
add the new one to their calendar. Deactivating someone clears theirs.

### Someone's session

If a laptop or phone is lost: the person clicks **Sign out of all devices**, or an admin uses
**Sign out everywhere** in their Edit dialog (Users and roles). Their Google password should
be changed too.

## When a maintainer leaves

1. Remove them from GitHub, Railway, Google Cloud and the Airtable base.
2. Rotate `SESSION_SECRET` and any secret they made or could see (in practice all of the above).
3. Deactivate their Users row in the app (this also ends their sessions).
4. Check the Audit page and Railway's activity for their last week.
