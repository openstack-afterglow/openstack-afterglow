## Implementation Tasks

- [x] 확인된 국가 판정 코드·운영 미설정 및 frontend IP null 경계, longest-prefix/사설 주소/누락 주소를 source와 실제 local execution으로 확인한다. 공식 국가 DB의 형식·라이선스·전량 size/cardinality를 확인한다.
- [x] `/api/monitoring`에 health/관측기 reports/jobs가 함께 분류되는 경로와 현재 origin 차원 부재를 확인한다. Source별 수치·legacy bucket을 외부 접속으로 소급 단정하지 않는다.
- [x] 현재 NIC 합계/TCP probe/neighbor/route가 per-peer packet counter가 아니라는 경계와 controller-core radial workspace/evidence layer 요구사항을 정리한다. Representative node kernel/BTF/실제 CIDR 선행 조건을 read-only로 확인한다.
- [x] 사용자와 실측 범위 및 승인 범위를 확정한다. 사용자는 **물리 스위치·포트까지**(호스트 방향별 흐름+LLDP+switch telemetry)와 **운영 반영까지**(Afterglow·관측 수집기 한정)를 선택했다. 관리 주소·인증·exporter 선행 조건은 실제 증거로 확보하고, 불가 구간을 NIC/추정치로 대체하지 않는다.
- [x] 실제 원본 IP/proxy chain을 backend와 frontend에서 보존·검증하는 계약을 구현하고 untrusted/위조 header·direct listener·IPv4/IPv6/mapped 주소·확인 불가를 검증한다. 기존 rate limit/session binding은 변경 영향이 입증되지 않은 상태로 바꾸지 않는다.
- [x] 승인된 전체 IPv4/IPv6 offline country DB를 provider/revision/checksum/attribution과 함께 지원한다. Backend config/model/예시/K8s/Helm/Compose/Kolla·readonly file 배포 경로를 동기화하고 위치 미확인 사유를 공개한다. 미계측 주소의 `site_country` fallback이나 외부 lookup은 추가하지 않는다.
- [x] 명시 cluster CIDR에 근거한 내부/외부/미확인 origin 집계·API 필터·frontend control/coverage와 기존 미분류 기간을 구현한다. Observer/health를 내부 요청으로 확인할 수 있는 근거를 보존하며 요청 route를 origin 대신 쓰지 않는다. Backend/frontend·dedupe/TTL/drop/HMAC/HLL 경계를 유지한다.
- [x] 선택한 실제 flow collector의 방향별 packets/bytes·window/identity/reset·sampling/offload/namespace/누락 상태를 구현하고 기존 비특권 보고 경로와 통합한다. Raw payload/클라이언트 IP durable 저장, NIC-to-peer 배분, endpoint 이중 합산 및 가짜 완전 메시를 금지한다. 실제 알려진 peer 간 트래픽으로 증가/역방향/0/재시작/누락 경계를 exercise한다.
- [x] 하나의 controller-centered radial graph로 role 목록/trace/probe 화면을 통합한다. 실측 edge width/brightness·packets/s 또는 bytes/s 선택, evidence layer, selection inspector·stable refresh·pan/zoom/fit·keyboard/touch·mobile sheet를 완성하고 obsolete 기본 표현을 제거한다. 컨트롤러가 실제 transit라는 추정은 하지 않는다.
- [ ] 소비자-visible 경계/상태전이 회귀와 실제 backend/frontend/collector runtime smoke, 모바일·태블릿·데스크톱 및 767/768·1023/1024 경계·네 locale/light/dark/reduced-motion browser 화면을 검증한다. Synthetic/real/production 근거를 분리한다. 영향받는 문서/changelog/architecture stamp·staged guard를 갱신하고 모두 완료된 뒤 archive한다. 배포 요청/승인이 있으면 정확한 release·backup·Kolla 표준 절차·운영 화면까지 별도 검증한다.
