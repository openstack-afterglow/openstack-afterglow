## Implementation Tasks

- [x] Identify the exact CI failure and restrict the repair to the runtime dependency install.
- [x] Reuse the committed npm lock with frozen production installation and align version metadata without changing dependencies.
- [x] Build actual frontend images for amd64/arm64 and exercise the built runtime's locale HTTP path.
- [x] Run the project gate and staged architecture guard; record the minimal repair evidence for dev integration.
