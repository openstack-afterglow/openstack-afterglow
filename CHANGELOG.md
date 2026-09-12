# Changelog

이 프로젝트의 모든 주요 변경사항은 이 파일에 기록됩니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 을 따르며,
프로젝트는 [SemVer](https://semver.org/lang/ko/) 2.0.0 을 따릅니다.

## [Unreleased]

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
