# Durable chat work log

## Problem

The current indexed Lumen message page projects execution metadata only onto user retry rows. Assistant tool/reasoning events already exist in the encrypted run journal, but the final assistant loses those details when the client replaces its draft with stored history.

## Change

Reuse the existing public `execution.activity` projection on final assistant IDs in bounded indexed pages. Include the actual run-start boundary, model/context stages, approval decisions, tool failures, child outcomes and terminal timestamps. Do not add a second approval system, database schema, hidden reasoning source or provider request.

Afterglow keeps preparation quiet, opens one live work panel, places the existing approval card in that flow, and collapses the completed panel to one elapsed-time disclosure above the answer. Reopening history preserves all public steps. Tool groups no longer hide their rows behind an extra category disclosure.

## Delivery boundary

Source/local qualification only. Lumen may deploy first: the UTC start boundary is the additive `execution.started_at` metadata field, while every `execution.activity.kind` remains understood by the deployed reader. No new activity enum or reader-only release is required. Older Lumen history without the field receives an honest untimed history label. Temporary-thread expiration remains unchanged. No push, publication, rollout or production-provider/cloud acceptance belongs to this slice.
