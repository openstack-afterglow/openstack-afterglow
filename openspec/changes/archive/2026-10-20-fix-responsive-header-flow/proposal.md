# 상단 바 반응형 흐름 수정

## 문제
검색창 absolute viewport 중앙 배치는 오른쪽 Cloud Shell·모드·언어 컨트롤의 실제 폭을 반영하지 않아 버튼과 겹친다. 모바일 프로젝트 선택과 유틸리티도 좁은 화면에서 화면 밖으로 밀렸다.

## 변경
root layout의 기존 flex 흐름에서 검색창이 남는 공간을 사용하도록 하고 최대24rem으로 제한한다. 기존768/1280 검색 handoff를 보존한다. 모바일 프로젝트 선택은 기존 drawer에 유지하고640px 미만 Docs도 drawer에서 제공한다. compact gap/padding만 조정한다.

## 경계
새 컴포넌트·breakpoint·JS observer·API·권한·schema·서비스 배포 변경은 없다. 기존 LocaleSelect 동시 변경을 보존한다.

## 수용 기준
320–1920px 상단 컨트롤 겹침·이탈0, 1279/1280 검색 trigger1개, 모바일 drawer 프로젝트/검색 사용 가능. 실제 Chromium 검증은 합성 identity/API와 실제 working-source UI로 한정한다.
