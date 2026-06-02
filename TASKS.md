# Appertivo Tasks

## Tomorrow: Tuesday, June 2, 2026

### Start Here
- [x] Create a clean Git commit for the current beta baseline before adding more features.
- [ ] Run the app from Factory Console at `http://127.0.0.1:5001` and walk through the diner, restaurant, and admin flows once.
- [ ] Review the six sample specials on the homepage and decide whether the mix looks like the Skagit launch you want to sell.
- [ ] Enter the production environment variables in Railway and verify the first deploy.

### Get Real Restaurants Into The Feed
- [ ] Pick the first 10-20 Skagit Valley restaurants to contact.
- [ ] Use the outreach inbox to draft a short founder email for those restaurants.
- [ ] Ask for one current special, a photo, and permission to publish it as a launch example.
- [ ] Replace sample specials with the first restaurant-approved posts as replies arrive.
- [ ] Track which restaurants need follow-up.

### Close The Diner Loop
- [ ] Test the homepage early-list signup and unsupported-market waitlist signup.
- [ ] Decide on the first alert format: a simple Skagit daily digest is the smallest useful version.
- [ ] Wire an admin-triggered digest send for opted-in diners before building scheduled background jobs.
- [ ] Send a test digest to yourself and verify links, map directions, and special tracking.

### Production Readiness
- [ ] Configure production `SECRET_KEY`, `ADMIN_PASSWORD`, `APP_BASE_URL`, email credentials, and R2 storage if photo hosting is needed.
- [ ] Replace Tailwind's browser CDN with a production build before public launch.
- [ ] Run `py -m pytest -q` and apply `py -m flask --app app db upgrade` in the deploy environment.
- [ ] Verify the public homepage, one restaurant page, one special detail page, one signup, and one restaurant lead submission after deploy.

## Completed Tonight
- [x] Shift the homepage from restaurant-facing copy to a diner-focused, location-first discovery experience.
- [x] Add Skagit Valley as the first market with city matching and an outside-market waitlist state.
- [x] Add six labeled launch-preview specials and an idempotent `flask --app app seed-demo-specials` command.
- [x] Add subscriber location storage and migrate the local database through `20260601_06`.
- [x] Verify the map toggle, responsive homepage, and Seattle waitlist state in a browser.
- [x] Prepare Railway deployment with Railpack, Gunicorn, migrations, a healthcheck, and a safe launch-data seed.
- [x] Fix SQLite test isolation and verify the full suite: `25 passed`.

## Parking Lot
- [ ] Add a database-backed `Market` model when the second launch region is real.
- [ ] Add restaurant claim flow and lightweight restaurant self-service.
- [ ] Add food-category preferences and saved specials for diners.
- [ ] Add scheduled background jobs after the first manual digest proves useful.
- [ ] Explore pricing after restaurants actively publish and diners click alerts.
