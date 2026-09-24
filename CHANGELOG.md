# Changelog

이 프로젝트의 모든 주요 변경사항은 이 파일에 기록됩니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 을 따르며,
프로젝트는 [SemVer](https://semver.org/lang/ko/) 2.0.0 을 따릅니다.

## [Unreleased]

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
