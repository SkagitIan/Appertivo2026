# Appertivo Tomorrow Plan: June 2, 2026

## Current Position

Appertivo is a working concierge beta, not a blank prototype. The product has a diner discovery feed, restaurant profiles, map view, city filtering, location search, a Skagit Valley launch preview, outside-market waitlists, restaurant intake, admin approval, lead capture, distribution tracking, and outreach tooling.

The gap is operational: the feed needs real restaurant-approved specials and opted-in diners need a useful alert.

## Morning Priorities

- [ ] Commit the current beta baseline.
- [ ] Run the full app from Factory Console and do one end-to-end walkthrough.
- [ ] Choose the first 10-20 Skagit restaurants for founder outreach.
- [ ] Send the first outreach batch asking for one current special and photo.
- [ ] Define the smallest useful diner digest and send a test to yourself.
- [ ] Confirm deployment target and production environment variables.

## Useful Commands

```powershell
py -m pytest -q
py -m flask --app app db upgrade
py -m flask --app app seed-demo-specials
```

Factory Console URL:

```text
http://127.0.0.1:9000
```

Appertivo local URL from Factory Console:

```text
http://127.0.0.1:5001
```

## Tonight's Verified State

- Database migration: `20260601_06`
- Imported restaurants: `374`
- Visible launch-preview specials: `6`
- Automated tests: `23 passed`
