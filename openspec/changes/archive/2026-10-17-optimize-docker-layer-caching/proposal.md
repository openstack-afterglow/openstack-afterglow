## Why

애플리케이션 소스 복사 뒤에 backend 시스템 패키지 설치, frontend 운영 의존성 설치, native VM datastore/kernel 설치 및 재귀 chown이 위치해 소스만 바뀌어도 느린 레이어가 무효화된다. 실제 BuildKit 단계 시간과 source-only rebuild로 병목을 구분하고 설치 레이어 캐시를 보존한다.

## What Changes

- OS/도구/외부 의존성 설치를 소스와 독립된 앞쪽 레이어로 이동한다.
- Backend·worker의 로컬 crypto 패키지 소스를 외부 의존성 설치 뒤로 분리하고 개발 target도 동일 원칙을 적용한다.
- Frontend의 npm 운영 의존성을 compiled build와 runtime script 복사 전에 설치한다.
- Native VM의 MariaDB/Redis 및 amd64 cloud kernel 설치는 애플리케이션 소스를 상속하지 않는 runtime base에서 실행한다.
- 소유권은 COPY --chown으로 지정하여 소스 변경마다 가상환경·node_modules 전체를 chown하지 않는다.
- 고정 공개 source snapshot과 task-only image tag/Compose project에서 build timing, source-only cache reuse 및 실제 runtime을 검증한다.

## Capabilities

### New Capabilities

없음. 기존 Docker target의 cache boundary만 변경한다.

### Modified Capabilities

Backend·worker·frontend·개발 및 native target의 build graph. Target 이름·런타임 명령·의존성 버전·지원 architecture·인증 및 데이터 계약은 유지한다.

## Impact

주요 변경은 Dockerfile이며 필요 시 .dockerignore의 무관한 로컬 build-context 입력을 제외한다. ARCHITECTURE.md, 기존 배포/검증 문서 및 CHANGELOG.md에 구조와 실측 증거를 기록한다. 공유 dev checkout의 기존 미커밋 변경·실행 stack·volume·key를 보존하며 production/원격 배포·version bump·commit/push는 수행하지 않는다. Native cloud VM의 실제 KVM boot는 이 build-layer 변경의 로컬 container runtime 증거와 구분한다.
