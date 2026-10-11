## Why

사용자 제공 화면에서 Lumen 작업 공간 전체가 공통 PageShell의 가운데 정렬·80rem 최대 폭·외부 padding에 갇혀 채팅 기록 sidebar와 대화 화면 양옆에 큰 빈 영역이 생긴다. 사용자 요청은 기존처럼 채팅 페이지 전체를 가용 영역에 채우되 내부 메시지 기록과 입력창만 콘텐츠 박스 크기로 제한하는 것이다. 제공한 화면을 재현 근거로 사용하며 운영 권한 오류를 다시 확인하거나 변경하지 않는다.

## What Changes

- 채팅 및 채팅 프로젝트 라우트의 외부 PageShell을 폭 제한·외부 padding 없는 viewport-height 작업 영역으로 바꾼다.
- 채팅 sidebar·toolbar·배경은 기존 전역 header/service navigation을 제외한 전체 가용 영역을 채운다.
- 새 채팅·기존 대화의 메시지와 composer는 공통 `--app-content-max-width`(80rem)와 기존 내부 gutter를 사용해 같은 중심축에 배치한다.
- 기존 mobile/tablet 기록 drawer, desktop sidebar/rail, transcript scroll·history cursor·입력/전송·권한·프로젝트 동작은 유지한다.

## Impact

Frontend markup/CSS만 변경한다. 일반 PageShell·이미지/오디오 Studio·설정·관리자 화면의 폭, API·인증·DB·과금/provider·배포는 변경하지 않는다. 실제 Chromium에서 새 채팅/기존 메시지, 390–2560px·light/dark, navigation/sidebar 상태·composer/scroll 경계를 확인하고 기존 상세 문서·디자인·아키텍처·changelog를 갱신한다. 캡처는 합성 fixture/튜토리얼을 사용하며 운영 인증/추론 성공으로 표기하지 않는다.
