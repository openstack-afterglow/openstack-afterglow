## Implementation Tasks

- [x] Reproduce the polluter→victim failure in one pytest process on unchanged backend source, show the fixture order, and verify the victim passes alone.
- [x] Restore all three scoped token overrides in try/finally before assertions; remove unused monkeypatch parameters.
- [x] Pass the ordered pair, both complete files (140tests), Ruff check and format-check.
- [x] Pass the complete canonical gate in the configuration-isolated detached worktree (exit0; backend15024, frontend7962, contract262, functional292).
- [x] Record the distinct CHANGELOG/testing/architecture entry, archive and commit on ux/slop-pass-2 without merge/push.
