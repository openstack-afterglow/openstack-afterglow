## Why

사용자와 관리자 역할 할당 UI/API에서 native Keystone `admin`을 프로젝트에 새로 부여하지 못하게 하되 기존 direct admin grant를 제거할 수 있어야 한다. System scope의 정확한 admin grant/revoke는 기존 계약과 마지막 관리자 보호를 유지한다.

## What Changes

- 사용자/project 및 domain-IAM replacement와 관리자 user/group project assignment에서 native admin 신규 추가를 거부한다.
- 기존 direct admin은 제거 가능하다. 기존 admin을 보존하는 managed-role save는 새 grant로 간주하지 않으며 group/inherited grant를 직접 사용자 grant인 것처럼 제거하지 않는다.
- 사용자/관리자 역할 체크박스는 미할당 admin 선택을 막고 기존 direct admin은 해제할 수 있도록 표시한다. 해제 뒤 신규 재선택은 막는다.
- System:all admin 관리 UI/API와 마지막 enabled admin 보호는 유지한다. `project_admin`, 서비스별 `*_admin`은 native `admin`과 다르며 기존 의미를 보존한다.

## Capabilities

### New Capabilities
없음.

### Modified Capabilities
Native admin 프로젝트 grant의 추가 금지/기존 해제 정책.

## Impact

기존 미커밋 관리자 상세 transport 수정은 보존한다. 소스/회귀/관련 문서만 변경하며 운영 grant 자동 제거, role 삭제/변경, IAM/schema/config/deploy/commit/push는 하지 않는다. API 직접 호출·혼합 role delta·기존 admin 해제·system 예외·화면을 격리 환경에서 검증한다.
