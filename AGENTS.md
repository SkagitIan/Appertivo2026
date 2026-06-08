# AGENTS.md

## Project Focus

This project is **Today's Specials**: a simple local food discovery feed for what restaurants are serving right now.

Keep the product focused on one core loop:

1. Restaurants send or post today's specials.
2. AI helps turn messy restaurant input into clean, structured specials.
3. Customers discover, follow, save, and get alerts for specials they care about.

The main question the product should answer is:

> What's good today?

## Product Goals

Prioritize work that supports the MVP from `README.md`:

- Customer-facing specials feed.
- Restaurant profile pages.
- Special submission by email or manual form.
- AI parsing into draft specials.
- Admin approval queue.
- Follow and email alert system.
- Simple restaurant claiming later.

Avoid features that distract from the MVP:

- No complex restaurant dashboard until the core loop works.
- No scraping dependency.
- No heavy integrations on day one.
- No social media automation unless it directly supports specials intake or alerts.

## Coding Style

Simple code is better than complex code.

Follow these preferences:

- Write clear, boring, readable code.
- Prefer small functions and straightforward files.
- Use descriptive names over clever abstractions.
- Keep business logic easy to find and easy to change.
- Avoid premature optimization.
- Avoid large frameworks or dependencies unless they clearly reduce complexity.
- Prefer explicit code over magic.
- Add comments only when they explain why something exists, not what obvious code does.

## Railway CLI Access

The Railway CLI is installed, authenticated, and linked from this repository to the
production application service.

- Workspace: `skagitian's Projects`
- Project: `gleaming-energy`
- Environment: `production`
- Application service: `Appertivo2026`
- PostgreSQL service: `Postgres`
- Public URL: `https://appertivo2026-production.up.railway.app`

Use Railway CLI commands from this repository root. Start with:

```powershell
railway whoami
railway status
railway logs --latest --lines 120
```

The application deploys automatically when `main` is pushed to GitHub. Verify a
deployment by checking Railway status and logs, then request:

```text
https://appertivo2026-production.up.railway.app/health
```

Agents may use the Railway CLI without additional approval to:

- Inspect authentication, project linkage, deployment status, and recent logs.
- Link this local repository to the existing `gleaming-energy` project and
  `Appertivo2026` production service if the local Railway link is missing.
- Verify the public homepage and `/health` endpoint.
- Trigger or inspect a deployment when the user has asked to deploy, redeploy,
  commit and push a deployment fix, or diagnose a failed deployment.

Ask the user before using Railway CLI commands that:

- Add, change, print, or remove production environment variables or secrets.
- Add or remove custom domains.
- Create, remove, or modify services, databases, or volumes.
- Run one-off production database writes outside the checked-in migration and
  `seed-launch-data` deployment flow.
- Delete deployments or perform any other destructive action.

Never print secret values into chat, logs, commits, or documentation. Prefer
`railway.toml` and committed migrations for repeatable deployment changes.

## Product Style

Keep the user experience simple:

- Restaurants should not need to learn a complicated tool.
- Customers should quickly see what is available today.
- Admin tools should help clean and approve specials fast.
- AI should assist the workflow, not become the product.

Use plain language in UI copy. The tone should be local, useful, and direct.

## Implementation Guidance

When adding or changing features, ask:

- Does this help restaurants publish today's specials faster?
- Does this help customers find today's specials faster?
- Does this strengthen the local specials graph?
- Can this be built in a simpler way?

Prefer incremental changes that can be tested quickly in one local market.

## Documentation

Keep documentation short and practical.

When adding a feature, update docs only with information future contributors need to understand the product, setup, or workflow.
