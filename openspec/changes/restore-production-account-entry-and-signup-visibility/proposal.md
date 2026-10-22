## Why
운영1.30.22에서 관리자 overview/domains/notifications503, 공개 이메일 가입 unavailable, 조직 SSO provider 없음이 보고됐다. 관리자503은 실제 executor token이 raw is_admin_project를 생략하여 deps.py726에서 거부되는 원인을 읽기 전용으로 증명했으며 이 change는 그 분석을 보존한다. SMTP STARTTLS/auth는 실제 성공하고 signup defaultfalse가 이메일 가입 화면을 막는다. 운영 auth registry가 비어 있어 local DMSLab SSO 설정만 선별 반영해야 한다.

## What Changes
- 기존에 동작하던 관리자 API의 회귀를 SDK native 계약에 맞춰 수정한다. 생략 가능한 legacy is_admin_project는 SDK 기본 true를 존중하되 explicit false/null/non-boolean·wrong scope·admin-role 부재·fresh caller revocation은 계속 거부한다. 사람의 Personal grant나 executor/native identity는 바꾸지 않는다.
- 사용자 승인에 따라 공개 이메일 가입을 활성화하고 DMSLab 도메인3de8d34d778e423ab7a92a4992378583의 local OIDC provider 및 gmail.com/konkuk.ac.kr 자동 참여 정책만 연결한다. 다른 domain/GitLab.com 설정·native tuple/grant는 자동 이전하지 않는다.
- 이메일 검증·OIDC 가입 admission과 로그인 화면의 회원가입 버튼 노출을 독립 제어하는 관리자 설정을 제공한다. 기존 관리자/도메인 manager의 이메일 도메인 정책 범위와 identity-only Accounts/Personal topology를 유지한다.
- 실제 issuer discovery/native federation/callback 연결과 보존·readiness를 검증한다. 사용자의 비밀번호·provider secret·authorization code/token은 출력하지 않는다.
- 운영 config는 보호된 백업/검증 뒤 배포서버의 전체 대상 표준 reconfigure로 반영하며 per-controller loop는 사용하지 않는다.

## Acceptance
원인 분석 evidence, 독립 visibility/admin controls 및 정책 경계 회귀, 정본 gate·native fleet deployment, 실제 public signup/SSO 연결과 미검증 경계를 보고한다. 실제 mailbox 수신/user login을 임의로 성공 처리하지 않는다.
