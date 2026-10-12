## Why

사용자가 `visual-cloud-product-story`의 실제 화면에서 서버·GPU 연결선의 단절, 기관 클라우드 입체 면의 뒤비침/겹침, 잘려 읽을 수 없는 빈 Lumen 캡처와 의미 없는 다시 보기를 지적했다. 기존 bounds/overflow 통과는 접점과 가림 관계 또는 설명의 유효성을 증명하지 못했다. 사용자 지적은 결함의 기준이며 같은 증거를 재확인하기 위한 테스트를 반복하지 않는다.

## What Changes

- 서버 자원에서 VM까지 선이 실제 도형 접점에 닿도록 합류 경로를 정리한다.
- GPU 데이터·가속기·모델의 시작/끝 접점과 paint 순서를 바로잡는다.
- 기관 클라우드와 전체 SVG의 면을 불투명하게 구성하고, 뒤쪽 면과 연결선이 앞쪽 면에 비치지 않게 한다. Kubernetes도 같은 기준으로 검토한다.
- Lumen의 잘린 빈 이미지와 단순 이미지 등장 효과를 제거한다. 공개 가능한 대화 자료와 기존 ChatBubble 계약을 우선 조사하여 질문·답변이 읽히고 순차적으로 나타나는 장면으로 교체한다. 시연 자료를 실제 사용자 기록이나 실제 provider 실행으로 표시하지 않는다. 공개 랜딩에서 비공개 대화/credential을 읽거나 유료 provider를 호출하지 않는다.
- 기존 finite/offscreen/hidden/replay/reduced/no-JS 계약과 네 언어·theme·service destinations는 유지한다. 정지와 중간 frame 모두 실제 브라우저로 점검한다.

## Capabilities

### New Capabilities

없음. 새로운 cloud 기능이나 API를 추가하지 않는다.

### Modified Capabilities

공개 landing의 제품 장면, 입체 도형 연결, Lumen 대화 설명과 replay의 시각적 정확성.

## Impact

Frontend landing composition/graphic/chat presentation 및 해당 localization, 필요한 consumer regression, architecture/design/user/testing/changelog 문서. 서비스/API/인증/DB/schema/config/운영 자원/배포는 변경하지 않는다. 공유 checkout/index와 동시 변경을 보존한다. 완료 기준은 각 지적 장면의 읽을 수 있는 전후 screenshot/recording, 정확한 도형 접점·불투명 가림, 실제 질문→응답 replay, 주요 responsive/locale/theme/reduced/keyboard 조건이다. 전체 gate·실제 inference·운영 배포 여부는 로컬 시각 검증과 별도 기록한다.
