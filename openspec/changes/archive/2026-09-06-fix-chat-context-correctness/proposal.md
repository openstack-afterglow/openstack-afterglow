# Correct temporary chat terminal state

## Why

A failed or canceled temporary durable run leaves its optimistic assistant draft marked `streaming`, because only `run.completed` clears the flag and temporary threads are not reloaded from persistent conversation history.

## What Changes

Clear and retain the optimistic temporary draft before ending a failed or canceled run, so its terminal footer is rendered. Keep persistent-history reload behavior unchanged.

## Acceptance

A temporary run that emits `run.failed` or `run.canceled` returns the composer and message footer to a non-streaming terminal state without a history reload.
