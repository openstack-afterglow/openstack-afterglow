---
layout: default
title: 사용자 가이드 화면 캡처·시각 점검
lang: ko
---

# 사용자 가이드 화면 캡처·시각 점검

점검일: **2026-10-11**. 사용자가 직접 인증한 실제 콘솔을 읽기 전용으로 탐색하고, 제출 전 폼·기존 자원·빈 상태·접근 제한 화면을 촬영했다. 공개 문서 변경은 로컬 실행본에서 확인했으며 운영 배포 완료 기록이 아니다.

## 발견한 시각·사용성 문제

확인한 문제는 아래 네 건이다. 각 항목은 관찰한 화면과 조건에 한정한다. 이번 요청에서는 기록만 하고 서비스 화면·권한 정책은 수정하지 않았다.

| ID · 우선순위 | 화면·재현 조건 | 관찰한 문제와 사용자 영향 | 근거 | 권장 조치 · 상태 |
|---|---|---|---|---|
| VIS-01 · 중간 | 한국어 콘솔 `/palimpsest/packages`, 관리자 identity, 1440×1000 | `Administrative or service identities cannot authorize package access`가 영어로 표시되고 `다시 조회`만 제공된다. 일반 프로젝트 사용자 identity가 필요하다는 해결 방법을 한국어로 안내하지 않아 재조회로 해결될 것처럼 보인다. | [실제 접근 제한 화면](../frontend/static/docs/screenshots/palimpsest-access.webp). 관리자·서비스 identity 거부 정책 자체를 결함으로 판정하지 않는다. | 안전한 오류 코드를 한국어 포함 네 언어로 설명하고 일반 사용자로 다시 로그인해야 하는 조건을 안내한다. **미수정·기록 완료**. |
| VIS-02 · 낮음 | 한국어 콘솔 `/dashboard/database/instances` → 인스턴스 생성, 1440×1000 | 마지막 탭이 `진보된`으로 표시된다. 고급 설정을 뜻하는 탭이라는 의미가 불명확하다. | [실제 DB 생성 폼](../frontend/static/docs/screenshots/trove-create.webp) 및 해당 화면의 접근성 트리. 생성은 제출하지 않았다. | `고급 설정`처럼 작업 의미가 분명한 한국어로 수정한다. **미수정·기록 완료**. |
| VIS-03 · 중간 | 한국어 콘솔 `/dashboard/drover`, 기존 ERROR 클러스터 카드, 1440×1000 | 사용자 오류에 raw `HttpException: 503`, 내부 API URL과 볼륨 식별자가 길게 표시된다. 다음 행동보다 SDK/백엔드 세부 정보가 앞에 오며 좁은 카드에서 읽기 어렵다. | 인증된 실제 inventory에서 관찰. [공개 캡처](../frontend/static/docs/screenshots/drover-clusters.webp)는 ERROR 상태만 남기고 내부 주소·식별자·오류 원문을 가렸다. | 간결한 사용자 오류와 다음 행동을 먼저 표시하고, 민감정보를 제거한 지원용 상세는 별도 disclosure로 제공한다. upstream 503의 원인은 이 점검으로 확정하지 않는다. **미수정·기록 완료**. |
| VIS-04 · 낮음 | 한국어 콘솔 `/dashboard/volumes`, 1440×1000 | 페이지 주 제목이 `볼륨 볼륨`으로 중복 표시된다. 서비스 이름과 자원 복수형을 나란히 합친 것처럼 보이지만 원인 코드는 이번 점검에서 확정하지 않았다. | [실제 볼륨 목록 화면](../frontend/static/docs/screenshots/cinder-volumes.webp)의 주 제목. | 한국어 제목을 `볼륨`으로 정리하고 다른 언어의 서비스명·자원명 조합도 함께 검토한다. **미수정·기록 완료**. |

## 결함과 구분한 실제 상태

