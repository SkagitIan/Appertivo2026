# Appertivo Launch Tasks

## Launch Target

Today is Wednesday, June 3, 2026. The go-live target is Monday, June 8, 2026.

The next two work days should get Appertivo over the hump from working concierge beta to public Skagit Valley launch:

- Real restaurant-approved specials replace launch-preview content.
- Restaurant owners have a simple way to send one special and say yes.
- Diners can join the list and receive a useful manual alert or digest.
- The production site is deployed, verified, and ready to share.

## Current Verified State

- Automated tests: `42 passed` on June 3, 2026.
- Product loop exists: public feed, city filtering, maps, restaurant pages, public special submission, private restaurant submit links, admin draft approval, manual special publishing, metrics, distribution kits, outreach inbox, Resend inbound webhook, and Railway health check.
- Production wiring exists: `railway.toml` runs migrations and safe launch seeding before Gunicorn, with `/health` as the health check.
- Main gap: the feed still depends on labeled preview specials until restaurant-approved posts arrive.
- Main product gap: subscriber capture exists, but a manual diner digest or alert send path is not implemented yet.
- Main launch gap: production domain/email/storage settings and real content need final verification.

## Definition Of Go-Live

Appertivo is launchable on June 8 when all of these are true:

- [ ] Public production URL loads the homepage, restaurants index, one restaurant page, one special detail page, and `/health`.
- [ ] At least 10 restaurant-approved specials are published, or a hard floor of 6 real approved specials if outreach is slower than expected.
- [ ] No unlabeled fake content appears as real. Any remaining demo content is clearly labeled as launch preview or hidden below real posts.
- [ ] Diner signup works in production and sends new subscribers into a usable list.
- [ ] A manual digest or alert can be previewed, test-sent, and sent to opted-in Skagit subscribers with an unsubscribe path or compliant provider-managed unsubscribe.
- [ ] Restaurant lead capture works in production.
- [ ] Restaurant special intake works through at least one low-friction path: admin entry, public `/submit-special`, or private restaurant token link.
- [ ] Admin can approve, publish, expire, and distribute a special without code changes.
- [ ] Email sender domains, reply-to inboxes, and Resend inbound webhook are verified or explicitly deferred from launch copy.
- [ ] Production environment has `SECRET_KEY`, `ADMIN_PASSWORD`, `APP_BASE_URL`, `DATABASE_URL`, and email/storage variables set as needed.
- [ ] `py -m pytest -q` passes before the launch deploy.

## Day 1: Wednesday, June 3, 2026

Theme: stabilize production, add the smallest missing diner alert path, and prepare restaurant outreach so real specials can arrive.

### Dev Critical Path

- [ ] Add a manual diner digest MVP instead of scheduled background jobs.
  - Admin-only page or CLI command can select active Skagit specials.
  - Preview shows subject, HTML body, text body, recipient count, and included specials before sending.
  - Test send can go to `EMAIL_TEST_RECIPIENT`.
  - Production send targets opted-in Skagit subscribers only.
  - Each special link uses a tracked channel such as `email_digest`.
  - Send result logs success/failure count without exposing secrets.
- [ ] Add the minimum unsubscribe or suppression path required before any marketing-style diner email is sent.
  - Prefer provider-managed unsubscribe if using Loops.
  - If sending directly through Resend, add a subscriber unsubscribe token/route and exclude unsubscribed subscribers.
- [ ] Add digest tests covering preview generation, recipient filtering, unsubscribe exclusion, tracked links, and test-send guardrails.
- [ ] Replace Tailwind browser CDN with a production-safe asset path, or make an explicit launch decision to keep the CDN only if no visual/build regressions can be handled today.
- [ ] Update `.env.example` and docs for any digest, unsubscribe, sender, or production variables added today.
- [ ] Run `py -m pytest -q`.

### Production Readiness

- [ ] Verify Railway linkage from repo root: `railway status`.
- [ ] Confirm production deploy logs show migrations and `seed-launch-data` completing.
- [ ] Confirm production `/health` returns OK.
- [ ] Verify `APP_BASE_URL` points to the public production URL that will be shared.
- [ ] Confirm `ADMIN_PASSWORD` and `SECRET_KEY` are not using defaults.
- [ ] Confirm Resend sender domain status, from addresses, reply-to addresses, and inbound webhook destination.
- [ ] Confirm photo storage decision for launch:
  - Use R2 if credentials and public base URL are ready.
  - Otherwise launch with URL/manual images and defer owner photo uploads that need durable public hosting.

### Restaurant Data And Outreach

- [ ] Import or reconcile the enriched restaurant CSV with contact emails, using only high-confidence owner/contact emails.
- [ ] Keep chain/excluded venue decisions intact; do not bloat the launch catalog with non-target businesses.
- [ ] Pick the first 25 restaurant targets across Mount Vernon, Burlington, Anacortes, Sedro-Woolley, La Conner, and Bow/Edison.
- [ ] Prioritize independent places likely to have specials, happy hours, bakeries/cafes, breweries, tacos, seafood, brunch, and high-review local favorites.
- [ ] Create outreach campaigns for the first batch in `/admin/outreach`.
- [ ] Draft one short founder email asking for:
  - One current special.
  - Price, day/time availability, and a photo if they have one.
  - Permission to publish on Appertivo as part of the Skagit launch.
  - Confirmation of the best contact for future specials.
- [ ] Prepare a no-friction reply format owners can use: `Restaurant, special, price, valid day/time, photo/website link, yes to publish`.
- [ ] Send only reviewed outreach emails. If Ian is unavailable for review, queue drafts and prepare a single approval checkpoint.

