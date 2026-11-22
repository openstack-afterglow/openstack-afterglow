# Keystone defaults-only precheck support

## Why

Kolla's default `keystone_internal_url` is an unversioned Identity API root. Keystone serves version discovery from this root as HTTP 300 with a JSON list of supported versions. Afterglow already accepts this URL and appends `/v3` in its backend, but the deployment precheck required HTTP 200 and blocked a valid defaults-only deployment.

## What Changes

- Accept HTTP 200 only with a v3 version document and HTTP 300 only with a v3 discovery entry.
- Keep non-Keystone 300, 5xx, malformed documents, TLS errors and connection failures fail-closed.
- Do not change defaults, operator configuration, or require a `globals.d` override.
- Add local HTTP/real-Ansible regression fixtures and document the supported discovery behavior.
