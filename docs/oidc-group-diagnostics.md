# How to: 별도 GitLab 클라이언트로 OIDC 그룹 클레임 확인하기

`scripts/oidc_group_probe.py`는 **새 진단 전용 OAuth 애플리케이션**으로 로그인하여 검증된 ID 토큰과 UserInfo의 그룹 값을 따로 기록하는 일회성 로컬 콜백이다. Afterglow 로그인 경로·설정·배포와 Keystone federation·mapping·그룹·역할·프로젝트는 변경하지 않는다. 이 문서 작성 시 신규 클라이언트 발급이나 사람의 로그인, live federation 요청, native 쓰기는 수행하지 않았다. 실제 신규 자격으로의 수락 여부는 운영자가 아래 절차로 확인해야 한다.

## 1. 진단 전용 애플리케이션 준비

GitLab의 **프로필 편집 → Access → Applications → Add new application**에서 새 사용자 소유 앱을 만든다. 화면 명칭은 설치 버전에 따라 다를 수 있다.

- 운영 Afterglow/Keystone 앱과 구별되는 이름을 사용하고 **Confidential**을 선택한다. 기존 앱을 재사용하거나 기존 앱의 **Renew secret**을 누르지 않는다. 갱신하면 운영 앱의 기존 secret이 무효화된다.
- Redirect URI는 정확히 **`http://127.0.0.1:8765/callback`** 하나를 등록한다. `localhost`, 다른 포트·경로·마지막 슬래시로 바꾸지 않는다. HTTP는 이 loopback 콜백에만 사용하며 GitLab 통신은 HTTPS다.
- Scope는 **`openid profile email`**만 선택한다. `api`, `read_api`, `read_user` 등은 필요 없다. 그룹 확인을 위해 API 권한을 늘리지 않는다.
- 새 Application ID와 secret은 개인 비밀 저장소에 보관한다. Secret을 채팅·명령 인자·환경 변수·저장소·화면 공유에 붙여 넣지 않는다. 일반 사용자 동의 흐름을 유지하고 trusted 앱으로 만들지 않는다.

기존 `backend/.venv`에 프로젝트 의존성이 설치된 체크아웃과 대화형 터미널을 사용한다. 진단을 위해 운영 앱 설정이나 Python 환경을 교체하지 않는다.

## 2. 터미널 A에서 실행하고 같은 브라우저로 로그인

저장소 루트에서 실행한다. 아래 `NEW_DIAGNOSTIC_CLIENT_ID`는 **새 앱의 ID로만** 바꾼다. Secret은 옵션이 아니라 `getpass` 프롬프트에 입력하므로 화면에 표시되지 않는다.

```sh
backend/.venv/bin/python scripts/oidc_group_probe.py \
  --issuer https://git.dmslab.re.kr \
  --client-id 'NEW_DIAGNOSTIC_CLIENT_ID'
```

`--client-id`를 생략하면 ID도 대화형으로 입력할 수 있다. 기본 scope는 `openid profile email`, 포트는 `8765`, 인가 대기 시간은 `300`초다. `--client-secret` 옵션이나 insecure 모드는 없다. 프로세스는 환경 변수의 proxy 설정을 사용하지 않는다.

1. 터미널에 출력된 redirect URI가 앱 등록값과 같은지 확인한다.
2. 출력된 **무작위 일회용 `http://127.0.0.1:8765/start/...` URL을 직접 연다.** `/callback`을 수동 호출하거나 GitLab 인가 URL만 다른 브라우저로 복사하지 않는다. 시작 URL이 설정한 브라우저 쿠키와 state가 콜백에 함께 필요하다.
3. 조사할 사용자로 GitLab에 로그인하고 새 앱의 최소 권한 동의 화면을 확인한다. 브라우저의 일반 성공 문구와 터미널의 `Private report:` 경로를 확인한다. 보고서는 HTTP로 제공되지 않는다.

