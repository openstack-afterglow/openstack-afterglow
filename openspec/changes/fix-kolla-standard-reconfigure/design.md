## Context

On a fresh toolbox, Cloud Shell is checked before Manila's task creates the shared CLI cloud configuration. Operator pins also override the moving image channels.

## Goals / Non-Goals

**Goals:** Ensure the full standard Kolla invocation works independently of prior toolbox state and selects the current published image channels.

**Non-Goals:** Bypass migration preflight, alter persisted credentials, or replace stock service data.

## Decisions

Prepare the shared toolbox cloud before either Cloud Shell or Manila checks. Install the Manila plugin only when Manila is enabled. Retain existing immutable per-invocation image resolution; operator pins are intentional and must be explicitly removed only for application channels.

## Risks / Trade-offs

Moving channels can introduce migrations: inspect and rehearse the exact current cutover with a verified recovery point. Standard untagged reconfigure also affects stock services, so assess its actual full inventory and health before execution.
