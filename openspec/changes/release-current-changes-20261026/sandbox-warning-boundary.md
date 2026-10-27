# Pre-existing standalone sandbox subprocess lifecycle concern

Exact Lumen0.6.11 dev CI `40379595192` succeeded, including the sandbox package lane (45 passed,9 skipped,3 warnings). Its `PytestUnraisableExceptionWarning` reports `BaseSubprocessTransport.__del__` → pipe close after the event loop is closed. The same traceback/test names/counts occur in exact prior0.6.10 CI `40331730752`.

The standalone `packages/lumen-sandbox` tree is unchanged (`c420b7d3a23f4ef6cccb7a6e1ba26b8523b927e5`), remains0.1.1, and does not import the changed service cache. Read-only source inspection found that Kubernetes sandbox `McpProcess.kill` signals the process group, while manager/lifespan cleanup does not explicitly await every child exit and pipe drain. This is a pre-existing product ownership concern, not defensibly a harmless test-only warning. The logs do not prove live orphan processes or production effects.

No warning suppression, timing relaxation, source change or test rerun was performed. This concern is intentionally outside the user-approved Valkey routing patch and the current controller API/worker cutover; existing native runtime resources are separately fenced/checked. Do not describe0.6.11 as repairing sandbox process shutdown or claim native sandbox/guest execution qualification from image version checks.

Evidence: `~/.local/share/afterglow-proofs/lumen-valkey-sentinel-20261027/hosted-sandbox-warning-classification.json`, current/prior hosted sandbox logs. Any repair requires a separately scoped sandbox lifecycle change and its actual child/pipe drain proof.
