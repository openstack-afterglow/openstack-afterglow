## Why

VM 생성 이미지 선택은 repository를 고른 뒤 태그 목록을 전체 이미지 목록 맨 아래의 두 열 카드로 표시한다. 사용자 요청은 선택한 이미지 카드를 바로 펼쳐 태그를 검색하고, 각 태그의 이름·해시값·업로드 시각·용량을 한 행에서 비교하는 것이다.

## What Changes

- 이미지 카드 자체를 단일-open accordion으로 확장한다. 선택한 카드는 이미지 grid의 전체 폭을 사용하고 자기 header 바로 아래에 검색과 태그 행 목록을 표시한다. 전체 목록 하단의 별도 태그 panel과 자동 하단 scroll은 제거한다.
- repository별 태그 이름을 공백 trim·대소문자 무시 substring으로 검색한다. 결과 없음과 검색 초기화/다른 repository 열기를 처리하며 검색·접기·펼치기는 선택한 UUID를 바꾸지 않는다.
- 태그는 이름·콘텐츠 해시·업로드 날짜시간·용량 순서의 단일 행으로 표시한다. 긴 태그/해시는 전체 title/접근성 값을 유지하고 좁은 화면은 TableShell 내부에서만 가로 scroll한다. 카드 두 열 fallback은 사용하지 않는다.
- 기존 ImageDigest의 SHA-256/512·pending/unavailable 규칙을 재사용하며 wizard 행에서는 UUID 줄만 숨긴다. 기존 관리자/사용자 이미지 catalog는 기본값으로 UUID 표시를 유지한다.
- current-upload 판정·최신 우선 정렬·OS/global 검색·비활성 태그 선택 차단·과거/누락 선택 경고·source image name callback을 유지한다.

## Capabilities

### New Capabilities

- 선택한 repository 안의 독립적인 태그 검색.

### Modified Capabilities

- VM 이미지 카드의 인라인 확장과 단일 행 태그 선택/메타데이터 비교.

## Impact

SelectImage, ImageDigest의 선택적 UUID 표시, 네 언어 vm-wizard catalog와 관련 소비자 회귀가 대상이다. backend API·image identity·VM 생성·권한·배포는 변경하지 않는다. 상세 계약은 DESIGN.md, ARCHITECTURE.md와 docs/api/images.md에 기록하고 rapid proposal/checklist만 사용한다. specs 레이어를 추가하지 않는다. 실제 Chromium의 합성 image fixture에서 mobile/tablet/desktop, 네 언어·light/dark, 검색/초기화/전환/재선택·row 메타데이터·local scroll을 검증한다. 운영 cloud/인증 acceptance나 배포 성공으로 확대하지 않는다.
