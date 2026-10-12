## Why

사용자는 메인 페이지 전체 시각을 키네틱 아트로 바꾸길 원한다. 이전의 picture-led 설명과 연결선/가림/채팅 수정은 유지하면서, opacity-only 장면을 실제 조형물이 움직여 관계를 설명하는 유한 choreography로 발전시킨다.

## What Changes

- 디자인 방향: 연구자·기관 담당자를 위한 조각적 키네틱 아트. 기존 graphite/neutral, semantic blue, warm CTA, Pretendard/IBM Plex 유지. DESIGN_VARIANCE 7, MOTION_INTENSITY 7, VISUAL_DENSITY 3.
- Hero도 개별 정적 하드웨어 사진 대신 동일한 판·블록·슬랫 조형으로 플랫폼의 서버/GPU/대화/컨테이너를 보여준다.
- 서버 자원 결합, GPU 데이터→모델, 컨테이너의 노드 배치, 기관 장비의 공유 클라우드화 각각을 다른 조립 choreography로 표현한다.
- 이동 중 도형에 연결선을 억지로 붙이지 않는다. 불투명 composite solid가 먼저 정렬되고, 고정된 접점 사이 경로가 그 후 나타난다. 완성된 상태는 정적 설명 그림으로도 유효하다.
- Lumen은 기존 명시적 작성 예시와 실제 ChatBubble을 유지하며 읽을 수 있는 대화 전개에 작은 응답 조형을 결합한다. private history나 live provider 호출 없음.
- 기존 한 번 재생/명시적 replay/offscreen·hidden pause/reduced·no-JS 최종 frame, locale, hash/guide/console/contact 계약 유지. 스크롤 hijack·무한 autoplay·새 dependency/WebGL·운영 변경 없음.

## Capabilities

### New Capabilities

없음. 공개 설명 시각 표현의 변경이다.

### Modified Capabilities

- Public landing의 6장면을 공통 조형·유한 motion 언어로 통일한다.
- 공용 motion vocabulary에 token-backed 조립 keyframe을 정의해 feature 임의 duration/easing를 만들지 않는다.

## Impact

Frontend landing, 공용 motion CSS/metadata, 디자인·architecture·검증 문서만 변경한다. API/auth/schema/config/deployment 불변. 실제 Chromium before/after 기록, 중간 frame/가림/연결/legibility, mobile/tablet/desktop·light/dark·4locale·keyboard·reduced·no-JS를 검증한다. 공유 index와 동시 변경을 보존하고 이 change만 archive한다.
