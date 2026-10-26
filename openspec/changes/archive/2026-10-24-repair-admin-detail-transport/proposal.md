## Why

관리자 목록이 configured admin-project transport로 다른 프로젝트 자원을 표시하지만 Identity 디렉터리 및 공용 상세가 Personal/member transport 또는 일반 사용자 URL을 사용하여 403/404를 반환한다. 운영 read-only 조사 근거는 `~/.local/share/afterglow-proofs/admin-detail-surfaces-20261025/investigation.json`이다.

## What Changes

- Identity 관리자 목록/상세/선택 도메인 검증에 fresh system-admin 인가와 기존 검증된 관리자 executor를 일관 적용한다.
- 인스턴스 관리자 상세 및 관련 읽기·콘솔·로그를 관리자 경로로 연결하고 실제 부모/자식 소유 프로젝트를 확인한다. 기존 상세에 노출된 lifecycle·삭제·volume/interface·보안 그룹·Floating IP·파일 스토리지 연결·비밀번호 작업은 기존 관리자 경로를 재사용하거나 동일 기능의 bounded 관리자 경로로 복구한다. 사용자 경로의 guard는 완화하지 않는다. Fixed executor로 target 소유 생성을 보장할 수 없는 새 볼륨 생성은 관리자 상세에서 제공하지 않으며 사용자 생성은 유지한다.
- 이미지 관리자 상세/멤버/이미 존재하는 관리자 작업 경로를 올바르게 선택한다.
- 파일 스토리지, 로드밸런서, DB의 관리자 상세/하위 읽기를 전용 경로로 연결한다. 부모 자원의 실제 project를 기준으로 child를 제한한다.
- 기존 정상 관리자 볼륨/컨테이너/네트워크/서브넷/하이퍼바이저 경로 및 caller-owned K3s 서비스 credential 계약은 보존한다.

## Capabilities

### New Capabilities

없음. 기존 관리자 상세 기능의 transport 결함을 수정한다.

### Modified Capabilities

관리자 Identity 디렉터리와 project-owned native 자원의 상세 조회 일관성 및 오류 처리.

## Impact

backend 관리자 router/pytest, frontend 공용 상세 controller 및 관련 회귀, 아키텍처/API/검증 문서/CHANGELOG에 한정한다. 역할 부여, 사용자 Personal 토큰 승격, 공통 사용자 guard 제거, DB/schema/config 변경, 운영 변경, commit/push/tag/deploy는 범위가 아니다. 검증은 cloud credential과 운영 DB를 제거한 격리 snapshot에서 실행한다. 실제 HTTP 및 browser smoke는 합성 native fixture와 설치된 SDK/실제 앱 경로를 명확히 구분한다.
