---
title: 도메인 IAM
parent: API 레퍼런스
nav_order: 13
---

# 도메인 IAM API

> 기본 경로: `/api/v1/iam`

현재 선택한 canonical **작업 도메인** 안에서 사용자·프로젝트 멤버·초대·로그인 방법·할당 예산과 관측을 관리합니다. 계정 소속 **identity/home 도메인**과 작업 도메인은 다르며, 다른 도메인 가입으로 기존 identity가 이동하지 않습니다. 시스템 전체 domain inventory 및 Default manager bootstrap은 [관리자 API](admin.md#도메인-관리와-관측), 공개 로그인·링크 수락과 작업 도메인 전환은 [인증 API](auth.md)를 사용합니다.

## 인증과 도메인 경계

모든 route는 access bearer와 `require_domain_manager`를 요구합니다. 서버는 작업 도메인의 canonical `Default` 프로젝트에서 현재 유효한 `manager`를 확인합니다. 직접·그룹·범위 상속·실제 역할 ID 추론을 포함하되 다른 프로젝트의 manager/admin 이름이나 JWT의 과거 flag는 권한 근거가 아닙니다. **System admin만으로는 사용자 IAM을 우회할 수 없습니다.** 선택 프로젝트와 무관하므로 읽기 전용 일반 프로젝트 또는 프로젝트 미선택 상태에서도 해당 Default manager는 접근합니다. Body/query 또는 `X-Project-Id`로 작업 도메인을 바꾸지 못하며, 인증 API의 명시적 도메인 전환을 먼저 수행해야 합니다.

사용자 화면은 `/dashboard/iam/users`와 `/dashboard/iam/projects`로 분리한다. 사용자 관리의 users/invitations/login/recovery/monitoring 및 도메인 전체 프로젝트 관리는 위 manager 경계를 유지한다. 프로젝트 관리에는 현재 Default `project_creator`도 진입할 수 있지만 `/api/v1/projects`의 현재 프로젝트 owner/admin 권한으로만 멤버·소유권을 관리하며, creator라는 이유로 사용자 directory·creator 위임·다른 사용자의 프로젝트를 관리하지 못한다. 프로젝트 선택창의 새 프로젝트는 같은 fresh capability를 사용하고 활성 조직 도메인의 프로젝트 관리로 이동할 수 있다.

Project·조회한 group은 native 작업 domain ID를 다시 확인합니다. 사용자 directory는 home 사용자와 현재 native 명시적 할당·유효 멤버십으로 확인되는 **joined 사용자**를 포함하며, manager 읽기 projection만으로 외부 사용자를 가입자로 만들지 않습니다. User의 `domain_id`는 실제 home identity 도메인으로, 작업 도메인과 다를 수 있습니다. Joined 사용자는 프로젝트 멤버로 관리할 수 있지만 **name/email/password뿐 아니라 enabled 변경도 home-bound**입니다. 다른 도메인의 manager는 그 계정 자체를 편집할 수 없습니다. 새 멤버 변경 대상 프로젝트는 enabled여야 합니다. Foreign domain/비활성 프로젝트/현재 권한 없음은403, native object 없음은404, 확인 불가는503입니다. IAM credential 변경은 operational account 및 privileged/service/federated 계정을 보호합니다. Enabled-only 변경도 마지막 활성 effective common manager와 소유권 보호를 통과해야 합니다. 보호 대상은 조회 가능하되 허용되지 않은 편집을 UI에 제공하지 않습니다.

IAM JSON body는 알 수 없는 필드를 거부합니다. Project quota PATCH형 PUT만 flat quota 이름들을 받고 **알려진 quota key만** 허용합니다. 일반 IAM validation은422 `{detail:"Invalid IAM request"}`이며 password/token을 반사하지 않습니다. 일반 IAM·quota·monitoring route는 `Cache-Control: no-store, private`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`; login-policy/provider route는 no-store/private·no-cache입니다. 아래 성공 코드 외에 인증401, authority403, 검증422, mutation 충돌409, storage/native 장애503 및 명시된 rate limit429가 가능합니다. 오래된 권한이나 빈 정상 목록으로 실패를 대체하지 않습니다. Quota/monitoring의 section별 unavailable 및 부분 완료는 아래 별도 응답 계약을 따릅니다.

## 전체 route 목록

아래 경로는 `/api/v1/iam` 기준이며 **모두 같은 도메인의 관리자 authority**를 요구합니다. 별도 표기가 없는 성공은200입니다.

| 메서드·경로 | 요청 | 응답·제한 |
|---|---|---|
| `GET /context` | 없음 | `{domain_id,domain_name,is_domain_manager,is_system_admin}` |
| `GET /users` | 없음 | `{items:[User]}` |
| `POST /users` | 없음 | **405**; manager 직접 human 생성은 제공하지 않음 |
| `PATCH /users/{user_id}` | UpdateUser | User; 20회/분 |
| `DELETE /users/{user_id}` | 없음 | `{status:"removed",domain_id,user_id}`; 현재 도메인에서만 내보내기, 20회/분 |
| `GET /projects` | 없음 | `{items:[Resource]}` |
| `GET /groups` | 없음 | `{items:[Resource]}` |
| `GET /projects/{project_id}/members` | 없음 | `{items:[Member]}` |
| `GET /projects/{project_id}/assignable-roles` | 없음 | `{roles,is_owner,can_manage_owners}` |
| `PUT /projects/{project_id}/members/{user_id}/roles` | `{role_ids:["exact-role-id"]}` | 갱신된 Member |
| `DELETE /projects/{project_id}/members/{user_id}` | 없음 | `{status:"removed",member:Member}`; **204 아님** |
| `GET /invitations` | 없음 | `{items:[Enrollment]}` |
| `POST /invitations` | `{email,projects:[{project_id,role_ids}]}` | 201 Enrollment; projects 생략/빈 배열은 Default만, 10회/분 |
| `DELETE /invitations/{invitation_id}` | 없음, int ID | 204 |
| `GET /operations` | 없음 | `{items:[Enrollment]}`; kind와 무관하게 failed 및 recovery 상태 작업만 |
| `DELETE /operations/{operation_id}` | 없음, int ID | 204; 부분 실패 보상 |
| `GET /login-policy` | 없음 | LoginPolicy |
| `PUT /login-policy` | PolicyUpdate | LoginPolicy |
| `GET /providers` | 없음 | `{items:[Provider]}` |
| `POST /providers` | ProviderCreate | 201 Provider |
| `PATCH /providers/{provider_id}` | ProviderUpdate | Provider |
| `DELETE /providers/{provider_id}` | 없음 | 204 |
| `GET /quotas` | 없음 | DomainQuotaSnapshot; 할당 합계·정책·최근 native quota 작업 |
| `PUT /quotas/defaults` | `{revision,defaults}` | 갱신된 DomainQuotaSnapshot; 미래 프로젝트 기본값 전체 교체 |
| `GET /projects/{project_id}/quotas` | 없음 | ProjectQuota; 같은 작업 도메인의 정확한 프로젝트 |
| `PUT /projects/{project_id}/quotas` | flat nonempty QuotaMap | QuotaWrite; HTTP200이어도 partial/unknown 가능 |
| `GET /monitoring` | 없음 | ManagerMonitoring; query/window/pagination 계약 없음 |
| `GET /monitoring/forecast` | 없음 | 도메인 전체 Nova 할당 추세; 서비스별 미지원/불명 상태 유지 |

`GET /monitoring/forecast`는 현재 도메인의 비활성 프로젝트도 포함한 전체 프로젝트를 조회하고 각각 Nova simple-tenant-usage를 명시 microversion2.39의 unpaged GET으로 읽는다. 반환 project/window와 모든 instance usage row를 검증한 경우에만 최근7일 allocation의 선형 추세와30일 후 비율·한도 도달 예상 일수를 계산한다. 분모는 전체 project quota 배분 합계이고 실제 CPU/RAM 이용률·미래 수요나 예약 보장이 아니다. 한 프로젝트라도 history가 불명/거부이면 aggregate 예측을 공개하지 않는다. Storage/GPU/다른 서비스의 도메인 전체 이력은 지원하지 않으며0으로 꾸미지 않는다. 응답은 `{domain_id,observed_at,window_days,horizon_days,source,entries:[{metric,unit,status,error,current,limit,trend}]}`다.

사용자 IAM은 **모니터링 및 배분** 한 탭에서 도메인 전체 resource 관측·project/user 귀속 상세·예측·quota 예산/기본값/개별 project 배분을 제공한다. 세 요청/오류는 독립적이며 하나의 native 장애가 나머지 관측을 숨기지 않는다. Context 재검증 중 탭을 열어도 권위 확인이 끝난 뒤 최초 조회를 시작한다.

Directory 목록에는 limit/marker 계약이 없고 native 작업 domain inventory를 검증해 반환합니다. `/context`의 `is_domain_manager=true`는 해당 Default의 현재 유효 manager를 뜻합니다. `is_system_admin`은 별도 현재 system authority이며 이 값만으로 IAM에 진입할 수 없습니다.

## 사용자 요청·응답

`User={id,name,email,enabled,domain_id,protected}`. `domain_id`는 home 도메인이며 joined 사용자의 작업 도메인으로 덮어쓰지 않습니다. `protected`는 credential/profile 보호 판정으로 외부 home 사용자도 true입니다. Enabled-only 변경은 별도 보호 판정을 하므로 이 boolean이 모든 필드의 편집 허가를 뜻하지는 않습니다. `Resource={id,name,description,domain_id,enabled}`이고 project/group 목록에 공통 사용합니다.

조직 manager는 `POST /invitations`로 이메일 초대를 발행하며 직접 human 생성은 제공하지 않습니다. Native 신규 계정은 검증된 초대 수락 또는 공개 가입/신뢰된 외부 가입에서 shared accounts에 만들고 shared personal의 자기 primary project를 준비합니다. Explicit system-admin의 새 human 생성은 [관리자 API](admin.md)를 사용하며 선택 domain의 Default에는 자동 가입하지 않습니다. 기존 identity·credentials·home을 조직으로 옮기거나 복제하지 않습니다.

신규 human 결과에는 `{user_id,domain_id,domain_name,identity_domain_id,identity_domain_name,personal_domain_id,personal_project_id,personal_project_name}`가 포함됩니다. Working domain은 personal, immutable identity domain은 accounts이며 초대 target 조직은 원래 invitation 문맥에 별도로 유지합니다. 개인 프로젝트 이름은 정규화 username 최대47자+하이픈+암호학적 임의 소문자8자+숫자8자리로 최대64자이고 본인 직접 native member 하나·동결 project quota·native provenance readback 뒤 활성화합니다. Owner/admin/reader·manager/Default/domain quota pool은 새 개인 공간에 자동 부여하지 않습니다. `personal_domain_name` 입력은 제거됐고 extra field는422입니다.

조직 directory는 기존 organization-home 사용자와 현재 native project grant로 참여가 확인된 사용자만 표시합니다. 공유 account 전체를 목록·프로젝트 후보로 노출하지 않으며 비멤버를 role/group/membership API로 추가할 수 없습니다. 신규 조직 admission은 초대 수락 또는 명시 trusted OIDC만 허용합니다.

UpdateUser는 `{name?,email?,password?,enabled?}`만 받습니다. 최소 하나의 non-null field가 필요하며 null/빈 PATCH는422입니다. Name/email/password 제한은 생성과 같습니다. Email 변경은 현재 email 정책을 검증하고 **모든 identity 도메인**의 다른 계정 email과 충돌하면409 `Email belongs to another account`입니다. Password 변경에는 password method enabled 및 email 정책 통과도 필요하며 `afterglow_local_password=true`를 확정합니다. Email-only 변경은 password method가 꺼져 있어도 가능합니다. 이 manager/home-bound 관리 경로와 본인 profile의 검증 링크 변경은 다르며 일반 `/api/v1/profile` PATCH는 email 소유권을 변경하지 않습니다. Domain 이동·개인 도메인 이름·project 이동 필드는 없습니다. `enabled:false`는 먼저 대상 사용자가 관련된 미완료 ownership journal을 검사하며409 `project_ownership_native_operation_unresolved`로 차단합니다. 이어 **home뿐 아니라 joined 작업 도메인까지 포함한 현재 native effective project ownership**을 검사하고 owner-bearing 할당이 있으면409 `Transfer project ownership before disabling or deleting this identity`로 거부합니다. 소유권 이전·미완료 작업의 적법한 정리 후 다시 요청해야 하며 마지막 활성 effective Default manager 보호도 별도로 적용합니다. 성공 후 대상 세션 회수·권한 cache 무효화를 수행합니다.

### 현재 도메인에서 사용자 내보내기

`DELETE /users/{user_id}`는 계정 삭제가 아니다. Fresh manager와 graph lease 아래 현재 도메인의 직접 project/domain 역할 및 안전한 domain-local group membership만 회수하고 native membership 부재를 readback한다. 사용자·비밀번호·enabled·리소스와 다른 도메인 할당은 변경하지 않는다. 자기 자신403, 계정 홈이 현재 domain인 경우409(`domain_eviction_identity_home`), owner/manager-bearing source409, privileged/service identity403이다. 소유권과 관리 권위는 먼저 전용 절차로 이전해야 한다. 다른 범위에 grant가 있는 공유 group·외부 domain group·내부 manager projection은409로 차단하여 다른 도메인 접근을 손상시키지 않는다. 미완료 ownership journal도 차단한다.

변경 직전 전체 native source를 검증하며 변경 후 native 실패·readback 불명은503 `domain_eviction_uncertain`이다. 일부 권한이 이미 회수되었을 수 있으므로 자동 rollback/retry하지 않는다. 목록/권위/세션 검증 cache를 무효화하며 로그인 family는 보존한다. UI는 명시 confirmation 뒤 한 번 제출하고 불명 결과에서는 새 조회 전 재제출을 막는다. `User.protected`는 credential 보호 표시이지 외부 계정의 domain eviction을 일괄 금지하는 flag가 아니다.

사용자 결정(2026-10-26): 이 작업의 내보내기는 잘못 연결된 외부-home 계정의 **현재 접근만 회수**하는 기능이며 영구 가입 금지/계정 연결 이전이 아니다. SSO auto-join 정책과 기존 pending 초대를 유지한다. 따라서 다음 SSO 로그인에서 기존 trusted auto-join 규칙을 통과하거나 기존 초대를 수락하면 다시 가입할 수 있다. 확인창·사용자 도움말도 이 한계를 명시하며 enrollment revoke/tombstone/identity merge를 부수 효과로 수행하지 않는다.

## 멤버·역할과 `can_manage_owners`

`Member`는 `{user_id,username,email,source,roles,is_owner,is_manager,direct_role_ids,effective_role_ids,external_role_ids,group_name?}`입니다. Source는 direct/group/inherited/mixed이며 direct/effective/external ID를 구분합니다. 각 role은 현재 catalog의 `{id,name,description,domain_id,protected,system_only,implied_role_ids,inherited_role_ids,parent_role_ids,area,grade}`입니다.

Assignable roles는 안전한 canonical global project grades·서비스 역할과 제거 전용 native `admin` metadata를 반환하되 **project_owner는 제외**합니다. 편집 catalog의 native admin은 신규 grant 허용 목록이 아니며 초대에서는 제외합니다. `is_owner`는 호출자의 실제 유효 project owner 여부이고 `can_manage_owners`는 IAM에서도 **항상 false**입니다. 검증된 domain manager는 project_admin을 부여·회수할 수 있지만 owner-bearing 일반 역할 변경은409이며 소유권은 전용 이전 흐름을 사용합니다.

PUT role_ids는 최대256개의 unique exact safe ID입니다. 기존 immovable direct grant는 전체 선택에 포함할 수 있지만 추가/제거하지 않으며 group/domain-inherited grant도 유지합니다. Reader/service 쓰기 조합·불완전 계층·system-only 역할을 검증합니다. 대상은 enabled home/joined 사용자여야 하며 아직 대상 프로젝트의 유효 멤버가 아니어도 추가할 수 있습니다. DELETE는 현재 유효 멤버의 관리 가능한 직접 역할만 제거하며 그룹/상속 권한은 남습니다. **Default의 project_reader는 PUT/DELETE에서도 유지·보충**되므로 DELETE 성공을 도메인 탈퇴로 해석하지 않습니다. 멤버 없음404, 잘못된 역할 선택422, 권한 경계403, owner-bearing 변경/계층/동시 변경409, 조회 불가503입니다. 역할 추가·회수는 목록·권위·기존 토큰 검증 cache를 무효화하지만 로그인 family를 일괄 폐기하지 않습니다. 이후 요청은 현재 권한으로 검사하므로 본인의 관리 권한까지 제거하면 이후 편집은403입니다.

Native `admin`은 카탈로그에 기존 할당 해제를 위한 `area=legacy`, `grade=admin`으로 보일 수 있지만 신규 PUT·초대 grant는422/403으로 차단합니다. 기존 admin 사용자에 대한 domain IAM의 privileged-account 보호는 유지하며, graph lease 안에서 다른 역할 변경 없이 그 프로젝트의 direct admin만 제거하는 정확한 요청에 한해서 회수를 허용합니다. System/domain/다른 프로젝트 admin·service/operator identity와 credential 편집은 이 예외로 허용하지 않습니다. 그룹·상속 admin은 원래 provenance에서만 관리하고 `system:all` 전용 관리 API는 기존대로 유지합니다.

Default의 manager들은 같은 도메인의 모든 프로젝트에 **공통 관리 주체**로 남으며 native `project_reader` 읽기 접근을 받습니다. 일반 프로젝트에 manager 또는 manager를 암시하는 역할을 별도로 부여할 수 없습니다. 각 프로젝트의 `project_owner/admin/member/reader` 위임은 그대로 유지됩니다. 마지막 유효 manager·Default rename/disable/delete·관리용 읽기 projection을 보호하고, grant/group/account/role graph 변경은 공유 graph lease 아래 최신 상태를 재검증합니다. Native 변경 뒤 응답만 실패해도 실제 상태를 다시 읽어 읽기 projection과 관련 권위 cache를 정리하며 요청 자체를 성공으로 표시하지 않습니다. Native의 group membership 제거는 unscoped 증명까지 사용자 전체 토큰을 회수할 수 있으므로 이 경우의 재로그인은 유지합니다.

### 소유권 계층과 project_creator

도메인 관리 우선순위 `manager > owner`는 **관리 authority**이지 `manager → project_owner` native inference edge가 아닙니다. 기존 `project_owner → project_admin → project_member → project_reader`, `project_member → member`, `project_reader → reader` DAG를 유지합니다. 일반 프로젝트 생성자는 단일 명시적 직접 owner가 되고 admin/member/reader는 복수 사용자가 가능합니다. 두 번째 owner·그룹/상속 owner 생성·마지막 owner 제거를 일반 grant로 처리하지 않습니다. 기존 다중 owner는 자동 선택·회수하지 않고 명시적으로 해결해야 합니다.

현재 enabled canonical Default 프로젝트의 effective `manager` 또는 `project_creator`가 프로젝트를 만들 수 있습니다. Creator capability는 다른 project membership grade·domain-scope 동명 grant·system-admin 권한이 아니며 login/startup에서 role/grant를 자동 seed하거나 기존 domain grant를 이동하지 않습니다. Manager의 위임은 같은 Default project의 직접 creator grant이며 사전 명시적 preset setup과 enabled joined 사용자가 필요합니다. 일반 사용자의 삭제에는 현재 creator capability와 sole ownership이 모두 필요하고 manager는 domain authority를 사용합니다. 어느 경우든 Default·리소스/자식 프로젝트가 있는 프로젝트·삭제 확인 불가 상태는 삭제할 수 없으며 force/teardown은 없습니다. 이 흐름은 `/api/v1/projects`의 capabilities·creators·eligible-users·ownership·ownership-transfer·deletion-check API를 사용하며 `/iam`에 별도 creator/ownership route는 없습니다.

IAM 프로젝트 접근 화면의 **새 프로젝트**도 같은 `/api/v1/projects` 경로와 fresh capability를 사용한다. Manager는 `project_creator` 할당이나 프리셋 존재와 무관하게 생성하며 위임 경고는 생성 차단이 아니다. 실제 생성 UUID를 목록에 다시 읽고 선택한다. 생성 불명은 재전송하지 않는다.

## 초대 요청과 링크

POST `/invitations`는 email 3–255자와 `projects` 배열(생략 시 `[]`, 최대256개)을 받는다. 각 항목은 `{project_id,role_ids}`이며 project ID는1–64자, 역할은1–256개의 unique exact safe IDs다. 같은 project 중복·과거 top-level `project_id`/`role_ids`는422다. `{ "email": "joined@example.org", "projects": [] }`는 target `Default` reader만 부여한다. 각 선택 프로젝트에는 명시적인 project membership grade가 하나 이상 필요하고 owner/native admin/manager 승격은 금지한다. Project admin 및 서비스 역할은 live domain authority·safe graph 검증 범위에서 추가한다. UI는 이메일 입력 후 **초대 이메일 발송**에서 여러 프로젝트·각 역할 선택 창을 열고 최종 확인에서 이메일 한 통과 enrollment 한 건만 발행한다. 취소는 발행하지 않는다. 발행 시 email host를 login allowlist로 검증하되 password method 활성 여부는 확인하지 않는다. 새 계정 수락 시 password method를 다시 검증하고 기존 계정의 authenticated 수락에는 password method가 필요하지 않다.

Enrollment DTO에는 기존 id/kind/domain_id/project_id/project_name/email/role_ids/user_id/identity_domain_id/status/timestamp와 personal_domain_id/personal_project_id/personal_project_name·native_writes_settled/recovery_required가 포함됩니다. 과거 personal_domain_name 컬럼은 historical provenance일 뿐 새 입력이 아닙니다. Global registration/managed_create와 조직 admission 없는 external은 domain_id=null로 시작하고 shared personal working ID를 확정하며 identity_domain_id는 accounts입니다. Invitation의 domain_id는 원래 admission target 조직이고 nullable invitation target은 허용하지 않습니다. 공개 생성 결과의 personal working ID와 이 operation target을 혼동하지 않습니다. Token/password·native correlation·grant journal은 반환하지 않으며 token은 SMTP 링크로만 전달하고 digest로 저장합니다. native_writes_settled는 불확실 native 효과의 settlement이지 accepted/cleanup 성공이 아닙니다. Owner/admin의 프로젝트 멤버 관리는 이미 조직에 참여한 사용자로 한정하고 조직 email 초대는 manager만 발행합니다.

Enrollment와 public invitation 응답의 `projects`는 `[{project_id,project_name,role_ids}]` 전체 계획이다. 새 영속 row는 `kind="invitation_multi"`, `project_id=null`, 기존 `role_ids` JSON에 이 계획을 저장하며 schema 변경은 없다. 기존 `kind="invitation"` single-project row는 계속 읽고 수락한다. 새 요청/새 row를 구형 reader와 섞어 서비스하지 않는다. 구형 exact-kind reader는 새 링크를 처리하지 못하므로 API·worker/frontend의 coordinated cutover가 필요하며, 이 source 검증은 운영 mixed-version qualification이 아니다. 기존 `added_grants`/personal quota journal은 덮어쓰지 않는다.

### Lifecycle states

| `status` | 의미·수락 가능 여부 |
|---|---|
| `delivery_pending` | 메일 전송 결과를 아직 확정하지 않음; 수락 불가 |
| `delivery_failed` | SMTP 전송 실패; 수락 불가 |
| `pending` | 전달 성공·아직 사용하지 않은 링크(또는 managed-create 초기 intent); 링크 만료 전만 수락 가능 |
| `expired` | pending의 expires_at 경과를 응답에서 계산한 상태; 수락 불가 |
| `account_creating` | shared domain/native account 생성 intent를 durable commit; recovery_required=true |
| `granting` | personal project와 필수/선택 native grant intent; recovery_required=true |
| `activating` | 새 계정 최종 enabled 상태 적용·검증 중; recovery_required=true |
| `accepted` | 계정·추가 grant·activation 및 SQL accepted commit 완료; 재수락 불가 |
| `failed` | 실행 실패 후 확인 가능한 native 효과의 보상 완료; 같은 token으로 재실행 불가 |
| `recovery_required` | native 결과가 불명확하거나 보상 미완료; 같은 token으로 재실행 불가 |
| `revoked` | 링크 회수 및 필요한 보상 완료; 재수락 불가 |

`GET /invitations`는 해당 domain의 두 invitation kind 이력을 최신순으로 반환한다. 추가 project 없는 초대도 list/revoke 가능하다. 모든 선택 project의 native ID/domain을 확인하며 disabled 이력은 허용하고 삭제된 project는 저장된 이름을 쓴다. 현재 존재하는 project가 다른 domain이면403이다. Public 조회·redemption은 모든 선택 project가 현재 enabled여야 한다. 수락 시 inviter의 현재 domain manager authority와 모든 project/role 계획을 첫 native write 전에 재검증한다.

수락·회수는 graph lease → SQL row lock 순서로 직렬화합니다. 기존 계정은 authenticated 수락에서 enabled 본인과 초대 email을 확인하고 원래 identity를 유지합니다. 새 계정은 name/password만 입력하고 shared accounts user와 shared personal primary를 준비합니다. 초대 수락 두 경로는 target 조직 Default reader를 즉시 부여하고 선택 safe project role은 additive로 추가합니다. 관리자 생성·공개 signup에는 이 조직 grant를 적용하지 않습니다. 기존 direct grant·group/domain inheritance를 지우지 않습니다. Native 호출 전에 exact domain/project/role·phase·correlation을 durable 기록하고 readback하며 새 계정은 disabled 준비 뒤 마지막에 요청 enabled 상태를 검증합니다. Password는 journal에 저장하지 않고 기존 account email/password를 덮어쓰거나 reset으로 실패를 복구하지 않습니다.

새 개인 프로젝트는 본인 직접 native member와 정확한 primary/user/enrollment marker를 사용하고 raw/effective native provenance·동결 project quota를 검증한 뒤 활성화합니다. Member의 manager/owner/admin 승격 graph나 foreign/group/inherited grant는 거부합니다. 개인 manager/Default/domain budget은 없으며 개인 권한을 초대 target 조직으로 전파하지 않습니다. Member grant 거부·응답 유실·상속/그룹 충돌은 accepted가 아니고 명시 settlement와 exact owned-empty 자원 정리만 허용합니다. Shared accounts/personal domain이나 기존 user를 보상 삭제하지 않으며 기존 owner 기반 personal grant도 자동 변경하지 않습니다.

Native 변경 전에 정책/이메일/계정 충돌 등을 거부하면 해당403/409 등 오류가 반환됩니다. 외부 변경 intent 이후 실패는503 `detail="Enrollment operation <id> failed; native changes compensated"` 또는 `... recovery required`이며 row를 failed/recovery_required로 보존합니다. Process crash도 durable account_creating/granting/activating intent를 남깁니다. 이 상태의 링크 재사용은410입니다. 불확실한 create를 새 password reset이나 무조건 retry로 처리하지 않습니다.

`GET /operations`는 **kind와 무관하게** account_creating/granting/activating/recovery_required/failed row만 반환합니다. 따라서 invitation도 이 목록에 포함될 수 있습니다. `DELETE /operations/{operation_id}`는 같은 live domain authority로 해당 작업의 보상을 실행합니다. `DELETE /invitations/{invitation_id}`는 invitation kind만 대상으로 회수·필요 보상을 수행합니다. Pending뿐 아니라 delivery 실패·expired·failed·recovery 상태도 회수할 수 있습니다. Accepted/revoked 회수는409(멱등 성공 아님), ID/도메인/kind 불일치는404입니다.

신규 shared-topology 보상은 journal에 기록된 **이번 작업의 추가 grant만** 역순 회수하고, exact marker로 소유권을 입증한 새 account 사용자와 empty personal 프로젝트만 정리합니다. 공통 account/personal domain이나 기존 identity/domain/project·기존 grant는 삭제하지 않습니다. 새 사용자의 추가 외부 권한/그룹과 프로젝트의 리소스·자식 inventory를 재검사하며 증명되지 않으면 정리하지 않습니다. 과거 private-domain receipt와 native provenance는 이전·소급 삭제하지 않습니다. 불확실한 applying/unknown grant나 native create는 현재 부재만으로 끝났다고 판정하지 않고503과 recovery_required를 유지합니다. 현재 system operator의 native 요청 종료 확인 및 exact readback settlement가 선행해야 하며 IAM에는 settlement route가 없습니다. 기존 enrollment settlement와 새 shared/personal settlement의 body·범위는 구분합니다. DELETE204는 확인된 이번 작업의 보상·회수 완료만 뜻하며 남은 native 효과를 성공으로 숨기지 않습니다.

전역 signup은 `/auth/registrations`의 email-first account 계정·personal 프로젝트 생성입니다. `/auth/domains/{domain_id}/registrations`는403 `invitation_required`이며 SQL signup opt-in으로 다시 열 수 없습니다. Migration096은 pending/delivery_pending의 과거 target-domain registration만 회수하고 accepted 계정·invitation·중단된 native-write journal은 보존합니다. `/iam/operations`는 선택한 exact domain의 enrollment 보상이고 nullable global proof 목록이나 account recovery proof API가 아닙니다. 비밀번호/username/본인 email 변경은 별도 [복구 API](auth.md#이메일-소유-기반-계정-복구프로필-이메일-변경)와 migration097을 사용합니다.

Canonical email 소유권·provider stable issuer/sub 연결은 global입니다. 기존 이메일이 여러 home에 있거나 legacy native tuple이 다른 user와 충돌하면 자동 merge/reset하지 않고409로 차단합니다. 운영자는 exact user/home·issuer/sub·native IdP/protocol tuple·멤버십/소유권을 검토한 명시적 이관을 준비해야 합니다. Provider 연결은 본인의 password 또는 authenticated native 계정 proof가 필요하며 manager의 email 초대나 auto-join 설정이 그 proof를 대신하지 않습니다.

## Quota: 도메인 할당 예산과 미래 기본값

### Route와 요청

다음 다섯 route도 `/api/v1/iam`과 같은 live Default manager authority를 사용합니다. System-admin-only ceiling/reconciliation은 별도 경계이며 이 IAM API로 ceiling을 변경하거나 unknown 작업의 fence를 해제할 수 없습니다. Quota 대상 프로젝트는 native 작업 도메인 일치를 요구하지만 **disabled 프로젝트도 조회·할당 계산·quota 갱신 대상**입니다. 일반 멤버 편집의 enabled-only 조건과 다릅니다.

| 메서드·경로 | 정확한 요청 | HTTP200 응답 |
|---|---|---|
| `GET /quotas` | body/query 없음 | DomainQuotaSnapshot |
| `PUT /quotas/defaults` | `{ "revision": 0, "defaults": { "instances": 2, "cores": 4 } }` | 갱신된 DomainQuotaSnapshot |
| `GET /projects/{project_id}/quotas` | body/query 없음 | ProjectQuota |
| `PUT /projects/{project_id}/quotas` | `{ "instances": 3, "cores": 6 }`; `limits` wrapper 없음 | QuotaWrite; status를 반드시 확인 |
| `GET /monitoring` | body/query 없음 | 아래 ManagerMonitoring |

**QuotaMap**은 알려진 key → strict integer(최소-1) object입니다. Boolean·float·문자열 숫자·null·알 수 없는 key는422입니다. Project PUT은 **nonempty 부분 갱신**으로 생략 key는 그대로 둡니다. Defaults PUT은 strict nonnegative `revision`과 `defaults`가 모두 필수이며 extra field는 금지합니다. Defaults는 **전체 교체**이고 `{}`로 지울 수 있습니다. Revision은 ceilings/defaults가 공유하며 초기0, 저장마다1 증가합니다. 오래된 revision은409 `quota_policy_revision_conflict`입니다. Project PUT에는 revision 입력이 없습니다.

| Section | 요청·정책 key | native 응답 key·단위 |
|---|---|---|
| `compute` | `instances`, `cores`, `ram`, `key_pairs`, `server_groups`, `server_group_members`, `injected_files`, `injected_file_content_bytes`, `injected_file_path_bytes`, `metadata_items` | 같은 이름; cores는 vCPU, ram은 MiB, `*_bytes`는 byte, 나머지는 count |
| `volume` | `volumes`, `snapshots`, `gigabytes` | 같은 이름; gigabytes는 GiB, 나머지는 count |
| `network` | `network`, `subnet`, `port`, `router`, `floatingip`, `security_group`, `security_group_rule` | 같은 이름; count |
| `file_storage` | `shares`, `share_gigabytes`, `share_snapshots`, `share_snapshot_gigabytes`, `share_networks`, `share_groups`, `share_group_snapshots` | 순서대로 `shares`, `gigabytes`, `snapshots`, `snapshot_gigabytes`, `share_networks`, `share_groups`, `share_group_snapshots`; gigabytes 계열은 GiB, 나머지는 count |

GPU ledger·provider/model quota·다른 서비스별 한도는 이 QuotaMap에 없습니다. File-storage 요청의 prefix는 Cinder의 동명 key와 구별하기 위한 것으로 native 응답에서는 위 mapping을 사용합니다.

### DomainQuotaSnapshot

```json
{
  "domain_id": "working-domain-uuid",
  "revision": 0,
  "ceilings": {},
  "defaults": {},
  "enforcement_scope": "afterglow_project_allocations",
  "allocations": {
    "instances": { "limit": 0, "status": "ready", "within_budget": true }
  },
  "projects": [],
  "operations": [],
  "allocation_blocked": false,
  "blocking_operation_id": null,
  "drift": false,
  "defaults_future_only": true
}
```

위 allocations는 한 key의 모양을 보여주는 예시이며 실제 응답은 **모든 QuotaMap key**를 포함합니다. Projects는 enabled/disabled를 포함한 native 도메인 inventory의 `{id,name,enabled}` 배열입니다. 정책 미설정 시 revision=0, ceilings/defaults=`{}`입니다.

- Domain ceiling은 **각 프로젝트 native limit의 합계에 대한 할당 예산**입니다. `in_use`나 `reserved` 합계가 아니고, 범용 native domain usage cap도 아닙니다. Afterglow의 프로젝트 생성·enable 및 quota write 경로에서 검증하며 외부 native 관리자의 직접 변경까지 막는다고 보장하지 않습니다.
- Ceiling 미지정 key 또는 ceiling=-1은 Afterglow 예산 제한 없음입니다. Native 프로젝트 limit=-1도 unlimited이지만 **유한 ceiling 아래에서는 할당 합계를 증명할 수 없어 거부**합니다. 0은 실제 zero limit이지 unknown/unlimited가 아닙니다.
- Allocations의 `limit`는 알려진 유한 limit들의 합계(`status:"ready"`), 하나라도 native unlimited면-1(`"unlimited"`), 하나라도 읽기 불가/필드 누락이면 null(`"unavailable",error:"quota_unavailable"`)입니다. Unknown이 unlimited보다 우선합니다. 프로젝트가 없으면 유한 합계0입니다.
- `within_budget`는 unavailable이면 null, ceiling 없음/-1이면 알려진 allocation에 true, finite ceiling이면 유한 합계와 비교한 boolean입니다. `drift`는 하나라도 within_budget=false인 경우만 true이므로 **drift=false가 관측 완전성을 뜻하지 않습니다.**
- Defaults는 **앞으로 생성하는 프로젝트만** 사용하며 기존 프로젝트를 덮어쓰지 않습니다. 각 default 자체가 해당 finite ceiling보다 크거나 unlimited이면409 `quota_default_exceeds_ceiling:<key>`입니다. Defaults 저장은 미래 여러 프로젝트 몫을 예약하지 않으며, 실제 생성 시 기존 disabled 프로젝트까지 포함한 allocation을 다시 검증합니다. 새 프로젝트는 quota/default readback을 확인하기 전 enable하지 않습니다. 생략 default key는 native 기본 limit를 그대로 예산 계산에 포함합니다.
- 동시 Afterglow allocation/policy 변경은 공유 graph mutation lease와 SQL journal 경계를 사용합니다. 변경 대상 limit를 제안값으로 **치환한 뒤** 합산하므로 기존 target limit를 이중 계산하지 않습니다. Finite ceiling의 다른 프로젝트가 unknown/unlimited면409 `quota_budget_unverifiable:<key>`, 초과이면409 `quota_budget_exceeded:<key>`입니다. 외부 drift를 줄이는 명시적 target limit 감소는 아직 예산 초과여도 허용될 수 있지만 unrelated 초과 항목이나 증가는 허용하지 않습니다.
- 요청 key의 native section/필드를 사전 관측할 수 없으면503 `quota_native_preflight_unavailable`이며 쓰기하지 않습니다. 도메인 불일치는403 `quota_domain_mismatch`/`quota_project_domain_mismatch`, 프로젝트 부재는404 `project_not_found`, native/정책 storage 확인 불가는503입니다. 응답 오류는 IamRoute의 `{detail:"고정 오류 code 또는 메시지"}` 형식이며 이 quota API에 별도 top-level code 필드는 없습니다.

### ProjectQuota와 native usage

ProjectQuota는 `{project_id,compute,volume,network,file_storage,availability,errors}`입니다. 각 성공 section은 **native key** → `{limit,in_use,reserved?}` object입니다. Limit는 strict integer ≥-1, in_use는 nonnegative integer이며 reserved는 native가 nonnegative integer로 제공한 경우만 있습니다. Neutron의 `used`를 `in_use`로 정규화합니다. Reserved 부재를0으로 만들거나 limit와 actual usage를 같은 수치로 표시하지 않습니다. Native가 노출하지 않은 optional quota key는 **생략**합니다.

Section별 실패는 HTTP200 안에서 해당 section=null, `availability[section]=false`, `errors[section]="quota_unavailable"`로 반환하며 다른 section 결과는 보존합니다. Disabled Manila는 같은 null/false에 `"service_disabled"`입니다. 성공 section은 availability=true이며 errors에 해당 key가 없습니다. 이는 service/field 가용성이지 zero usage 증거가 아닙니다.

### QuotaWrite·operations와 recovery

QuotaWrite는 `{project_id,domain_id,operation_id,status,updated,errors}`입니다. Operation_id는 **UUID 문자열**이고, updated는 확인된 section 이름 배열, errors는 section → 안전한 오류 code입니다. HTTP200은 모든 native section이 갱신됐다는 뜻이 아닙니다.

| Write `status` | 의미 |
|---|---|
| `updated` | 요청한 모든 section이 native 성공 응답 뒤 readback 일치 |
| `partial` | native 호출은 반환했지만 일부 readback이 요청과 다름; `native_readback_mismatch` |
| `unknown` | native 호출 실패/timeout 또는 readback 불가; `native_outcome_unknown`/`native_readback_unavailable` |

각 section의 intent를 SQL에 저장한 후 native PUT을 한 번 호출하고, **예외가 나도 readback**합니다. 단, 호출 실패 뒤 현재 값이 요청과 같아도 원래 controller가 종료됐다는 증거가 아니므로 unknown입니다. Unknown이 나오면 뒤 section은 실행하지 않고 errors=`not_attempted`로 남깁니다. 부분 쓰기를 자동 rollback/retry하지 않습니다. 각 응답 후 프로젝트 quota cache를 무효화합니다.

`GET /quotas`의 operations는 최대50개이며 applying/unknown을 우선하고 그 안에서 최신 created_at 순입니다. 각 항목은 `{id,project_id,status,requested,sections,created_at}`이고 requested는 원래 flat QuotaMap입니다. Sections는 native key 기반 observed limit와 phase를 보존합니다. Phase는 `pending`, `writing`, `verified`, `partial`, `unknown`이고 error/observed는 가용한 경우만 있습니다. Operation status는 실행 중 `applying`, 완료 `updated/partial/unknown`, 운영자 readback 정리 후 `reconciled`입니다. Reconciliation section은 `observed`, `not_attempted`, `project_deleted`일 수 있습니다.

**Applying/unknown 작업 하나라도 있으면** domain의 후속 allocation/default/policy 변경을409 `quota_native_operation_unresolved`로 막고 snapshot의 allocation_blocked=true 및 blocking_operation_id로 표시합니다. 이 journal은 enrollment의 `GET /operations`와 **다릅니다**. Enrollment DELETE로 quota 작업을 지우거나 원래 quota PUT을 반복하지 않습니다. System operator가 원 native 호출의 종료를 별도로 확인한 뒤 전용 system-admin reconciliation에서 strict `native_calls_settled:true`와 현재 readback을 기록해야 합니다. 이는 요청값 달성/rollback을 보장하지 않고 현재 실제 limit를 수용하는 recovery이며, provider write/replay를 수행하지 않습니다. 새 disabled 프로젝트가 생성 보상으로 삭제됐다면 native GET 부재와 domain directory 부재를 함께 확인해야 fence를 해제합니다. Readback 불가이면503으로 fence를 유지하고, 성공 후에도 남은 drift는 표시·예산 검증됩니다.

## ManagerMonitoring: 프로젝트·사용자·리소스 관측

`GET /monitoring`는 query window나 pagination 없이 현재 작업 도메인의 snapshot을 반환합니다. 응답은 `{domain,projects,users,resources,inventory,coverage}`입니다. Domain directory 실패는 요청 전체 오류로 반환하고, 개별 native service 관측 실패는 metric 상태로 남깁니다. 시스템 전체 traffic/session/application credential 관측이나 secret은 이 DTO에 포함하지 않습니다.

| 필드 | 정확한 모양·의미 |
|---|---|
| `domain` | `{id,name,enabled}`; name은 display name |
| `projects` | `[{id,name,enabled,quotas:ProjectQuota,resources:[Metric]}]`; disabled 포함 |
| `users` | `[{id,name,domain_id,enabled,project_ids,membership_state,resources:[Metric]}]`; home 및 현재 joined identity, domain_id는 home |
| `resources` | 도메인 프로젝트에 귀속되는 resource metrics 및 quota allocation metrics |
| `inventory` | `[{category,id,name,project_id,user_id,status}]`; 명시적으로 이 도메인 project 소유임을 확인한 resource만, user_id/status는 nullable |
| `coverage` | `{observed_at,partial,notes}`; ISO timestamp, 완전성 boolean 및 안전한 사유 문자열 배열 |

Metric은 `{service,metric,kind,value,unit,status,error?}`입니다. Kind는 `count`, `utilization`, `allocation`; unit은 `count`, `vcpu`, `MiB`, `GiB`, `bytes`입니다. Status는 `ready`, `partial`, `unavailable`, `denied`, `disabled`, `unlimited`이며 관측 불가/unlimited value는 null입니다. Quota allocation metric 이름은 `quota_<요청 key>`입니다. 이 합계 역시 프로젝트 **limit의 합계**이지 사용량이 아니며 실제 in_use/reserved는 projects[].quotas에 있습니다. Resource utilization은 현재 inventory에서 읽은 instances의 vCPU/RAM과 volumes의 size 합계로, CPU 사용률이나 시간대별 소비량이 아닙니다.

Native 프로젝트 귀속을 확인할 수 있는 instances, volumes/snapshots/backups, floating IPs, networks/subnets/routers/security groups, load balancers, images, containers, shares/share snapshots/share networks/security services를 관측합니다. 다음은 이 whole-domain 집계 경계에서 지원하지 않아 enabled 서비스라도 `unavailable`/`domain_aggregate_unsupported`입니다: keypairs, database_instances/database_backups, k3s_clusters, waygate_gateways, magnum_clusters, buckets, packages, secrets. 서비스 설정이 꺼져 있으면 `disabled`/`service_disabled`입니다. Native 거부는 `denied`/`native_denied`, 장애는 `unavailable`/`native_unavailable`, 소유 project 확인 불가는 `owner_unavailable`로 표시합니다. 일부 귀속만 확인되면 partial로 알려진 행만 반환하며, 빈 inventory만으로 미지원 서비스가 비었다고 해석하지 않습니다.

**사용자 귀속의 한계:** project_ids는 native effective project assignment 관측 결과이며 리소스 소유자/생성자를 뜻하지 않습니다. Membership 조회 실패 시 membership_state=`unavailable`이고 project_ids는 확인된 부분만 남을 수 있으므로 빈 배열을 authoritative 무소속으로 표시하지 않습니다. Resource의 `user_id` 또는 `os-extended-snapshot-attributes:user_id`가 실제 directory 사용자와 일치할 때만 해당 사용자 metrics에 포함합니다. 현재 로그인 사용자·프로젝트 owner·멤버 전체에게 공유 리소스를 임의 배분하지 않습니다. 어느 resource든 user 귀속을 확인할 수 없으면 해당 category의 사용자 metrics를 partial/`user_attribution_unavailable`로 표시하고, inventory.user_id=null 및 coverage.notes에 `<category>:user_attribution_unavailable`을 남깁니다. 도메인/프로젝트 합계는 여전히 그 resource를 포함할 수 있습니다. **프로젝트 native quota를 사용자별 quota로 나누거나 사용자별 enforcement를 제공하지 않습니다.**

Coverage.partial은 membership/귀속 누락 또는 ready/disabled/unlimited가 아닌 domain metric이 있으면 true이며 notes에 `project_memberships_unavailable`, category별 귀속 사유, `resources_incomplete`가 포함될 수 있습니다. `observed_at`은 snapshot 생성 시각이지 모든 native 서비스의 원자적 동시 측정 보장이 아닙니다.

### 현재 구현상 주의

- 초대·멤버 추가의 경계: email로 도메인 가입을 초대하는 IAM API는 manager-only입니다. Project owner/admin은 이미 joined인 eligible 사용자를 project 역할 관리로 추가합니다. 이 직접 추가 경로와 도메인 email 초대는 서로 다른 권한 경계입니다.

계약 근거: [IAM schemas/routes](../../backend/app/api/identity/iam.py), [enrollment service](../../backend/app/services/domain_iam.py), [project membership/ownership service](../../backend/app/services/project_service.py), [quota routes](../../backend/app/api/identity/domain_quotas.py), [quota schemas](../../backend/app/models/domain_quotas.py), [allocation orchestration](../../backend/app/services/domain_quotas.py), [native quota adapter](../../backend/app/services/quota_native.py), [manager monitoring](../../backend/app/services/domain_monitoring.py).

## 로그인 정책

LoginPolicy:

```json
{
  "domain_id": "domain-uuid",
  "password_enabled": true,
  "allowed_email_domains": [],
  "signup_enabled": false,
  "signup_email_domains": [],
  "revision": 0,
  "configured": false,
  "smtp_configured": true,
  "usable_provider_count": 0
}
```

`smtp_configured`와 `usable_provider_count` 값은 예시입니다. 정책을 저장한 적 없으면 password=true, login allowlist=[], signup=false, signup allowlist=[], revision=0, configured=false입니다. SMTP flag는 설정된 SMTP enabled/host를 반영하며 실제 배달 성공 증거가 아닙니다. Usable provider count는 enabled/configured이며 **현재 revision에서 native federated session 발급에 성공한** provider 수입니다.

PUT body는 정확히 `{password_enabled,signup_enabled,allowed_email_domains?,signup_email_domains?,revision?}`입니다. 두 boolean은필수, 각 host 배열 기본[]·최대100개, revision은선택 nonnegative integer/null입니다. Host는 wildcard·`@` 없이 정확한 IDNA lowercase ASCII host로 정규화·중복제거·정렬합니다. 빈 login allowlist는 email host 제한 없음입니다. Signup opt-in은 nonempty signup list가 필요하며 login list가 제한적이면 그 subset이어야 합니다.

Email host는 입력 trim·trailing dot 제거 후 최대253자이며 IDNA 정규화 뒤 최소2개 DNS label이 필요합니다. 각 label은1–63자 소문자 영숫자/`-`이고 앞뒤 `-`는 금지하며 최종 label은 숫자만일 수 없습니다. Login allowlist가 비어 있으면 기존 password 계정의 email 부재/invalid email을 강제 수정하지 않습니다. IAM 계정 생성·초대·onboarding은 전달/검증 가능한 email이 필요하므로 별도 email 검증을 계속 수행합니다.

성공 PUT은 revision을1 올립니다. Expected revision 불일치는409 `revision_conflict`; signup domain 없음은422 `signup_domains_required`, login allowlist 밖의 signup host는422 `signup_domain_not_allowed`, SMTP 미설정은409 `smtp_not_configured`. Password를 끄려면 다른 usable provider가 필요하며 없으면409 `last_login_method`입니다. 먼저 password를 유지한 상태에서 provider의 **실제 로그인**을 성공시켜야 합니다. Configuration/discovery 성공만으로 검증됐다고 취급하지 않습니다.

위 SQL `signup_enabled/signup_email_domains`는 **전역 email-first 가입이나 tenant-local 사용자 생성 권한이 아닙니다**. 기존 조직에 아직 멤버십이 없는 verified OIDC 사용자의 자동 참여에서 운영자 파일의 provider별 `auto_join_email_domains` proof에 **추가 제한**으로 적용됩니다. 저장된 domain policy가 있으면 signup_enabled=true와 exact signup_email_domains 일치가 모두 필요하며 false/불일치는 조직 참여를 거부합니다. SQL row가 없으면 기존 파일 auto-join baseline을 유지합니다. 기존 멤버는 이 신규 참여 제한의 대상이 아니지만 login allowed_email_domains 검사는 계속 적용됩니다. Manager가 file issuer trust·전역 signup·로그인 화면 표시 정책을 확장할 수 없고, 계정 생성은 여전히 Accounts identity+Personal로 제한됩니다. 기존 조직 생성 capability와 per-domain registration403 계약도 유지합니다. 전역 signup은 system enrollment policy와 operator `[auth].public_signup_enabled/signup_email_domains`, 기본 조직 auto-join ceiling은 `[auth.default]` 또는 exact `[auth.domain."<ID>"]`의 map이며 도메인 전체 대체/생략 상속·기본 거부·provider별 exact host·allow_providers를 함께 요구합니다.

## Provider CRUD 필드

Provider response는 다음 필드를 포함하며 secret은 절대 반환하지 않습니다.

| 필드 | 타입·의미 |
|---|---|
| `id`, `domain_id`, `name`, `kind` | string; kind=oidc/github |
| `issuer_url`, `authorization_url`, `token_url`, `api_url` | nullable string; 현재 normalized/pinned endpoint |
| `client_id` | string |
| `client_secret_configured` | boolean; secret 존재 여부만 |
| `scopes` | string array |
| `keystone_idp_id`, `keystone_protocol_id` | string; 해당 domain의 native federation 연결 |
| `enabled` | boolean |
| `revision` | integer; 최초 생성1, security edit마다 증가 |
| `verified` | boolean; enabled/configured 및 verified_revision==revision, verified_at 있음 |
| `verified_revision`, `verified_at` | nullable integer/ISO timestamp; 성공한 실제 native session issuance만 설정 |
| `federation_token_type` | id_token 또는 access_token |
| `token_endpoint_auth_method` | nullable string; client_secret_basic/post |
| `created_at`, `updated_at` | nullable ISO timestamp |

ProviderCreate는 `name`, `kind`, `client_id`, `client_secret`, `keystone_idp_id`, `keystone_protocol_id` 필수이며 나머지는 아래 선택 필드입니다. ProviderUpdate는 같은 필드를 부분 갱신하며 `revision?`을 expected revision으로 추가합니다. Kind는 최초 생성 후 불변(422 `kind_immutable`). Verification 필드·id/domain_id·timestamp·client_secret_configured는 **입력 금지**입니다.

| 입력 | 제한·기본값 |
|---|---|
| `name` | 1–64자·trim·control character 금지·고유 domain-local 이름 |
| `kind` | oidc 또는 github |
| `client_id` | 1–255자·trim·내부 공백/control character 금지 |
| `client_secret` | 1–4096자, **write-only**; PATCH 생략/null이면 기존 secret 유지 |
| `issuer_url`, `authorization_url`, `token_url`, `api_url` | 각 nullable·최대512자; kind별 의미는 아래 |
| `scopes` | 생성 생략/null은 kind 기본값; PATCH 생략/null은 unchanged. 최대20개·각1–128자 printable ASCII(공백·double quote·backslash 제외); 빈 배열 금지·중복제거 |
| `keystone_idp_id`, `keystone_protocol_id` | 1–64자 영숫자/`_`/`.`/`-` |
| `federation_token_type` | OIDC 기본id_token; access_token 선택 가능; GitHub는access_token |
| `token_endpoint_auth_method` | OIDC discovery가 광고한 Basic/Post만; 미지정은Basic 우선, discovery 미제공은Basic. GitHub는Post |
| `enabled` | 생성 기본true; PATCH 생략/null unchanged |
| `revision` | PATCH만, 선택 nonnegative integer/null; 불일치409 revision_conflict |

PATCH의 non-clearable field null은 unchanged이며 endpoint/auth-method null은 kind별 normalization/rediscovery에 전달합니다. OIDC는 issuer를 필수로 받고 authorization/token endpoint를 discovery에서 읽어 pin합니다. 이 derived endpoint에 임의 nonempty 값을 입력하면422 `invalid_endpoints`; API URL은null입니다. Access-token federation도 ID token을 로컬 검증하며 UserInfo `sub` 일치가 필수입니다. GitHub는 issuer를 받지 않고 endpoint 생략 시 `https://github.com/login/oauth/authorize`, `https://github.com/login/oauth/access_token`, `https://api.github.com`을 사용합니다. OIDC scope 기본openid/email/profile(필수openid/email), GitHub 기본read:user/user:email(필수user:email)입니다.

Provider URL은 public HTTPS, credential/fragment 금지이며 issuer/api URL에는 query도 금지입니다. Authorization/token query는 허용하지만 OAuth reserved key 충돌은422 `unsafe_url`입니다. Authorization reserved keys: client_id,redirect_uri,response_type,scope,state,nonce,code_challenge,code_challenge_method,response_mode,request,request_uri. Token reserved keys: client_id,client_secret,code,code_verifier,grant_type,redirect_uri. DNS/실제 outbound destination의 SSRF 경계와 TLS 검증을 유지하고 redirect를 따라가지 않습니다.

CRUD는 Keystone IdP·protocol 존재와 IdP enablement를 read-only로 확인합니다(422 `idp_not_found`, `idp_disabled`, `invalid_keystone_federation`; 확인 장애503). IdP의 default domain과 작업 도메인이 같아야 한다는 검사는 없습니다. 실제 callback/link에서 mapping을 검사합니다. 운영자 registry OIDC는 Accounts `type: local` email 매핑과 로그인 조직 기존 그룹의 조건부 규칙을, 그 외 공급자는 user-only stable-sub mapping을 사용하며 native 결과의 exact user ID/home과 canonical 계정 연결을 확인합니다. Projects/roles·cross-domain·무조건 group provisioning은 거부하며 unsafe/조회 불가는503 `native_mapping_unsafe`입니다. CRUD가 IdP/mapping을 생성하거나 federation 성공을 증명하지는 않습니다. Native는 전체 `federated` tuple PATCH와 readback을 지원해야 하며 연결은 원래 local password/home/email/name/default project와 다른 tuple을 보존합니다. Secret은 domain/provider에 묶인 encrypted ciphertext로 저장합니다.

## Revision·검증·마지막 로그인 방법 보호

Security edit 대상은 issuer/authorization/token/api URL, client_id, scopes, Keystone IdP/protocol, federation token type, token auth method, enabled, secret 교체입니다. 실제 변경(또는 secret 제공)은 revision을 올리고 verified_revision/verified_at을 null로 초기화하여 pending state 및 세션을 무효화합니다. 표시 이름만 변경하면 revision/proof를 유지합니다.

기존 secret을 유지하는 동안 token destination은 pin됩니다. Issuer 또는 token URL 변경은 새 secret이 필요하고 누락은422 `client_secret_replacement_required`. Discovery drift도409 `provider_changed`로 로그인 중단하며 secret과 함께 issuer를 다시 제출해 discovery endpoint를 새로 pin해야 합니다. 새 URL로 기존 secret을 자동 전송하지 않습니다.

Password가 꺼진 동안 마지막 proven provider의 security edit·disable·delete는409 `last_login_method`입니다. 먼저 password를 다시 켜거나 대체 provider에서 실제 native session을 발급해 exact revision proof를 확보합니다. 성공 callback 뒤 session 저장과 proof stamp 사이에 revision이 바뀌어도409 `provider_changed`를 반환하고 생성 session을 revoke/delete합니다.

Provider 없음/foreign domain은404 `provider_not_found`, 이름 충돌409 `provider_name_conflict`, stale write409 `revision_conflict`, 잘못된 scopes422 `invalid_scopes`, 지원하지 않는 client auth422 `unsupported_token_auth_method`, access-token federation의 UserInfo 없음422 `userinfo_required`, provider/discovery 오류502 `provider_error`, SQL/Keystone/secret storage 장애503 `unavailable`입니다. 이 오류는 `{detail,code}` 형식이며 provider authorize/callback cookie·PKCE·nonce·same-site 계약은 [인증 API](auth.md#도메인-우선-로그인과-provider-federation)를 따릅니다.
