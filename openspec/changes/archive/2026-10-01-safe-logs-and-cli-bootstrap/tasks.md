## Lumen client setup

- [x] Chat API-key guide emphasizes public model ID, full one-time key, macOS/Linux CA paths and safe copyable commands.
- [x] Dashboard serves functional macOS/Linux and Windows installers for Codex/Claude, with private key entry, idempotence and profile preservation.
- [x] Validate installation scripts, real dashboard rendering and navigation/responsiveness.

## Verification and rollout

- [x] Update architecture, design guidance, CLI setup docs and changelog for the installer surface.
- [x] Run affected frontend and installer checks; state Windows/runtime, deployment and provider verification limits.

## Observed verification

- `PWSH=<official portable PowerShell 7.6.6> POWERSHELL_TELEMETRY_OPTOUT=1 npm run test:target:js`: orchestration 102 passed, Kolla contracts 26 passed, installer 27 passed / 1 explicit Windows-only DPAPI/ACL skip. This is the final integrated result after stale Anthropic API-key clearing and source-independent shared-CA rerun corrections.
- `npm run test:lumen`: backend 41 passed, frontend 131 passed. Focused `ChatApiKeysManager.test.ts`: 11 passed. Frontend `npm run check`: 0 errors / 0 warnings; `npm run build`: passed.
- Actual dashboard `curl | sh` under a controlling macOS PTY and fresh bash: private key entry, echo restoration, full key/model environment, discovery subpath, preserved model/provider/project, private 0600/0700 modes and stale direct-provider key clearing observed. Node behavior suite also exercised fresh zsh, cancellation, backups/rotation, unsafe input and TOML preservation.
- Network-disabled `python:3.12-slim`, UID 65534: actual installer and fresh bash loaded synthetic keys/models, validated system CA, preserved defaults and private HTTPS subpath, and applied 0600/0700 modes.
- Actual dashboard `irm | iex` under portable PowerShell: unsupported host refused before persistence. Windows parser/config/profile/encoding/CA behaviors ran; real Windows private prompt, CurrentUser DPAPI/ACL and profile startup did not run on macOS. No insecure emulation was used.
- Chromium with synthetic auth/discovery: five exact copy payloads and no synthetic browser token, tab navigation/single panel, 390/767/768/1023/1024/1440px without page horizontal overflow. Compiled preview rendered prerequisites/effective-model guidance; both static installers' served SHA-256 matched source.
- CLI-only temporary-index architecture stamp and `--staged` check passed; actual Git index was untouched. Pre-existing backend logging, cloud-shell and `pf.md` work is excluded and preserved. `gbrain` CLI is unavailable, so no knowledge sync was claimed.

## Verification and release limits

No native Windows security/runtime acceptance, authenticated Codex/Claude provider request, live TLS handshake, production rollout, commit or push was performed. The full project `npm run test:gate` was not run; targeted checks above are not a full-gate claim. This change configures already-installed CLI clients and does not establish desktop configuration or resolve the separate native OpenAI/logging investigations.

