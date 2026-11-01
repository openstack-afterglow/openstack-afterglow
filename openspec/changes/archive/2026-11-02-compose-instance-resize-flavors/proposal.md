## Why
관리자·사용자 인스턴스 상세에서 리사이즈 버튼이 정지(SHUTOFF) 상태에서만 보여 실행 중 VM에서는 리사이즈를 찾을 수 없다. 리사이즈 대상 선택도 VM 생성 마법사의 새 flavor 선택(직접 구성·저장 구성·카탈로그)과 달리 단일 select에 머물러 있다.

## What Changes
- 사용자/관리자 상세에서 ACTIVE·SHUTOFF 인스턴스에 리사이즈를 노출한다(백엔드는 이미 두 상태를 허용). 실행 중이면 재시작 다운타임을 안내한다.
- 리사이즈 모달이 VM 생성과 같은 FlavorComposer를 사용한다. 직접 구성/저장 구성/카탈로그 모드를 제공하며 카탈로그는 기존 instance-scoped resize-flavors를 쓴다.
- composer options/history/save/operation readback에 선택적 `instance_id` resize 문맥을 추가한다. 현재 flavor를 기준으로 증분 quota(인스턴스 수 0, 현재 CPU/RAM/GPU 반환분 credit)를 평가하고 동일 flavor·image-backed 디스크 축소를 차단한다. Host 범위는 현재 VM 할당을 반환하지 않는 보수적 advisory이며 Nova가 최종 배치한다.
- 리사이즈 helper를 서비스 모듈로 옮겨 사용자·관리자 경로가 공유한다.

- 사용자 요청으로 함께 처리: 인증 서비스 장애 화면 로그아웃·3회 실패 자동 로그아웃, 도메인 관리자의 본인 프로젝트 역할 편집과 그룹 전용 멤버의 직접 역할 편집.

## Capabilities
### Modified Capabilities
인스턴스 리사이즈 대상 선택과 노출 상태, flavor composer의 resize 평가.

## Impact
Backend compute/admin routes·flavor_composition/eligibility, frontend instance detail controller/header/modal·composer store/component, 9 locale, tests, ARCHITECTURE/docs/CHANGELOG. Schema/설정/의존성/운영 배포 변경 없음. 실제 Nova 리사이즈 실행은 운영 VM 다운타임을 유발하므로 synthetic/로컬 검증만 수행한다.
