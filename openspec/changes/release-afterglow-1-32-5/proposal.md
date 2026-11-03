# Release Afterglow 1.32.5

## Why
현재 dev의 완료된 MCP, IAM, 채팅과 인증 UI 변경을 정확한 source에서 검증하고 GitHub에 발행한다.

## What Changes
공유 checkout의 사용자·동시 변경과 비밀을 보존하고 독립 검토에서 발견한 관리자 보존 및 채팅 추적 오류를 수정한다. 전체 gate와 실제 변경 경로를 검증한 뒤 동일 source의 정상 dev commit/push, exact-SHA CI, 불변 numeric tag, GitHub Release, OCI image·Helm을 검증한다. 사용자가 Kolla 전환을 직접 수행하므로 운영 서비스·SQL·native 변경은 제외한다. SQL106, 모든 writer, native 서비스 버전·권한과 원래 key 및 복구 지점은 운영자의 별도 선행 조건이다.
