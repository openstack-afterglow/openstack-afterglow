# Lumen CLI connection guide and bootstrap

Improve chat API-key settings for Codex and Claude Code: emphasize editable configuration, full one-time API key and public model IDs; show copyable macOS `/private/etc/ssl/cert.pem` and Linux `/etc/ssl/certs/ca-certificates.crt` CA settings without disabling TLS. Show `codex --strict-config -c model_provider=lumen` with the requirement that the user-level default model is an active Lumen Responses model, and retain `-m` guidance to preserve other defaults.

Host public setup scripts under the dashboard origin at `/install/lumen.sh` and `/install/lumen.ps1`. Only public Lumen endpoint URLs go in the curl/irm command. Installers prompt for the full API key privately on the local terminal, store it in a private POSIX key file or Windows current-user DPAPI store, configure Codex Responses and Claude Code Anthropic environment, and update the user profile idempotently. Preserve unrelated Codex settings and default provider/model; explicitly ask before replacing the top-level model. No CLI binary installation or provider request is performed.

Acceptance: actual dashboard rendering and copy controls expose both CA paths, public bootstrap URLs, endpoint/model/key checks and exact Codex command. Installers preserve settings, support reruns, private key entry/storage, shell-profile loading and unsafe-input failure paths. Verify local browser and installer behavior; distinguish platform-specific runtime limitations and local checks from deployment or live provider success.

Pre-existing service logging changes, other repositories, production rollout and the unresolved native OpenAI failure are outside this change and remain preserved.

