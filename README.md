# Appertivo2026

Appertivo is a small Flask MVP for a local "today's specials" wall.

It answers one question:

**What's good today?**

## What Is Included

- Public specials feed with city filtering.
- Location-led discovery with Skagit Valley as the first launch market.
- Public restaurant pages.
- Public how-it-works, restaurant, diner, and get-started marketing pages.
- Public restaurant lead capture with an admin review queue.
- Email subscriber capture for the upcoming diner digest.
- Admin dashboard at `/admin`.
- Restaurant add and edit screens.
- Special add, edit, approve, expire, and delete screens.
- Placeholder AI intake workflow at `/admin/intake`.
- Unified special intake pipeline for public forms, admin entry, and simulated email or SMS webhooks.
- Private restaurant submission links generated from restaurant admin pages.
- Draft review and trusted direct-publishing workflows.
- Per-special distribution kits with tracked links and aggregate metrics.
- Optional photo uploads using local storage or Cloudflare R2.
- SQLite database by default.
- CSV seed import for independent Skagit Valley restaurants.

## What Is Not Included Yet

- User accounts.
- Payments.
- Automated diner digest and alert delivery.
- Automated restaurant-special email parsing.
- Social scraping.
- Restaurant dashboards.
- Complex permissions.
- Background jobs.

## Install

From this folder:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Seed Data

```bat
python seed.py
flask --app app db stamp head
```

This resets the configured database, imports `skagit_restaurants_master.csv`, excludes
known chain locations, and adds clearly labeled launch-preview specials. The stamp records
that the freshly created schema is current. SQLite is used by default.

To add or refresh only the launch-preview specials without resetting the database:

```bat
flask --app app seed-demo-specials
```

To use PostgreSQL instead, set `DATABASE_URL` before running the seed or app:

```bat
set DATABASE_URL=postgresql+psycopg://user:password@localhost/appertivo
```

## Run

```bat
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

Admin:

```text
http://127.0.0.1:5000/admin
```

The local admin password defaults to `admin`. Set `ADMIN_PASSWORD` and `SECRET_KEY` in production.

## Deploy To Railway

The repo includes [`railway.toml`](railway.toml) for Railway's Railpack builder:

- Runs `flask --app app db upgrade` before each deploy.
- Seeds the Skagit restaurant directory only when the database is empty.
- Refreshes the labeled launch-preview specials without deleting production data.
- Starts Gunicorn on Railway's injected `PORT`.
- Verifies startup through `GET /health`.

In Railway:

1. Create a project from the GitHub repository.
2. Add a PostgreSQL service.
3. Set the app service variable `DATABASE_URL=${{Postgres.DATABASE_URL}}`.
4. Set `SECRET_KEY`, `ADMIN_PASSWORD`, and `APP_BASE_URL`.
5. Add the email, OpenAI, and R2 variables from `.env.example` when those integrations are ready.
6. Generate a public domain from the app service Networking settings.

Do not run `python seed.py` against production. That local-development command resets the
configured database. Railway uses the safe `flask --app app seed-launch-data` command.

## Photo Storage

Development uploads are stored under `instance/uploads`.

For production, create an R2 bucket with a public custom domain and set:

```text
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_BUCKET=<bucket>
R2_ACCESS_KEY_ID=<key>
R2_SECRET_ACCESS_KEY=<secret>
R2_PUBLIC_BASE_URL=https://images.example.com
```

R2 exposes an S3-compatible API. A custom domain is preferred for production public assets.

## Tests

```bat
python -m pytest -q
npm run test:e2e
npm run test:prod-smoke
npm run test:launch
```

`npm run test:e2e` starts an isolated Flask app on `127.0.0.1:5012`, resets a
dedicated SQLite database, and captures outbound Resend/Loops calls to
`output/playwright/email-capture.jsonl` instead of sending real email.

`npm run test:prod-smoke` is read-only. It checks the configured production URL
(`E2E_PROD_BASE_URL`, or the Railway URL by default) for `/health`, the homepage,
restaurants, one restaurant detail page, and one live special detail page.

## Database Migrations

New databases:

```bat
flask --app app db upgrade
```

After pulling the special intake pipeline, run:

```bat
py -m flask --app app db upgrade
```

## Special Intake Walkthrough

1. Open `/submit-special`, choose a restaurant, enter special text, and submit it.
2. Log in at `/admin`, then open `/admin/special-submissions` to confirm the raw submission exists.
3. Open `/admin/special-drafts`, preview the generated draft, and approve it.
4. Publish the approved draft from the preview or draft queue.
5. Open `/admin/specials` to confirm the published special exists.

Private `/submit/<token>` links also accept an optional email address. When provided,
the draft queue can send the restaurant a publish/approval link without a real email
provider during local E2E tests.

Development-only webhook simulation is disabled by default. Set `SPECIAL_WEBHOOK_TEST_ENABLED=1`,
then POST JSON containing `raw_text` and optional `restaurant_id`, `sender_email`, `sender_phone`,
and `image_url` to `/webhooks/email-special` or `/webhooks/sms-special`.

TODO: verify real provider signatures before enabling production webhook intake, route verified
Resend inbound special emails into the pipeline, add an SMS provider, and optionally add reviewed
AI image generation.

Existing seeded databases created before migrations were added:

```bat
flask --app app db stamp 20260601_00
flask --app app db upgrade
```

## Factory Console

Factory Console is configured to run this app on port `5001`:

```text
http://127.0.0.1:5001
```

The console project entry points to:

```text
github: SkagitIan/Appertivo2026
```

## Notes

The app creates the SQLite tables automatically on startup. The database file is stored in Flask's `instance/` folder as `appertivo.db`.
