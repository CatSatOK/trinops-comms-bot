# Data handling (GDPR)

This service runs a customer chat bot, so it stores what visitors type. This
note describes what is held, why, and how to action a data-subject request. It
is engineering documentation, not legal advice.

## What personal data is stored

Held in the `conversations` and `messages` tables:

- a per-visitor session id (random, stored in the visitor's `localStorage`)
- every message the visitor sends and every reply, with timestamps
- whether the conversation was escalated to a human, and when

Message text is free-form, so a visitor may type personal data into it. Treat
transcripts as potentially containing personal data.

When a conversation is escalated, the transcript is written to the outbox
(`data/outbox/` in demo mode) or emailed to the support address in production.

## Lawful basis

The bot answers questions the visitor chose to ask. Show a short notice next to
the widget pointing at this policy so visitors know the chat is stored. There is
no marketing use of the data and no third-party analytics.

## Claude / LLM fallback

- When a question is not matched from the FAQ and `ANTHROPIC_API_KEY` is set,
  the message plus FAQ context is sent to the Anthropic API to draft a reply.
- Leave `ANTHROPIC_API_KEY` empty to disable this entirely; unmatched questions
  then get a canned fallback and nothing leaves the service.
- Input is length-capped server-side before any API call.

## Retention

- Demo mode stores conversations in a local SQLite file (`data/comms.db`).
- In production, set a retention period and delete transcripts past it (the
  erasure endpoint below is the mechanism). There is no automatic expiry job in
  this demo.

## Right to erasure (right to be forgotten)

`DELETE /conversations/{id}` (admin-authenticated when `DEMO_MODE=false`) deletes
the conversation and, via cascade, every message in it. It returns
`204 No Content`. To find the right conversation, list them with
`GET /conversations` (the visitor's session id is shown).

Note: an escalation transcript already delivered to the outbox/support inbox is
a separate copy outside this database; erase that at its destination too.

## Access control

- Listing, reading, and erasing conversations require the `X-API-Key` admin
  header when `DEMO_MODE=false` (see `.env.example`).
- The chat WebSocket itself is unauthenticated by design but rate-limited,
  length-capped, and supports an Origin allowlist (`ALLOWED_ORIGINS`).

## Data location and transfers

- Data stays in the configured database (`DATABASE_URL`). The only outbound
  transfer is the optional Anthropic API call above and escalation emails when
  `DEMO_MODE=false`. Account for both in your own processing records.