- **Key Manager**: 베타 기능이 꺼진 실제 안내 화면이다. 베타 설정을 바꾸거나 비밀 payload를 열지 않았다.
- **Palimpsest**: 관리자 identity 접근 거부 화면을 패키지 목록이나 키 발급 성공 화면으로 설명하지 않는다.
- **Audio Studio**: 음성 모델이 없는 실제 catalog 상태다. 생성 결과를 합성하지 않았다.
- **Trove·볼륨 백업**: 비어 있는 목록도 실제 현재 상태다. 설명용 자원을 만들지 않았다.
- **Octavia**: 캡처는 기존 **TCP** 리스너·풀 화면이며 본문의 **HTTP** 예제와 다르다. 캡처를 리스너·풀 절차에 배치하고 프로토콜 차이를 설명했다. ACTIVE·ONLINE은 실제 요청 성공 증거가 아니다.
- **브라우저 파일 선택기**: 한국어 앱 안의 `Choose Files` 같은 네이티브 문구는 캡처 브라우저의 언어에 따를 수 있다. 앱 번역 결함으로 단정하지 않는다.
- 로딩 skeleton·자동 갱신 중 일시 disabled·개인정보 가림으로 생긴 빈 영역·자동화의 잘못된 스크롤 위치는 제품 UI 결함으로 집계하지 않았다. 최종 캡처는 로딩이 끝난 상태를 사용한다.

## 추가한 실제 화면

전체 **15개 가이드 · 42개 WebP · 각 1440×1000**. 자산은 `frontend/static/docs/screenshots/`에 있으며 해당 작업 단계에서 표시한다. 이름·프로젝트·IP·자원 ID·대화 제목·개인 키 이름 등 불필요한 실제 정보는 이미지 픽셀에서 제거했다. 공개 서비스 URL·공개 모델명·폼의 설명용 기본값은 사용법을 읽을 수 있도록 유지한다.

| 가이드 | 화면 수 | 촬영한 위치 |
|---|---:|---|
| 시작하기 | 3 | 빈 로그인 폼, 프로젝트 선택 메뉴, 사용량 개요 |
| Nova | 4 | 이미지 선택, flavor 선택, VM 설정, 기존 인스턴스 상세 |
| Neutron | 5 | 네트워크 생성, 서브넷 생성, 라우터 생성, 보안 그룹 규칙, Floating IP 목록 |
| Octavia | 2 | 로드밸런서 생성, 기존 TCP 리스너·풀 상세 |
| Cinder | 4 | 볼륨 생성·목록, 백업 목록·생성 |
| Manila | 2 | 파일 공유 생성·목록 |
| Glance | 2 | 이미지 catalog, 업로드 폼 |
| Object Storage | 3 | 버킷 목록·생성, 버킷 내부 파일 업로드 영역 |
| Trove | 2 | DB 생성 폼, 현재 빈 목록 |
| Barbican | 1 | Key Manager 베타 제한 안내 |
| Drover | 2 | 클러스터 생성 폼, 기존 클러스터 목록 |
| Waygate | 3 | 서버 목록·생성·기존 서버 상세 |
| Lumen | 6 | 새 채팅, 모델 선택, 사용량, 이미지 Studio, 오디오 Studio, API 키 설정 |
| Palimpsest | 1 | 현재 identity 접근 제한 안내 |
| MCP | 2 | 개인 키 발급 전 설정, 키 없는 OAuth 설정 JSON |

## 확인 범위와 증거

