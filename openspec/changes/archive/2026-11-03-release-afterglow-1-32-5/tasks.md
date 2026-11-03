## Qualification

- [x] 요청 시점의 완료된 public 변경과 review correction을 고정하고 private/index/동시 작업을 보존한다.
- [x] 도메인 마지막 관리자 및 채팅 종료 표시 회귀를 고치고 변경 경로·전체 gate·실제 runtime을 검증한다.
- [x] 1.32.5 버전과 문서를 동기화하고 정확한 snapshot을 기본 dev에 커밋·push한다.
- [x] 정확한 SHA CI 통과 뒤 numeric tag·GitHub Release·image/latest·Helm을 발행·검증한다.
- [x] SQL106·동일 key·native 서비스 호환성·writer 및 복구 선행 조건을 발행 기록에 남긴다. Kolla 전환은 사용자가 수행하며 이번 범위에서 제외한다.
- [x] 증거와 차단 조건을 기록하고 완료된 발행 artifact를 archive하며 소유 격리 자원을 정리한다.

## Evidence

- Source `92cb744ab615de699e552dfa3423f3956b5b8f4d`, full source CI 41664544663, tag image CI 41666263431, Helm CI 41666263078. [GitHub Release 1.32.5](https://github.com/openstack-afterglow/openstack-afterglow/releases/tag/1.32.5) includes Korean and English version, release date, changes, and deprecated/removed features.
- Release/latest digest and revision match: API `sha256:7de219321bb60c58a82529cb71b4b6d47fdbf23ba7c2058ccf9c8fbc8404305b`, frontend `sha256:f6b47af23c8f5b5a7319aba25183903dba67b9f935140f06e325f4151f63e296`, worker `sha256:af1978772cc6c9b37bb22aba1e77a54894e61cd21e4944c67e41cbb9b77339ba`. Published chart version/appVersion 1.32.5 and digest-pinned non-root linux/amd64 runtime version 1.32.5 verified.
- Full gate source `3ca09d9c27882b0c82f4f39c3a0f8131f1949341ba5473c36613773416f4e60f`: backend 13506 passed/106 skipped, frontend 6782, contracts 258, disposable DB 220/53 deselected. Protected proof `~/.local/share/afterglow-proofs/release-1.32.5-20261104/`.
- Kolla and production SQL/native service changes excluded per user. SQL106 columns were absent in the three controller observations before publication; the user owns actual schema/backup/writer/native compatibility and rollout. API lifespan and packaged chat-error end-to-end were not tested.
