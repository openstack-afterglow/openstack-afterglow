# Changelog

이 프로젝트의 모든 주요 변경사항은 이 파일에 기록됩니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 을 따르며,
프로젝트는 [SemVer](https://semver.org/lang/ko/) 2.0.0 을 따릅니다.

## [Unreleased]

### Added
- **프론트엔드 4개 언어·번역 참여** — 한국어를 기본·원문으로 영어, 일본어, 중국어 간체를 동일 키의 기능별 JSON 카탈로그에 대응한다. 공개·로그인·콘솔 언어 선택은 쿠키·SSR HTML lang에 반영하며 날짜·숫자와 CJK 글꼴도 선택 언어를 따른다. 원어민은 UI 코드 변경 없이 CSV/JSON으로 번역·검수할 수 있고 키·변수·태그 중첩·한글 잔존 검사 및 한국어 원문 해시의 검수 상태를 제공한다. 잘못된 CSV나 읽을 수 없는 카탈로그·검수 JSON은 쓰기 전에 거부한다. 좁은 화면의 번역문·표 스크롤과 xterm 접근성 이름·알림을 처리하며 전역 터미널 버퍼는 유지한다. 초기 번역은 초안이며 backend 오류·사용자 데이터·운영자 작성 문구는 번역하지 않는다. 언어 전환은 페이지를 다시 mount하므로 저장하지 않은 폼은 초기화될 수 있다.
- **독립 서비스 실제 로직 검증** — dev Compose의 `services:config/up -- --only lumen,waygate,palimpsest`와 수동 URL·API key/Keystone token의 `services:verify`를 추가한다. BFF mock·datastore-only·synthetic UI와 실제 API/worker 실행을 분리한다. 기본은 인증 조회이며 `--exercise`에서 Lumen native journal/history/usage, Waygate 소유 disposable server의 client 설정·encrypted migration·정리, Palimpsest 실제 SquashFS upload/download·선택 OCI bundle·정리를 검사한다. 선택하지 않은 callback/readiness는 요구하지 않으며 Waygate 자체 startup callback·권한·실패 정책은 보존한다.
  - 검증: Lumen 실제 Docker API/worker·MariaDB/Redis에서 fake provider의 11개 journal event·history·15-token ledger 대조, Hub native source·격리 MariaDB·genuine Keystone에서 실제 SquashFS 두 chunk·OCI bundle·등록 정리, Waygate native source·genuine Keystone에서 인증 조회와 ID 미설정 mutation 차단, orchestration 106개 통과. Waygate 전체 client 시나리오는 전용 ACTIVE source/target 부재로 미검증이며 Docker Hub→Keystone TCP timeout·외부 provider·VM/data plane·운영 배포·전체 gate도 통과로 기록하지 않는다.
- **인스턴스 인터페이스 보안 그룹 합집합** — 보안 그룹 바로 아래에서 인바운드·아웃바운드의 IP 버전, 프로토콜, 포트/ICMP 유형·코드와 출발지/대상을 확인한다. 적용 그룹의 중복 및 같은 대상의 겹치거나 연속된 TCP/UDP/SCTP 포트를 합치고, 다른 인터페이스·CIDR·원격 그룹은 섞지 않는다. 조회 오류/누락 시 불완전한 정책을 숨기며 SG 응답의 포트별 적용 ID를 우선한다. 일반 silent polling은 표·오류 상태를 보존하며 저장 후 브라우저에서 독립 조회한다. 합성 identity/API의 실제 Chromium에서 저장 전후·지연된 이전 응답·오류·누락·dark/light 390–1440px 내부 표 스크롤을 확인했다. 보안 그룹 허용 정책이며 실제 접속이나 운영 배포·Neutron 변경을 검증한 것은 아니다.
  - 최초 frontend 변경은 브라우저 broker만 수정했다. 후속 공통 cache 무효화는 같은 프로세스·event loop의 이전 flight 분리·재저장을 차단하지만 다른 worker와 규칙 CRUD의 인스턴스별 SG cache는 별도 한계다. 실제 Neutron snapshot의 즉시 최신성을 보장하지 않는다. 당시 관련 frontend 95 tests는 통과했으나 전체 check는 Sidebar/AdminSidebar 테스트의 `exact` 옵션 오류 40건으로 실패했다.
- **ProxySQL 모니터링** — 관리자 모니터링 메뉴와 명령 팔레트에 ProxySQL을 추가하고 기존 `ProxySQL — MariaDB 접속 경로` Grafana 대시보드(`afterglow-proxysql`)를 연결한다. MySQL은 유지하며 TOML·환경 변수·Kubernetes/Helm에서 ProxySQL UID를 지정할 수 있다. 새 exporter나 대시보드를 생성하지 않는다.
  - 검증: 격리된 canonical Compose 설정과 실제 Chromium에서 운영 Grafana의 실제 패널·그래프, MySQL 보존, 공유 메뉴·명령 팔레트 및 390–1440px breakpoint 화면을 확인했다. arm64/amd64 빌드·실행 및 관련 API/config·디자인 검사는 통과했다. 필수 gate의 docs·unit·contract·functional 단계는 통과했으며 마지막 backend format 검사에서 변경 범위 밖의 3개 파일이 실패해 전체 gate는 통과하지 못했다. Afterglow identity만 합성이며 운영 배포는 하지 않았다.
- **프로젝트·그룹 검색·필터 및 최신 생성순** — 두 관리자 목록에서 이름·전체 ID·설명을 검색하고 도메인으로 필터링한다. 프로젝트는 활성/비활성 조건을 함께 적용하며 전체 inventory를 검색·정렬한 뒤 페이지를 나누고, 검색·필터 변경 시 첫 페이지로 돌아간다. 결과 수·초기화·조건에 맞는 결과가 없는 상태를 제공하며 refresh/prefetch에 조건을 유지한다. Keystone 생성일 또는 정확한 성공 생성 이벤트로 최신순을 정하고, 기록이 없는 기존 항목은 생성일을 추정하지 않고 마지막에 표시한다. 관리자 생성 이벤트와 목록 cache 무효화를 추가했다. 실제 Chromium→격리 API/SQLite에서 검색·필터·페이지 이동·신규 최상단 표시와 dark/light 반응형 화면을 확인했으며 운영 배포·실제 Keystone 변경은 포함하지 않는다.
- **Lumen 모달리티 모델·가격 편집** — 이미지 출력 모델과 종류별 후보/등록 필터, 전용 가격 modal, text/image/audio 입력·캐시 입력·출력 독립 단가와 초·분·시간 단위를 제공한다. Unit/duration/characters/session/tokens 기준과 요청 전체 token 예약액을 구분하고 기존 JSON·단가·metadata를 보존한다. Save/reopen 및 mobile modal을 실제 component→격리 Lumen HTTP/SQLite로 확인했으며 대응 Lumen 정산 구현이 필요하다. 운영 배포·유료 provider 가격 검증은 포함하지 않는다.
- **Lumen 프로바이더 표시 설정·모델 카탈로그 순서** — 표시 이름, 외부 요청의 API provider 선택자, 실제 연결 방식을 분리하고 이름·선택자·프로바이더/모델 표시 순서를 편집한다. 등록 모델을 프로바이더별로 필터링하며 bulk 선택·삭제는 보이는 행만 대상으로 한다. 사용자 모델 선택창은 Lumen에 저장한 순서를 유지한다. Migration 021을 적용한 Lumen이 필요하며 선택자 변경 후 외부 클라이언트도 새 값을 사용해야 한다. 격리 MariaDB·실제 BFF/Lumen HTTP 및 synthetic provider 연결로 검증하며 운영 배포·실제 NVIDIA 계정 추론은 포함하지 않는다.
- **Lumen 로컬 CLI bootstrap** — API 키 연결 가이드에서 필수 전체 키·활성 공개 모델·TLS CA 설정을 구분하고 대시보드의 `/install/lumen.sh`·`/install/lumen.ps1` 다운로드 명령을 제공한다. 설치기는 private prompt, POSIX 0600 키 파일 또는 Windows CurrentUser DPAPI/private ACL, backup·marker 기반 profile 갱신을 사용한다. 기본 provider/model은 보존하며 명시적 model-only opt-in과 effective model 조건이 충족될 때만 짧은 Codex 명령을 안내한다. macOS 실제 다운로드·Linux 격리 실행과 portable PowerShell 동작을 검증했지만 Windows DPAPI/ACL 실동작, 운영 배포와 authenticated provider 호출은 검증하지 않았다.
- **Lumen image/audio/realtime Studio** — 관리자 media kind·정확 단가 편집, 프로젝트 소유 이미지 생성·편집과 canonical asset, TTS/STT 생성·전사·채팅 재생을 연결했다. 실시간 음성은 명시적 microphone 승인 뒤 Keystone-scoped admission, one-use Redis browser ticket, Origin-checked internal Lumen WS relay, PCM16 capture/재생·barge interruption·화면 자막을 사용한다. Provider key와 Lumen connect token은 browser에 노출하지 않고 scope 전환/로그아웃에서 microphone/socket/audio buffer를 정리한다. Synthetic WS, MariaDB/Redis, BFF/UI tests는 수행했지만 live provider inference와 브라우저 visual acceptance는 미검증이다.
- **관리자 하이퍼바이저 호스트 운영** — 호스트의 생존 상태와 Nova `nova-compute` 스케줄링 상태를 분리 표시하고 사유를 입력한 enable/disable을 제공한다. `up/disabled` 호스트의 전체 인스턴스 live/cold migration과 `down` 호스트의 펜싱 확인 후 evacuation은 각각 별도 확인 작업으로 제공한다. 모든 프로젝트의 VM을 페이지 끝까지 조회하고 요청·실패·건너뜀을 VM별로 표시하며, 비동기 요청을 완료로 표시하거나 `forced_down`을 자동 설정하지 않는다. 실제 운영 호스트 상태 변경·이주 성공은 아직 검증하지 않았다.
- **오디오 Studio 구간 타임스탬프 전사** — 실행 가능한 direct OpenAI `whisper-1` 모델이 capability로 광고할 때만 Lumen native STT에 `timestamp_granularities: ["segment"]`를 요청하고, provider가 반환한 시작·종료 시각만 구간 표와 TXT·SRT 다운로드로 제공한다. 지원하지 않는 모델은 사유를 표시하고 TXT만 내보내며, 요청한 구간이 빠진 응답은 추정하지 않고 실패로 처리한다. 대응 Lumen native timing 구현이 필요하다. 합성 API fixture를 쓴 실제 브라우저 검증이며 실제 provider 전사는 검증하지 않았다.

### Changed
- **1.30.1 patch 릴리스 준비와 배포 순서** — 완료된 현지화 branch를 최신 dev에 일반 통합하고 root/backend/frontend·Cloud Shell·Helm/Kolla의 버전을 일치시킨다. 정확한 dev CI 성공 뒤 불변 patch tag와 정식 image/package·latest 또는 게시된 stable alias를 검증하고, 필요한 operator package만 갱신한 후 요청한 `genconfig → pull → reconfigure -i multimode`를 실행하는 계약을 명시한다. 이 항목은 source 준비이며 tag 게시나 운영 rollout 성공을 주장하지 않는다.
- **최신 dev 현지화 갱신** — `ff007edb6e4bf75f0c0a05107ca6340b593675ff`를 `i18n`에 일반 병합하여 공용 콘솔 탐색·랜딩 미리보기, VM 용량·보안 그룹 합집합, 채팅 모델·미디어 가격·SDK 안내·Studio, 관리자 프로젝트·그룹·ProxySQL 및 Palimpsest 패키지를 네 언어에 맞춘다. 용량 fail-closed·요청 fence·안정 ID·provider prompt·API 경계는 유지하고 날짜·숫자와 접근성 이름을 현재 언어에서 계산한다. Palimpsest 페이지 언어 전환은 페이지의 일회성 secret·초안을 폐기하며 전역 chrome은 유지한다. 초기 외국어 문구는 검수 전 초안이다.
- **현재 운영 버전 Kolla 재배포 준비** — wireguardserver의 floating operator 입력을 이미 실행 중인 게시 버전(Drover0.2.25/Lumen0.5.0/Waygate0.2.0/Palimpsest client0.2.3)에 고정하고 기존 Kolla21.0.1.dev53·일반 의존성은 유지했다. 공식 installer로 누락된 stock-site import를 복원해 표준 reconfigure가 다섯 역할을 포함하게 했으며, sync 이후 연결 검증·native loadbalancer 영향·genconfig mutation·복구와 인증/데이터 선행 조건을 문서화했다. 새 dev 후보 승격이나 실제 서비스 재시작은 아니다.
  - 검증: before/after 실제 canonical CLI dispatch,110installed package compatibility, 네 sibling prechecks17host changed0/unreachable0/failed0, READ ONLY current-image ledger3/3·3/3·20/20 및 drift0. Image/start/health/restart가 동일한 ecosystem container30개와 보호 operator config67파일·inventory를 보존했다. Afterglow Manila/operator 인증·full-stock storage 복구와 실제 genconfig/reconfigure acceptance는 미완료다.
- **Palimpsest 프로젝트 패키지 경계 문서화** — `/palimpsest/packages`의 프로젝트 비공개 inventory, `xl` 이상 short-digest 표/그 아래 카드, 상세·이력·인증 다운로드와 Hub `package_authority` 기반 불변 참조 복사를 명시한다. 명시적 namespace 등록은 `packages_write`, 키 발급·목록·폐기는 본인 소유에 한정하며 일회성 secret 폐기와 프로젝트 전환/늦은 응답 fence를 설명한다. Browser package BFF의 원본 JWT/session project·user 정확 일치와 Keystone token 보존(교환·rescope·세션 scope 재작성 없음), native `ppk_v1_` gateway의 경로 allowlist·자격 혼용 거부·streaming·no redirects·no-store를 분리한다. 두 package transport는 설정된 trusted internal Hub URL만 사용하고 누락은 503이며 catalog/admin discovery fallback이 없다. 읽기 쉬운 namespace의 Hub 운영자 UUID 바인딩과 public origin authority를 내부 URL과 구분한다.
- **공개 소개 페이지 기능 설명 모션** — 첫 화면은 짧은 두 줄 메시지와 직접 실행하는 `연구 환경 구성 미리보기`다. 미리보기는 콘솔 창 형태로 요청·정책 확인·자원 배정·재사용 패널이 단계마다 하나씩 바뀐다.
  - 요청 항목 확인 → 쿼터 막대가 요청량만큼 참 → 시나리오별 자원 생성(GPU VM과 네트워크·공유 데이터 연결, 클러스터 노드와 Pod 배치, 공유 공간과 mount 3개) → 레이어·템플릿·스냅샷 저장 순서다.
  - 대기 패널은 만들어질 객체를 점선으로 미리 보여준다. 이전의 흐린 등각 그림, 겹치던 클러스터 서버, `√`로 보이던 완료 표시를 없앴다.
  - 하나의 버튼으로 시작·일시정지·계속·다시 체험한다. 시나리오가 바뀌어도 높이가 같고, 실제 자원·API를 호출하지 않는 예시임을 표시한다.
  - 신청→배정→관측→재사용 스토리는 구성원·VM·네트워크·공유 데이터가 계속 유지되는 하나의 장면에서 단계별 상세(요청 항목, 쿼터, 지표·활동 기록, 불변 레이어 분기)만 겹침 없이 바뀐다. Desktop에서는 읽는 위치가 단계를 고르고, mobile/tablet/짧은 화면/모션 감소에서는 단계 버튼과 전체 설명을 제공한다.
  - 스크롤에 따른 이동·확대와 `gsap` 의존성은 제거했다.
  - 제품 화면 미리보기는 아이콘 확대 그림 대신 프로젝트 개요·클러스터·네트워크 토폴로지 콘솔 축약 화면을 보여준다. 기능 그림의 글자는 디자인 글꼴로 렌더링한다.
  - 기능 카드에서 해당 워크플로우 필터로 이동하며, touch 기기에는 밀어 올림 안내를 표시한다.
  - 검증
    - 전체 frontend 276 files/1,892 tests+실행 로그 9, Svelte check 2,130 files 0 errors/0 warnings, production build를 통과했다. `bun install --frozen-lockfile`을 포함한 arm64·amd64 frontend 이미지를 격리 Compose project(`127.0.0.1:3089`)에서 healthy로 실행해 같은 브라우저 smoke를 확인한 뒤 제거했다.
    - 삭제했던 공개 페이지 행동 테스트(건너뛰기 포커스, 모든 콘솔 목적지, brand·footer, raster 부재)와 landing AA 가드를 복원했다.
    - 실제 Chromium에서 전후를 같은 조건으로 녹화해 비교했다(`~/.gstack/projects/afterglow/designs/landing-motion-audit-20261002/compare-*.png`). 확인한 항목: 세 시나리오 단계 전이, 키보드 시작·정지·재개와 focus 유지, 양방향 scroll 단계, dark/light, reduced-motion, 320–1920px와 200% zoom 등가 화면의 가로 넘침 0·12px·44px.
    - 운영 배포·Firefox/Safari·backend gate는 수행하지 않았다.
- **플레이버 호스트 용량 세부 정보 관리자 전용** — 호스트별 VM 최대 CPU·RAM, 후보 호스트 수, NUMA·GPU 근접성 및 Nova snapshot 설명을 관리자 VM wizard에서만 표시한다. 소비자 화면은 관리자 계정으로 사용해도 세부 정보를 렌더링하지 않으며, 플레이버 규격·프로젝트 쿼터·생성 가능/불가·차단 사유와 갱신 기능을 유지한다. 기존 서버 용량 검증과 미확인 차단 계약은 바뀌지 않는다.
  - 검증: selector 14·instances target backend 377/frontend 100·전체 frontend 1,862 tests+로그 runner 9·Svelte check 0 errors/0 warnings 통과. 로컬 arm64 frontend 반영 후 합성 identity/API의 Chromium에서 소비자·관리자 및 관리자 계정의 소비자 모드, 선택·생성 불가 항목, 390–1440px 카드/행과 가로 넘침 0을 확인했다. amd64 이미지 빌드·실행도 확인했다. 실제 VM 생성·운영 배포는 하지 않았다.
- **인스턴스 적용된 허용 규칙 접기/펼치기** — `허용 규칙 (합집합)` 표시명을 `적용된 허용 규칙`으로 바꾸고 인바운드·아웃바운드 표를 기본 접힘으로 제공한다. 방향·인터페이스별로 독립 조작하며 포트 순서 변경에도 펼침 상태를 보존한다. 로딩·오류·누락 안내는 접혀 있어도 숨기지 않는다. 기존 규칙 계산·저장·polling·API 계약은 유지한다.
  - 검증: 관련 frontend 13 files/97 tests와 전체 Svelte check 2127 files/0 errors/0 warnings 통과. 합성 identity/API의 실제 Chromium에서 마우스·Enter/Space, 390·768·1440px 버튼·표와 dark/light·오류 표시를 확인했다. 운영 배포·실제 Neutron 검증은 하지 않았다.
- **콘솔 서비스 메뉴 아이콘 rail** — 세부 사이드바는 사라지거나 프로젝트 오른쪽에 복원 버튼을 만들지 않고 56px 아이콘 rail로 접힌다. 최상단의 같은 버튼으로 펼치며 목적지별 SVG·tooltip·현재 선택·keyboard focus·프로젝트·모드를 유지한다. Workspace·panel·dock은 240px/56px/0 경계를 공유한다. Header 열기/drawer 닫기와 로고를 정렬하고, 중복 현재 페이지/전체 메뉴 항목을 제거했다. 토폴로지는 활동 바로 아래로, 프로젝트 설정은 기존 프로젝트 popup으로 한정한다.
  - 검증: 최종 arm64 canonical frontend(`sha256:bac03fad…`, env/mount/group 보존)와 amd64 build의 container 안 `linux/x64` `/health` 200을 확인했다. Backend의 Keystone `172.30.0.253:5000` 연결 timeout으로 재로그인이 불가해, 최종 build는 내장 튜토리얼·관리자 미리보기의 Chromium에서 검증했다. User/admin 14개 폭에서 56px rail·44px 목적지·focus·Enter/Space를 확인했다. 800×300에서는 전역 scrollbar 세로 스크롤과 가로 넘침 0, rail 이동 시 상태 유지, 240/56/0 panel 경계와 저장 폭 보존을 확인했다. 실제 인증 admin 확인은 scrollbar 수정 전 build의 1440px 기본 동작까지다. Navigation 66 tests, Svelte check 0 errors, backend 3453·contract 133·functional 28은 통과했다. 동시 작업의 landing typography 2 tests와 Palimpsest packages backend Ruff check 실패로 gate는 실패다. 운영 배포는 하지 않았다.
- **콘솔 전역 메뉴·서비스 사이드바 분리** — 전체 폭 header에서 로고 옆 세로선·Admin badge·페이지 경로를 제거한다. 모든 화면의 햄버거는 전체 메뉴 drawer를 열고, 세부 페이지는 소속 서비스 항목과 페이지 이름을 왼쪽 상단에 표시한다. Sidebar 숨김·복원이 workspace와 panel/dock 경계를 함께 바꾸며 모바일은 drawer 상단에 페이지 문맥을 표시한다. 기존 목적지·서비스/beta/권한·프로젝트·모드·중앙 검색·Cloud Shell 승인 조건을 보존한다. 숨겨진 responsive footer의 Tab 대상과 tablet panel 경계 회귀도 수정했다.
  - 검증: 실제 인증된 user/admin의 320–1920px·dark/light, direct/nested route, modal focus·dismissal, sidebar 숨김·복원, 실제 volume 검색·프로젝트 popup을 확인했다. 800px panel 경계와 저장 선호 폭 보존, non-session dock CSS geometry, 승인 취소 ticket POST 0, arm64/amd64 build·runtime와 Compose env/mount 보존을 확인했다. 전체 unit/contract/functional tests와 타입검사는 통과했지만, 수정하지 않은 backend 3개 파일의 Ruff format check로 `test:gate`는 실패했다. Cloud Shell 생성·운영 배포는 하지 않았다.
- **콘솔 헤더 배치** — Cloud Shell을 우측 기존 프로젝트 선택 자리로, 프로젝트 선택을 좌상단 로고 오른쪽으로 옮겼다. 리소스 검색은 사이드바를 포함한 전체 화면 중앙에 고정하며 좁은 desktop에서 폭을 줄인다. 프로젝트 이름은 아이콘을 유지한 채 말줄임하고 기존 서비스 capability·desktop-only·승인 조건과 mobile/tablet 진입점은 유지한다.
  - 검증: 실제 인증된 user/admin Chromium의 320–1920px 범위와 breakpoint 경계에서 중앙 정렬·비중첩·48px header를 확인했다. 프로젝트 dropdown·실제 볼륨 검색·Cloud Shell 승인 취소(ticket POST 0), dark/light와 arm64/amd64 이미지 빌드·runtime 실행, 로컬 Compose healthy·env/mount 보존을 확인했다. Cloud Shell 생성 재시도·운영 배포는 하지 않았다.
- **관리자 메뉴 기능별 재분류** — 별도 서비스 그룹을 제거한다. Drover·클러스터 템플릿은 컨테이너, Lumen·채팅 통계·사용자 쿼터·모델 설정·도구 설정은 Lumen, Waygate는 네트워크에 배치하고 Palimpsest는 독립 최상위 링크로 제공한다. 모바일 드로어와 명령 팔레트도 같은 분류를 쓰며 기존 URL·서비스 표시 조건·권한·사용자 메뉴는 유지한다. 탐색 회귀 38개와 Svelte 검사가 통과했고 실제 컴포넌트의 합성 인증/route store Chromium에서 390–1440px 화면과 이동을 확인했다. 운영 배포는 하지 않았다.
- **VM 생성용 동일 호스트 용량 선택** — 고정 flavor 규격은 유지하고, VM 생성 wizard에서만(`capacity=create`) 프로젝트 쿼터와 같은 eligible compute의 CPU·RAM·GPU 교집합으로 선택을 제한한다. 표시값은 한 호스트에서 VM 하나가 받을 수 있는 최대치(`min(잔여, max_unit)`)다. 예를 들어 VCPU 24×ratio 2.0 호스트는 36이 남아도 VM 하나는 24까지다. 물리 코어를 임의로 절반 계산하지 않는다. 사용자·관리자 목록과 sync/SSE 제출은 같은 판정을 쓰며, 확인된 부족은 409, 용량을 확인하지 못하면 flavor 종류와 무관하게 503으로 mutation 전에 차단한다.
  - 미확인 용량은 GPU 여부와 무관하게 `호스트 용량 확인 불가`로 생성할 수 없다. 운영자 인증·Placement 장애나 기본 compute AZ 정책(`nova.default_compute_availability_zone`) 누락 동안에는 wizard·API로 VM을 생성할 수 없다. 로컬 DMSLAB은 이 정책이 비어 있어 CPU flavor 21개가 모두 `호스트 용량 미확인`으로 선택 가능했다. 그중 어떤 호스트에도 들어가지 않는 `cpu.16c_128g`도 있었다. 기본 `/api/v1/flavors`는 쿼터만 판정하므로 K3s·Drover 선택지는 바뀌지 않는다.
  - 단일 NUMA 셀 flavor(`hw:numa_nodes=1`, `hw:mem_page_size=small|any`)는 호스트 합계로 판정한다. 합계 부족은 차단하고 합계 적합은 허용한다. `NUMA 셀·GPU 근접성 미확인 · Nova 최종 확인` 진단은 관리자 VM wizard에서만 표시하고, 소비자 화면은 선택 가능 여부만 반영한다. 다중 셀·hugepage pool 정책은 `확인 불가`다.
  - `capabilities:cpu_info:*`를 hypervisor 정보로 판정한다. alias 없이 이름만 등록된 GPU HDMI audio function을 `<chip>-audio` flavor alias에 매핑하고, GA104/GA106 audio 기본 항목을 추가해 GPU inventory에서 GPU로 세지 않는다.
  - 운영자 세션을 재사용한다. 명시적 요청은 5초 timeout·재시도 없이 내부 15초 deadline을 사용하고 caller 대기는 20초로 제한한다. Placement는 flavor shape마다 한 번 조회하고 목록은 10초 single-flight snapshot을 공유한다. 실패 shape를 캐시해 조회와 traceback 반복을 막는다.
  - 운영 읽기 전용 전체 79 flavor 측정: 27.0초 → cold 4.4초. 일반 프로젝트의 가시 catalog 재구성 후 fresh 6회 중앙값은 private-heavy 목록 2.90초·단일 GPU admission 0.45초, public-only 목록 0.77초다. TTL 내 warm은 HTTP 0회이며 15초 폴링의 steady 지연은 아니다. 목록·쿼터 endpoint 전체 지연이나 p95 검증으로 확대하지 않는다. 미확인 flavor는 76개에서 6개(Placement에 없는 GTX TITAN X)로 줄었다.
  - Wizard는 자동 갱신 중에도 선택과 Next를 잠그지 않는다. 테스트는 선택 후 실제 2단계로 돌아가 Next 가능 상태를 확인한다. 수동·제출 직전 확인과 늦은 응답 fence는 유지한다. CPU-only 부족 문구는 GPU를 포함하지 않으며 카드/행·선택 경고·상세에 같은 구분을 적용한다.
  - 운영 flavor/설정 변경, GPU VM 생성, 배포는 하지 않았다.
- **Lumen 외부 CLI 연결 안내** — API 키 설정에서 Lumen compat discovery의 공개 주소로 Codex Responses와 Claude Code Anthropic API 설정을 생성한다. 일반 Lumen API 키 전체 값은 셸의 숨김 입력으로 받고 복사되는 설정·명령에 포함하지 않으며, 활성 공개 모델 ID와 중복 ID의 provider 선택만 별도로 안내한다. 원격 Claude Code의 실제 text/Bash tool 연속 실행은 확인했지만 이 UI의 운영 배포·사용자 브라우저 연결 성공으로 대체하지 않는다.
- **볼륨·DB 백업 사용자 동선 상시 노출** — 기존 Cinder 볼륨 백업과 Trove DB 백업의 목록·생성·복원·자동 백업을 브라우저별 베타 설정에서 분리했다. 예전 `false` 값이 남아도 탐색 메뉴와 직접 경로에서 사용할 수 있으며 볼륨 백업 목록은 프로젝트 전환 시 늦은 응답을 폐기한다. File Storage는 별개다. 운영 Manila의 실험적 share-backup API는 확인했으나 독립 백업 저장소·데이터 노드 mount 설정이 없어 실제 복원이 가능한 백업 기능은 아직 제공하지 않는다. 스냅샷은 백업으로 표시하지 않는다.
- **볼륨 상세 작업 메뉴 일치** — 목록 패널과 단독 볼륨 상세에서 목록과 같은 상태·관리자 조건으로 VM 부팅, 확장, 스냅샷, 백업, 이전 및 강제 삭제를 연다. 기존 모달과 VM 마법사를 사용하며 성공한 변경 뒤 열린 상세·목록을 갱신한다. 연결된 볼륨의 일반 삭제는 차단한다.
- **이미지·오디오 Studio 화면 재구성** — 이미지 Studio는 중앙 프롬프트 입력창, capability 기반 옵션 행, 첨부·단일 제출 작업 행과 로컬 원본 스타일 썸네일을 제공한다. 스타일은 제출 프롬프트 끝의 보이는 지시문으로만 전달한다. 오디오 Studio는 `텍스트 → 음성`/`음성 → 텍스트` 탭, 모델 capability의 목소리·형식 선택, 생성 음성 재생·다운로드, 업로드 원본 미리듣기를 제공하고 상단 경로를 `LUMEN / 오디오`로 표시한다. 모델 준비·가격 확인, 프로젝트 범위, idempotency, 취소·기록과 검사된 asset 경로는 유지하며 비디오 생성은 추가하지 않았다.
- **이미지 Studio 자동 요청** — 수동 생성/수정 선택을 제거하고 `이미지 만들기`로 통합했다. 첨부가 없으면 생성 API, 첨부가 있으면 이미지와 프롬프트를 입력 이미지 API로 보내 참고 생성/수정을 모델이 처리한다. 업로드 실패·모델 입력 거부 후 첨부를 보존하고 이미지 없는 생성으로 자동 재시도하지 않으며, 명시적 제거만 text-to-image로 전환한다. 직접 API의 명시적인 생성/편집·인가·과금 계약은 변경하지 않았다. 로컬 Compose frontend 및 합성 Chromium 요청·결과·오류·dark/light 반응형을 검증했지만 실제 provider 추론·품질과 운영 배포는 포함하지 않는다.
- **기본 브랜딩 SVG 전환·여백 보정** — 로그인·랜딩·사용자/관리자 sidebar·favicon과 frontend/backend/setup/Kubernetes/Helm/Kolla 기본값을 supplied SVG로 교체했다. Wordmark는 bundled Pretendard Latin outline으로 고정하고 실제 도형의 좌우·상하 여백을 36으로 맞췄다. 로그인은 비율·중앙 정렬을 유지하고 앱 테마에 맞는 글자 색을 표시한다. 업로드된 raster 로고와 custom 설정·reset 우선순위, third-party 로고는 유지하며 구형 bundled PNG/ICO·RingMark·전용 gradient는 제거했다. 구형 경로를 명시한 외부 설정은 새 이미지와 함께 이관해야 한다.
  - 검증: Chromium 반응형·앱/OS 반대 dark/light scheme·관리자 합성 upload/reset 확인, 현행 로컬 Compose backend/frontend healthy와 실제 public config·로그인·랜딩·favicon decode 확인, SVG source/image SHA 일치, arm64·amd64 빌드/실행 및 `test:all` 통과. 운영 배포, live 관리자 인증/업로드 브라우저 검증, Firefox/Safari는 포함하지 않는다.
- **Cloud Shell 전용 프로젝트 기본 네트워크·보안 그룹·public endpoint** — `interface` 기본값을 `public`으로 바꿨다. `network_id`를 비우면 전용 Cloud Shell 프로젝트의 DB default → 관리자 지정 외부망을 쓰는 자동 생성 → 자동 생성 비활성 시 shared 정책 순서로 외부 연결 가능한 네트워크를 선택한다. `security_group` 기본값은 전용 프로젝트의 `default` 그룹이며 ID 우선·이름 차선으로 하나의 exact ID를 확정하고 기존 규칙을 유지한다(egress-only 아님). 다른 프로젝트 소유·모호한 그룹·외부 연결 없는 네트워크는 홈 생성 전에 거부한다. Backend·예시·K8s generator/Helm·Kolla precheck가 같은 계약을 렌더하며, Kolla precheck는 그룹을 전용 프로젝트 안에서만 찾고 ingress-free 검사를 제거했다.
  - 검증: 실제 DMSLab cloud_shell 프로젝트에서 `Default` 네트워크·라우터 자동 생성과 default SG 확정을 확인했다. 로컬 Compose backend/frontend/notion-worker 재생성 뒤 실제 public capability와 desktop trigger·승인·취소·1023px 숨김을 Chromium으로 확인했다(인증 API만 합성). amd64 빌드를 확인했고 운영 배포는 하지 않았다.

### Fixed
- **Notion worker 정상 종료** — Docker PID 1에서 SIGTERM을 무시해 stop timeout 뒤 강제 종료(exit137)되던 오류를 수정했다. 기존 Waygate의 signal runner 패턴으로 SIGTERM/SIGINT를 task cancellation에 연결하고 스케줄러·DB engine을 정리한다. 초기 대기·동기화 주기와 fail-closed 정책은 유지한다. Canonical arm64·amd64 이미지의 기본 CMD에서 첫 fail-closed 사이클 뒤 SIGTERM과 초기 대기 중 SIGTERM/SIGINT가 모두 exit0·0.4초 미만으로 종료했다. 외부 Notion/OpenStack 동기화나 운영 rollout 성공으로 해석하지 않는다.
- **언어 변경 중 live 터미널 보존** — dashboard/admin 페이지의 locale key가 열린 컨테이너 터미널·k3s 셸을 파괴해 socket과 scrollback을 잃던 회귀를 수정했다. 터미널 host 네 경로는 route key로 수명을 유지하며 일반 페이지의 locale remount와 auth/project 경계는 바꾸지 않는다. 실제 Chromium·xterm·격리 loopback WebSocket에서 네 언어의 접근성 이름 갱신, 같은 세션·버퍼·입출력 유지와 정상 navigation cleanup을 확인했다. 합성 identity/transport 검증이며 live Keystone·Zun·Kubernetes acceptance는 아니다.
- **Kolla 비대칭 controller 이미지 선택** — 세 Palimpsest API와 한 worker처럼 controller별 활성 component가 다른 구성을 동일 flag 검사로 거부하던 오류를 수정했다. 활성 published-mode 서비스 consumer만 합집합에 참여하며 각 host의 effective image/ref·namespace/tag와 later-only rollback pin을 보존한다. 상충 입력은 registry·credential 접근 전에 거부하고 locally enabled consumer에만 frozen digest를 전달한다. 실제 Kolla CLI에서 수정 전 12개 새 소비자 회귀가 실패했고 최종 contract26·resolver11·native runtime41이 통과했다. Serial·`--limit`·channel 이동·extra-var·source/disabled 경계는 유지하며 운영 genconfig/pull/reconfigure 증거는 아니다.
- **Mermaid SVG label 보존** — Mermaid의 root `htmlLabels: false`로 native SVG text를 사용해 기존 SVG-only sanitizer가 HTML label을 제거하던 결함을 수정한다. `securityLevel: strict`, `foreignObject`·event-handler 차단을 완화하지 않는다. Baseline와 dependency-patched compiled frontend의 Chromium에서 빈 label을 재현했으며 provider/API 계약은 바꾸지 않는다.
- **Inherited dependency 보안 갱신** — Backend에 PyJWT2.15.0·AnyIO4.14.2·urllib32.8.0·AsyncSSH2.24.0·pypdf6.19.0의 patched floor/lock을 요구한다. Frontend는 devalue5.9.3·DOMPurify3.4.16·smol-toml1.7.1·Vitest/coverage4.1.11부터 사용하며 Bun·npm graph와 root version을 일치시킨다. OpenStack CLI와 Kolla operator urllib3도2.8.0 floor를 적용하되 기존 service/Kolla source pin·운영 환경을 바꾸지 않는다. 단일HS256·TLS verify/CA·project/endpoint·markdown sanitizer 경계는 유지하고 unrelated dependency를 일괄 upgrade하지 않는다.
- **Palimpsest native 인증 경계** — 일반 JWT Hub catch-all의 native project/key/cache 진입을 token exchange·rescope 전에 차단하고 기존 legacy family·export ticket은 유지한다. Package key의 단일 project assertion을 Hub로 그대로 전달하고 중복은 거부한다. Native TLS는 설정된 CA로 검증하며 OpenStack insecure 설정으로 끄지 않고 초기화·transport 오류를 안전한 503으로 처리한다.
- **Mutation 이후 cache freshness** — 같은 프로세스·event loop의 invalidate는 이전 single-flight chain의 합류·재저장·삭제 권한을 fence하여 관리자 project CRUD 뒤 이전 inventory가 다시 cache되는 경합을 막는다. 기존 origin 호출자는 취소하지 않으며 분산 worker/direct writer의 일관성까지 보장하지 않는다.
- **프로젝트 전환 수명** — 공유 전환 상태로 drawer remount 후 동시 rescope를 막고, 로그아웃·identity 전환을 거친 이전 응답이 새 로그인에 적용되지 않게 한다. 동일 identity JWT refresh는 허용한다. 사용자 tutorial에는 fixture가 없는 native Palimpsest 메뉴를 노출하지 않는다.
- **Nova 용량 투영 경계** — PCI count를 numbered-group 한도 16과 list 할당 전에 비교하여 과도한 메모리 할당을 막고 aggregate의 쉼표 구분 metadata를 Nova와 같은 후보 값으로 비교한다.
- **Lumen 채팅 실패 진단** — 대시보드 모델 목록 실패에 HTTP 상태를, 채팅 접수 실패에 HTTP 상태와 제한된 안전 detail을, 접수 후 durable 실행 실패에 오류 코드·안전 메시지·run ID를 표시한다. API-key 기반 Codex Responses 성공과 Keystone native run 성공은 별개로 취급하며 운영 OpenAI provider 추론은 독립 검증한다.
- **볼륨 상세 일관성 및 이름 변경** — 볼륨 목록 작업 메뉴와 상세 화면에서 소유 볼륨의 이름을 변경한다(`in-use` 포함). 목록 패널과 전체화면 상세가 동일한 컴포넌트·데이터·작업을 사용하고, 연결된 인스턴스의 프로젝트별 실제 이름과 UUID를 표시한다. 이름 조회 실패는 명시적 UUID 대체로 남기고 폴링 오류에는 이미 표시한 볼륨 정보를 유지한다. 실제 운영 Cinder 이름 변경은 수행하지 않았다.
- **Waygate 목록 폴링 및 클라이언트 발급** — 서버·클라이언트·연결/프로젝트 네트워크 조회가 반복될 때 이미 표시한 목록을 지우지 않고 ID별 실제 변경분만 반영한다. 빈 목록·오류 후 재시도·수동 갱신에서도 초기 skeleton으로 되돌아가지 않으며 트래픽의 보고 지연 판정과 프로젝트/서버 격리는 유지한다. 클라이언트 발급 POST에서 상속 플래그를 생략해 이를 거부하는 기존 배포 API의 `422`를 방지하고, DNS·keepalive 명시 override는 보존한다. 기존 서비스의 동적 상속 및 PATCH 호환은 배포 버전 확인이 필요하다.
- **Studio 오디오 재생 차단** — 프런트엔드 CSP에 `media-src`가 없어 `default-src 'self'`가 생성 음성과 선택한 원본의 object URL 재생을 막던 문제를 `media-src 'self' blob:`으로 수정했다. 원격 미디어 origin은 허용하지 않는다.
- **Cloud Shell Zun 세션 생성·정리 호환** — Cloud Shell Zun 호출이 microversion header 없이 1.1로 처리되어 list command·typed mounts·`tty`·`auto_remove`가 거부되고, 명시적 `privileged: false`가 Zun 기본 policy(전원 거부)에 걸려 세션 생성이 항상 실패했다. `OpenStack-API-Version: container 1.36` 고정과 `privileged` 필드 생략으로 수정했다. 정리는 admin 전용 force delete 대신 owner 권한의 `stop=true` 삭제를 사용한다. keystoneauth가 404/409를 먼저 예외로 바꿔 삭제 확인이 항상 실패하고 lease가 남던 문제도 `raise_exc=False` 상태 매핑으로 고쳤다. 일반 Containers UI의 Zun 호출은 기존 1.1 계약을 유지한다.
  - 검증: 실제 Zun에서 member 권한의 container create 수락과 `stop=true` 삭제, 없는 UUID의 GET→`None`·DELETE→`ZunResourceNotFound` 매핑을 확인했다. 새 stock-Zun 계약 테스트는 수정 전 코드에서 406, `raise_exc` 수정 전 코드에서 404로 실패한다. 검증 컨테이너는 zun-compute의 Cinder RBD `mkfs -t ext4` 실패로 Error가 되어 shell attach·bootstrap은 검증하지 못했다.

## [1.29.0] - 2026-09-28

### Added
- **보안 그룹 쿼터·사용 현황·규칙 편집 동선** — 사용자 화면에서 현재 프로젝트의 그룹 및 규칙 허용량·사용량과 보안 그룹을 사용하는 인스턴스를 표시한다. 각 규칙의 IPv4/IPv6을 별도 열로 확인하고, 규칙은 표 안에서 CIDR 또는 같은 프로젝트의 보안 그룹을 대상으로 추가한다. 비워 둔 원격 IP에는 IP 버전별 전체 대역, 끝 포트에는 시작 포트를 적용한다. 직접 수정할 수 없는 Neutron 규칙은 기존 설정을 복사해 명시적으로 제거·재생성하며 그 사이 정책 변경을 안내한다.
- **관리자 프로젝트별 전체 리소스 쿼터** — 기존 인스턴스·vCPU·RAM·볼륨·용량 및 GPU 정책을 유지하면서 Cinder 스냅샷, Neutron 네트워크·서브넷·포트·라우터·Floating IP·보안 그룹/규칙, 활성화된 Manila 공유·용량·스냅샷·공유 네트워크·그룹/그룹 스냅샷 한도를 조회·조정한다. Nova 추가 쿼터도 제공되는 경우 표시한다. 서비스별로 변경 항목만 저장하고 누락된 사용량·미지원 필드를 0 한도로 오인하지 않는다. 멀티서비스 API 일부 실패는 부분 성공으로 표시한다.
- **관리자 이벤트 뷰어** — 기존 활동 이력을 시스템 관리자 전용 전역 타임라인·상세·필터 및 서비스·프로젝트·페이지·액션별 실패 집계로 조회한다. 인증된 변경 요청의 성공/실패와 Keystone/GitLab 로그인 성공을 기록하고, 선택적 RabbitMQ oslo.messaging 알림을 별도 출처로 영속 수집한다. 리소스 ID·요청 ID·사용자·프로젝트·에러를 함께 조사할 수 있지만 알림 발행이 꺼진 OpenStack 작업이나 수집 이전 기록까지 보장하지는 않는다.
- **관리자 서비스 탐색과 Waygate 작업 공간** — Drover·Lumen·Palimpsest·Waygate를 관리자 `서비스` 그룹과 검색 팔레트에 모으고 템플릿·채팅 설정 하위 경로를 유지한다. `/admin/waygate`는 사용자 Network의 `/dashboard/network/waygate`와 UI 기능을 공유하지만 관리자 문맥으로 표시한다. 두 화면 모두 프로젝트 미선택 시 요청하지 않으며 프로젝트 전환 후 이전 서버·클라이언트·첨부 네트워크·트래픽·다운로드 응답을 폐기한다.
- **Waygate 실시간 피어와 상속 설정** — 프로젝트 네트워크 이름과 UUID를 함께 표시하고, 피어 전용 끔/1/2/5/10/15/30/60초 자동 갱신을 기존 서버·네트워크 갱신과 분리한다. 수신 보고의 실제 간격·시각으로 지연과 미확인 상태를 구별하고 이전 프로젝트·서버의 늦은 응답을 버린다. 서버 DNS·PersistentKeepalive 기본값을 상속하는 클라이언트는 다운로드·QR·목록에서 변경을 동적으로 반영하며 DNS 생략과 keepalive 0을 명시 override로 유지한다. 기존 클라이언트의 키/PSK는 변경하지 않고 MTU는 클라이언트별로만 관리한다. 다운로드·QR·설정 아이콘과 활성화·삭제 동작은 좁은 화면에서도 같은 순서로 제공한다.
- **Palimpsest Dockerfile 전체 루트 빌드·SSH VM** — FROM만으로도 Glance의 부팅하지 않은 volume clone에서 전체 루트 squashfs를 생성한다. 후속 Dockerfile 명령은 child-first OverlayFS 변경분으로 봉인하고 실제 blob SHA-256 기반 계보만 재사용한다. 기존 `/usr` 부분 계보는 거부한다. GitHub commit context의 COPY/ADD를 지원하며 inline은 context 없이 빌드한다. URL 가져오기는 공인 DNS 응답에 연결을 고정하고 redirect마다 다시 검증한다. Builder가 Manila share에 원자적으로 남긴 token-bound manifest는 Nova console 유무와 무관하게 일회용 read-only SSH 검증 VM에서 모든 blob의 실제 바이트와 대조한 뒤에만 봉인한다. 소비 VM은 전용 Cinder upper의 initramfs root overlay로 재부팅한다. Nova console이 없어도 guest가 post-reboot overlay/SSH 상태를 확인한 뒤 `/run`에 기록한 token을 backend의 임시 Ed25519 SSH 키로 검사한다. SSH 검증 경로는 guest 키를 제거해야만 활성화되며 console 검증 경로는 키 제거를 시도한다. local private key는 성공/실패 모두 삭제한다. DMSLab OpenStack에서 실제 루트·명령 레이어 빌드, 캐시 재사용, SSH 소비 VM 생성과 재부팅 후 upper 영속성을 검증했으며 운영 배포는 별도다.

### Fixed
- **로컬 Lumen media migration 이력 복구** — 동일 SQL을 예전 `019-media-model-registry`로 적용한 DB는 정확한 파일명·SHA-256과 실제 media 열/JSON 제약을 검증한 뒤 canonical `020-media-model-registry` 이력만 추가한다. 기존 이력·모델·대화·볼륨은 유지하고, 미확인 duplicate column이나 이력/스키마 불일치는 계속 실패시킨다. 개발 Compose가 빌드하는 형제 Lumen 소스의 수정된 migration runner가 필요하다.
- **이미지·오디오 Studio 메뉴 노출** — 실제 사이드바의 AI 채팅 그룹에 기존 이미지 생성·편집과 TTS/STT 화면을 연결하고, 부모 Lumen 메뉴가 동시에 선택되는 표시를 제거했다. Chat 서비스 비활성화 시 세 항목 모두 숨긴다.
- **Palimpsest 재사용 루트 빌드·소비 복구** — cached SquashFS를 byte SHA-256 검증하며 builder 로컬 디스크에 복사하고 input NFS를 loop mount 전에 해제해 Manila share가 `device is busy`로 종료를 막지 않도록 했다. Import의 root→delta artifact ID 순서를 소비 계보 검사까지 유지하고 guest mount에서만 delta→root로 뒤집어 `FROM`+`RUN` 소비 VM이 거부되지 않게 했다.
- **Palimpsest SSH 소비 VM 부트 장치·루트 전환** — Glance 부트 이미지를 Nova BDM의 `image→local, boot_index=0`으로 명시하고, 별도 Cinder upper는 `volume→volume, boot_index=-1`로 유지해 Nova 400 부트 순서 거부를 수정했다. 첫 부팅 staging에서 `layer-identity-merge.py`에 소비자 루트 `/`를 전달해 cloud-init 생성 SSH 계정과 `/home/<user>` 소유권을 보존하고, initramfs `local-bottom`의 `prereqs` 인자 처리, `multi-user.target.wants/layer-{activate,health}.service` 링크 복사, `/boot`·`/boot/efi`만 남긴 overlay `/etc/fstab`으로 재부팅 후 루트 overlay 활성화를 완결했다.
- **Palimpsest 부모 Dockerfile 환경 상속·NFS 검증** — sealed 부모의 전체 root→delta 계보와 누적 ENV/WORKDIR를 자식 build 계획·RUN 실행으로 복원한다. 환경은 일반 SSH 비로그인 명령·대화형 로그인과 systemd 서비스에 전파하고, WORKDIR는 대화형 로그인 시작 위치로 사용한다. Manila가 반환한 첫 NFS export가 열리지 않아도 builder·read-only 검증 VM·전체 루트 소비 VM은 다른 export 위치를 유한한 제한 내에서 시도한다. 검증 VM은 console 결과와 무관하게 실제 blob 바이트를 대조한 뒤에만 봉인하며, 소비 VM은 digest 확인 후 NFS를 해제해 재부팅 시 Cinder blob만 사용한다.
- **Palimpsest 완료 작업의 VM 재실행** — 관리자 작업 기록에서 봉인된 Dockerfile job의 `import_id`로 새 VM을 만들 수 있다. 작업 당시의 root→delta artifact ID와 봉인·계보를 재검증하며 변경된 프로필 이름에서 최신 artifact를 다시 선택하지 않는다. 구형 임포트 작업은 계속 표시하지만 Dockerfile digest가 없어 지원하지 않는 VM 실행 버튼을 보여주지 않는다. 프로필 기반 기존 API는 유지한다.
- **Lumen 밝은 테마 작성창 대비** — 입력창·placeholder·포커스 경계·도구/첨부·비활성 전송 상태를 기존 surface/ink/line 토큰에 맞춰 밝은 테마에서 읽을 수 있게 조정한다. 어두운 테마의 색상 계약은 유지한다.
- **Drover 외부 provider 직접 연결** — 클러스터 생성의 내부 `Default` 자동 선택과 Tenant 네트워크 선택을 제거했다. 외부 provider만 명시 선택할 수 있으며 선택을 생략하면 Drover 관리자 기본 정책을 사용한다. 내부 NIC는 생성 후 추가하고 K3s 기본 네트워크와 분리한다.

## [1.28.0] - 2026-09-27

### Added
- **기간 사용량·다중 리소스 쿼터 예측** — vCPU·RAM·타입별 GPU의 최근 7일 할당 추세로 30일 예상 사용률과 한도 도달일을 표시한다. 블록 스토리지는 Cinder의 현재 사용량을 제공하고, 인스턴스별 사용 시간과 네트워크·스토리지·컴퓨트·선택적 Manila/Swift/Trove 현황을 추가했다.
- **관리자 이미지 repository 카탈로그와 검증** — 전체 marker 페이지를 모아 repository/tag 카드로 탐색하고 최신 업로드 기준으로 정렬한다. 기존 관리 작업은 desktop 표와 mobile/tablet 카드에 유지한다. DB 소유 승인 기록과 Glance 정체성·해시를 대조해 tag별 검증/미검증/조회 불가를 구분하며, 관리자 새 업로드 자동 승인과 명시적 승인·해제를 제공한다. 기존 public 이미지에는 검증을 소급 부여하지 않는다.
- **중복 이미지 tag의 현재·이전 업로드 구분** — 동일 repository/tag의 최신 생성 UUID를 현재로 표시하고 이전 업로드를 Glance SHA-512/256과 UUID로 조회·검색한다. 같은 해시도 별도 업로드로 보존하며, 필터나 업로드 진행 상태로 과거 이미지를 현재로 대체하지 않는다. VM 선택기는 현재 tag만 제시하고 비활성 대상 선택을 막는다. Glance 삭제 보호 상태를 목록에서 유지해 보호된 UUID에는 관리자 삭제 동작을 제공하지 않는다.
- **Palimpsest Dockerfile Glance FROM·실시간 검사** — `FROM`만으로 활성 Ubuntu Glance 이미지 이름/UUID 또는 버전별 유일한 이미지를 선택하고, 중복 버전 tag에는 복사 가능한 후보를 제시한다. 동일 이름은 최신 생성 이미지를 고르며 독립 `base_image_id` 입력은 제거했다. 이미지별 캐시를 분리하고 관리자 전용 lint가 문법 오류·해석된 이미지·새/상속/전체 레이어 예상치를 행별로 표시한다. 스튜디오는 600ms 지연 검사하며 실제 빌드에서 재검증한다.

### Fixed
- **Nova 사용량 리포트 정상화** — SDK의 플레이버·시작/종료 시각과 `total_vcpus_usage`를 보존해 `unknown` 플레이버 및 0 vCPU 시간 문제를 수정하고, 90일 조회가 30일로 축소되던 오류를 수정했다.
- **불완전한 quota 응답 구분** — 사용량 리포트의 Nova·Cinder 원본 quota를 strict 모드로 검사하고 캐시를 분리해, 빈 응답이나 사용량 누락을 정상 0 사용량·무제한으로 오인하지 않는다.
- **Object Storage 암묵적 폴더 탐색** — 폴더 marker 없이 `path/sub/file`로만 저장된 객체도 Horizon처럼 폴더→하위 폴더→파일 순서로 탐색한다. openstacksdk가 버리던 Swift `delimiter`/`subdir`를 원본 JSON 목록에서 끝까지 페이지 조회해 보존하고, 중간 페이지 오류를 빈 목록으로 캐시하지 않는다. 이런 폴더의 이름 변경·이동·휴지통/영구 삭제는 실제 저장된 키만 처리해 없는 marker 때문에 실패하지 않으며 새 marker를 만들지 않는다.
- **Object Storage 이동 중 원본 유실 방지** — SDK raw 요청은 오류 응답에도 예외를 내지 않아, 실패한 Swift COPY를 성공으로 보고 원본을 삭제할 수 있었다. 복사·marker 생성·raw 삭제는 2xx 응답만 성공으로 처리하고, 복사가 실패하면 파일·폴더 이동/이름 변경/휴지통 이동은 원본을 지우지 않는다. 같은 이름으로 이름 변경하면 아무 것도 바꾸지 않고, 폴더를 자기 하위로 옮기거나 대상이 원본과 겹치는 이동은 변경 전에 `400`으로 거부한다.
- **프로젝트 전환 중 이미지 목록 혼동 방지** — 대시보드 이미지 요청을 프로젝트·인증 토큰·요청 순서에 묶어, 이전 요청이 늦게 성공하거나 실패해도 새 프로젝트의 카탈로그·로딩·오류 상태를 덮어쓰지 않는다.
- **이미지 보호 상태·Dockerfile 검사 일치** — Glance 메타데이터 수정 응답에도 보호 상태를 유지하고, SDK가 보호 값을 비워 보낸 이미지의 목록 조회가 실패하지 않는다. 잘못된 `FROM` 이후의 유효 지시어도 lint 예상치에 남기고 부모의 base image ID 누락을 plan/build와 동일하게 거부한다. 인라인 Glance 조회가 이벤트 루프를 막거나 장애 내부정보를 노출하지 않도록 했다.
- **사용량 화면의 현황·RAM 비율** — 부가 quota 요청이 지연되어도 사용량 보고서를 먼저 표시하고, strict Nova/Cinder 쿼터가 실패하면 정규화된 현황 0/무제한을 숨긴다. 1GB 미만 RAM도 반올림 전에 사용률을 계산한다.

### Changed

- **Lumen 0.3.1 operator pin 준비** — Kolla operator root role tag/lock 및 API·worker sample image를 새 릴리스에 맞춘다. Palimpsest root 0.2.4와 수정된 Hub image 승격은 Astra 승인·KVM runner 격리 결정까지 보류하며, 이 변경만으로 운영 배포나 실제 provider 추론을 주장하지 않는다.

## [1.27.0] - 2026-09-27

### Added

- **Waygate 클라이언트 설정·실측 트래픽** — 인증된 VPN 화면에서 클라이언트별 DNS, 선택적 MTU, PersistentKeepalive(0 비활성화)를 발급·수정하고 PSK 사용 여부와 재import 필요성을 표시한다. 클라이언트 RX/TX 누적량·속도는 실제 agent 보고의 gateway 카운터를 반대로 매핑한 값이며, 최대 60개 보고로 구성한 낮은 대비의 카드 배경 wave는 누락·지연·카운터 초기화 시 가짜 속도를 만들지 않는다. `.conf` 다운로드·QR은 계속 제공한다. Waygate 0.2.0의 migration 003 및 API가 선행되어야 하며, 이 기능 코드는 이 release preparation 시점에 운영에 배포하지 않았다.

### Changed

- **Waygate 0.2.0 pin** — Kolla operator root role은 공개된 `v0.2.0` tag/lock을, backend·worker SDK dependency는 그 release merge commit `572393905d50ef4cd7c90232bba43bb0cf40efbd`를 사용한다. SDK 자체 버전은 `0.1.2`로 유지한다.

## [1.26.1] - 2026-09-27

K3s 클러스터 삭제의 floating IP 보존 수정은 Drover `v0.2.25`에 있으며, Afterglow는 운영자 lock과 Drover SDK commit을 그 릴리즈로 올리는 PATCH 릴리즈다.

### Fixed

- **보존 요청한 OCCM floating IP 유지** — Kolla operator lock과 backend `drover-sdk` 고정 commit을 Drover `v0.2.25`(merge `a18f207a`)로 올렸다. SDK 코드는 바뀌지 않았다(`0.2.21`). Drover `v0.2.24`는 클러스터 삭제 때 OCCM이 만든 LoadBalancer floating IP를 모두 삭제했다. 이제 `loadbalancer.openstack.org/keep-floatingip: "true"` Service의 IP는 OCCM처럼 남기고, Kubernetes를 읽지 못해 보존 의사를 알 수 없을 때도 남긴다. 검증 범위는 Drover `docs/release-0.2.25.md`에 있다.

## [1.26.0] - 2026-09-26

VM 플레이버 리사이즈 엔드포인트가 추가되어 MINOR 릴리즈다. K3s 라우팅·OCCM 수정은 Drover `v0.2.24`에 있으며, Afterglow는 운영자 lock과 Drover SDK commit을 그 릴리즈로 올린다.

### Added

- **소유 VM 플레이버 리사이즈** — 프로젝트 쓰기 권한 사용자는 본인 VM의 플레이버를 현재 자원 대비 증분 쿼터로 평가한 뒤 리사이즈하고, `VERIFY_RESIZE` 상태에서 확인하거나 되돌릴 수 있다. 이미지 기반 VM은 디스크 축소를 거부하며 관리자 경로는 유지한다.

### Changed

- **Palimpsest root 배포판 이름 전환** — Kolla operator가 Palimpsest role을 `palimpsest-client` `v0.2.3`에서 설치한다. 이전 `palimpsest-local`은 같은 role 파일을 소유하므로 설치기가 남은 배포판을 거부하고, operator 안내에 제거 후 재설치 절차를 추가했다.
- **Drover 생성 네트워크 선택 UI** — Afterglow 생성 대화상자는 내부 `Default` 자동 선택과 Tenant 네트워크 선택을 제거했다. 외부 Provider 네트워크만 명시적으로 고를 수 있고, 선택을 비우면 Drover의 관리자 기본 정책에 맡긴다. 내부 NIC는 클러스터 생성 후 추가하도록 안내한다. Provider NIC 고정·Pod 라우팅 구현은 별도의 Drover 변경이다.
- **Drover v0.2.24 운영자 승격** — Kolla operator lock과 backend `drover-sdk` 고정 commit을 Drover `v0.2.24`(merge `cacc2573`)로 올렸다. SDK 코드는 바뀌지 않았다(`0.2.21`). 이 릴리즈에서 K3s Pod 응답 라우팅 규칙이 네트워크 재구성·재부팅 뒤에도 유지되고, 게스트 플러그인이 public Keystone endpoint로 인증하며, OCCM이 노드 초기화와 LoadBalancer Service를 단독으로 맡고 클러스터 삭제 시 함께 정리된다. 검증 범위는 Drover `docs/release-0.2.24.md`에 있다.

### Fixed

- **지원하지 않는 추론 끄기 숨김** — 채팅 추론 강도 선택기는 Lumen `/v1/chat/models`의 `reasoning_none_supported`가 true인 모델에만 "없음"을 노출한다. gpt-5·o3·gemini-2.5-pro처럼 Lumen이 `none`을 422로 거부하는 모델에서 전송 실패를 막는다. 현재 선택과 다른 모델로 재생성할 때도 실행 모델 기준으로 정규화한다. Lumen의 422 변경보다 먼저 또는 함께 배포한다.
- **운영 GitHub SSH 확인 이력 503 복구** — 운영 MariaDB에 누락된 `vm_github_ssh_users`를 검토된 migration 080으로 생성해 GitHub 프로필·공개키 확인 뒤 이력 기록이 503으로 실패하던 경로를 복구했다. Kolla `reconfigure`·`upgrade`도 새 backend를 시작하기 전에 일회성 DB bootstrap을 실행해 신규 테이블을 누락하지 않는다. 기존 테이블 변경은 여전히 별도의 SQL migration을 먼저 적용한다.

## [1.25.0] - 2026-09-25

### Added

- **VM 생성 전 GitHub SSH 사용자 확인** — GitHub 프로필과 공개 SSH 키 유무를 자원 생성 전에 확인하고 canonical login을 사용한다. 사용자별 최근 확인 이력은 최대 20건을 유지하며 공개키 본문은 저장하지 않는다.
- **모델별 프롬프트 캐시 가격 관리** — 관리자가 캐시 읽기·5분 쓰기·1시간 쓰기 단가를 독립적으로 설정·해제할 수 있다. 사용량 화면은 캐시 종류를 구분하고, 가격 변경은 수정한 항목만 전송한다.

### Changed

- **CI 검증·이미지 발행 경계 정리** — 독립 테스트 계층을 병렬 실행하고, dev 이미지 변경 감지에 아직 발행되지 않은 source 변경도 반영한다. 동일 입력의 dev→main PR 검증은 기존 push 실행을 참조하며, 이미지 발행은 전체 검증 결과와 source revision 일치를 확인한다.

- **신규 모델 조회·검토 등록** — Lumen의 bounded live 모델 후보를 출처·완전성·오류와 함께 표시하고 표시명·입력/출력 단가를 검토한 뒤 등록·활성화하거나 비활성 저장한다. 별도 기능 편집에서만 명시 override를 적용하며, 조회 실패는 정적 fallback으로 숨기지 않는다. 열린 채팅 선택기는 목록 새로고침과 변경 신호로 새 모델을 반영하되 기존 유효 선택을 유지한다.
- **Lumen 클라이언트별 연결 안내** — 채팅 API 키 설정에서 Codex, Claude Code, OpenAI, Claude 문서를 한꺼번에 펼치지 않고 네 개의 선택 버튼으로 분리했다. 기본 Codex 문서만 표시하고 선택한 클라이언트의 설치·환경 변수·설정 예제와 복사 동작만 교체하므로 긴 연결 안내를 훑지 않아도 된다.
- **오브젝트 업로드 무결성·형식 검사** — 백엔드 프록시 업로드가 no-op 스캔 대신 실제 바이트를 본다. 업로드 스트림을 한 번 훑어 SHA-256을 계산해 브라우저 값과 비교하고, 저장된 객체는 ETag·part 수로 검증한 뒤에만 공개한다. 형식 정책은 좁게 유지해 인라인 렌더링 확장자(`.png`/`.pdf` 등)의 내용 위장과 확장자를 속인 실행 파일만 거부하고, 나머지 파일은 탐지한 형식을 기록만 한다. 검증된 digest와 탐지 형식은 객체 메타데이터와 업로드 dock의 `SHA-256 확인` 표시로 노출된다.

### Fixed
- **인증 장애의 숨은 재시도 제거** — Keystone token 검증의 `404 Failed to validate token`을 실제 세션 무효(401)로 처리하고 background refresh만 만료되어도 로그인 화면으로 전환한다. 실제 503·네트워크 장애에는 작성 중인 화면을 보존한 인증 복구 dialog에서 재시도·로그아웃을 제공하며, 진행 중 refresh가 실패해도 로컬 로그아웃은 완료한다. 서버 세션 폐기를 확인하지 못하면 이를 별도로 알린다.
- **로컬 Lumen migration 이미지 누락 복구** — sibling plugin workspace의 현재 lock·설치·runtime source를 반영해 SQL 실행 전 `lumen_plugin_api` import 실패를 복구했다. Lumen 이미지 빌드가 stale lock을 거부하고 최종 non-root runtime에서 migration CLI import를 검사하도록 강화했으며, API/worker/controller의 amd64·arm64 실행과 로컬 migration 재실행을 확인했다.
- **모델 조회·등록 경합 격리** — provider 전환, 화면 닫기, 재조회와 인증 scope 변경 뒤 도착한 응답을 버리고 bulk 등록의 provider·선택 snapshot을 고정한다. 등록 실패 항목만 남겨 재시도할 수 있다.
- **채팅 클라이언트 탭 스크롤바 제거** — 공유 Tabs의 가로 스크롤 설정과 탭 테두리 때문에 연결 방법 선택줄에 1px 세로 스크롤바가 나타나던 문제를 해당 화면에서만 수정했다. 좁은 화면에는 네 탭을 두 열로 모두 노출하고, 긴 설정 코드 블록의 가로 스크롤은 유지한다.
- **오브젝트 브라우저 폴더 진입 복구** — 컨테이너 탐색 상태 초기화 effect가 `prefix`를 의존성으로 추적해, 폴더를 열면 즉시 루트로 되돌아가던 문제를 고쳤다. 초기화는 이제 컨테이너·프로젝트가 바뀔 때만 실행된다.

- **토폴로지 캔버스 휠 확대·축소 복구** — 휠 이벤트의 입력 장치를 추정해 마우스 휠은 확대, 트랙패드 두 손가락 스크롤은 화면 이동으로 가르던 휴리스틱을 없앴다. 브라우저가 장치를 알려주지 않아 근본적으로 맞출 수 없었고, 두 차례 완화(`wheelDeltaY` 120 배수 → 크기 임계)에도 실제 마우스에서 휠이 계속 이동으로 분류돼 확대가 되지 않았다 — macOS 는 마우스 휠에도 부드러운 스크롤을 적용해 소수점 `deltaY` 를 보내므로 "소수점 = 트랙패드" 규칙에서 이미 걸린다. 이제 **휠은 장치를 가리지 않고 항상 커서 기준 확대·축소**다. 배율이 델타에 비례해 트랙패드의 작은 델타는 작은 확대로 부드럽게 누적되며, 화면 이동은 배경 드래그·휠 버튼 드래그·화살표 키가 맡는다.
- **로컬 Palimpsest Hub source build 복구** — dev Compose와 local-services preflight를 실제 sibling layout인 repository-root context + `docker/hub/Dockerfile`에 맞춰, backend/frontend 재생성 시 dependency build가 존재하지 않는 `hub/Dockerfile`에서 중단되던 회귀를 수정했다.
- **Apple Silicon backend source build 복구** — Backend image가 OpenTofu `linux_amd64` archive를 고정하고 GitHub release를 한 번만 내려받던 계약을 `TARGETARCH` 기반 `amd64`/`arm64` 선택, 공식 SHA-256 pin 검증, bounded retry로 교체했다. OpenTofu acquisition을 별도 stage로 격리해 일시적 download 실패가 대용량 runtime package layer를 무효화하지 않는다.
- **Kolla Notion worker 암호화 의존성 복구** — worker-only uv group에서 누락된 `afterglow-crypto`를 저장소의 `services/afterglow-crypto` 정본으로 backend/worker 모두에 regular-install하고, 최종 worker image 안의 Notion config 암복호화 smoke와 immutable-digest Kolla 검증 절차를 추가했다.

## [1.24.0] - 2026-09-21

### Added
- **오브젝트 브라우저 그리드 보기** — 사용자 버킷 탐색기가 기본적으로 파일 카드 그리드를 보여준다. 폴더는 한 줄짜리 카드로 구분해 더블클릭·Enter로 진입하고, 이미지·PDF는 백엔드가 만든 320px WebP 축소본을 viewport 진입 시점에 가져와 표시하며, 나머지는 큰 형식 아이콘으로 대체한다. 미리보기는 모달로 열려 이미지·PDF·텍스트를 넓게 보여주고, 기존 트리 목록은 툴바 토글로 유지되며 선택은 브라우저에 저장된다.

- **Lumen active-path history와 Claude Gateway 연결** — 채팅은 Lumen의 revision-fenced opaque cursor를 사용해 40개씩 최대 3페이지를 유지하고 처음/이전/다음/최신 탐색, prepend viewport 보존, stale-cursor 단일 복구, old-window 새 응답/전송 처리를 제공한다. Claude Code는 public device issue/poll을 Lumen과 직접 수행하고 Afterglow의 `/oauth/claude/authorize` shell 및 authenticated BFF로 현재 사용자·프로젝트 승인/거부를 완료하며, 설정 화면은 discovery가 광고한 Gateway 주소만 안내한다.
- **전역 Cloud Shell** — Root header에서 현재 프로젝트 권한을 승인한 뒤 전용 service project의 ephemeral Zun 세션과 사용자×프로젝트별 5GiB Cinder 홈을 사용하는 binary xterm을 연다. 사용자 전역 single-session ticket/lease, project switch·logout cleanup, idle/max expiry와 orphan reconciliation, HMAC-managed reset, Origin·frame 검증, tmpfs Keystone credential, non-root/capability-free multi-architecture image를 포함한다. Mobile bottom sheet와 tablet/desktop resize dock, token-based 공통 terminal theme, Kubernetes/Helm/Kolla config·precheck, API/security/deployment 문서와 opt-in live scenario를 함께 제공한다.
- **Waygate 명시적 테넌트 서브넷 연결** — VPN 상세 화면에서 프로젝트 내부 네트워크와 IPv4 서브넷을 검색·선택해 정확한 `{network_id, subnet_id, nat_mode}` 계약으로 연결하고, client 설정 다운로드·QR·연결 상태를 panel-safe 반응형 카드로 제공한다. Waygate는 선택된 서브넷의 Neutron port를 생성·추적하고 attach/detach 실패를 rollback하며, gateway VM callback은 operator가 지정한 직접 public HTTP(S) origin만 허용한다.

### Fixed

- **VM cloud-init bootstrap 경계와 GPU monitoring 설치 복구** — library가 없는 plain/GPU/data-mount VM에서 legacy OverlayFS artifact, layer health token/report, `union_*` Nova metadata를 제거하고 typed empty cloud-config list를 보장했다. GPU/data mount bootstrap은 독립 유지하며 DCGM GitHub tarball/custom unit을 NVIDIA repository의 `datacenter-gpu-manager`·`datacenter-gpu-manager-exporter`와 vendor units로 교체하고 repository architecture를 fail-closed 매핑한다.

- **Cloud Shell terminal·live smoke 안전성** — 비동기 xterm mount 뒤 `ready` 전이가 stdin을 실제로 활성화하고, dock 최소화 중에도 같은 terminal instance와 scrollback을 유지한다. Destructive live smoke는 명시적 disposable username·확인 문구를 요구하고 기존 session/home이 있으면 mutation 전에 거부한다.
- **선택적 Compose 재빌드의 Waygate callback parse 실패** — shared Compose anchor의 필수 변수 보간이 모든 service 선택 전에 실행되던 문제를 제거했다. 이미 실행 중인 dependency를 유지하는 `--no-deps` frontend/backend 재생성은 Waygate public URL 없이 parse할 수 있고, full local stack과 Waygate API/worker는 실제 VM-reachable callback URL을 계속 fail-closed로 요구한다.
- **토폴로지 캔버스에서 마우스 휠로 확대가 되지 않던 문제** — 입력 장치 추정이 `wheelDeltaY` 가 120 의 배수가 아니면 전부 트랙패드로 떨어뜨려, 노치를 잘게 쪼개 보고하는 고해상도 휠(자유 회전 마우스 등)에서는 휠을 굴려도 화면만 움직였다. 이제 120 배수는 확정 증거로만 쓰고, 트랙패드 표식(가로 성분·소수점 델타·한 자릿수 픽셀 델타)이 하나도 없으면 마우스 휠로 본다. 트랙패드 두 손가락 스크롤의 화면 이동은 그대로다. 아울러 **마우스 휠 버튼(가운데) 드래그로 화면 이동**을 추가했다 — 노드 위에서 눌러도 노드를 잡지 않고 이동만 하며, 움직이지 않고 떼도 선택이 바뀌지 않고, 브라우저 기본 자동 스크롤과 가운데 클릭 동작은 막는다.
- **토폴로지 트렁크 배지가 스위치 카드와 같은 숫자를 반복하던 문제** — 1.23.0 에서 provider uplink 배지만 접었으나, tenant 트렁크 배지는 `trunkNetIds` 가 항상 네트워크 하나라 `traffic.networks[netId]` 그대로였고 이는 바로 옆 가상 스위치 카드가 이미 찍는 값과 같았다. 이제 배지는 **네트워크를 2개 이상 합칠 때만** 그려 스위치 카드가 못 보여주는 것만 맡는다. 값은 사라지지 않고 스위치 카드에 그대로 있으며, 트렁크 선의 굵기(`switchThroughput` 추정)와 hover 설명도 유지된다. 배지 표시 임계도 카드가 보조 행을 숨기는 LOD 경계(`k < 0.5`)에 맞춰, 카드는 비었는데 배지만 떠 있던 구간을 없앴다.

## [1.23.0] - 2026-09-18

### Changed

- **Kolla 형제 서비스 root 패키지 전환 완료** — Drover 0.2.22·Lumen 0.2.2·Waygate 0.1.3·Palimpsest(local) 0.1.4 root distribution이 Kolla role을 shared-data로 제공한다. Afterglow in-tree role은 `afterglow` 하나뿐이며, operator는 형제 dev 커밋 SHA(drover 3d21f785, lumen 3ab1f2ff, waygate 9933deb9, palimpsest c82bc0f)와 이를 재생성한 `operator/uv.lock`으로 고정한다.
- **계약 테스트 소유권 정리** — 외부화된 역할에 대한 Afterglow 측 소스 역할 참조와 validator 회귀 테스트를 형제 저장소 소유로 이관하고, Afterglow 계약 스위트는 자체 역할·aggregate dispatch·installer 소유권 경계(root distribution metadata lookup, 설치/재설치/제거 후 파일 보존)를 검증한다.
- **Kolla 테스트 환경 고정** — `deploy/kolla/README.md`가 legacy tag가 아닌 commit SHA pin을 동기화 계약으로 명시한다.

### Fixed

- Waygate 아키텍처 가드가 시스템 Python 3.9에서 stamp에 실패하던 `datetime.UTC` 참조를 수정하고, Lumen/Palimpsest의 ruff 0.16 포맷 드리프트를 정규화했다.

### Fixed

- Kolla 계약 테스트에서 외부화된 Waygate·Palimpsest 소스 역할 참조를 제거하고, root distribution 메타데이터로 설치·재설치·제거 후 형제 역할과 운영자 파일의 보존을 검증한다. 테스트에 형제 checkout이나 임시 worktree 경로가 필요하지 않다.

## [1.22.0] - 2026-09-17

### Added

- **Kolla 독립 서비스 명시적 릴리즈 버전 태그 지원** — Waygate, Palimpsest 등 독립 배포 서비스의 Kolla 이미지 사전 검증기(`validate_image_ref.py`)에서 `@sha256:...` 다이제스트뿐만 아니라 `:v0.1.0`, `:v0.2.20` 등 `latest`를 제외한 명시적 릴리즈 버전 태그 입력을 공식 허용하고, bare reference 및 가변 `:latest` 태그는 차단 유지.
- **독립 형제 서비스 공식 릴리즈 연동** — Waygate `v0.1.0`, Drover `v0.2.20`, Lumen `v0.2.1`, Palimpsest Hub `v0.1.0`의 공식 릴리즈 버전을 확정하고 Kolla 기본 이미지 참조에 반영.

### Changed

- **디자인 시스템 및 HIG 검토 반영** — Apple HIG 상호작용 규칙, 반투명 플로팅 레이어 소재, 액션 컬러 복원, 라이트/다크 테마 명도/채도 보정.
- **볼륨 백업 기본 활성화** — VM 및 볼륨 생성 시 백업 기본 활성화 정책 적용.
- **상세 아키텍처 및 대화형 API 플로우 다이어그램 추가** — 인터랙티브 아키텍처 및 API 흐름도 문서화.

## [1.21.0] - 2026-09-16

### Added

- **토폴로지 리소스 생성·케이블 연결** — 사용자 캔버스에서 네트워크·라우터·인스턴스·로드밸런서·DB 생성 진입점을 제공하고, VM NIC·라우터 외부 게이트웨이·내부 서브넷 인터페이스 연결을 드래그 후 확인 모달로 실행한다. 서브넷이 없는 네트워크는 CIDR/DHCP를 지정해 생성한 뒤 라우터에 연결하며, 라우터 연결만 실패하면 생성된 서브넷을 보존해 중복 생성 없이 재시도한다.
- **네트워크 리소스 소유권 강제** — 네트워크·서브넷·라우터와 연결 mutation은 현재 프로젝트의 소유 metadata가 없거나 다른 프로젝트이면 404로 fail-closed 한다. 외부·공유 네트워크는 계속 표시하지만 사용자 생성·삭제·연결 affordance와 API mutation 대상에서는 제외한다.

### Changed

- **관리자 Flavor 접근 정책·GPU 쿼터 카탈로그** — Private GPU Flavor 목록에 `Quota 연동`/`수동` 정책 배지를 표시한다. 프로젝트 GPU 쿼터 표는 저장된 row에 한정하지 않고 Flavor·Placement에서 발견한 전체 alias, 전체 기본값, 프로젝트 effective 상태를 합쳐 RTX3060·RTX3090·RTX3090TI 등 모든 클러스터 GPU 타입을 즉시 설정할 수 있다. 권한 변경 영역은 dry-run 미리보기와 통합 Compute 정책이 실제 Nova Flavor Access를 반영하는 경계를 명시한다.
- **공지 대상 검색·미읽음 표시** — 관리자 공지 작성에서 사용자와 프로젝트를 이름 또는 ID로 검색해 선택하도록 바꾸고 키보드 탐색·빈 결과·반응형 팝오버를 제공한다. 사용자 알림함은 발송자에 `(관리자)`를 표시하며, 로그인·프로젝트 전환 직후 미읽음 수를 조회해 header 알림 옆에 reduced-motion-safe danger 점멸 점을 표시한다.
- **관리자 사용자 쿼터 페이지네이션** — 사용자 쿼터 화면이 Keystone 사용자 전체를 순차 수집하지 않고 한 번에 20명만 marker 기반으로 불러온다. 공통 이전/다음 탐색과 현재 페이지 표시 건수를 제공하고, 검색과 Lumen quota 결합도 현재 사용자 페이지로 한정해 아직 불러오지 않은 사용자를 미확인 계정으로 잘못 표시하지 않는다. 쿼터 변경 뒤에도 현재 페이지를 유지한다.
- **인증 갱신 중 관리자 화면 보존** — 서비스 목록은 user/project 변경 시 이전 행을 지우고 늦은 응답을 차단한다. 같은 사용자의 token 갱신은 기존 행을 유지하며, 쿼터 화면의 현재 페이지와 진행 중 페이지 이동도 보존한다.
- **관리자 전체 볼륨 일괄 삭제·상태 필터 정리** — `/admin/volumes`에서 현재 marker 페이지의 볼륨을 개별/전체 선택하고 확인 후 최대 50개를 한 요청으로 삭제할 수 있다. Cinder 처리 결과를 ID별로 분리해 일부 실패에도 나머지를 계속 처리하며 성공 선택만 제거하고 실패 선택은 유지한다. 필터·페이지·page size·관리자 project scope 변경 시 선택을 비우고, 상태 카드와 선택지는 실제 count가 1개 이상인 상태만 표시하며 활성 상태가 0이 되면 전체 필터로 복귀한다.

- **관리자 서비스 필터·정렬** — 서비스 상태의 9개 탭에 검색과 조합형 필터를 추가했다. Host·서비스 유형·Zone·Status/State, Network의 Alive/Admin State를 독립적으로 선택하고 각 표 열을 정렬할 수 있다. API Endpoints는 이름·유형·리전 정렬과 URL 검색, Storage Pools는 backend·protocol·vendor·숫자 용량을 지원한다. 탭 전환과 새로고침에도 선택을 유지하며 기존 행을 계속 조작할 수 있다. 미확인과 down, 원본 0건과 검색 결과 0건을 구분하고 초기화·표시 건수를 제공한다.

- **컨텍스트 구성 검사** — 작성창에서 실제 포함된 메시지·지침·메모리·스킬·에이전트·요약·도구/MCP·첨부 metadata를 펼쳐 보고 전체 모델 한도 대비 비중, 응답 예약, 안전 버퍼와 남은 입력을 구분한다. 미계수 재료와 미로딩 재료를 분리하고, 한도 미확인이나 부분 계수에서는 정확한 여유 용량을 표시하지 않는다. 과거 기록의 구성을 임의로 만들어 내지 않는다.

- **Compose 실행 모드 분리** — `docker-compose.yml`은 frontend/backend 최소 실행, `docker-compose.dev.yml`은 현재 Afterglow·Lumen·Waygate·Drover·Palimpsest 소스 빌드와 로컬 통신, `docker-compose.prod.yml`은 GHCR 이미지 pull과 운영 인증서 HAProxy TLS/LB 및 catalog 연결을 담당한다. 기존 overlay와 installed-image 개발 fallback을 제거하고 규정·명령을 통일했다. `services:config`는 private Compose 입력을 준비하며 `services:up/smoke/down`은 기존 `afterglow-local-services` project·DB/cache/checkpointer·키·volume을 보존한다. 실제 대시보드 조회 실패와 상류 Nova 503은 container health로 숨기지 않는다.
- **개발 설정·cache 격리** — private config snapshot에 한정한 0640/supplemental-GID 접근으로 Linux non-root 컨테이너를 지원하고 암호화 키는 0600으로 유지한다. 로컬 Drover의 Sentinel 상속을 차단하며 기존 키와 volume은 보존한다.

- **개발 Compose 기능테스트 통합** — 별도 `docker-compose.test.yml`을 제거하고 dev manifest의 `test` profile로 MariaDB/PostgreSQL/Redis 실행을 통일했다. 전용 loopback 3307/5434/6380과 tmpfs로 앱 데이터와 분리하며, 테스트 실행기는 세 서비스만 기동·종료한다. Cloud 자격 증명 없는 테스트와 `--no-start`/`--keep`을 지원하고 named volume·orphan을 삭제하지 않는다.

- **독립 서비스 endpoint 선택** — Waygate·Drover·Lumen·Palimpsest를 `SERVICE_*_INTERNAL_URL` 또는 `[services] *_internal_url`로 지정할 수 있다. BFF와 대시보드·관리자·MCP의 scoped SDK 호출을 통일했으며 root/`/v1` 주소를 지원한다. Dev는 shell/`.env` → private TOML → local DNS, 기본·운영은 미설정 시 catalog를 사용한다. 명시적 빈 환경 변수는 catalog를 선택하며 운영 HTTPS·인증·project scope와 원격 OpenStack 연결은 유지한다.

- **API Search 선택과 답변 상단 출처** — Lumen이 native 검색을 지원하는 모델에 Search 선택을 연결하고 기본 검색 모델은 `Search · 기본`으로 표시한다. 검색 변경은 context preview와 completion 요청에 반영하며 managed 검색과 분리한다. 출처 번호·제목·도메인을 답변 위에 가로 목록으로 표시하고 작은 화면에서는 목록 안에서만 스크롤한다.

- **관리자 AI 공급자 계정 크레딧·사용량 분리** — `/admin/chat`의 모든 configured provider에 Lumen 귀속 일·주·월·누적 요청·토큰·raw USD cost를 유지하면서 별도 `계정 크레딧` 영역을 추가했다. DeepSeek는 공식 API의 통화별 총 잔액·구매 충전액·지급 credit을 표시하고, OpenRouter는 inference key의 limit/remaining을 account-wide balance와 구분한다. Direct OpenAI/Anthropic은 별도 암호화 관리자 키로 공식 조직 비용·사용량 report를 표시하되 공식 API가 현재 선불 잔액·충전액을 반환하지 않음을 명시하고 결제 console로 연결한다. Gemini console-only와 Perplexity 제품 범위 제한, HTTPS-only 외부 action, bulk refresh fence와 provider CRUD 실패 격리를 유지한다.
- **볼륨 백업 기본 활성화** — 저장된 브라우저 선호가 없으면 Cinder 볼륨 백업 메뉴와 흐름을 기본 노출한다. SSR과 브라우저 초기화가 선언된 beta 기본값을 동일하게 사용하며, 사용자가 현재 브라우저에서 명시적으로 끈 `false` 선호와 다른 beta 기능의 비활성 기본값은 유지한다. UI 노출과 실제 Cinder backup service 가용성은 별도로 검증한다.

- **토폴로지 패킷 흐름 기본 표시** — 캔버스의 패킷 흐름 시뮬레이션을 기본 on으로 바꿨다. 툴바 체크박스로 끌 수 있고, `prefers-reduced-motion` 환경에서는 종전대로 토글과 무관하게 완전히 비활성이다.

### Fixed

- **관리자 기본 설정 리소스 검색 목록 위치** — `/admin/settings`의 리소스 정책 선택이 공통 `SearchSelect`를 사용하도록 바꿨다. 이전에는 결과 목록이 항상 입력 아래에 고정되어 페이지 하단 정책(Waygate floating network 등)에서 검색 결과가 화면 밖으로 잘려 보이지 않았다. 이제 trigger 위·아래 중 넓은 쪽에 목록을 열어 하단 정책은 위로 펼치며, 목록 높이는 viewport 안으로 제한된다. 선택은 목록 항목으로만 확정되고 `선택 안 함`이 해제를 담당하며, 초기 catalog 조회가 실패한 정책은 목록을 열 때 다시 조회한다. API·권한·draft 보관 범위는 그대로다.

- **로컬 Ceph placeholder 검증 격리** — 생성된 개발 설정에서 비활성 Ceph mount의 placeholder 경로로 `/dev/null`을 허용하되, 운영자가 직접 입력한 파일·디렉터리는 기존 타입 검증을 계속 적용한다.
- **관리자 RBD 볼륨 삭제 복구 fail-closed 전환** — 오류 볼륨 진단이 system-admin Cinder/Nova dependency를 독립 tri-state로 확인하고, 선택적 restricted CephX adapter로 RBD directory·image/header/data/trash를 교차 검증한다. 안전한 경우에만 `rbd_id` mapping을 복원/정리하고 force-delete 뒤 Cinder·backend·quota를 다시 확인한다. Per-volume Redis lock과 residue/unverified 결과를 추가해 404 또는 조회 실패를 삭제 성공으로 오판하지 않으며 관리자 패널은 검증된 terminal success에서만 닫힌다.

- **관리자 DB 인스턴스 소스 정정** — `/admin/database-instances`가 OpenStack control-plane `mysqld_exporter` dashboard를 tenant DB처럼 함께 표시하던 문제를 제거했다. 관리자 목록은 인증된 Trove `/mgmt/instances`에서 사용자 생성 DB와 owning project를 읽으며, management 조회 실패를 빈 목록으로 숨기지 않고 명시적인 오류로 표시한다.

- **토폴로지 메뉴 독립 동작** — 사이드바 그룹의 자동 확장·강조를 URL 상위 접두사가 아닌 실제 하위 메뉴 경로로 판정한다. 토폴로지를 눌러도 네트워크 그룹이 자동으로 펼쳐지거나 활성화되지 않으며, 기존 URL·네트워크 상세 경로의 자동 확장·사용자가 선택한 접기/펼치기 상태는 유지한다.

- **반응형 현재 모드 표시 통일** — 관리자 계정의 사용자·관리자 sidebar가 전환 목적지가 아니라 현재 화면의 `사용자 모드`·`관리자 모드`를 icon과 함께 표시하도록 desktop header와 맞췄다. 링크·title·접근성 이름은 기존처럼 반대 모드로 전환하는 동작을 명시하며 1024px 경계의 표시 위치만 sidebar에서 header로 바뀐다.

- **프론트엔드 health 검증** — `/health`를 인증 없이 JSON으로 반환하여 로그인 redirect를 제거했다. Compose healthcheck도 redirect를 따라가지 않고 실제 JSON 상태를 확인한다.

- **로컬 Drover 대시보드 인증** — SDK가 전달한 기존 Keystone token을 Drover에서 무범위 재인증해 원래 프로젝트를 잃던 문제를 수정했다. 프로젝트 헤더가 없는 호출은 토큰 자체를 검증하며 명시적 rescope와 fail-closed 권한 검사는 유지한다. 로컬 smoke는 `k3s-stats`의 `available: true`와 count 범위까지 확인해 HTTP 200인 실패 응답을 통과시키지 않는다. Nova 503은 별도 upstream 장애로 계속 실패 처리한다.

- **서비스 discovery redirect** — Waygate/Drover의 BFF root를 upstream `/v1/`로 전달하여 내부 container hostname으로 향하던 307 대신 version JSON을 반환한다.

- **Lumen 인증 요청 지연 격리** — async 인증 dependency의 동기 Keystone 호출을 제한된 threadpool에서 기다리도록 수정했다. 느린 인증이 전체 API event loop를 막던 문제를 제거하며 token/project/admin 검증과 실패 응답은 유지한다.

- **Perplexity 실행 상태 정합성** — 실제 provider 검색 이벤트에서만 출처와 성공을 생성하고, 실패한 tool call은 durable 기록까지 실패로 유지한다. 함수 schema의 strict 지원 여부와 optional 인자를 보존하여 provider가 지원하지 않는 strict 선언을 강제하지 않는다.

- **큰 화면의 채팅 설정 높이** — 복귀 동작과 설정 본문이 같은 parent 높이를 나눠 쓰도록 바꿔 viewport 최소 높이가 중복되던 문제를 제거했다. Tablet/desktop의 내용 스크롤과 mobile의 자연스러운 main 스크롤을 유지한다.

- **토폴로지 트래픽 강도 스케일과 중복 트렁크 배지** — 선 굵기·흐름 점의 하한을 100 kbps 에서 1 kbps 로 낮추고 포화 지점을 1 Gbps 로 넓혔다. 실측에서 NIC 43개 중 39개가 옛 하한 아래라 `계측 없음` 과 똑같은 스타일로 그려져 어떤 네트워크가 바쁜지 읽을 수 없었다. 이제 계측값이 있으면 항상 `계측 없음` 보다 굵고, 모든 트렁크를 2.5px 로 같게 만들던 굵기 하한을 없앴다. 트렁크 강도는 같은 바이트가 보내는 쪽·받는 쪽에서 두 번 잡히던 최대 2배 과대 표시를 없앴다 — 실제 통과량은 `max(rx,tx)` 와 `rx+tx` 사이로만 계측되므로 그 중점을 쓰고, 하위망이 여럿인 uplink 는 망별로 추정한 뒤 더한다. 흐름 점은 예산이 모자랄 때 개수를 잘라 그리지 않고 건너뛴다(잘린 개수는 흐름 빈도를 거짓으로 낮춘다). provider uplink 배지는 그 라우터의 하위 tenant 망이 2개 이상일 때 라우터당 하나만 그려, 같은 숫자를 배지 2개와 스위치 카드로 세 번 찍고 남의 존 카드를 덮던 문제를 없앴다.

- **대화 제목·Perplexity 출처·컨텍스트 표시** — 서버가 아직 처리 중인 제목을 30초 뒤 클라이언트에서 실패로 바꾸던 처리를 제거했다. Lumen의 미예약 첫 제목 복구와 수동 제목 revision 보호를 연결하고, Agent 검색 이벤트/output item의 출처를 LiteLLM 변환 뒤에도 보존한다. 모든 화면 폭에 상단 기록·출처 목록을 제공하며 답변 카드와 출처 패널에 반환된 snippet을 표시한다. 컨텍스트는 Sonar의 정규 catalog 한도와 남은 token을 사용하고, 미확인 한도·계수 불가·잘못된 예산·요청 실패를 구분하여 키보드/터치로 설명한다.

- **그룹 멤버 검색 테마 대비** — 관리자 그룹의 검색 결과와 빈 결과 패널에 남아 있던 하드코딩 다크 배경을 공통 raised surface로 전환했다. 활성 그룹 설명·ID·멤버 이메일·로딩/빈 상태는 disabled 전용 색상 대신 읽을 수 있는 보조 ink를 사용하고, 삭제·제거·오류는 semantic danger tone, 추가 동작은 공통 primary Button을 사용한다. 라이트·다크 모드에서 각 표면·텍스트·동작 대비를 실제 Chromium으로 확인했다.

- **작은 화면의 채팅 기록·설정 접근** — 전역 헤더 아래에 가려졌던 채팅 메뉴 열기 버튼을 workspace header로 이동했다. 1024px 미만에서 기록·사용자 설정 드로어를 열고 Escape/바깥쪽 클릭으로 닫을 수 있으며 설정 화면에 채팅 복귀 버튼을 추가했다. 출처와 긴 코드가 메시지 grid를 넓히던 문제도 공통 ChatBubble에서 수정했다.

- **Perplexity Sonar·GLM-5.3 가격 거부 수정 연동** — Lumen은 내부 transport key와 공개 모델 ID의 가격 조회 차이를 처리하고 공식 Agent API 가격을 적용한다. Sonar는 API base에 따라 Agent/legacy 가격을 구분하며 수동 가격과 알 수 없는 모델의 `pricing_unavailable` 거부는 유지한다.

- **provider 트렁크 트래픽 중복 표시** — 캔버스가 provider 네트워크 전체 NIC 합산값을 그 provider에 붙은 모든 라우터 트렁크에 복제해, 서로 다른 하위망을 가진 링크들이 모두 같은 트래픽처럼 보였다. 이제 하위 스위치 쪽 트렁크는 해당 네트워크 합산을 유지하고, external·shared provider-tier 스위치 쪽 트렁크는 그 라우터가 직접 연결한 tenant 네트워크들만 합산한다. shared provider가 일반 router interface로 연결되는 경우도 대상 네트워크 tier로 uplink를 판정하며, provider 네트워크 자체는 합산에서 제외한다. 배지도 `네트워크 합산`과 `하위망 합산`으로 범위를 구분한다. 라우터 exporter가 없어 실제 L3 링크 자체의 내부/외부 비중은 여전히 계측하지 않는다.

- **토폴로지 응답 8~10초 지연** — 사용자·관리자 토폴로지 핸들러가 서로 의존하지 않는 OpenStack 조회를 직렬로 수행해 각 응답 시간이 그대로 합산되고 있었다(운영 request 로그 `duration_ms` 8286~9939). 이제 네트워크·서브넷·라우터·Floating IP·라우터 인터페이스 포트, 그리고 topology·compute 포트 인덱스·Trove IP·Nova 서버를 각각 동시에 가져온다. 함께 과다 조회도 줄였다 — compute 포트 인덱스는 실제로 읽는 속성만 요청하고, `list_floating_ips`는 전체 포트·전체 서버 detail 목록을 받아 거르는 대신 FIP가 붙은 포트만 id로 조회하고 인스턴스 이름은 detail 없는 목록에서 읽는다. 운영 컨테이너 실측에서 동일한 payload를 유지하며 fan-out이 8938 ms → 2208 ms, `get_topology` 4267 ms → 781 ms, `list_floating_ips` 3167 ms → 349 ms 로 줄었다.

## [1.20.0] - 2026-09-12

### Added

- **캔버스형 네트워크 토폴로지 뷰** — 사용자·관리자 토폴로지 페이지에 "레인 | 캔버스" 토글(기본 캔버스)을 추가했다. 캔버스는 네트워크마다 가상 L2 스위치를 두고, 네트워크를 **provider 로부터의 라우터 홉 깊이**대로 위에서 아래로 계층 배치한다(provider 가 깊이 0, 한 홉마다 한 행씩 내려가며, 라우터로 provider 에 닿지 않는 독립 망은 맨 아래 한 행). 각 행은 자기 라우터 레인을 위에 둔다. 라우터는 자신이 게이트웨이인 네트워크 존에 소속되고, 존 내부는 라우터 → 스위치 → 로드밸런서 → 인스턴스 → 데이터베이스 순으로 위에서 아래로 쌓인다. 로드밸런서는 자기 뒤에 물린 멤버 인스턴스 위에 정렬되며 멤버가 여럿이면 가장 왼쪽 멤버를 기준으로 한다. 멀티 NIC 인스턴스는 소속 네트워크 존의 교차 영역에 놓고 NIC별 케이블과 트래픽 굵기를 그린다. 합성 L3 코어 노드는 두지 않고 외부(프로바이더) 네트워크의 가상 스위치 자체를 구름 모양 인터넷 경계로 표시하며, Floating IP 점선은 해당 외부망 스위치로 직접 잇는다. 연결선 굵기와 흐르는 점의 빈도는 최근 30초 사용량을 연속으로 반영하고(예전 4단계 계단 제거), 점 개수는 경로 길이에 맞춰 정해 긴 케이블이 같은 트래픽에서 더 한가해 보이지 않게 한다. 라우터가 전혀 없는 격리 네트워크는 나갈 경로가 없어 트래픽이 정의상 전부 내부 통신이므로 케이블을 양방향으로 흘려 인스턴스↔스위치↔인스턴스를 보여주고, 라우터가 있는 네트워크는 내부/외부 비중을 계측으로 가를 수 없어 게이트웨이 방향만 표시한다. 토폴로지 트래픽은 Prometheus `rate(...[30s])` 로 바뀌었고, 이를 뒷받침하기 위해 `instances-node`·`instances-libvirt` scrape interval 을 10초로 낮췄다. 팬/줌, 블럭이 서로 겹치지 않는 배치(수동으로 겹쳐 놓으면 가장 가까운 빈 자리로 밀어낸다), 드래그 시 실시간 존 재계산과 localStorage 배치 저장, 이름·IP·CIDR·MAC 검색 하이라이트, 옵트인 패킷 흐름 시뮬레이션, 읽기 전용 네트워크 패널을 제공하고 라우터 트렁크 배지는 네트워크 합산 트래픽임을 명시한다. 토폴로지 API는 추가 OpenStack 호출 없이 인스턴스 NIC `port_id`/`mac_addr`, flavor/image id, 네트워크 MTU, 라우터 SNAT·정적 경로를 더 반환하고, provider 세그먼트 정보는 관리자 응답에만 포함한다.
- **네트워크 사용량 추이 통계** — 토폴로지 네트워크 패널에 최근 15분(15초 간격) rx/tx 스파크라인과 평균·최대·최근 값을 추가했다. 순간값만으로는 "지금 조용한 망"과 "원래 조용한 망"을 구분할 수 없었다. 새 엔드포인트 `GET /api/v1/networks/topology/traffic/history`는 instant 경로와 포트 인덱스·PromQL·귀속 규칙을 공유하므로 패널의 순간값과 그래프가 어긋나지 않고, 평균·최대는 별도 `avg_over_time` 쿼리가 아니라 반환한 표본에서 계산해 그래프 최고점과 라벨 숫자가 항상 일치한다. 통계는 rx+tx 합계가 아니라 **방향별**이라 바로 위 `합산 트래픽` 행(`▼ 수신 ▲ 송신`)과 눈으로 대조된다. 구간은 15분·30분·1시간 토글로 고르며 구간에 따라 표본 간격이 15초 또는 30초가 된다. `step` 은 range 별 고정값(15·30초)으로 rate 윈도우를 넘지 않게 고정했고 표본이 없으면 0 이 아니라 `—` 로 구분한다. 패널을 열 때만 1회 조회한다 — 폴링에 얹으면 Prometheus 부하가 네트워크 수만큼 곱해진다. 이 값은 예전과 같이 해당 네트워크 NIC 들의 합이며 라우터↔스위치 트래픽이 아님을 패널 캡션에 명시한다.
- **Lumen 대화 컨텍스트 수명주기** — 이미 생성된 token을 100ms 안에 화면으로 따라잡는 bounded reveal, 신규 대화의 즉시 history 반영, 첫 정상 응답과 성공한 compaction에서만 갱신하는 의미 기반 제목, 실제 provider 입력 예산의 70% 권고·80% 자동 압축 및 작성창의 수동 압축/중단을 연결했다. 원본 메시지는 보존하고 Lumen의 암호화 checkpoint와 durable compaction run만 모델 입력 prefix를 대체한다.
- **채팅 설정 팝업과 사용량·API 키 쿼터 관리** — 사용량·API 키·메모리·MCP·도구·스킬 설정을 채팅 화면 위의 큰 팝업에 모으고, MCP OAuth 복귀용 `/dashboard/chat/settings?section=…` deep link도 같은 채팅 화면과 지정 탭 팝업을 연다. API 키 화면에서 키 이름을 바꾸고 월·주간 크레딧 한도를 본인 쿼터 범위 안에서 설정하며(빈 값은 해제) 키별 당월·당주 사용량을 함께 본다. 관리자에게는 `/admin/chat/quotas`를 추가해 Keystone 사용자 목록과 Lumen 지갑 쿼터를 `user_id`로 병합하고 월·주간 한도를 편집한다(지갑이 없는 사용자는 Lumen이 보고한 기본 월 한도와 `기본값` 표시). 월간과 주간 한도는 독립적으로 공존하며 주간 경계는 ISO 주(월요일 `00:00` UTC)다. Lumen 쪽 admission·원장 합계·상한 판정은 Lumen이 소유하고 Afterglow는 범용 `/api/v1/chat/{path}` BFF로 PATCH/PUT을 전달한다.

### Changed

- **상세 패널 닫기 버튼 중복 제거** — `SlidePanel`이 이미 닫기 버튼을 그리는데 자식 패널이 또 그려 헤더에 × 가 두 개 보였다. 인스턴스·라우터·네트워크·이미지·컨테이너·볼륨·파일 스토리지·로드밸런서·DB 인스턴스·Drover 클러스터·Flavor 관리·Waygate·VM 생성 위저드 등 21곳에서 자식 쪽 버튼을 제거하고, 그 버튼을 클릭하던 튜토리얼 투어 4개 스텝의 셀렉터를 `[data-slide-panel-close]`로 재배선했다. SlidePanel 아래 컴포넌트 트리를 정적으로 스캔하는 규칙을 추가해 재발을 막는다.
- **토폴로지 캔버스 휠 동작 분리** — 마우스 휠은 확대·축소, 트랙패드 두 손가락 스크롤은 위치 이동으로 나눴다. 브라우저가 입력 장치를 알려주지 않아 델타 단위·`wheelDeltaY` 노치·가로 성분·소수점 여부로 추정하며, 근거가 없으면 이동으로 본다. `ctrl`/`⌘`+휠과 핀치는 종전대로 항상 확대·축소다.

- **프론트엔드 운영 화면 재설계** — 사용자·관리자·채팅·인증·공개 화면을 중립적인 dark/light 토큰과 일관된 240px 반응형 셸, 밀도 높은 리소스 표·도구 모음·작업 영역으로 통합했다. 공통 모달·탭·메뉴의 키보드 및 focus 격리를 강화하고 VM 생성기의 프로젝트 전환 요청을 취소·세대 격리해 오래된 응답이 새 범위를 덮어쓰지 못하게 한다.
- **Lumen 공개 모델 ID와 provider 선택 정합화** — 관리자 모델 화면과 메시지 모델 선택기가 `api_model_name`/`api_provider`를 내부 LiteLLM route와 분리해 표시·검색·복사한다. Perplexity Agent API·Router·기존 Sonar URL 안내를 구분하고 OpenAI/Anthropic SDK 예제가 선택적 `LUMEN_PROVIDER`를 `extra_body`로 보내도록 갱신했으며 모바일·태블릿·데스크톱 배치를 검증했다.
- **관리자 모델명 축약 및 Gemini/Perplexity 접두사 정규화·공급자 무관 라우팅** — 관리자 모델 목록에서 반복되는 provider 접두사(예: `perplexity/perplexity/`, `gemini/gemini-`)를 제거하고 간결한 모델명과 기능 배지를 표출하도록 개선했다. Gemini 모델의 LiteLLM 경로 접두사를 공용 API ID와 분리하여 카드 제목과 API ID가 일관되게 표출된다. 다른 공급자와 겹치지 않는 고유 모델은 `provider` 인자 없이도 자동으로 라우팅된다.
- **대화 삭제 시 확인(Confirm) 절차 추가** — 대화 기록에서 삭제 버튼 클릭 시 대화 제목을 포함한 확인 대화상자(confirmDialog)를 거치도록 개선하여 오삭제를 방지했다. 확인 시에만 삭제 API를 호출하고 성공 피드백을 표시하며, 백그라운드 완료 대화가 삭제 불능 상태로 남지 않도록 스트리밍 상태 경계를 정합화했다.

### Fixed
- **토폴로지 트래픽이 전혀 표시되지 않던 회귀** — 토폴로지 rate 윈도우를 `2m`에서 `30s`로 좁힌 것이 원인이었다. `rate()`는 윈도우 안에 최소 2 샘플이 필요한데 **이 저장소는 운영 Prometheus의 scrape_interval을 제어하지 않는다**(운영은 Kolla 배포본이고 설정은 저장소 밖이다). 근거로 삼았던 `deploy/k8s*/monitoring/prometheus/configmap.yaml`은 운영이 쓰지 않는 다른 배포 경로였고 job 이름조차 다르다. 운영(scrape 1분)에서 libvirt NIC 쿼리가 0 시계열을 반환해 선 굵기·흐르는 점·트래픽 숫자가 모두 사라졌다. 윈도우를 저장소 공통값 `2m`으로 되돌리고, 히스토리 step도 공용 `calc_step()` 관례로 맞췄으며, 윈도우 확보용으로 낮췄던 `deploy/k8s*` scrape 10초도 30초로 되돌렸다. 같은 조사에서 잠복 결함 둘도 함께 고쳤다 — node 쿼리의 `sum by (instance_id, device)` 가 같은 NIC 을 여러 job 이 중복 scrape 할 때 트래픽을 2배로 보고하던 것을 `max by` 로 dedup 했고(운영 실측 1.9~2.0배), 히스토리 `step` 이 scrape 보다 촘촘해 같은 값이 반복되는 계단을 만들던 것을 `scrape ≤ step ≤ window` 계약으로 고정했다(실측 인접 동일값 75% → 0%). 재발 방지로 "토폴로지 윈도우는 같은 메트릭을 읽는 다른 코드보다 좁을 수 없다"를 단정하는 테스트를 추가했다 — 배포 파일을 읽어 scrape를 검사하던 기존 테스트는 운영이 쓰지 않는 파일을 보고 있어 이 회귀를 통과시켰다.
- **장시간 열린 화면의 access token 즉시 갱신** — JSON·채팅/SSE·첨부·업로드/다운로드의 인증 복구를 공통화했다. 요청 전 만료 임박/진행 중 refresh를 기다리고, 첫 401은 새 토큰으로 한 번 재시도한 뒤 결과를 전달한다. 탭 복귀 시 즉시 만료를 확인해 60초 timer 지연 의존을 없앴으며, refresh 503/429/network는 세션을 보존한다. 업로드 취소·진행률, SSE 재생 위치, 기존 logout/토큰 회전 경합 보호와 외부 presigned 요청의 자격 격리를 유지한다.
- **Kolla Valkey failover 뒤 refresh 503 반복** — Afterglow가 `groups['valkey'][0]`을 master로 고정해 두어 Sentinel promotion 뒤 replica에 session timeout key를 쓰면서 `ReadOnlyError`를 내던 문제를 수정했다. Kolla의 모든 Sentinel과 monitor 이름으로 현재 master를 찾고, 기존 `redis_url`의 사용자명·비밀번호·DB index를 발견된 master 연결에 그대로 적용한다. Redis 쓰기 실패 시 refresh를 503으로 거부하는 fail-closed 정책은 유지한다.
- **node_exporter 폴백 트래픽 과소보고** — 토폴로지 트래픽의 node_exporter 경로가 `sum by (instance_id, device)` 결과를 누산하지 않고 대입해, 게스트 안 네트워크 device 가 여러 개인 인스턴스(k3s `flannel.1`, Waygate `wg0`, `bond0`, 두 번째 NIC 등)에서 **마지막 device 하나만** 세고 있었다. 제외 정규식(`lo|veth|docker|cni|tap|qbr`)이 이런 인터페이스를 걸러내지 못하므로 흔한 경우다. 이제 device 전체를 더하며, 순간값 엔드포인트와 새 히스토리 엔드포인트가 같은 입력에서 같은 네트워크 합산값을 내는지 교차 검증하는 테스트로 고정했다(수정 전 3.5배 차이).

- **상단 현재 모드 표시** — 관리자 계정의 desktop header가 이동 목적지가 아니라 현재 route 상태를 표시한다. 일반 화면은 사용자 아이콘과 `사용자 모드`, `/admin` 화면은 shield와 `관리자 모드`를 보여주며 링크와 접근성 이름은 반대 surface 전환 동작을 명시한다.

- **토폴로지 Floating IP 프로젝트 범위 보정** — 사용자 토폴로지 응답의 `floating_ips`가 다른 리소스와 달리 프로젝트로 필터링되지 않아, 관리자가 프로젝트를 전환해 조회하면 전체 Floating IP 목록이 해당 프로젝트 캐시에 남을 수 있었다. 이제 조회 단계와 응답 단계 모두 현재 프로젝트 소유분만 남기고, 조회 중 발생한 인증·의존 서비스 오류(HTTPException)는 500으로 뭉개지 않고 원래 상태 코드로 전달한다.
- **프론트엔드 재설계 마감 품질 복구** — 네트워크 토폴로지의 그래프·범례·요약을 겹치지 않는 문서 흐름으로 복원하고 light 테마 대비를 재조정했다. TypeScript/Svelte 오류와 접근성·반응성 경고를 0건으로 정리했으며, route/on-demand로 지연 로드되는 채팅·Mermaid·Shiki 청크의 빌드 경고 기준을 실제 산출물에 맞게 명시했다.
- **Backend API 지연 증폭 및 cache refresh 경쟁 제거** — 한 요청에서 관리자 권한과 OpenStack 연결이 같은 인증 결과를 재사용하고, 동일 cache key의 동시 miss를 single-flight로 합쳐 Keystone/OpenStack 원본 조회 폭증을 막는다. 명시적 refresh는 선행 동일-key 작업 뒤에 자체 loader를 실행하고 마지막에 저장해 오래된 작업이 새 snapshot을 덮어쓰지 못한다. 최신 세션의 `last_seen` Redis 쓰기도 요청 경로에서 사전 생략하며 background 갱신 실패는 관측 가능한 warning으로 처리한다.

## [1.19.1] - 2026-09-07

### Fixed

- **프론트엔드 CI Blob 계약 안정화** — 생성 파일 다운로드 테스트가 런타임별 `Blob` constructor identity 대신 실제 크기와 MIME type을 검증하여 브라우저·Node 실행 환경 모두에서 동일한 사용자 계약을 확인한다.

## [1.19.0] - 2026-09-07

### Added

- **Lumen 구독 프로바이더 관리** — 관리자가 실험적 ChatGPT device authorization과 Claude subscription token 연결을 설정·해제하고 재인증 상태를 확인할 수 있다. 브라우저에는 provider credential을 반환하지 않으며 공유 계정 사용 경고와 반응형 인증 흐름을 제공한다.

### Fixed

- **Lumen 로컬 Compose Keystone 인증 전달** — 명시적 Lumen Keystone 환경변수와 공통 OpenStack fallback을 migrate/API/worker에 일관되게 전달하고 문서화된 dual env-file 실행 계약을 검증한다.

## [1.18.1] - 2026-09-04

### Added

- **채팅 API 모델 ID 복사** — 메시지 작성창의 모델 선택 목록에서 API `model` 인자용 `model_name`을 확인·복사할 수 있다. 복사 액션은 모델 선택과 분리되며 성공·실패 알림과 모바일 배치를 지원한다.
- **채팅 작성창 명령 팔레트** — `/` 명령을 입력하면서 필터링하고 방향키로 선택한 뒤 Tab으로 자동완성할 수 있다. 새 프로젝트·모델 선택 명령과 `@` 빠른 추가 액션을 제공하며, 여러 모델 프로바이더는 데스크톱·태블릿 왼쪽 탐색과 모바일 가로 탐색으로 전환된다.

### Changed

- **분리 서비스 Kolla 역할 소유권 전환** — Drover와 Lumen 역할을 각 서비스 릴리즈의 SHA256 고정 wheel로 설치하고 Afterglow에 중복된 역할 트리와 내장 AI 런타임 의존성을 제거했다.
- **실제 OpenStack 테스트 수동 실행 전환** — 안정적인 전용 클라우드가 준비될 때까지 push·PR·main CI의 live lifecycle 시나리오를 명시적 workflow dispatch로만 실행한다.

### Fixed

- **외부 채팅 SDK 연결 안내 교정** — 대시보드 호스트에 `api.`를 붙이던 추론을 제거하고 Lumen discovery의 SDK별 공개 URL을 사용한다. 완전한 Python 예제와 실패/재시도 처리를 제공하며 모바일 설정은 가로 탭으로 배치한다. 실제 API 키와 모델로 양 SDK의 일반·스트리밍 응답 및 화면에서 추출한 예제 실행을 검증했다.
- **Lumen 채팅 세션 인증 복구** — BFF가 Keystone 토큰의 실제 연결 프로젝트와 시스템 관리자가 선택한 논리 프로젝트를 분리해 전달하고, 브라우저가 대상 프로젝트 헤더를 위조하지 못하게 하며, 로컬 Compose도 실제 Keystone 설정을 Lumen에 주입한다.
- **분리 서비스 배포 안정성 복구** — Lumen PostgreSQL 네트워크·trusted-origin 수정 릴리즈와 credential 비노출 Kolla 환경을 소비하고 Drover 서비스 프로젝트 범위를 올바르게 해석한다.
- **Kolla mutable image 갱신 복구** — pull·reconfigure가 mutable image tag의 새 manifest를 확인해 캐시된 컨테이너를 재생성하면서 명시적 digest override는 보존한다.

## [1.18.0] - 2026-08-29

### Changed

- **분리 서비스 API 버전 상속 일반화** — Keystone catalog endpoint가 `/v1`, `/v2`, `/v2.1` 중 하나를 포함할 때 SDK와 Afterglow 프록시가 중복 버전 경로를 만들지 않고 endpoint의 실제 버전을 권위 있게 사용한다.
- **GPU 쿼터 판정 Drover 통합** — PCI alias와 flavor extra spec을 Drover의 쿼터 응답으로 일관되게 판정하고, CPU flavor는 우회하면서 GPU 생성은 모든 인프라 변경 전에 쿼터를 확인한다.

### Fixed

- **선택 조회 장애 격리와 필수 GPU 검증 fail-closed** — 선택적인 Drover 읽기 실패는 명시적인 unavailable/필터링 응답으로 제한하고, GPU 생성의 거부·전송 오류·비정상 응답은 각각 409/503으로 중단해 무관한 화면과 실제 생성 안전성을 함께 보존한다.
- **Drover GPU alias 수량 계산 복구** — `alias`, `alias:count`, 여러 PCI alias가 섞인 flavor를 모두 계산하고 잘못된 0·음수 수량은 최소 1로 보정하며 오디오 등 비GPU PCI alias를 제외한다.
- **Kolla 서비스 이미지 갱신 안전성 강화** — digest 기반 서비스 이미지 갱신 시 보안 런타임 설정과 자격 증명을 노출하지 않고 유지하도록 upgrade/reconfigure 계약을 보강한다.

## [1.17.1] - 2026-08-28

### Added

- **관리자 서브넷 운영 상세** — allocation pool, 할당 IP·포트, Neutron binding host와 DHCP agent 배치를 확인하는 관리자 API·화면을 추가하고 네트워크 목록에 실제 CIDR을 표시한다.

### Changed

- **시스템 관리자 외부 프로젝트 조회** — 홈 프로젝트에서 검증한 시스템 관리자 토큰을 유지하면서 명시한 대상 프로젝트를 논리적 리소스 범위로 사용해 별도 tenant role 없이 관리자 상세 조회를 수행한다.
- **Kolla 캐시를 stock Valkey로 통일** — Afterglow, Drover, Lumen, Palimpsest, Waygate가 Kolla Valkey를 공용 Redis 호환 캐시로 사용하고, 누락된 서비스·inventory·비밀번호를 배포 전 검사한다.
- **관리자 Swift 집계에 시간 예산 적용** — 프로젝트별 account metadata를 제한된 동시성과 deadline으로 집계해 Swift 장애가 관리자 overview 전체를 30초 이상 지연하지 않게 한다.
- **Kolla 생명주기 및 기본 설정 동기화** — Kolla Ansible 플러그인 생명주기 및 기본 런타임 변수 동기화를 정비하고 인벤토리 프리플라이트, 풀 의미론, 업그레이드 순서를 검증한다.
- **자동 런타임 배치 정책 동기화** — 배포·재구성·업그레이드 생명주기 과정에서 런타임 배치 정책(`import_runtime_infrastructure_settings.py`)을 동기화하도록 계약을 확장한다.

### Fixed

- **동시 401 세션 소실 방지** — 이미 교체된 access token의 늦은 401은 최신 토큰으로 재시도하고, 동일 토큰 세대의 refresh 실패를 합쳐 401 fan-out이 유효한 세션을 반복 회전·삭제하지 않게 한다.
- **관리자 버전 API 500 제거** — Drover 분리 뒤 삭제된 전역 `k3s_version` 설정을 응답·타입·화면에서 제거해 관리자 overview가 현재 런타임 계약으로 응답한다.
- **Dependabot 보안 취약점 패키지 조치** — 프론트엔드/백엔드 의존성 및 잠금 파일의 보안 취약점을 조치하고 호환성을 확보한다.
- **백엔드 프로덕션 이미지 패키징 수정** — 백엔드 프로덕션 Docker 이미지에 runtime placement policy 스크립트(`scripts/import_runtime_infrastructure_settings.py`)가 포함되도록 `/app/scripts/` 경로 복사 단계를 추가한다.

## [1.17.0] - 2026-07-31

### Added

- **사용자 리소스 목록 일괄 선택** — Compute, Storage, File Storage, 컨테이너, Database, Object Storage, Key Manager, Network 관리 목록에 공통 선택·전체 선택·상태별 일괄 작업 오버레이를 추가했다.
- **관리자 가이드 투어** — Compute·Storage·Library·Network·Containers·Key Manager·Monitoring·System·Identity의 주요 화면에 읽기 전용 단계별 튜토리얼과 관리자 전용 mockup fixture·경로·상태 저장을 추가했다.


### Changed

- **채팅·MCP 제어 플레인 통합** — 내장 AI 채팅, 멀티모달 입력·대화 버전 트리·사용자 메모리, 사용자/관리자 MCP·커스텀 HTTP 도구와 OAuth 위임 흐름을 일관된 제어 플레인으로 통합.
- **Palimpsest 런타임과 이미지 카탈로그 확장** — 콘텐츠 주소화 레이어·OCI 번들 허브·로컬 KVM 런타임 및 Glance 이미지 태그 관리 흐름을 추가.
- **Waygate 네트워크·복구 흐름 완성** — 기존 VPN 흐름을 Waygate 연결·백업·마이그레이션 지원으로 전환.

### Fixed

- **Notion GPU map relation 복구** — Nova server의 embedded flavor metadata를 우선하고 UUID/이름 기반 상세 조회로 보충하며, exact GPU Spec title이 없으면 시스템 canonical GPU 이름을 등록해 alias·개수·relation을 연결하도록 수정.
- **대시보드 화면 높이별 정보 밀도 조정** — overview API가 최근 인스턴스를 최대 12개까지 안전하게 제공하고, dashboard는 화면 높이에 따라 5·8·10·12개 행을 표시한다. 데스크톱 시스템 알림은 사용 가능한 높이에 맞춰 확장·스크롤된다.
- **운영 DB 스키마 조정 복구** — 기존 테이블에 누락된 채팅·MCP 열/인덱스/외래 키를 멱등 마이그레이션으로 보정해 관리 API 503을 방지.
- **로컬 DB 테스트 대상 격리** — 개발 스키마를 대상으로 한 파괴적 DB 테스트를 거부하고, 전용 pytest 스키마만 사용하도록 고정.

## [1.16.2] - 2026-07-14

### Added

- **공개 랜딩 페이지** — 테마 대응 에디토리얼 연구 클라우드 소개, 고정 섹션 내비게이션, VM/GPU·Kubernetes 워크플로우 안내, 실제 대상 사용자·조직 표기, 데이터·관측·레이어·라우터 워크플로우 비주얼, 합성 제품 proof 화면, 테마 불변 SVG media canvas, 테마별 헤더·favicon 아이콘, 인터랙티브 워크플로우, 인증 상태별 콘솔 접속 및 직접 문의 CTA를 루트 경로에 추가하고 로그인 화면을 `/login`으로 분리.

### Changed

- **랜딩 플레이트 아트워크 테마 대응** — 홈 랜딩의 plate 이미지(15종)를 `<img>`에서 인라인 SVG로 전환해 다크/화이트 모드에 동적으로 대응. `<img>`로 로드된 SVG는 격리 문서라 페이지 CSS 변수가 적용되지 않아 라이트 모드에서도 어둡게 남던 문제를 해결하고, 하드코딩 색상을 테마 전환 토큰(`pf-*`/`ps-*` 클래스)에 매핑.

### Fixed
- **대시보드 모니터링 로딩 최적화** — 리소스별 로딩·오류·취소를 독립 처리하고 최근 인스턴스·쿼터·메트릭·K3s 조회의 중복 및 블로킹 작업을 줄여 첫 카드와 전체 대시보드 응답을 단축.
- **대시보드 Floating IP 쿼터 갱신 복구** — openstacksdk Neutron quota alias 직렬화로 인해 발생하던 overview 503을 수정해 실제 floating-IP limit/usage를 유지한다.

- **로그아웃 로그인 이동 통일** — 헤더·프로젝트 선택·세션 보안 화면의 명시적 로그아웃과 세션 폐기 뒤 로그인 페이지로 history replacement 이동하도록 맞추고, 동일 탭의 동시 토큰 갱신과 localStorage로 확인되는 cross-tab winner 뒤에는 최신 토큰을 먼저 폐기하며, mock 세션도 재진입하지 않게 종료.

## [1.16.1] - 2026-07-08

### Added

- **관리자 기본 설정/브랜딩 관리 페이지** — 관리자가 기본 설정과 로그인 브랜딩을 한 곳에서 조정할 수 있는 전용 설정 화면과 관련 테스트를 추가.
- **Notion 관리자 동기화 및 인벤토리 확장** — 관리자 Notion 설정/동기화 흐름과 OpenStack/GPU 인벤토리 연계를 확장.
- **타깃형 로컬 테스트 워크플로우** — `scripts/test-target.js` 기반의 선택 실행 흐름과 문서를 추가해 영역별 검증을 빠르게 반복할 수 있도록 정리.

### Changed

- **로그인/로그아웃/프로젝트 선택 흐름 정리** — 기본 프로젝트 선택, GitLab callback, 로그아웃 경로, 인증 상태 전파를 묶어 브라우저 전환·재진입 시 흐름을 더 일관되게 정리.
- **관리자 개요/인스턴스 UX 개선** — 관리자 개요 타일 표시를 다듬고 인스턴스 리사이즈 모달 상호작용을 보강.
- **의존성 및 테스트 도구 정비** — Dependabot 업데이트와 lockfile 동기화를 반영하고 테스트 문서를 최신 워크플로우에 맞게 정리.

### Fixed

- **로그인 페이지 테마 로고 이중 요청 제거** — 초기 SSR/hydration 구간에서 light/dark 로고가 함께 요청되던 문제를 제거하고 기본 로고 슬롯 매핑을 바로잡음.

## [1.16.0] - 2026-07-07

### Added

- **브라우저 로컬 베타 기능 관리 확장** — 계정 설정의 베타 토글을 Key Manager, 볼륨 백업/스냅샷, 파일 스토리지 스냅샷·Share Network·Security Service, DB 백업까지 확장하고 `localStorage` 기반 브라우저별 선호를 유지.
- **베타 기능 게이트 컴포넌트** — 비활성화된 베타 화면에서 계정 설정으로 이동하는 공통 안내 UI를 추가해 아직 검증 중인 기능의 진입점을 일관되게 차단.
- **베타 게이트 회귀 테스트** — 베타 store, 계정 토글, 공통 게이트, 내비게이션 소스 계약, 볼륨 요약 카드 조건부 렌더링을 테스트로 고정.

### Changed

- **내비게이션 베타 필터링** — Sidebar, AdminSidebar, Command Palette가 비활성 베타 항목을 숨기도록 통합 필터를 적용.
- **고위험 기능 기본 비활성화** — Key Manager, 볼륨 백업/스냅샷, 파일 스토리지 스냅샷·Share Network·Security Service, DB 백업의 목록·상세·생성 흐름을 명시적으로 켠 브라우저에서만 노출.

## [1.15.2] - 2026-06-15

### Security

- **cloud-init export 값 인젝션 방어** — `union_ro_share_export`/`union_manifest_share_export`를 화이트리스트 정규식으로 검증해 cloud-init YAML 구조 주입(임의 write_files/runcmd)을 차단. 형식 검증 정규식의 종단 앵커를 `$` → `\Z`로 교정해 trailing-newline 우회까지 차단.
- **union `get_dependents` IDOR 방어** — 부모 레이어 소유권을 진입부에서 우선 검증하고, 공유 부모의 자식 중 타 프로젝트 소유 레이어를 응답에서 필터링.
- **`secret_key` 엔트로피 게이트** — 비기본이어도 32자 미만이면 `AFTERGLOW_ENV=production` 부팅을 거부(dev는 경고).
- **에러 응답 내부정보 노출 차단** — `openstack_error_to_http`가 5xx에서 OpenStack 내부 URL/메시지를 일반 메시지로 치환(관리자에게만 원문). 깨진 `http_status`→`status_code` 속성 버그도 교정.
- 라이브러리 카탈로그 `is_admin` 키 오타 수정(`is_system_admin`).

### Added

- **GPU 진단 엔드포인트** `GET /api/admin/gpu-hosts/raw` — 오디오 필터 미적용 실 device_id/vendor_id 노출.
- **인스턴스 일괄 선택/액션** — `POST /api/instances/bulk-action`(화이트리스트·max 50·per-id IDOR·부분성공) + 관리자 목록 일괄 액션, 상태 전이 시 autoRefresh 가속.
- **ERROR 인스턴스 복구** — 자동 진단(안전 검사 5종) + 시나리오별 복구 추천 + 관리자 확인 후 원클릭 실행.
- **인스턴스 리소스 사용량 통계**(min/avg/max) + 7일 저사용 리사이즈 권장.
- **GPU 카탈로그 DB화** + 엑셀/CSV 템플릿 다운로드·업로드, flavor 속성 템플릿, 하이퍼바이저-GPU 페이지 통합(+ GPU 모델 컬럼).
- **인스턴스 마이그레이션** — CPU 호환 호스트 필터링 + 마이그레이션 추적 + 라이브 제어.
- **라이브러리 레시피 모듈화** — 범용 빌딩 블록 + apt 스택 레이어, NFS/CephFS 파일 스토리지 직접 마운트.
- **Helm GPU 디바이스 맵 오버라이드**(`gpu.configToml`) + `config2helm.py` 동기화.
- **작업 기록 체계 OpenSpec 도입** — 단일 `milestone.md`를 `openspec/changes/`(진행)·`changes/archive/`(완료)로 분할·이관.

### Changed

- **쿼터 데이터 소스 통합** — 쿼터 카드/타일을 `/api/dashboard/summary` → `/api/dashboard/quotas`로 전환(중복 OpenStack API 호출 제거).
- **문서 정비** — README 간결화 + 문서 사이트 안내, `milestone.md` → OpenSpec 이관(redirect stub).

### Fixed

- **인스턴스 페이지 SSR 500** 3가지 원인 수정.
- **스토리지** — 접근 규칙 생성 실패 3종, NFS share type proto별 fallback + 409 노출, DHSS=False share network 처리, 생성 마법사 단계 스킵.
- **인증** — 탭 간 세션 동기화 + 깨진 401 refresh 복구 경로, `/api/libraries/file-storages` 인증 추가(비인증 export_locations 노출 차단).
- **UX** — GPU quota 카드 깜빡임 제거, 개요 카드 호버 통일, openpyxl 미설치 시 xlsx 다운로드 안내.
- **배포** — backend startupProbe 한도 5분 → 20분 확대, 마이그레이션 `ValidationError` 수정.

## [1.15.1] - 2026-06-11

### Security

- **cloud-init/SSH 보간 값 쉘·YAML 인젝션 방어 강화** — Manila/Keystone 등 외부 API 반환값(export_path, cephx_user 등)도 신뢰하지 않고 `shlex_quote` 쿼팅. cloud-init YAML 개행 주입 차단 검증 추가.

### Added

- **Helm 차트 (`helm/afterglow`)** — 기존 Kustomize + `generate_k8s.py` 2단계 배포를 values 기반 단일 차트로 통합. 18개 리소스(backend/frontend/worker/redis HA/ingress/middleware) + 선택적 모니터링 스택(grafana/prometheus/opensearch, 기본 비활성).
- **ArgoCD Helm 추적 전환** — `argocd/generate_helm_application.py`로 git 미추적 values 파일을 Application `valuesObject`로 인라인. Image Updater는 helm parameter(digest 전략)로 전환, worker 이미지도 자동 추적 추가.
- **config2helm.py** — 기존 `config.toml`을 Helm values 파일로 변환하는 마이그레이션 스크립트.
- **Redis Sentinel HA** — 캐시 백엔드 Sentinel 모드 지원 (`sentinel_enabled`/`sentinel_hosts`). K8s에서 redis StatefulSet + sentinel 3노드 구성.
- **라이브러리 빌더 사전 생성 share 경로** — `existing_share_id`로 기존 Manila share 재사용 빌드 지원 + python311 E2E 테스트.
- **버전 관리 정책 문서(VERSIONING.md)** 및 보안 개발 가이드라인(CLAUDE.md) 추가.

### Fixed

- **빌더 안정화** — python311 빌드 타임아웃 + NFS 병렬 복사, SHUTOFF 후 console 미지원 환경 early sentinel fallback, poweroff 전 60초 대기로 sentinel 조기 감지 윈도우 확보, DB 비가용 시 ephemeral 빌드 진행 및 빌트인 레시피 fallback, build_id 직접 반환.
- **Manila** — `update_share_metadata` body 키 수정(`set_metadata` → `metadata`), prebuilt share 조회 시 public share(타 프로젝트 소유) 포함, 중복 시 최신(`union_built_at`) 우선 선택.
- **프론트엔드 로그인 안정화** — 로그인 직후 취소 요청 폭증·컴포넌트 이중 마운트 수정, 로그인창⇄대시보드 무한 진동 수정.
- **K8s Redis 네임스페이스 버그** — redis ClusterIP 서비스가 master(redis-0)만 타겟하도록 수정, replica/sentinel 설정의 네임스페이스 하드코딩을 상대 이름으로 변경(dev 네임스페이스 sentinel이 prod 호스트를 바라보던 문제 해소).
- **E2E 테스트** — JWT 만료 시 자동 재로그인, SSH 타임아웃 600초 확대, consumer VM keypair 지정, `AFTERGLOW_SKIP_SSH=1` 조건부 건너뜀.

---

## [1.15.0] - 2026-06-09

### Security — 전수 보안 감사 (milestone #69)

- **[CRITICAL] k3s nodegroup 명령 주입 차단** — `labels`/`taints`에 K8s 문법 Pydantic validator 추가. stampede reconciler 경유 root cloud-init RCE 차단. shlex_quote 전면 적용.
- **[CRITICAL] 계정 잠금 서브시스템 신규** — Redis 기반 `(username, domain)` 실패 카운트·지수 백오프·일시 잠금. 관리자 해제 엔드포인트(`POST /admin/users/unlock-account`) 추가.
- **[HIGH] JWT 경로 idle 세션 타임아웃 적용** — `_resolve_jwt_token_info` + `/refresh` 엔드포인트에 세션 타임아웃 검증 연결.
- **[HIGH] GitLab OIDC nonce 검증 추가** — authorize URL에 nonce 포함, callback에서 id_token 클레임 검증. 토큰 재생 공격 차단.
- **[HIGH] X-Auth-Token 레거시 인증 경로 제거** — 바인딩·블랙리스트를 우회하는 X-Auth-Token 경로 전면 제거. Bearer JWT 단일 인증으로 통일.
- **[MEDIUM] token-binding fail-closed 전환** — 바인딩 검사 예외 시 401 반환. 알 수 없는 binding mode 설정 시 시작 거부.
- **[MEDIUM] 기타** — SD 토큰 `hmac.compare_digest` 적용, 세션 소유권 이중 검증, 이메일 HTML 인젝션 방어, Trove 로그 비밀번호 redact.
- **admin_legacy_project_policy 기본값 False** — system:all 스코프만 시스템 관리자 인정. `backend/scripts/bootstrap_system_admin.py` 마이그레이션 CLI 신규.

### Added

- **세션 기기정보 표시** — 로그인 기기 타입·OS 세션 목록 표시. 개별 세션 삭제 지원.
- **관리자 사용자 목록 강화** — 검색·정렬·필터·통계 카드(전체/활성/비활성)·최근 변경 로그 추가.
- **토큰 출처 바인딩** — IP + 기기 지문 기반 토큰 바인딩. 블랙리스트·전체 로그아웃·Keystone 직접 폐기 지원.
- **활동 로그 미들웨어** — CRUD 자동 로깅 미들웨어 도입. 프로젝트 상세 GET 엔드포인트 추가.
- **DB 백업 관리 페이지** — APScheduler cron 스케줄링 + 복원 모달 UI.
- **federated 사용자 패스워드 변경 카드 숨기기** — OIDC/외부 로그인 사용자에게 비밀번호 변경 UI 미노출.

### Fixed

- **trusted_proxies 기본값 복원** — loopback 전용(`127.0.0.1/32,::1/128`)으로 복원. Docker 프록시 설정 가이드 추가.
- **DB 백업 타임아웃 false-negative 교정** — 백업 생성 타임아웃 오감지 수정 + 에러 노출 개선.
- **프론트엔드 이름 버튼 hover 색상 복구**.
- **모바일 헤더 정리** — 스탯 타일 3개·breadcrumb 단축·페이지 크기 고정.
- **모바일 목록 이름 컬럼** — 화면 폭 2/3 제한·말줄임 처리.
- **쿼터 한도 안내** — 쿼터 초과 메시지를 관리자 문의로 변경.

### Changed

- **캐시 기본값 OFF** — 캐시 opt-in(`?cache=true`) 방식 전환. write-through/patch_list 헬퍼 추가.
- **프론트엔드 포트 3080** — Docker/Kubernetes/Kolla 전반 프론트엔드 포트 3000 → 3080 통일. K8s deployment(containerPort, PORT env, 3개 probe), Service, Ingress, ConfigMap, docker-compose.prod, kolla defaults, generate_k8s.py, config.py 기본값 모두 갱신.
- **이름 셀 클릭 영역 확장** — 아이콘+텍스트+빈공간 전체로 확장.

---

## [1.14.7] - 2026-06-04

### Added

- **Notion 자동 동기화 워커** — 주기적 Notion 동기화를 담당하는 경량 독립 워커 컨테이너 추가. 기본 간격 30분, `afterglow-worker` 이미지로 분리 배포.

### Fixed

- **Notion 워커 timezone 버그** — MySQL naive datetime 비교 시 TypeError 묵살로 매 60초마다 재동기화되는 문제 수정.
- **Notion 워커 DB 연결** — `settings.database` → `settings.database_url` (flat 키), `await init_db` → `init_db` (동기) 수정.
- **Notion 동기화 시각 표시** — 프론트엔드에서 UTC 문자열 대신 현지 시각으로 표시.
- **빌드 현황 테이블** — sticky 헤더의 `border-collapse` 충돌로 스크롤 시 구분선이 사라지는 문제 및 긴 `library_id`로 인한 수평 스크롤바 유발 수정.

### Changed

- **빌드 현황 UI** — 테이블 높이를 `max-h-80`으로 제한하고 내부 스크롤 추가. 목록이 많아도 페이지가 길어지지 않음.
- **목록 행 클릭 UX** — 행 전체 클릭 → 이름 영역(링크)만 상세 이동으로 통일. 체크박스·액션 버튼과의 클릭 충돌 제거.

### Dependencies

- `vitest` 3 → 4, `@vitest/coverage-v8` 3 → 4 (메이저 업그레이드, 237 테스트 통과).

---

## [1.14.1] - 2026-05-09

### CI / 인프라

`v1.14.0` release pipeline 이 두 단계에서 fail 하여, 동일 보안 패치 + workflow
fix 를 묶은 정식 release 로 1.14.1 발행.

- **`Apply tag version` 스텝의 npm not found** (PR #18) — `docker-build.yml` 에
  tag push 일 때만 `actions/setup-node@v4` 추가
- **arm64 self-hosted macos runner 의 uv cache lock race** (PR #19) —
  backend/frontend 두 잡이 동일 `~/.cache/uv/.lock` 동시 접근 → 300s timeout.
  `astral-sh/setup-uv` 의 `enable-cache` 를 `${{ matrix.arch == 'amd64' }}` 로
  분기 (linux runner 별도 인스턴스만 캐시).

`v1.14.0` 의 ghcr 이미지 (`-amd64`/`-arm64` single-platform 만 푸시되고
멀티아치 manifest 미생성) 는 broken release 로 두고 1.14.1 을 정식 사용.

보안 패치 내용은 1.14.0 과 동일 (PR #17). 상세는 아래 참조.

---

## [1.14.0] - 2026-05-09 (broken release)

> ⚠️ 이 release 는 CI pipeline fail 로 ghcr 의 멀티아치 `:v1.14.0` manifest 가
> 만들어지지 않은 broken release 입니다. 동일 변경사항을 1.14.1 로 재발행했으니
> [1.14.1](#1141---2026-05-09) 을 사용하세요.

### 보안 (Security) — PR-A + PR-B (2차 보안 패치)

1차 PR (Critical 5 + High 13) 후 잔존 취약점 전수 조사로 식별된
신규 Critical 5 + High 7 + Medium 11 + Low 9 중 최우선 카테고리 처리.

#### Defense-in-depth IDOR 가드

OpenStack RBAC (project-scoped Keystone token) 이 1차 방어선이지만, policy 가
광범위하거나 admin 토큰 누설 시 백엔드에서 한번 더 차단하도록 `assert_resource_owner`
헬퍼를 mutation/detail 엔드포인트에 일관 적용.

- **Network/Router/SG/FIP/Subnet** — `GET`/`DELETE`/`UPDATE` (외부·공유 네트워크 면제)
- **Loadbalancer** — LB/listener/pool/member/health-monitor (lb_id sub-path 모두)
- **Database (Trove)** — instance/databases/users/backups + restore from backup;
  특히 `enable_root_user` (root password 발급) cross-project 차단
- **Storage (Cinder)** — volume/snapshot/backup + transfer endpoint
- **Object Storage** — 신규 컨테이너 생성 시 `X-Container-Meta-Owner-Project-Id`
  자동 부착 (Swift account 모델이 1차 방어, metadata 는 운영 도구 토대)
- **File Storage (Manila)** — share access-rule (list/grant/revoke) 의 owner 검증
  비대칭 해소 — 다른 프로젝트 share 에 IP rule 추가로 cross-tenant CephFS mount
  가능했던 케이스 차단

#### K3s 보안 강화

- **Kubeconfig 다운로드 audit log** — 매 GET 마다 `audit_log.rec(action="kubeconfig_download")`
  + source IP 기록. 토큰 탈취 시 forensic 추적 가능.
- **Callback source IP 로깅** — `_get_real_ip` (1차 PR 의 `trusted_proxies` 검증)
  으로 추출한 source IP 를 callback 로그에 기록. body.server_ip 와 불일치 시 warning.
- **HKDF v3 sub-key 도메인 분리** — 단일 마스터키로 4종 데이터
  (kubeconfig / node_token / notion / manager_password) 를 암호화하지만,
  HKDF-SHA256 으로 도메인별 sub-key 파생 → cross-domain decrypt 불가 (key separation).
- **v2/legacy ciphertext fallback 유지 + deprecation warning** — 다음 PR 에서
  마이그레이션 스크립트와 함께 제거 예정.

#### Health Bearer 토큰 lifetime

- `_TOKEN_TTL`: **30일 sliding → 7일 절대 만료**. 이전엔 매 호출마다 TTL 갱신되어
  사실상 영구 토큰이었음 — VM userdata 노출 시 무기한 cephx rotate 권한.
- 7일 이상 살아있는 인스턴스는 health_check.sh 가 자동 재발급.

### 변경 (Changed)

- `backend/tests/conftest.py` — `mock_conn` fixture 가 SDK `get_*` 응답을
  caller-owned 자원으로 default stub. cross-project 거부 테스트는 `.return_value`
  override 로 작성.

### 검증

- 단위 테스트: **1247 passed, 20 skipped**
- ruff lint + format check: 모두 통과
- advisor 검토 반영: object-storage 검증은 metadata 부착만 (회귀 회피),
  kubeconfig redemption URL 신설 제외 (URL artifact leak 회피),
  v2/legacy crypto 즉시 제거 회피 (배포 사고 방지)

### 마이그레이션 가이드

이 릴리스는 backward-compatible 입니다. 기존 v1/v2 ciphertext 는 자동으로
복호화되며 deprecation warning 만 로그에 1회 (도메인 단위) 기록됩니다.
신규 암호화는 모두 v3 prefix.

다음 릴리스에서 v2/legacy fallback 이 제거되므로 그 전에 마이그레이션 스크립트
(별도 PR 제공 예정) 로 batch re-encrypt 권장.

### 범위 외 (후속 PR 예정)

- PR-C: background task token lifetime + cephx rotate race lock
- PR-D: Frontend localStorage 토큰 → HttpOnly cookie + CSP nonce
- PR-E: K8s securityContext + NetworkPolicy + digest pin + HAProxy non-root
- PR-F: CI scanning (bun audit / pip-audit / trivy) + dependabot
- PR-G: Manila CSI application credential + extend-session CSRF + WebSocket subprotocol
- PR-H: Low 항목 일괄 (SECRET_KEY 엔트로피, Grafana JWT TTL, SecretStr 등)
- v2/legacy crypto fallback 제거 + 마이그레이션 스크립트

상세: [docs/releases/v1.14.0.md](docs/releases/v1.14.0.md), [docs/security.md](docs/security.md)

---

## [1.13.9] - 2026-05-07 이전

이 릴리스 이전 변경사항은 [git tag history](https://github.com/openstack-afterglow/openstack-afterglow/tags)
와 commit log 를 참고하세요. CHANGELOG 정식 운영은 1.14.0 부터 시작합니다.
