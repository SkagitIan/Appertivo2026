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
