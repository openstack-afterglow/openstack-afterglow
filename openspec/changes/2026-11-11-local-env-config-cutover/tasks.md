# 작업 체크리스트

## 구현

- [x] `.local-services/` 사본, `secrets.json`, `lumen.env`, `compose.env`, 정책 mount 제거
- [x] 루트 `afterglow.conf`를 compose가 직접 mount, 로그·nova 별칭을 루트 `logs/`·`nova-pci-aliases/`로 이동
- [x] 기존 생성 키 3개를 값 출력 없이 `.env`로 이전하고, Lumen 암호화 키가 기존 키와 같음을 해시로 확인
- [x] `[local]`·OpenStack 값의 우선순위 셸 > `.env` > conf, 출처만 출력
- [x] `LUMEN_ENCRYPTION_KEY` 우선 해석과 `AFTERGLOW_LOCAL_ENCRYPTION_KEY` fallback
- [x] ceph·geoip 마운트 허용 목록을 셸 > `.env` > conf 순서로 해석

## 검증

- [x] `node --test scripts/local-services-config.test.js`: 13 pass, 1 todo(아래 열린 결정)
- [x] 실제 `.env`와 `afterglow.conf`로 `services:config` 통과(출처만 출력)
- [x] `check_architecture.py --stamp` 후 `--staged` 통과
- [ ] `npm run services:up`으로 전체 스택 기동 및 non-root 컨테이너의 루트 `afterglow.conf` 읽기 확인 — 미실행
- [ ] `npm run test:gate` — 미실행

## 열린 결정

- [ ] `env_file: .env` 격리: 모든 서비스가 `.env` 전체를 컨테이너 환경에 받는다. 선택지: (a) 서비스별 `env_file` 제거 후 필요한 키를 `environment:`에 명시, (b) 개발 전용 노출을 수용하고 문서화. 테스트 `the Lumen encryption key does not reach non-Lumen containers`는 todo로 남아 있다.

## 완료 후

- [ ] 위 미체크 항목과 열린 결정이 끝난 뒤에만 `openspec/changes/archive/`로 이동
