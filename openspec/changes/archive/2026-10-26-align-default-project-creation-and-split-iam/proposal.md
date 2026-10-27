## Goal
조직/legacy 도메인의 canonical Default 프로젝트에 effective manager 또는 project_creator가 있는 사용자는 프로젝트 선택창과 IAM 프로젝트 관리에서 프로젝트를 생성하고 허용된 프로젝트를 관리할 수 있어야 한다. 통합 사용자·프로젝트 IAM을 별도 탐색/route로 분리한다.

## Scope
- Default manager 경계는 유지하고 project_creator 생성/위임 권위를 같은 도메인의 enabled canonical Default project grant로 통일한다. Legacy domain-scoped 동명 grant는 대체 권위로 사용하지 않는다.
- /dashboard/iam/users와 /dashboard/iam/projects를 분리한다. Creator-only는 generic project APIs로 자신의 허용된 프로젝트/소유권을 관리하고, 도메인 전체 users/login/provider/invitation/delegation은 manager-only다.
- Workspace chooser의 기존 fresh creation capability를 공유하고 현재 도메인 project management 진입점을 제공한다. 모든 언어와 responsive/theme 및 scope/ABA guards를 유지한다.
- Personal/account 기존 경계, Default 보호, owner transfer journal, graph lease와 fresh mutation guard를 보존한다. 권한/role 자동 생성·운영 grant 이동·배포·commit/push를 하지 않는다.

## Acceptance
Default manager(creator preset 없어도 가능), Default creator, 둘 다 없는 사용자, 다른 scope/disabled/revoked/모호한 role의 양·음성 회귀. 사용자/프로젝트 탐색 분리와 creator-only 사용자 directory 비조회, chooser 및 IAM의 실제 compiled create/manage flow를 검증한다. source/runtime/synthetic/live 경계를 분리 기록한다.
