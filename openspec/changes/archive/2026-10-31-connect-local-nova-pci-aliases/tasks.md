## Implementation Tasks

- [x] 현재 로컬 backend source/DB 목적지·자동화와 기존 Nova GPU alias 조합을 읽기 전용으로 확인한다.
- [x] 개발 Compose에 공개 PCI snapshot 전용 read-only mount를 추가하고 controller 정제 snapshot을 준비한다.
- [x] DB/키/포트/기존 mount를 보존하여 backend 이미지를 빌드·검증하고 로컬 backend만 재기동한다.
- [x] 현재 native 관리자 인증·revision API로 기존 GPU profile을 승인하고 compute pool 조회를 서비스 계층에서 확인한다 (HTTP 화면 경로와 PUT 편집은 미실행).
- [x] 실제 실행 증거와 운영 경계를 architecture/배포/변경 기록에 남기고 archive한다.
