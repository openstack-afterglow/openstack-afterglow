# 선택 프로젝트 쿼터 사용량 표시

대시보드 CPU/RAM은 도메인 전체 소비 대신 선택 프로젝트 소비를 표시한다. 기존 domain-scope API 계약은 보존하고 native project limit을 overview에 보존하여 native/domain/project cap의 유한 최소 한도를 표시한다. 공유 잔여량은 보조 정보이며 프로젝트 사용량이나 한도로 합성하지 않는다. 미확인 프로젝트 소비를 도메인 소비나 0으로 대체하지 않는다. 운영 배포·쿼터 변경·DB 변경은 제외한다.
