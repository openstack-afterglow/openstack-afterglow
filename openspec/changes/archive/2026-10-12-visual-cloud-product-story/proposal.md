## Why

사용자가 직전 랜딩을 너무 심심하고 글이 많다고 평가했다. 연구자·교수가 문단을 순서대로 읽어야 제품을 이해하는 기존 운영 미리보기·기능 카드·workflow·audience 설명을 제품 그림과 기능별 모션 장면으로 바꾼다. 목적은 Afterglow가 무엇을 제공하는지 첫 화면에서 이해시키는 것이다. 사용자 관측은 재검증 대상이 아니라 변경 기준이다.

## What Changes

- Hero는 큰 서버/GPU 제품 일러스트와 서버·GPU 학습·AI 채팅·Kubernetes의 즉시 보이는 진입점을 둔다. 실제 장비 사진이 아닌 생성된 개념 이미지로 명시한다.
- 서버는 자원에서 연구용 VM으로, GPU 학습은 데이터에서 GPU와 모델로, AI 채팅은 실제 Lumen 화면으로, Kubernetes는 container에서 cluster로 보여주는 개별 대형 장면을 둔다. 제목 하나·설명 한 문장·가이드 link만 남긴다.
- 기관 구축은 서버·GPU·storage/network가 기관 클라우드와 연구팀으로 연결되는 개념 모션을 둔다. 콘솔 이용과 구축 문의의 행동 목적지는 그대로 유지한다.
- 장문 기능 매트릭스·6개 workflow filter·운영/console fixture 체험·audience 중복 설명과 전용 dead code/catalog/static artwork를 clean cutover한다. 공개 hash destinations는 새 장면에서 보존하며 navigation은 서비스 이름으로 명료화한다.
- 모션은 IntersectionObserver로 화면 진입 시에만 시작하는 유한 cascade이다. Offscreen/hidden에서는 pause, reduced motion/API 없는 환경/no-JS에서는 완성된 정적 장면을 제공한다. Replay는 명시적인 control이며 자동 carousel·scroll hijacking·무한 loop·WebGL·새 animation dependency는 없다.
- Brand palette·theme·Pretendard/IBM Plex roles·공용 Button/ToggleGroup/icon·기존 auth destination·4locale 계약을 보존한다.

## Capabilities

### New Capabilities

- Visual-first explanatory scenes for research cloud services and institution-owned on-premises construction.

### Modified Capabilities

- Public landing presentation only. 서버·GPU AI 학습·Lumen chat·Kubernetes·기관 구축 외 지원 기능을 추가하거나 약속하지 않는다. Palimpsest 실험 레이어 기록/저장/포크/재사용은 계속 홍보하지 않는다.

## Impact

Frontend public landing composition, local asset, motion lifecycle, four public-entry catalogs, affected existing regressions and architecture/design/user/testing/changelog documentation. API/schema/auth/config/paid provider/cloud operation/deployment are unchanged. Local browser acceptance is separate from real provisioning or production qualification; concurrent work and shared Git index/review markers are preserved.
