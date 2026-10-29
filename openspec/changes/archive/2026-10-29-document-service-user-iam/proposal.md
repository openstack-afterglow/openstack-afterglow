## Why

사용자가 특정 서비스를 사용하려면 어떤 프로젝트 역할과 서비스 역할이 필요한지 공개 문서에서 확인하기 어렵다. Waygate·Palimpsest·Drover·Lumen과 기본 클라우드 서비스의 역할을 실제 구현 기준으로 설명하고, 조직 manager와 서비스별 관리 등급의 경계를 분명히 해야 한다.

## What Changes

- 공개 `/docs/iam`에 사용자 관점의 상세 IAM 가이드를 추가한다. 기존 typed static DocGuide·검색·목차·관련 문서·번역 구조를 그대로 사용한다.
- 작업 도메인/프로젝트, manager와 프로젝트 등급, 서비스 등급과 세부 역할, 기능별 필요 조건·예시·권한 문제 확인 순서를 설명한다.
- 전역 `admin` 역할 및 그 전용 운영 절차는 새 가이드에서 설명하지 않는다. `project_admin`과 서비스별 `*_admin`은 실제 허용 범위만 설명한다.
- 기존 시작·서비스 문서에서 IAM 안내를 연결하고 지원하는 9개 언어를 동기화한다.
- 사용자 문서 개요·변경 기록·아키텍처 문서에는 새 문서 경로와 정본만 기록하며 상세 내용을 중복하지 않는다.

## Capabilities

### New Capabilities

- 공개 서비스별 사용자 IAM 참조 및 역할 조합 안내.

### Modified Capabilities

- 문서 검색·탐색에서 IAM 가이드 발견 가능. 권한 검사·API·서비스 정책·역할 할당은 변경하지 않는다.

## Impact

프론트엔드 정적 문서와 관련 문서 기록만 변경한다. 운영 IAM·OpenStack 자원·DB/schema·배포·자격 증명은 변경하지 않는다. 현재 checkout 및 형제 서비스 source에 근거하며 운영 policy override 또는 배포 완료의 증거가 아니다. 기존 동시 변경과 index를 보존하고 커밋·push·배포하지 않는다.
