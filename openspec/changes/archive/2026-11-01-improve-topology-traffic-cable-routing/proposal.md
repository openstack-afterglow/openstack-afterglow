# 토폴로지 실측 방향과 다중 케이블 간격

## 목표와 범위
공유 dev의 기존 변경을 보존하면서 canvas NIC별 실측 TX/RX를 양방향 표시하고 switch–하위 노드 여백과 다중 연결의 꺾임을 동적으로 분리한다. Backend/API/schema/config/운영 배포는 변경하지 않는다.

## 설계
- NIC TX는 VM→switch, RX는 switch→VM. 양의 유한값만 움직이고 미측정/0은 정적이다. Native API는 2분 평균/15초 polling이며 개별 packet/peer 관측은 아니다.
- 추정 aggregate trunk/FIP/Internet을 실제 packet으로 애니메이션하지 않는다. 기존 선 굵기·숫자와 전역60dot budget/reduced-motion/visibility를 유지한다.
- switch 아래 기본 여백을 확대하고 incident fanout에 따라 여백·bend lane을 확장한다. 순서별 약6world px (100%에서 약1.6mm) 분리, 위/왼쪽은 길게 아래/오른쪽은 짧게 한다.
- 모든 케이블은 직각·독립 endpoint·결정론적 순서와 drag 재계산을 유지한다.

## 완료 기준
관련 geometry/traffic 회귀와 실제 compiled component Chromium smoke에서 다중 NIC/다중 switch 연결, 양방향/저속/0/unknown, motion toggle/reduced-motion, responsive/theme을 확인한다. Source/synthetic proof와 실제 cloud acceptance는 구분한다.
