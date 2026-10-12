## Why

현재 공개 랜딩은 Palimpsest의 불변 실행 레이어 저장·포크·재사용을 이미 제공하는 것처럼 홍보한다. 사용자가 해당 기능은 아직 지원하지 않는다고 확인했다. 연구자·교수가 현재 이용할 수 있는 서버, GPU 기반 AI 학습, Lumen AI 채팅, Kubernetes를 명확히 소개하고, 기관의 서버·GPU·스토리지·네트워크를 묶어 온프레미스 클라우드를 구축할 수 있다는 제공 범위를 별도로 전달한다.

## What Changes

- 사용자가 지정한 NHN Cloud, Google Cloud, AWS, Kakao Cloud, 공공 Kakao Cloud, LG CNS Cloud, KT Cloud, Cloudflare, DigitalOcean의 메시지·CTA·실제 화면·모션 구현을 primary source로 조사한다. 관측하지 못한 부분은 미검증으로 표시한다.
- 연구자·교수를 위한 benefit-first hero와 서버·AI 학습·AI 채팅·Kubernetes 네 가지 서비스를 소개한다. 기존 브랜드·URL·테마·공용 primitive를 유지한다.
- hero 체험은 요청→정책 확인→자원 구성의 세 단계로 끝낸다. 레이어 저장·포크·재사용, 자동 스냅샷·재사용 결과 등 미확정 홍보를 제거하고 실제 자원을 생성하지 않는 예시라는 경계를 유지한다.
- 긴 request-to-reuse scroll story를 클라우드 이용/온프레미스 구축 선택형 구성 설명으로 교체한다. 온프레미스는 요구 자원 확인→기관 내부 자원 통합→프로젝트별 서비스 제공을 설명하며, 버튼 선택이 실제 배포나 자원 이동을 수행하지 않는다.
- GPU 제공은 선택한 환경의 자원·쿼터·정책에 따르며, AI 채팅 모델과 이용 범위도 기관 설정에 따른다. SLA·보안 인증·고객 수·성능 수치·자동 외부 클라우드 연동을 만들어내지 않는다.
- 네 locale의 같은 키를 갱신한다. 자동 번역을 사람 검수 완료로 표기하지 않는다. 반응형·키보드·reduced motion과 실제 브라우저 전후 증거를 확보한다.

## Capabilities

### New Capabilities

- 새로운 backend 기능 없음. 현재 서비스의 공개 소개와 온프레미스 구축 문의 경로만 추가한다.

### Modified Capabilities

- 공개 landing 메시지, 서비스 카드, 환경 체험, 기관 구축 설명 및 관련 접근성/언어 표시.

## Impact

frontend/src/lib/components/landing, public-entry 네 언어 카탈로그, 관련 회귀·디자인 가드 및 공개 랜딩 문서에 한정한다. 기존 LandingJourney의 미지원 홍보와 전용 테스트는 clean cutover로 제거한다. Backend/API/schema/인증/운영 환경·배포·요금은 변경하지 않는다. dev 공유 checkout의 기존 변경·index·private 설정을 보존하며 commit/push/deploy는 하지 않는다. 로컬 공개 페이지 UI 검증은 실제 OpenStack provisioning·Lumen paid inference·기관 구축 완료의 증거가 아니다.