### Day 1 Acceptance Check

- [ ] A manual digest can be previewed and test-sent locally.
- [ ] Outreach batch is ready or sent with reviewed copy.
- [ ] Production health and admin access are verified.
- [ ] Test suite passes.
- [ ] Remaining launch blockers are listed at the top of this file or in the final Day 1 handoff.

## Day 2: Thursday, June 4, 2026

Theme: publish real content, verify the full production loop, and package the June 8 launch.

### Dev Critical Path

- [ ] Finish any Day 1 digest/unsubscribe work that did not pass tests.
- [ ] Add a production smoke-test checklist to docs or an admin launch checklist page if it saves real launch risk.
- [ ] Tighten homepage behavior once real specials exist:
  - Real specials sort above demo specials.
  - Demo specials remain visibly labeled or are hidden when enough real specials are live.
  - Empty city states push diner signup and restaurant submission, not dead ends.
- [ ] Verify special detail action tracking for directions, call, website, and share links from production URLs.
- [ ] Verify private restaurant submit-token flow from a generated token.
- [ ] Verify public `/submit-special` creates a draft and admin can publish it.
- [ ] Run `py -m pytest -q`.

### Real Specials Pipeline

- [ ] Process every restaurant reply into one of these states: needs follow-up, approved special, not interested, wrong contact, or later.
- [ ] Publish every approved special with:
  - Restaurant name and city.
  - Plain-language title.
  - Short description.
  - Price if provided.
  - Valid date/time or same-day expiry.
  - Photo only when permission/source is clear.
- [ ] For each published special, open the public detail page and verify directions/call/website actions.
- [ ] Generate a distribution kit for each approved special.
- [ ] Save a short social caption for each special.
- [ ] Keep a visible count of real approved specials versus launch-preview specials.

### Diner Launch Prep

- [ ] Build the first Skagit digest manually from the strongest active specials.
- [ ] Test send the digest to Ian.
- [ ] Check subject line, links, city labels, unsubscribe path, and mobile readability.
- [ ] Decide launch-send timing:
  - If 6 or more real specials are live by June 4, schedule/send the first early-access digest.
  - If fewer than 6 are live, keep collecting subscribers and send a launch-day digest on June 8.
- [ ] Create a simple fallback alert copy for launch day if the digest has too little content.

### Launch Copy And Sharing Kit

- [ ] Prepare owner-facing one-liner: `Appertivo is a Skagit Valley specials feed where restaurants can send one current special and get a public link to share.`
- [ ] Prepare diner-facing one-liner: `Find what Skagit restaurants are serving today, from happy hours to fresh drops and limited menus.`
- [ ] Prepare 3 social posts:
  - Launch teaser before real specials are loaded.
  - Launch-day diner post.
  - Restaurant-owner call for specials.
- [ ] Prepare 3 direct messages for restaurant owners:
  - Warm local intro.
  - Follow-up after no reply.
  - Thank-you with published special link.
- [ ] Prepare a short list of places/people to share with on June 8: local restaurant owners, chambers, downtown associations, food groups, personal socials, and friendly early diners.

### Day 2 Acceptance Check

- [ ] Production site passes the public smoke test.
- [ ] Admin can intake, approve, publish, expire, and distribute a special in production.
- [ ] At least the first real approved specials are live or queued with owners contacted.
- [ ] Digest test send works or the launch digest is explicitly deferred with the reason documented.
- [ ] Launch copy is ready.
- [ ] Test suite passes.

## June 5-7 Launch Buffer

Use this window only for launch blockers, real content, and verification.

- [ ] Follow up with restaurants that opened or replied.
- [ ] Publish additional approved specials.
- [ ] Replace or push down preview specials as real content grows.
- [ ] Verify custom domain or final Railway URL.
- [ ] Verify production database has the intended restaurant catalog and no reset command is run against production.
- [ ] Verify analytics/metrics by clicking one special link with a test channel.
- [ ] Send a final test digest.
- [ ] Screenshot the homepage, restaurant page, and special page for launch posts.
- [ ] Prepare launch-day admin login, production URL, and support contacts.

## June 8 Launch Morning

- [ ] Check production `/health`.
- [ ] Open homepage, restaurants index, one restaurant page, and one live special page on mobile and desktop.
- [ ] Confirm at least 6 real specials are live; target 10+.
- [ ] Send or schedule the first useful diner digest if content threshold is met.
- [ ] Share diner launch post.
- [ ] Send owner thank-you links for published specials.
- [ ] Send owner call-for-specials post/message.
- [ ] Watch admin dashboard for subscribers, leads, special views, and action clicks.
- [ ] Keep a short issue log for anything that breaks after sharing.

## Do Not Chase Before June 8

- [ ] Restaurant dashboards.
- [ ] Payments.
- [ ] Complex accounts or permissions.
- [ ] Fully automated scheduled jobs.
- [ ] Social scraping.
- [ ] Unreviewed AI publishing.
- [ ] Multi-market expansion beyond Skagit Valley.
- [ ] Pricing experiments before restaurants are actively sending specials.

## Useful Commands

```powershell
py -m pytest -q
py -m flask --app app db upgrade
py -m flask --app app seed-demo-specials
railway status
railway logs --latest --lines 120
```

Factory Console:

```text
http://127.0.0.1:9000
```

Local Appertivo from Factory Console:

```text
http://127.0.0.1:5001
```

Production:

```text
https://appertivo2026-production.up.railway.app
```
