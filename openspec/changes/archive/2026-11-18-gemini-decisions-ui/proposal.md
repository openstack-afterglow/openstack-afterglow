# Gemini Decisions in Decision Studio

## Why

Decision Studio can evaluate structured questions with an enabled OpenAI model. Gemini Decision 1 offers an independent decision-only route with shared text and image input and typed answers. Users need to select that model without treating it as a text-chat model.

## What Changes

- List decision-only models separately and branch the Studio editor and result presentation on the selected model's Lumen provider and kind/capability. Preserve the OpenAI editor and typed response path.
- Send text, JSON serialized as text, and inline images to the existing session/project-scoped Decisions BFF route. Enforce a 20 MiB serialized request cap. Lumen remains authoritative for validation, permission, pricing, and billing.
- Expose `decision` in the administrator model registry with input-token pricing only. Localize all new labels and errors in the nine supported locales.
- No production access, releases, tags, or merge to `dev` in this change.
