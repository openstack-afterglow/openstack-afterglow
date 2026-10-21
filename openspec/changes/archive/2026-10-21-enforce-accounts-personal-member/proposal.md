## Why

관리자 사용자 생성 화면과 backend가 선택 도메인의 Default reader 자동 참여를 제공하고, 공유 개인 프로젝트를 project_owner/project_reader로 생성한다. 사용자가 확정한 계약은 모든 신규 human의 identity home은 accounts 전용, 작업 공간은 personal의 사용자 이름+암호학적 임의 문자·숫자 프로젝트, 직접 native member 권한이다.

## What Changes

- Native 공유 identity 도메인의 정확한 이름은 accounts, 내부 identity-only kind는 account로 유지한다. 신규 user는 accounts에만 생성하고 해당 domain에 Default나 role을 생성하지 않는다. 기존 native identity ID/home/password/federation tuple 및 기존 grant는 자동 변경하지 않는다. 기존의 singular account domain은 identity-only로 보호하되 신규 가입 대상으로 재사용하지 않는다. 관리되지 않은 reserved name은 자동 채택하지 않고 provenance 오류로 차단한다.
- 관리자 생성의 선택 도메인은 관측 context일 뿐 조직 자동 가입 사유가 아니다. 공개 가입·관리자 생성·OIDC 신규 생성·신규 초대 수락은 같은 disabled user/project journal·quota/readback 파이프라인을 사용한다. 명시적 초대/신뢰된 OIDC 조직 admission만 별도 조직 Default reader를 추가한다.
- Personal 프로젝트 이름은 정규화 사용자 이름과 충분한 암호학적 random alphabetic/numeric suffix를 native 64자 이내로 생성하고 외부 write 전에 intent에 고정한다.
- 새 personal project에는 본인 직접 native member만 부여한다. Native metadata와 raw/effective 직접 member provenance를 함께 검증하여 primary 재사용·workspace 열람·scope·recovery가 project_owner를 요구하거나 생성하지 않게 한다. 기존 personal 프로젝트의 grant는 이 변경으로 재작성하지 않는다.
- 관리자 생성 UI는 accounts identity-only와 personal member 프로젝트를 정확히 안내하고 선택 도메인 UUID/자동 참여 결과를 표시하지 않는다. 아홉 locale의 계약을 동기화한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

신규 human 계정 생성, 개인 프로젝트 native 권한 및 검증, 관리자 onboarding 안내.

## Impact

Afterglow backend enrollment/account topology/project membership 경계, 관련 pytest, 관리자 Svelte modal와 locale catalogs, 아키텍처·auth/admin/testing 상세 문서. 새 DB column/migration, Keystone mapping 변경, 운영 계정/역할 이관, commit/push/deploy는 범위 밖이다. 신규 예약 도메인은 기존 durable provenance 검증을 유지하며 미확정 native writes는 replay하지 않는다. 검증은 격리 API/DB/native transport 및 실제 브라우저 surface로 수행하고 운영 가입/로그인 acceptance와 구분한다.

`rapid` schema에는 별도 delta-spec artifact가 없다. 기존 `openspec/specs/personal-domain-enrollment/spec.md`의 identity-home·personal role/이름·관리자 관측 domain·미래 quota 계약을 이번 확정 동작으로 직접 동기화하며, 과거 migration098와 승인/continuation 보안 경계는 유지한다.
