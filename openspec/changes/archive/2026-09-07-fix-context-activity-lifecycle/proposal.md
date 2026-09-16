# Fix chat compaction activity lifecycle

## Why

An automatic compaction is already represented by the active assistant run's `RunActivityItem` and `ExecutionTimeline`. A second chat-window status duplicates that lifecycle and can outlive or diverge from the run. The timeline label must still distinguish automatic compaction from manual compaction.

## What Changes

Render automatic compaction only through the assistant draft's execution timeline, with an explicit `컨텍스트 자동 압축 중` label. Keep the chat-window activity only for manual compaction, which has no assistant draft. Retain the slash-command caller for manual compaction and include its component regression in the named Lumen target.

## Acceptance

- An automatic `context.updated` event renders `컨텍스트 자동 압축 중` only in its active draft timeline; terminal runs hide unfinished activity and retain an explicit compacted history when supplied.
- A manual compaction remains visible in the chat window until its own terminal event.
- `/압축` remains the explicit manual-compaction caller and respects its disabled-reason gates.
- `npm run test:target -- lumen` includes ChatInput command coverage.
