## Implementation Tasks

- [x] Trace the cluster/node group create screens, list controller request body and Drover `v0.4.13` omitted-field contract.
- [x] Default both autoscaling switches on and send the cluster Stampede choice explicitly so off remains an opt-out.
- [x] Update the default-visible warning in ko/en/ja/zh-CN and the K3s API/architecture/changelog docs.
- [x] Add consumer-visible regressions for the default, explicit opt-out body and node group submission.
- [ ] Run i18n checks, Svelte check and the project gate; verify the compiled create screens in a real browser.
- [ ] Merge to dev, pass CI, publish `v1.30.15`, roll out Afterglow through canonical Kolla and verify the production screens.
- [ ] Record evidence and archive the change.