브라우저는 기본적으로 **스크립트와 같은 컴퓨터**에 있어야 한다. 다른 컴퓨터의 `127.0.0.1`은 스크립트 컴퓨터가 아니다. 원격 호스트에서 실행해야 한다면 브라우저 컴퓨터의 별도 터미널에 다음과 같이 **명시적인 SSH loopback 전달**을 유지한다. `operator@probe-host.example`은 운영자가 승인한 진단 호스트로 바꾸며 양쪽 포트 `8765`는 비어 있어야 한다.

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 operator@probe-host.example
```

스크립트는 원격 호스트에서 실행하고, 출력된 시작 URL은 SSH를 연 컴퓨터의 브라우저에서 연다. 등록 redirect URI는 그대로다. `0.0.0.0` 바인딩·공개 터널·운영 reverse proxy 추가는 하지 않는다. 원격 실행 시 결과 파일도 원격 호스트에 생긴다.

### 선택: 기존 개인 secret 파일 사용

비밀 저장소 등으로 **저장소 밖**에 준비한 파일만 사용한다. 파일은 현재 사용자 소유, 일반 파일, 링크 수 1, symlink 아님, 권한 `0600` 또는 그보다 제한적, 최대 16 KiB여야 한다. 내용은 새 앱의 secret 하나이며 끝의 개행만 제거된다. Shell의 `echo SECRET`로 만들지 않는다.

```sh
backend/.venv/bin/python scripts/oidc_group_probe.py \
  --issuer https://git.dmslab.re.kr \
  --client-id 'NEW_DIAGNOSTIC_CLIENT_ID' \
  --client-secret-file "$HOME/.local/share/afterglow/oidc-probe-secret"
```

기본 출력은 저장소 밖의 `~/.local/share/afterglow/oidc-probes/probe-<random>/report.json`이다. 실제 경로는 터미널 출력을 따른다. 디렉터리는 `0700`, 결과 파일은 `0600`으로 생성된다. `--output-dir`을 지정한다면 신규 개인 경로를 사용한다. 기존 디렉터리는 현재 사용자 소유의 private 디렉터리여야 하며 기존 결과 파일은 덮어쓰지 않는다.

## 3. 보고서 해석

이 콜백은 code + PKCE S256, state·브라우저 바인딩·nonce를 사용한다. Discovery/JWKS에 따른 ID 토큰 RS256 서명, issuer·audience·유효시간과 해당되는 `azp`·`at_hash`를 검증하고, UserInfo의 `sub`가 ID 토큰과 같을 때만 보고서를 생성한다. 토큰·secret·전체 원문 응답은 저장하지 않는다.

`report.json`에서 다음을 **각각** 읽는다. URL 형식의 claim 키는 점 경로가 아니라 JSON 객체의 정확한 키다.

| 보고서 항목 | 의미 |
| --- | --- |
| `issuer`, `client_id`, `requested_scope`, `granted_scope` | 사용한 issuer·새 클라이언트와 요청/응답 scope. 응답에 scope가 없으면 `granted_scope`는 `null`이며 임의로 보완하지 않는다. |
| `identity` | ID 토큰의 허용된 `sub`, `preferred_username`, `email`, `email_verified`만 기록. 없는 필드는 생략한다. `email` scope가 있어도 이메일 공개 정책 등에 따라 누락될 수 있다. |
| `id_token.claim_names`, `userinfo.claim_names` | 각 응답에 실제 존재한 claim 이름. 이름이 있다고 값의 모양까지 유효한 것은 아니다. |
| `id_token.group_claims`, `userinfo.group_claims` | 아래 다섯 그룹 claim의 존재 여부·JSON 유형·정확한 문자열 배열을 출처별로 기록. 다른 출처로 대체하거나 병합하지 않는다. |
| `comparison` | ID 토큰 `groups_direct`와 UserInfo `groups`가 모두 문자열 배열일 때만 `comparable=true`. `direct_only`는 전자에만, `all_only`는 후자에만 있는 값의 집합 차이다. 원래 배열은 해당 `values`에 보존된다. |
| `verification` | 토큰 검증·subject 일치와 **`keystone_transport_observed=false`**를 구분한다. Keystone WSGI 환경을 관찰했다는 뜻이 아니다. |

GitLab 공식 문서의 의미는 다음과 같다. 설치 버전·정책의 실제 응답은 이 보고서와 대조한다.

| 정확한 raw claim 이름 | 문서상 출처와 의미 |
| --- | --- |
| `groups_direct` | **ID 토큰**: 직접 회원인 그룹의 **경로**. 상위 그룹에서 상속한 멤버십 전체 목록이 아니다. |
| `groups` | **UserInfo**: 직접 또는 상위 그룹을 통해 회원인 그룹의 **경로**. |
| `https://gitlab.org/claims/groups/owner` | **UserInfo**: 직접 Owner인 그룹의 **이름**. |
| `https://gitlab.org/claims/groups/maintainer` | **UserInfo**: 직접 Maintainer인 그룹의 **이름**. |
| `https://gitlab.org/claims/groups/developer` | **UserInfo**: 직접 Developer인 그룹의 **이름**. |

