## Why

계정 MCP 연결 설명과 발급 form이 길게 적층되고 활동 목록이 한 번에 과다 표시된다. 계정과 내 리소스 shell의 폭·정렬이 다르며 리소스 overview는 VM·volume·FIP만 보여 준다. 현재 미지원인 squashfs 소비와 실제 동작 없는 HA 옵션은 기능이 있는 것처럼 보인다.

## What Changes

- OAuth/API 키 두 방법을 나란히 선택하고 선택한 setup·연결/키 목록만 표시한다. 간결한 이름·권한·만료 form과 각 mcp.json 전체 복사 버튼을 제공하며 기존 secret once-only·scope fence를 보존한다.
- 개인 MCP 키는 1일·1주·1달·3달·6달·1년·만료 없음·직접 선택을 실제 lifetime으로 지원한다. 날짜 preset은 발급 시점 기준으로 계산한다. 무기한은 명시적 opt-in, nullable expiry이며 OAuth/내부 위임 정책은 기존 finite TTL을 보존한다.
- 최근 활동은 기본10, 선택15/20과 이전·다음 페이지로 제한한다. 필터 변경은 첫 페이지, refresh는 현재 page를 유지하고 stale response/auth scope를 차단한다.
- squashfs consumer/HA beta 옵션의 UI·wizard 상태·payload·관련 obsolete caller/문구를 제거한다. Palimpsest의 실제 별도 build/package/runtime와 administrator 보유 데이터는 삭제하지 않는다. 새로운 Palimpsest 소비나 HA 구현을 추가하지 않는다.
- 내 리소스는 현재 지원되는 사용자 서비스 inventory 전체를 프로젝트 권한 안에서 조회한다. DB·Drover·Waygate 등을 포함하고 실패/미지원/권한없음은 빈 성공으로 표시하지 않는다. 기존 overview cache·refresh와 실제 owning-project 표시를 유지한다.
- 모든 페이지의 외부 콘텐츠 박스는 공통 80rem(1280px) 기본 최대 폭·auto margin·1rem mobile/1.5rem tablet·desktop padding으로 통일한다. 계정/내 리소스뿐 아니라 사용자·관리자 목록/상세·높이 제한 tool 및 공개 페이지의 외부 frame을 포함하며 개별 page max/padding variant를 제거한다. 내부 입력·읽기 영역·modal/panel의 목적별 폭은 보존한다. 토큰/기존 UI primitives·네 locale를 재사용한다.

## Capabilities

### New Capabilities

- 명시적 무기한 개인 MCP key lifetime과 preset 선택.
- 서비스별 inventory와 부분 실패가 있는 사용자 리소스 overview.

### Modified Capabilities

- account MCP setup/issuance, activity paging, VM wizard beta preference cutover, 전체 페이지의 공통 centered content composition.

## Impact

Frontend account/MyResources/ActivityLogTable·wizard/preferences/i18n, MCP personal authority lifetime/model/migration·consumer revocation/expiry guards, user-dashboard API/service/types/tests에 영향을 준다. 운영 DB·IAM·config·컨테이너/볼륨/키·배포·version·commit/push는 변경하지 않는다. Backend HTTP 회귀·실제 격리 API/DB/native 계약 smoke, 실제 Chromium 네 locale·dark/light·mobile/tablet/desktop, exact→named→test:gate 및 격리 architecture stamp를 증거로 남긴다. 기존 사용자 동시 변경과 공유 index를 보존한다.
