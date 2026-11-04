## Context
Waygate Trust 토큰의 native 만료와 local execution grant의 만료는 서로 다르다. Drover 보안 그룹은 프로젝트 quota를 공유하며 native used와 reserved 및 provider 기본 규칙이 필요하다. 장기 작업의 수락과 terminal은 다르다.

## Goals / Non-Goals
**Goals:** 현재 역할과 credential의 교집합을 유지한 Waygate 실행, 정확한 Drover quota 부족 사전 확인, 관리자 버전 정보 이동, 실제 단계와 장기 작업 추적.
**Non-Goals:** 사용자 token 권한 승격, 기존 quota 자동 상향, 미확인 쓰기 replay, 운영 인프라 변경.

## Decisions
- Trust·actor·project·발급 role IDs와 독립적인 grant 수명을 모두 검사한다. Keystone이 부여한 토큰 자체 만료만으로 local grant deadline을 대체하지 않는다.
- 신규 개인 프로젝트에서만 source fallback quota 여유를 늘리고 저장된 관리자 정책과 기존 프로젝트 quota를 변경하지 않는다. Native SG quota preflight는 현재 사용·예약과 초기 기본 SG/rule 요구량을 검증하지만 경쟁 이후 native provider 결정은 여전히 authoritative하다.
- 시스템 버전은 기존 API·system-admin 검증 아래 별도 시스템 정보 페이지에만 둔다.
- Operation tracker는 인증·프로젝트 scope에 묶고 native operation을 GET으로만 따라간다. Unknown 또는 연결 종료는 terminal이나 성공으로 합성하지 않고 완료 전 최소화 상태를 보존한다.

## Risks / Trade-offs
- 사용자 설정 정책과 일반 조직의 native 기본 quota는 source fallback 변경으로 바뀌지 않는다.
- Synthetic SDK/HTTP/browser는 실제 운영 권한과 cloud mutation을 보장하지 않는다. 운영 적용은 별도다.
