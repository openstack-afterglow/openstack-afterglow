## Implementation Tasks

- [x] Trace the cluster/node group create screens, list controller request body and Drover `v0.4.13` omitted-field contract.
- [x] Default both autoscaling switches on and send the cluster Stampede choice explicitly so off remains an opt-out.
- [x] Update the default-visible warning in ko/en/ja/zh-CN and the K3s API/architecture/changelog docs.
- [x] Add consumer-visible regressions for the default, explicit opt-out body and node group submission.
- [x] Run i18n checks, Svelte check and the project gate; verify the compiled create screens in a real browser. (i18n/svelte check error 0; `npm run test:gate` rc0; production v1.30.15 screens verified in headless Chrome with intercepted request bodies.)
- [x] Merge to dev, pass CI, publish `v1.30.15`, roll out Afterglow through canonical Kolla and verify the production screens. (dev 38390146794, tag Docker 38390970773, Helm 38390970449; controller1→2→3 reconfigure rc0.)
- [x] Record evidence and archive the change. (`docs/testing.md`, `evidence/production-verification.json`.)
