## 1. Service authority audit and correction
- [ ] 1.1 Audit and correct Lumen authority; preserve deployed engine and OpenID human boundary.
- [ ] 1.2 Audit and correct Drover authority and native capability endpoint.
- [ ] 1.3 Audit and correct Waygate authority, capability endpoint and provider attenuation.
- [ ] 1.4 Audit and correct Palimpsest authority on latest dev, including explicitly approved SDK/publication transition without deployed-repair rollback.
- [x] 1.5 Compare actual operator policy overrides and native role matrix (all3 policy inventory and fresh native role inference; probe token revoked204).

## 2. Qualification and publication
- [ ] 2.1 Final source gates and native runtime smoke for each service.
- [ ] 2.2 Integrate scoped changes safely; publish exact-SHA CI-qualified immutable versions and bilingual releases.
- [ ] 2.3 Verify all supported image architectures, revision/digests/aliases and package-owned Kolla role artifacts.

## 3. Operational rollout
- [ ] 3.1 Capture original config/datastore/key/schema and recoverable image identities; resolve migration/cohort prerequisites.
- [ ] 3.2 Update only approved four operator packages/pins and preserve Kolla/unrelated dependencies.
- [ ] 3.3 Execute canonical compute then control Kolla units with durable full logs and recap.
- [ ] 3.4 Verify every controller identity/readiness and authenticated role paths; record scope and unresolved risks.
- [ ] 3.5 Qualify Palimpsest production snapshot restore, latest schema/bootstrap and paired SQL/CAS rollback prerequisites.
- [ ] 3.6 Update/recover separately approved dedicated build-worker host while preserving exact key, journal and scratch volume.

## 4. 승인된 세 서비스 우선 전환 관측

- [x] 4.1 2026-11-04 세 서비스 기존 API/worker18개를 단계적으로 drain·정상 종료하고 SQL/PG stopped-writer backup 및 격리 복원을 검증했다. 증거: `/home/pieroot/.local/share/afterglow-authority-20261104/three-stopped-20261104T071024Z/evidence.json`.
- [x] 4.2 `compute` 전체와 `control --tags lumen,waygate,drover` reconfigure가 각 전체 recap에서 failed0으로 끝났다. Palimpsest application 전환은 사용자 선택에 따라 보류했다.
- [x] 4.3 세 controller에서 release digest/revision과 API healthy, worker running을 확인했다. 기존 Palimpsest API/worker container ID는 보존됐다.
- [x] 4.4 실제 임시 Keystone manager/member/reader와 reader 제한 credential로 세 서비스 목록·capabilities200을 확인하고, Lumen은 manager/member 대화 생성201·삭제204와 reader 생성403을 확인했다. 임시 자격증명과 프로젝트는 제거했다. 증거: `/home/pieroot/.local/share/afterglow-authority-20261104/live-role-matrix-after-v2.json`.
- [ ] 4.5 Drover·Waygate 실제 provider 리소스 생성/변경과 전체 사용자 화면은 검증하지 않았다. Palimpsest 운영 schema·worker 전환은 별도 승인 범위에서 수행한다.
- [x] 4.6 배포 후 compute12대 container census에서 미복구 health는 없고 native Nova compute12개 up/enabled와 각 호스트의 OVS agent12개 alive/enabled를 확인했다. compute7의 여러 container image 변경은 실제 reconfigure 결과이며 running/health를 확인했다. 증거: `/home/pieroot/.local/share/afterglow-authority-20261104/compute-after.json`, `compute-native-after.json`, `compute-ovs-after.json`.
