## Why

데스크톱 대시보드 상단 왼쪽에서 Cloud Shell을 명확하게 실행할 수 있어야 한다. 태블릿·모바일에서는 터미널 제어가 어려우므로 실행 버튼을 사이드바로 옮기지 않고 숨긴다.

## What Changes

- 기존 `CloudShellTrigger`에 터미널 아이콘과 `Cloud Shell` 레이블을 표시하고, root header의 breadcrumb 다음·검색 앞에 배치한다.
- 기존 `lg` 경계(1024px) 이상에서만 버튼을 표시한다. 사용자·관리자 사이드바에는 실행 버튼을 추가하지 않는다.
- 기존 서비스 capability, 인증, mockup 제외, 명시적 승인, 전역 singleton 세션·dock 동작을 유지한다. 버튼 클릭 자체는 자원을 생성하지 않는다.
- 기존 디자인 계약과 Cloud Shell 문서에 데스크톱 전용 실행 위치·작은 화면 숨김을 기록한다.

## Capabilities

### New Capabilities

없음. 기존 전역 Cloud Shell의 진입 UI만 변경한다.

### Modified Capabilities

- 전역 Cloud Shell 실행 버튼: 명시적 레이블, 상단 왼쪽 배치, 데스크톱 전용 표시.

## Impact

`frontend/src/routes/+layout.svelte`와 `frontend/src/lib/components/cloud-shell/CloudShellTrigger.svelte`가 대상이다. API·서비스 설정·인증 경계·터미널 lifecycle·이미지·배포는 변경하지 않는다. 실제 브라우저에서 desktop/tablet/mobile 및 1023→1024px 전환, 승인·취소 시 API 비호출, 승인 뒤 기존 실행 경로를 검증한다. 운영 OpenStack resource 생성은 검증 범위가 아니다.
