## 1. Default Activation

- [x] 1.1 Make missing browser and SSR beta preferences fall back to declared defaults.
- [x] 1.2 Enable volume backups in the default feature state while preserving an explicit browser-local opt-out.

## 2. Behavioral Coverage

- [x] 2.1 Cover fresh-browser activation, explicit opt-out, account-toggle state, and default navigation visibility.
- [x] 2.2 Run the focused frontend selector and the full project gate.

## 3. Documentation and Release

- [x] 3.1 Update volume documentation, architecture review, and changelog.
- [ ] 3.2 Archive the completed change, push `dev`, deploy the published frontend digest, and verify service flags plus Cinder backup readiness.
