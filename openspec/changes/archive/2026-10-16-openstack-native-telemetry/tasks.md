## Implementation Tasks

- [x] 기존 instance/system/project monitoring 소비자와 권한·캐시 경계 및 현대 Ceilometer/Gnocchi의 meter 의미를 조사한다.
- [x] Caller-scoped Keystone catalog discovery와 bounded native Gnocchi reader, resource ownership, 단위·counter rate·가용성 처리를 구현한다.
- [x] Instance 시계열·summary·list badge를 native-first와 지표별 기존 exporter fallback으로 통합한다.
- [x] Project dashboard와 관리자 system/resource monitoring에 native 실제 관측과 상세 측정값을 통합하고 기존 inventory/할당/호스트 도달성 의미를 보존한다.
- [x] UI·mock transport·API 호출자를 source/unit/status와 monitoring_available 계약으로 함께 이행하며 native 부재·부분 실패도 기존 모니터링을 유지한다.
- [x] 경계·단위·counter reset·프로젝트 격리 회귀와 실제 SDK/session HTTP→API 및 브라우저 변경 경로를 검증한다.
- [x] 문서·changelog·architecture 및 local/live 증거 경계를 갱신하고 OpenSpec을 archive한다.

완료 범위는 local source·합성 provider/identity 경계다. 상세 결과는 `verification.json`과 `docs/testing.md`를 따른다. 전체 gate의 변경 밖 storage11/domain-auth3 실패, frontend check의 변경 밖 PageState1error를 숨기지 않는다. 운영 수집 서비스 설치·정책 변경·live OpenStack 수용·배포·release는 이 change의 완료 조건이 아니다.
