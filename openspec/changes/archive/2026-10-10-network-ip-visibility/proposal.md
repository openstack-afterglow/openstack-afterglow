## Why

관리자 네트워크 목록은 이름이 같은 내부 네트워크와 외부·공유 네트워크를 검색하거나 필터할 수 없고 소유 프로젝트를 표시하지 않는다. 네트워크의 서브넷 카드에서 할당 IP와 연결 대상·잔여 풀을 바로 조사할 수 없으며 기존 서브넷 상세는 풀 범위와 포트만 보여 주고 실제 잔여 수량을 계산하지 않는다.

## What Changes

- 기존 관리자 네트워크 목록에 이름·전체 ID·소유 프로젝트 이름/ID·현재 언어의 유형 검색과 독립된 외부/공유 여부 필터, 내부 전용 선택, 초기화·결과 수를 제공한다. 소유 프로젝트는 기존 `/admin/projects/names` 조회를 재사용하고 실패 시 ID와 경고를 보존한다.
- 네트워크 상세의 서브넷에서 IP 사용량을 펼쳐 조회하고 기존 독립 서브넷 상세와 같은 표시를 재사용한다. 할당 IP·포트·연결 인스턴스/라우터 이름과 ID·DHCP 배치·프로젝트·노드를 조회한다.
- 기존 관리자 서브넷 API에 실제 할당 풀 기준 전체·사용·예약·잔여 수와 풀 밖의 할당 수를 추가한다. IPv4/IPv6 정수 구간을 병합하고 중복 IP를 제거해 계산하며 대규모 IPv6도 정밀한 십진 문자열로 전달한다. IPv6 자동 구성은 잔여 풀을 알 수 없음으로 명시한다.
- 조회 실패를 빈 성공으로 표시하지 않고 이름/DHCP 보조 조회 실패는 authoritative IP 목록과 구분한다. 인증 scope/상세 대상 전환 뒤 늦은 응답을 차단한다.
- 한국어·영어·일본어·중국어, 기존 디자인 토큰 및 mobile/tablet/desktop 경계를 유지한다.

## Capabilities

### New Capabilities
- 네트워크 유형 및 소유 프로젝트 기반 관리자 탐색.
- 서브넷별 정확한 풀 사용량과 연결 대상 통합 조사.

### Modified Capabilities
- 기존 관리자 네트워크/서브넷 화면과 관리자 서브넷 응답의 additive 필드.

## Impact

`frontend/src/routes/admin/networks`, `frontend/src/routes/admin/subnets`, 관리자 네트워크 컴포넌트·타입·네 locale, `backend/app/services/neutron.py`, storage 응답 모델과 관련 회귀를 수정한다. 기존 `require_admin` 및 OpenStack native 조회 범위·프로젝트 격리를 유지한다. 신규 DB schema·의존성·credential·배포 설정·운영 IAM/리소스 변경은 없다. 실제 로컬 컨테이너/HTTP/Chromium 증거와 합성 provider 경계를 분리하며 운영 배포는 이 요청 범위가 아니다.
