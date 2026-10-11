## Implementation Tasks

- [x] 기존 관리자 네트워크 목록·프로젝트 이름 조회·서브넷 IP/DHCP 조회와 디자인·인가 경계를 확인한다.
- [x] 관리자 네트워크 목록에 유형 필터·이름/ID/프로젝트/유형 검색·소유 프로젝트 표시와 실패/초기화/결과 수를 구현한다.
- [x] 서브넷 API에 정확한 IPv4/IPv6 풀 전체·사용·예약·잔여 집계와 연결 대상 이름·조회 한계를 구현한다.
- [x] 네트워크 서브넷 카드 및 독립 서브넷 상세에 공통 IP 조사 UI를 연결하고 인증/대상 전환·조회 실패·네 locale을 처리한다.
- [x] 관련 동작 회귀·진단·현지화 검사 및 프로젝트 게이트를 실행하고 정확한 결과를 기록한다.
- [x] 변경 소스의 canonical 다중 아키텍처 컨테이너를 빌드·실행하고 실제 HTTP 및 Chromium의 필터/소유자/할당량/실패/반응형/테마/네 locale을 검증한다.

## Verification and scope

- `docs/testing.md`의2026-10-11 local-only network receipt에 전체 결과·중간 실패와 환경 수정·운영 한계를 기록했다. Frozen dev +42 source/test 경로의 `1.30.11` snapshot이며 공유 MCP/migration checkpoint·index·review marker는 보존했다.
- `npm run test:gate` exit0: backend4,444, frontend339files/2,603, contract154, disposable functional35/9deselected, Ruff check/format560files. Working digest는 `4426f9d748dd38a7cce8e48f27f35518e744604414461a7eabe2c4a2b01ac6c1`/2,540files다. PowerShell36skip과 기존 경고는 기록했다.
- 동일 digest/2,540files의 별도 임시 index에서 architecture `--staged`도 성공했으며 `architecture-qualification.json`에 기록했다. 두 실제 index와 공유 review marker는 보존했다. Rapid schema의 proposal/tasks가 완료되어 delta spec 없이 CLI archive했다.
- Final frontend Svelte check2,350files/0errors/기존 warning1, i18n check0errors/0warnings·37namespaces/9,482messages, i18n scan991files/0Korean lines, production build exit0. Focused backend212와 frontend54개 통과.
- Canonical arm64/amd64 API·frontend 및 worker crypto smoke, 설치된 SDK→합성 cloud HTTP 각12조건, Chromium16동작 기록과3표면/4locale/2theme/6폭144조건에서 document/value overflow0. No native admin403/Neutron reads0 및 provider resource mutation0. Worker 실제 Notion sync와 live cloud/IAM·배포는 미검증이다.
- Durable proof: `/Users/pieroot/.local/share/afterglow-proofs/network-ip-visibility-20261010/`의 JSON·로그·screenshot. `ARCHITECTURE.md`, `docs/api/admin.md`, `docs/testing.md`, `CHANGELOG.md`를 갱신했다. 운영 설정·키·데이터·IAM/리소스 변경 및 운영 배포는 수행하지 않았다.
