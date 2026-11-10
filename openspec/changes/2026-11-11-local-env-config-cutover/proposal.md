# 로컬 설정을 루트 `.env`와 `afterglow.conf`로 직접 사용

## 배경

로컬 Compose는 `.local-services/` 디렉터리에 `afterglow.conf` 사본, 생성 키 파일(`secrets.json`), `lumen.env`, `compose.env`, 정책 디렉터리를 만들어 사용했다. 사용자는 이 분리를 없애고 로컬 실행이 루트 `.env`(비밀)와 `afterglow.conf`(비밀이 아닌 설정)만으로 동작하기를 요청했다.

## 목표

- 로컬 설정 입력은 루트 `.env`와 `afterglow.conf`만 사용한다. `.local-services/` 사본과 생성 파일을 만들지 않는다.
- 비밀은 `.env` 또는 셸 환경변수에만 둔다. `afterglow.conf`의 `[local]`은 비밀이 아닌 허용 키만 받는다.
- 우선순위는 셸 환경변수 > `.env` > `afterglow.conf`로 통일한다. 값은 출력하지 않는다.
- 기존 로컬 암호화 키는 값을 바꾸지 않고 `.env`로 옮긴다. 키가 바뀌면 로컬 DB의 암호화 데이터가 복호화되지 않는다.

## 범위 밖

- 운영 Compose·Kolla·Kubernetes 설정, 운영 DB, 운영 키.
- `env_file: .env` 격리 문제의 해결(별도 결정 필요, tasks.md 참조).

## 변경 요약

- `scripts/local-services.mjs`: 사본·생성 파일·`compose.env` 제거. `readDotEnv()`로 `.env`를 한 번 읽고, OpenStack·`[local]` 값의 출처를 보고한다. 마운트 허용 목록은 `afterglow.conf`, `logs/`, `nova-pci-aliases/`와 ceph·geoip 경로(셸 > `.env` > conf 순서로 해석)다. `down`은 설정 검사 없이 `compose down`만 실행한다.
- `docker-compose.dev.yml`: `afterglow.conf`를 직접 mount하고 `lumen.env`와 정책 mount를 제거했다. `LUMEN_ENCRYPTION_KEY`는 `${LUMEN_ENCRYPTION_KEY:-${AFTERGLOW_LOCAL_ENCRYPTION_KEY:-}}`로 해석한다.
- `scripts/local-services-config.test.js`: 설정 준비 계약을 검증하는 테스트로 재작성했다.
- 문서: `docs/deployment.md`, `docs/en/deployment.md`, `ARCHITECTURE.md`, `docs/architecture.md`, `docs/agent-development-guide.md`, `docs/openstack-service-catalog.md`, `afterglow.conf.example`, `CHANGELOG.md`, `.gitignore`, `.dockerignore`.
- `.env`: 기존 생성 키 3개를 값 출력 없이 추가했다. `.env` 권한은 0600이다.