역할별 claim의 그룹 **이름**을 전체 경로·UUID나 Keystone 역할명으로 해석하지 않는다. 동명이 가능하고, 세 역할 claim이 모든 GitLab 역할을 열거하는 것도 아니다. `all_only`를 무조건 상속 그룹이라고 확정하거나 `groups_direct ⊆ groups`를 강제하지 않는다. 응답 시점·버전·정책 차이를 조사할 단서다.

각 `group_claims[정확한 키]`의 상태를 구분한다.

- `status="missing"`, `json_type="missing"`, `values=null`: claim이 **없다**. 그룹이 0개라는 증거가 아니다.
- `status="array"`, `json_type="array"`, `values=[]`: claim이 존재하고 **빈 문자열 배열**이다.
- `status="array"`, 비어 있지 않은 `values`: 정확한 문자열 목록. 경로의 대소문자·하위 경로·원래 값을 보존한다.
- `status="invalid"`, `values=null`: `null`, 문자열, 객체, 숫자, boolean 또는 문자열 아닌 원소가 섞인 배열 등이다. `json_type`을 확인하며 빈 배열로 바꾸지 않는다.

### GitLab 연동 그룹은 소문자로 지정

2026-10-26 사용자 실측으로 현재 GitLab 환경의 `groups`와 `groups_direct` 모두 그룹 값이 소문자로 전달되는 것을 확인했다. GitLab 관리자 페이지의 소문자 정규화에 맞춰, **GitLab과 연동할 Afterglow의 그룹도 소문자로 생성·지정해야 자동 매핑된다.** 모든 그룹에 적용하는 이름 규칙이 아니라 GitLab 연동 대상 그룹의 운영 조건이다.

매핑 대상 도메인에서 그룹 이름을 실제 claim의 **전체 경로와 대소문자까지 동일하게** 맞춘다. 예를 들어 claim 값이 `research/ml-team`이면 이 시스템의 연결 대상 그룹 이름도 `research/ml-team`이어야 하며, `Research/ML-Team`이나 마지막 경로만 딴 `ml-team`으로 지정하지 않는다. GitLab 화면의 표시 이름보다 진단 보고서의 실제 값을 기준으로 확인한다.

이는 연결할 그룹의 이름을 준비하는 절차이며, Afterglow나 진단 도구가 claim·기존 그룹 이름을 자동으로 소문자로 바꾸거나 대소문자를 무시해 매핑한다는 뜻은 아니다. 기존 그룹의 일괄 이름 변경이나 신규 권한 부여는 수행하지 않는다.


## 4. 선택: mapping_engine용 후보 입력 내보내기

다음은 **ID 토큰의 `groups_direct`만** 선택하는 별도 진단 실행이다. `--mapping-source`와 `--mapping-claim`은 함께 지정한다. 새 실행마다 새 시작 URL로 로그인한다.

```sh
backend/.venv/bin/python scripts/oidc_group_probe.py \
  --issuer https://git.dmslab.re.kr \
  --client-id 'NEW_DIAGNOSTIC_CLIENT_ID' \
  --mapping-source id_token \
  --mapping-claim groups_direct
```

성공하면 같은 개인 출력 디렉터리에 `report.json`과 `mapping-input.txt`가 생긴다. 후자는 Keystone CLI의 `key: value` 행 형식으로, 기본 prefix `OIDC-` 및 그룹 구분자 `;`를 사용한다. 예를 들어 키는 `OIDC-iss`, `OIDC-preferred_username`, `OIDC-groups_direct`다. 선택 claim이 missing/invalid이면 다른 출처를 대신 사용하지 않고 export가 실패한다. 빈 배열은 빈 그룹 값의 행으로 보존한다. 그룹 원소에 빈 문자열·세미콜론·제어 문자가 있으면 모호한 변환을 거부한다. 보고서만 남았다고 export까지 성공한 것은 아니므로 종료 상태와 두 파일을 구분한다.

