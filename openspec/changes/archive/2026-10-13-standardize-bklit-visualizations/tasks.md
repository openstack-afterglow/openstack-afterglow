## Implementation Tasks

- [x] 프로젝트 전체 자체 수치 시각화 및 호출자·데이터·상호작용·예외 목록을 확정한다.
- [x] pinned Bklit registry source/MIT license, React client-only boundary, 공통 typed chart adapter와 theme/motion/locale 계약을 구현한다.
- [x] 공통 usage/quota/capacity 막대와 원형 meter를 Bklit로 전환한다.
- [x] 공통 Spark/TimeSeriesChart/TrafficArea/TrafficSparkline 및 서비스 이력·분포를 Bklit로 전환한다.
- [x] 관리자·사용자 route의 직접 구현 통계 막대·분포와 잔여 시각화를 전환하고 폐기된 LayerChart POC/dependency를 제거한다.
- [x] 관련 계약을 갱신하고 실제 Chromium에서 data refresh, empty/zero/unlimited/gap, tooltip, responsive/theme/reduced-motion을 검증한다. 최종32개 component 조건과24개 실제 route 조건, 367files/3615 frontend tests 통과; 범위 밖 type/gate 실패는 docs/testing.md에 기록했다.
- [x] 향후 Bklit 사용 기준·범위·upstream 갱신 방법을 DESIGN/architecture/개발 가이드와 상세 문서에 반영하고 architecture freshness 및 OpenSpec archive를 완료한다. Frozen public working/staged guard 동일891401c9…/2847files, 공유 index/review marker 보존; rapid archive 대상 확정.
