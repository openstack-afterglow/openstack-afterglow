## Why

관리자는 Lumen·Drover·Waygate·Palimpsest 관리 화면에서 대상 프로젝트의 서비스 세부 역할이 없어도 현재 Keystone `system:all` 관리자 권한으로 조회·생성·제거해야 한다. 기존 action gate의 일부는 이를 허용하지만 대상 프로젝트 재인증·native 실행 위임 경계가 요청을 먼저 거부한다.

## What Changes

- 기존 서비스 역할 또는 현재 검증된 system 관리자 권한을 네 서비스의 browser/native action 인가에 적용한다.
- 호출자의 인증 프로젝트와 작업 대상 프로젝트를 분리하고 `X-Project-Id`/`X-Target-Project-Id` 계약을 통일한다.
- 대상 프로젝트·도메인·사용자 활성 상태, native provider 정책과 credential attenuation을 보존한다.
- 프로젝트/domain admin, 위조 header, 회수된 system 권한 및 authority 장애는 system 예외가 아니다.
- 배포·운영 IAM 변경·운영 DB 접근은 포함하지 않는다.

## Capabilities

### New Capabilities

- `system-admin-service-operations`: 프로젝트 서비스 역할 없는 현재 system 관리자의 Lumen·Drover·Waygate·Palimpsest 관리 작업 및 거부 경계.

### Modified Capabilities

없음.

## Impact

Afterglow 인증 dependency·서비스 BFF, 네 native 서비스의 인증·실행 인가, 관련 회귀·아키텍처·API 문서. 기존 사용자·machine/API-key의 축소된 권한과 provider 상태 안전 규칙은 확대하지 않는다. Native durable 실행이 새 credential 저장을 요구하면 schema·암호화·회수·만료와 기존 writer 호환성을 구현 및 검증 기록에서 별도로 다룬다.