**터미널 B**에서는 운영과 **동일한 Keystone 설치 버전·mapping schema를 갖춘 격리 진단 컨테이너**를 사용한다. 운영 서비스 컨테이너를 변경하지 않고, 네트워크와 운영 DB·credential·설정 마운트 없이 준비한다. 운영자가 제공한 로컬 rules 사본과 후보 입력만 read-only로 사용할 수 있어야 한다. 아래 두 `/probe/...` 경로는 그 컨테이너 안에서 읽을 수 있는 실제 개인 파일 경로로 바꾼다. 이 명령은 rules를 서버에 등록하지 않는 **오프라인 평가**다.

먼저 같은 설치본의 도움말에서 schema 처리와 rules 형식을 확인한다. 최신 공식 CLI 소스는 rules의 기존 `schema_version`을 유지하며, 명시적 override는 `--mapping-schema-version`으로 정의한다. 아래 예시는 운영자가 제공한 rules 사본의 `schema_version: "2.0"`을 그대로 사용하는 형식이다. 설치 버전의 동작은 도움말과 대조하며, 필요한 경우에만 설치본이 실제 지원하는 옵션으로 `2.0`을 선택한다. 지원하지 않는 옵션을 추측하거나 schema `1.0`으로 낮추지 않는다. 해당 설치본이 schema `2.0`을 처리하는 방법을 확인하기 전에는 평가를 진행하지 않는다.

```sh
keystone-manage --config-file /dev/null mapping_engine --help
```

```sh
umask 077
keystone-manage --config-file /dev/null mapping_engine \
  --rules /probe/operator-rules.json \
  --input /probe/mapping-input.txt
```

`keystone-manage`가 PATH에 없다면 운영자가 확인한 해당 설치본의 절대 경로로 실행한다. Rules는 해당 설치본이 지원하는 JSON/schema 형식이어야 한다. 출력에도 identity·그룹·프로젝트 정보가 포함될 수 있으므로 개인 터미널에서만 확인한다. 성공은 **주어진 로컬 rules와 후보 입력의 변환 결과**일 뿐 그룹·역할·도메인의 native 존재, 프로젝트 접근 권한, 실제 federation 성공을 입증하지 않는다. `mapping_populate`, mapping 등록/변경, federation 로그인, IAM provisioning은 이 절차에 포함하지 않는다.

### raw claim과 실제 native transport는 다르다

Keystone은 보통 원본 ID 토큰이 아니라 Apache 등 인증 모듈이 전달한 환경 속성을 매핑한다. `groups_direct` → `OIDC-groups_direct` 또는 `HTTP_OIDC_GROUPS_DIRECT`라는 이름·대소문자·구분자는 배포 설정에 달려 있다. `--mapping-prefix HTTP_OIDC_`는 대문자 키의 **다른 후보 형식**을 만들 뿐 실제 transport를 캡처하지 않는다.

2026-10-26 운영자 파일 readback의 `/etc/kolla/docs/keystone-dmslab-oidc.md`와 `git.dmslab.re.kr.keystone_identity_mapping.json`은 schema `2.0` rules의 `OIDC-preferred_username`, `OIDC-email`, `OIDC-groups_direct` 및 `OIDC-email_verified` 조건을 가리킨다. 가이드는 `dmslab_oidc_transport`가 `HTTP_OIDC_*`를 `OIDC-*`로 정규화하고 boolean `1/0`을 `true/false`로 처리한다고 설명한다. 이는 **파일 근거**이며, 이 진단이 live Apache/WSGI 헤더나 모듈 실행을 관측한 것은 아니다. 현재 rules 자체에 issuer 조건이 있는 것은 아니며 `HTTP_OIDC_ISS` issuer pin은 별도의 protocol 신뢰 설정이다. 이 구분을 후보 입력이나 오프라인 rules 안의 같은 조건이라고 혼동하지 않는다.