- 로컬 실제 Chromium에서 **15개 가이드 × 4개 언어 = 60개 경로**, 총 **168개 figure**의 이미지 decode 1440×1000, nonempty alt·caption·한국어 캡처 안내, 원본 링크와 문서 언어를 확인했다.
- Lumen 가이드에서 **4개 언어 × light/dark × 390/767/768/1023/1024/1440px = 48개 조건**의 가로 overflow 0, 이미지 경계·비율과 원본 링크 영역을 확인했다. scrollbar가 있는 문서는 `scrollWidth - clientWidth`로 비교했다.
- Octavia 리스너·풀 그림의 실제 원본 링크를 클릭하여 새 탭에서 1440×1000 decode를 확인하고 그 탭을 닫았다.
- 전체 이미지 contact sheet와 필요 원본을 시각 검토하고 OCR 후보 위치를 추가 확인했다. OCR만으로 비밀 부재를 보증하지 않는다. 원본이 공개 static asset이므로 표시용 CSS가 아니라 저장된 이미지 자체에서 정보를 제거했다.
- Desktop 한국어 light 및 mobile 영어 dark 문서의 실제 렌더링 증거는 `openspec/changes/archive/2026-10-11-add-user-guide-screenshots/evidence/`에 보존한다.
- 관련 기존 문서 검증은 3개 파일·36개 테스트가 통과했다. `i18n:check`·`i18n:scan`과 production build 결과는 해당 OpenSpec 완료 기록에 남긴다.
- 전체 frontend type check에는 공유 작업의 MCP 접근 테스트·관리자 채팅 quota·내 리소스 번역 타입 오류가 관찰되었다. 이번 문서 renderer의 새 타입 오류는 보고되지 않았지만 전체 check 통과로 표기하지 않는다. 기존 `DocCodeBlock`과 `ProjectUsageTable`의 비대화형 `tabindex` 경고도 숨기지 않는다.
- 전체 `npm run test:gate`·운영 배포·실제 자원 생성/삭제·키 발급/회수·비밀 조회·설정/QR 다운로드·유료 모델 호출은 수행하지 않았다. 실제 캡처와 로컬 문서 검증을 그러한 작업의 성공 증거로 대체하지 않는다.

## 후속 채팅 폭 복원 점검 (2026-10-12, local-only)

위 네 건과 실제 가이드 캡처는 당시 관찰 기록으로 보존한다. 이후 사용자 제공 화면에 따라 채팅 레이아웃만 수정하며, 이 절의 Chromium 화면은 합성 identity/API를 사용한 로컬 실행 증거다. 운영 캡처를 합성 화면으로 교체하지 않는다.

| ID · 우선순위 | 화면·재현 조건 | 관찰한 문제와 사용자 영향 | 근거 | 조치 · 상태 |
|---|---|---|---|---|
| VIS-05 · 중간 | 사용자 제공 Lumen 채팅 화면 및 현재 source | 외부 `PageShell`의 가운데 정렬·80rem 상한·padding에 채팅 기록 sidebar와 대화 배경까지 묶여 가용 작업 영역 양옆이 비었다. | 사용자 첨부 화면과 채팅·프로젝트 3개 route의 wrapper. | 외부 wrapper는 full-bleed 작업 영역으로 복원하고 transcript/composer만 공통80rem으로 제한했다. **로컬 수정·검증 완료, 미배포**. |
| VIS-06 · 중간 | 로컬 새 채팅, 844×390 landscape | 중앙 정렬된 welcome/composer 묶음이 남은 높이보다 커지면 아이콘이 toolbar 쪽으로 올라가고 하단 프로젝트 선택이 잘린다. | `restore-chat-full-viewport`의 수정 전 Chromium 관찰 기록과 수정 후 capture·실제 element bounds. | 높이가 부족할 때 묶음을 workspace 내부에서 스크롤하고 충분할 때만 중앙 정렬한다. **로컬 수정·검증 완료, 미배포**. |

최종 production build를 실제 Chromium에서 새/저장 대화·4locale·두 테마·모바일/넓은 화면·짧은 높이·프로젝트 route의42조건으로 확인했다. 입력/drawer·scroll proof와 미실행 범위는 [`docs/testing.md`](testing.md#lumen-채팅-전체-작업-영역-복원-검증-2026-10-12-local-only), 화면과 수치는 [archived evidence](../openspec/changes/archive/2026-10-11-restore-chat-full-viewport/evidence/)에 보존한다.

