# 사용자별 프로젝트 권한 조회

## Why
관리자 사용자 페이지의 사용자 수정 모달에서 활성 세션과 함께 해당 사용자의 프로젝트 및 현재 유효 역할을 확인한다.
기존 사용자 수정 창은 프로필과 활성 세션만 보여 주어 어느 프로젝트에 어떤 권한으로 참여하는지 확인할 수 없다.

## What Changes
시스템 관리자 전용 읽기 API와 사용자 모달의 권한 목록, 로딩/빈 상태/조회 실패, 사용자 전환 응답 경계, 한국어·영어·일본어·중국어 문구를 구현한다. Keystone의 그룹·스코프 상속 할당 및 실제 역할 implication 그래프를 반영하고 프로젝트 외 domain/system 스코프는 프로젝트와 구분한다.

## Non-goals
역할 부여·회수, 로그인/인가 정책, 세션 폐기 동작, 운영 클라우드 변경, 배포·commit·push는 포함하지 않는다.

## API contract
GET /api/v1/admin/users/{user_id}/permissions → {items:[{scope_type:'project'|'domain'|'system',scope_id:string,scope_name:string,roles:[{id:string,name:string}]}],count:number}. 모든 이름은 실제 Keystone metadata 기반이며 조회 장애를 빈 목록으로 숨기지 않는다. effective assignment와 실제 role DAG를 사용하며 직접 할당이라는 표시를 추측하지 않는다. 응답은 현재 권한의 표시용 snapshot이며 인증 토큰이나 새로운 인가 입력이 아니다.

## Acceptance
관리자만 조회할 수 있다. 다른 사용자의 할당을 혼합하지 않는다. 그룹·상속·암시 역할을 표시하며 중복 역할을 제거한다. 화면은 세션과 권한을 함께 보여 주고 모바일에서 모달/작업 버튼이 화면을 벗어나지 않는다. 실제 로컬 browser/API smoke와 관련 regression selector를 검증한다. 운영 Keystone 증거와 합성 fixture 증거를 구분한다.