운영자가 제공한 **오프라인 rules 사본**의 `remote.type`과 후보 입력의 정확한 키를 먼저 대조한다. 이름 변환 실험이 필요하면 검토된 오프라인 사본에서만 명시하고, 원본과의 차이를 기록한다. 기존 native mapping JSON·digest·프로토콜 연결·provider pin은 수정하지 않는다. 기존 digest-pinned mapping을 그룹 확인 때문에 가볍게 변경하면 안 된다.

또한 새 진단 ID 토큰의 `aud`는 **새 클라이언트**다. 기존 Keystone 신뢰에 등록된 운영 client audience와 다르므로 기존 federation endpoint에 제출해서는 안 된다. 그 경로에서의 거부는 예상 가능한 별도 audience 경계이며, 진단 성공을 운영 신뢰 변경의 근거로 삼지 않는다. 본 도구는 mapping·그룹·역할·프로젝트를 자동 생성하지 않고 앱 설정도 수정하지 않는다.

## 실패 처리와 종료

- 포트 충돌이면 충돌 원인을 확인한다. 임의 포트로 바꾸기보다 등록값 `8765`를 유지한다. 포트를 의도적으로 바꾸는 경우 앱의 redirect URI와 `--port`를 함께 맞춰야 한다.
- Timeout·동의 거부·state/쿠키 불일치·서명/subject 오류·통신 오류는 실패다. 보안을 우회하거나 scope를 늘리지 말고 새 실행으로 시작한다. 정상 state/브라우저 바인딩을 통과한 콜백은 exchange 실패 시에도 재사용하지 않는다. 요청의 code/query나 토큰을 지원 채팅에 붙이지 않는다.
- 터미널 A는 일회성 콜백 처리 또는 대기 만료 후 종료한다. 중단은 `Ctrl-C`다. 대기 중 브라우저를 닫기만 해서는 listener가 즉시 종료되지 않는다.
- 결과에는 토큰이 없어도 사용자 ID·이메일·내부 그룹 이름/경로라는 **PII·조직 정보**가 있다. 보고서·후보 입력·오프라인 결과·secret 파일은 개인 권한으로 유지하고 저장소/공유 로그에 넣지 않는다.
- 확인 후 GitLab의 Authorized applications에서 **새 진단 앱**의 grant를 revoke하고, 더 이상 필요하지 않으면 새 앱을 삭제한다. 새 앱 삭제는 연결된 grant/token도 제거한다. 개인 결과와 secret 파일은 조직 보존 정책에 따라 제거하며 운영 앱·grant는 건드리지 않는다.

## 근거와 증거 한계

2026-10-26 공개 discovery 조회에서 issuer `https://git.dmslab.re.kr`, `/oauth/authorize`, `/oauth/token`, `/oauth/userinfo`, `/oauth/discovery/keys`, 응답 `code`, PKCE `S256`, 서명 `RS256`, `client_secret_basic`/`client_secret_post`, 그리고 `groups`/`groups_direct`의 **광고 여부**를 확인했다. Discovery는 특정 사용자의 claim 값이나 실제 native 전달 형식을 입증하지 않는다. 신규 클라이언트의 사람 로그인 결과는 별도 증거다.

- [설치 issuer의 공개 discovery](https://git.dmslab.re.kr/.well-known/openid-configuration)
- [GitLab 공식 OpenID Connect provider: claim 표](https://docs.gitlab.com/integration/openid_connect_provider/)
- [GitLab 공식 OAuth provider: 새 앱·scope·secret 갱신·회수](https://docs.gitlab.com/integration/oauth_provider/)
- [요청된 InfoGrab 한국어 OpenID Connect provider 참고](https://docs.infograb.net/docs/gitlab/integration/openid_connect_provider/)
- [Keystone 공식 Mapping Combinations: 환경 속성·오프라인 mapping_engine](https://docs.openstack.org/keystone/latest/admin/federation/mapping_combinations.html)
- [Keystone 공식 keystone-manage CLI](https://docs.openstack.org/keystone/latest/cli/keystone-manage.html)
- [Keystone 공식 CLI 소스: MappingEngineTester의 schema 처리 및 옵션](https://docs.openstack.org/keystone/latest/_modules/keystone/cmd/cli.html#MappingEngineTester)
