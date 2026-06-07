# Special Intake Flow

Appertivo supports three incoming-special paths:

1. Private restaurant link: `/submit/<token>`
2. Public pilot form: `/submit-special`
3. Email reply to `specials@appertivo.com`

The canonical admin create path is `/admin/specials/create`. `/admin/intake` is legacy paste intake and should be deprecated unless a future admin-only parser needs it.

## Outreach Link Workflow

Use a private URL when you cold-email a specific restaurant.

1. Open `/admin/restaurants`.
2. Find the restaurant and open edit.
3. In "Private submission link", click "Generate link" or "Rotate link".
4. Copy the generated `/submit/<token>` URL from the confirmation page.
5. Put that URL in the outreach email.

The full tokenized URL is only shown once. The database stores a hash, so rotating the link invalidates the previous URL.

Use `/submit-special` when you do not know the restaurant yet or want a general public form. That page only accepts included Skagit Valley pilot restaurants. Google Places suggestions can appear as "coming soon", but they cannot submit until the restaurant is in the included catalog.

## Incoming Paths

### Path A: Restaurant Clicks Private Link

1. Restaurant opens `/submit/<token>`.
2. The token identifies the restaurant.
3. Restaurant submits title, description, price, date/time, optional image, and optionally an email for the approval link.
4. The app creates `RawSpecialSubmission`.
5. `special_pipeline.generate_draft_from_submission()` creates `SpecialDraft`.
6. If `Restaurant.direct_publish_enabled` is true, the app approves and publishes immediately.
7. Otherwise the draft waits for approval in `/admin/special-drafts`.

### Path B: Restaurant Uses Public Pilot Form

1. Restaurant opens `/submit-special`.
2. They search for their restaurant.
3. Included pilot restaurants can be selected.
4. Non-included Google Places matches show "coming soon" and cannot submit.
5. Email is required for approval follow-up.
6. Submission creates `RawSpecialSubmission` and `SpecialDraft`.
7. The app attempts to email the preview/approval link.
8. Draft remains in `awaiting_approval` until approved.

### Path C: Restaurant Replies To Outreach Email

1. Restaurant replies to the outreach email or sends directly to `specials@appertivo.com`.
2. Resend inbound webhook calls `receive_resend_email()`.
3. If the sender matches an outreach campaign or restaurant contact email, the submission is attached to that restaurant.
4. Otherwise it enters the draft queue unassigned.
5. Admin assigns the restaurant from `/admin/special-drafts` if needed.
6. Admin can manually create or correct the special at `/admin/specials/create`.

## Draft To Published

1. Raw input is stored in `RawSpecialSubmission`.
2. Draft content is stored in `SpecialDraft`.
3. Preview lives at `/specials/preview/<approval_token>`.
4. Restaurant or admin approves/rejects via the preview link.
5. Admin publishes approved drafts from `/admin/special-drafts`.
6. Published specials appear in `/admin/specials` and public `/specials/<public_id>`.
7. Distribution tools live at `/admin/specials/<id>/distribution`.
8. The first published special for a restaurant schedules a Resend follow-up email
   5 minutes later when the submission or restaurant has an email address.

The local Playwright suite covers public form, private-token, trusted direct-publish,
admin publish, digest, outreach, and captured email/Loops behavior.

## AI Enhancement Target

Current code uses a local parser in `special_pipeline.polish_special_text()`. Production target:

1. Send raw text, form fields, and any OCR text to OpenAI.
2. Return structured fields: title, description, price, availability, start/end schedule, repeat rule, and CTA.
3. Correct spelling and grammar.
4. Add light marketing polish without inventing facts.
5. Preserve raw text for audit.

## Image Enhancement Target

Current code stores uploaded images as-is through local storage or R2. Production target:

1. If an image is uploaded, send it to Cloudinary's AI enhancement flow.
2. Store the enhanced image URL/path on `SpecialDraft`.
3. Keep the original raw image reference on `RawSpecialSubmission`.
4. Publish only reviewed images unless the restaurant is trusted.

## Publish Rules

Default: draft requires approval and admin publish.

Trusted restaurant: if `direct_publish_enabled` is true, private-link submissions can publish automatically after draft generation.

Recommended near-term rule: public form and email replies should require approval until sender identity and image policy are stronger.
