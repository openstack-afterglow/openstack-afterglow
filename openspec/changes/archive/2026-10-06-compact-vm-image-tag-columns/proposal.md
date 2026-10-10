## Why

VM 생성의 이미지 태그 행에서 긴 SHA 표시와 넓은 메타데이터 열이 태그 이름 공간을 차지한다. 사용자는 해시를 앞 8자리만 보이고 해시·업로드 시각·용량 열을 줄여 긴 태그를 더 읽을 수 있게 하며, 태그 hover에서 전체 이름을 확인하기를 요청했다.

## What Changes

- VM chooser만 `ImageDigest`의 compact 표시를 사용해 SHA-256/512 값의 앞 8자리를 보인다. 알고리즘·전체 해시는 title·접근성 이름으로 유지하고 기존 catalog의 기본 표시는 바꾸지 않는다.
- 이름·해시·업로드 시각·용량 네 열과 목록 내부 가로 스크롤을 유지하면서 메타데이터 열·열 간격·최소 목록 폭을 줄인다. 남은 폭은 태그 이름이 사용한다.
- 기존 native title tooltip convention을 재사용해 태그 이름 셀 전체를 hover 영역으로 한다. 잘린 태그도 전체 이름을 확인하고 비활성 행의 선택 불가 사유도 유지한다.

## Capabilities

### New Capabilities

없음. 새 UI primitive·tooltip portal·API·색상·motion을 추가하지 않는다.

### Modified Capabilities

- VM 이미지 태그 선택의 조밀한 표시와 전체 이름 조회.
- Rapid workflow의 proposal/tasks와 현재 DESIGN·ARCHITECTURE·상세 API 문서로 계약을 추적한다. specs layer는 추가하지 않는다.

## Impact

`SelectImage.svelte`, 공용 `ImageDigest.svelte`, 관련 기존 회귀 및 영향받는 문서. UUID·current upload 판정·정렬·비활성 차단·검색·자동 다음 단계·catalog 기본 SHA/UUID 계약은 유지한다. 실제 Chromium에서 긴 태그·8자리 값·열 정렬·지역 스크롤·hover 대상의 전체 title와 네 언어를 검증한다. 운영 배포와 cloud mutation은 범위 밖이다.
