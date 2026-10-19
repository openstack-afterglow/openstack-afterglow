## Implementation Tasks

- [x] 현재 Dockerfile·CI·Compose·lock source를 검토하고 source 뒤의 느린 설치와 chown 경계를 식별한다.
- [x] 고정 공개 snapshot에서 기존 target을 실제 빌드하고 source-only rebuild의 단계 시간/캐시 무효화를 기록한다. Arm64 source-only backend 48.964초(apt23.1/chown5.7), frontend62.553초(build44.3/npm+chown6.7)를 관측했다.
- [x] backend/worker/dev의 외부 의존성·시스템 설치를 소스 앞에 두고 runtime recursive chown을 제거한다. Dev의 writable venv 소유권 설정은 앱 소스 복사 전에 캐시한다.
- [x] frontend의 운영 의존성 설치를 compiled source/artifact 복사와 분리한다.
- [x] native VM/datastore와 amd64 cloud/kernel 설치를 애플리케이션 소스와 독립된 stage로 분리한다.
- [x] Backend/worker/frontend/native-vm/dev 양 architecture와 amd64-only native-cloud-vm 13개 target/platform을 build하고 실제 바이너리를 실행했다. Source-only 재빌드에서 OS·uv·npm·native kernel 설치 CACHED를 확인했고 crypto 소스 probe도 새 wheel에 반영됐다. Native supervisor 3조건의 HTTP200·종료0을 확인했으며 실제 KVM boot/운영 인증은 범위 밖이다.
- [x] 정본 개발 Compose의 별도 project에 양 architecture를 배포하여 API/frontend health200·login200, backend/worker UID1000·source hash, Redis의 미래 worker membership과 graceful exit0을 검증한다. Tmpfs 전용 SQL/Redis와 소유 project만 종료했다.
- [x] Architecture·배포 문서·changelog와 실측/검증 한계를 갱신했다. 격리 working/staged guard는 b07096a3/3,049files로 통과했다. `npm run test:gate`는8317passed/12failed/91skipped로 중단했으며 범위 밖 storage-delete11·host-observer timeout1과 미실행 downstream을 기록했다. 커밋/발행 qualification은 green으로 보고하지 않는다.
- [x] Rapid change의 generic strict validation을 실행하고 delta 부재 exit1과 정본 rapid no-spec/`--skip-specs --yes` 계약을 기록했다. 기능 delta/spec 관례를 추가하지 않는다.
