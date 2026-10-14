## Why

운영 수집 활성화는 완료됐지만 국가표가 설정되지 않았고 frontend 원본 주소 신뢰는 비활성이다. 현재 국가 `XX`는 국가표 미설정, IP 없음, 사설/예약 주소, 표 미일치를 구분하지 않는다. `/api/monitoring`에는 실제 외부 사용자 요청뿐 아니라 관측기 reports/jobs와 health 요청도 포함되며, 현재 hourly 집계에는 유입 origin 차원이 없다. 인프라 페이지는 역할별 목록, 전체 경로 지도, TCP probe 지도, 호스트 상세가 분리되어 있어 사용자가 요청한 controller 중심 방사형 메시와 방향별 실측 트래픽을 보여주지 못한다.

사용자 요구는 다음 세 가지를 모두 포함한다.

1. IPv4/IPv6 주소 대역을 근거로 접속 국가를 정하고 위치 미확인 사유를 설명한다.
2. 실제 클러스터 내부 요청과 외부 유입 요청을 구분한다. 경로명을 호출 주체로 오인하지 않는다.
3. Controller 그룹을 중심에 둔 하나의 네트워크 토폴로지에서 실측 방향별 packets/s·bytes/s에 따라 화살표 굵기·밝기를 표시한다.

## What Changes

### IP 국가 판정 및 요청 origin

- IPv4/IPv6 국가 IP 대역의 **오프라인 lookup**을 유지한다. 권고 데이터는 DB-IP IP to Country Lite의 월별 MMDB이며, 배포 시 파일 revision/checksum·읽기 전용 mount·provider attribution을 고정한다. Runtime 외부 GeoIP 호출이나 IP 전송을 추가하지 않는다. [DB-IP 공식 배포/CC BY 4.0](https://db-ip.com/db/download/ip-to-country-lite), [공식 범위 CSV 설명](https://db-ip.com/db/format/ip-to-country-lite/csv.html).
- 현행 `CountryLookup`는 canonical CIDR의 longest prefix를 조회하며 CSV 16MiB/250000행으로 제한한다. 공식 2026-10 DB-IP CSV는 710834개 **범위** 레코드/29.8MB이므로 단순히 현재 설정 경로에 공급자 CSV를 넣는 것으로 해결되지 않는다. 공급자 CSV를 CIDR 표인 것처럼 읽거나 일부 국가/주소만 남기는 방식은 금지한다. MMDB 지원/설정 변경 시 backend 모델·loader·예시·K8s·Helm·Compose·Kolla·consumer 계약을 함께 갱신하고 obsolete 설정 경로를 정리한다.
- 직접 peer와 proxy가 확정한 원본 client 주소의 provenance를 검증한다. 현재 backend Uvicorn의 exact proxy allowlist, app-level `_get_real_ip`, public HAProxy의 XFF overwrite 및 frontend adapter/reporter 경계를 함께 검토한다. Frontend에 단순히 ADDRESS_HEADER/XFF_DEPTH/trust=true만 추가하거나 모든 사설 대역을 proxy로 신뢰하지 않는다. 주소를 확인할 수 없으면 unknown을 유지한다.
- origin은 원본 주소와 operator가 승인한 실제 클러스터 CIDR로 분류한다. 요청 경로·User-Agent·HTTP 오류·`is_private`만으로 내부/외부를 단정하지 않는다. Cluster CIDR 밖의 사설/VPN/예약 주소와 검증되지 않은 proxy 주소는 외부 국가에 억지로 할당하지 않는다. 외부 ingress 경유 여부와 원본 주소가 내부 대역인지도 서로 다른 사실로 유지한다.
- API/UI에 source별 내부/외부/미확인 집계와 필터, origin 판정 근거 및 위치 미확인 사유를 추가한다. Observer/health 트래픽을 버리지 않고 내부 시스템 관측으로 구분한다. Backend와 frontend 수치는 합치지 않는다. 과거 raw IP/원문 URL은 저장되지 않았으므로 기존 bucket을 소급 국가/origin 판정하지 않고 legacy-unclassified coverage를 표시한다.
- `site_country=KR`는 서비스 위치일 뿐 caller 국가의 fallback이 아니다. 원문 IP·body·cookie·user-agent·token·URL/query의 durable 저장 금지를 유지한다.

### 하나의 controller 중심 방사형 topology workspace

- Controller들을 중앙 core에, compute/storage와 확인된 network device/외부 목적지를 주변 섹터/동심 레이어에 안정적으로 배치한다. Controller는 **레이아웃 중심**이며 모든 패킷이 controller를 경유한다는 뜻이 아니다. 확인된 compute↔compute, storage↔storage 및 cross-role 흐름도 그 실제 양 끝을 직접 연결한다.
- 별도 role 목록/NetworkMap/PeerProbeMap을 기본 화면의 하나의 그래프로 통합한다. 동일 graph selection에서 host/NIC/flow/evidence inspector를 연다. 필터와 범례, pan/zoom/fit, keyboard 선택과 확대, 터치 조작, 모바일 상세 sheet를 제공한다. Refresh마다 노드가 재배치되거나 선택이 바뀌지 않게 한다.
- 물리 LLDP, 이웃/route, TCP reachability, trace hop, 패킷 계측은 별도 evidence layer다. Controller 그룹 관계는 cable edge가 아니고 ARP/route/TCP 성공도 물리 연결 증명이 아니다. 현재 34개 TCP probe를 완전한 메시나 packet volume으로 표시하지 않는다.
- 실측 방향별 flow만 traffic arrow로 표시한다. 두 방향은 독립 counter이며, 두 endpoint 보고를 단순 합산하지 않는다. packets/s·bytes/s 단위와 관측 window·freshness·collector coverage·sampling/offload 범위를 인접 inspector/범례에 표시한다. 폭/밝기는 범위가 고정·표시된 단조 로그 척도로 연결하고 단위 전환/locale/theme/reduced-motion을 지원한다. 측정된 0, 미계측, stale/reset/unavailable은 서로 다른 상태다.
- NIC 전체 RX/TX를 개별 peer에 나누어 넣지 않는다. TCP latency, HTTP body bytes, traceroute 응답 수를 packets/s로 바꾸지 않는다. 물리 wire packets와 Linux datapath skb, sampled sFlow 추정치는 같은 계측으로 이름 붙이지 않는다.

### 실제 flow 수집의 승인 경계

현재 비특권 observer는 `/proc/net/dev` NIC 합계와 주소/neighbor/route, 선택 LLDP 및 TCP probe만 수집한다. 사용자 요구의 source→destination packet counter는 없다. 권고안은 관측기 sandbox를 약화하지 않고 **별도 최소권한 Linux flow collector**에서 등록된 node endpoint 방향별 헤더 counter만 집계한 후 비특권 observer가 이를 보고하는 구조다. Bounded map/시간 window, NIC/namespace/boot/ifindex identity, reset semantics, 중복 계측 방지, payload 미수집 및 실패 상태가 필수다. Collector 설치·커널 hook·권한 추가는 아래 사용자 선택 전 실행하지 않는다.

**사용자 확정:** 물리 switch/port까지 포함하고 호스트 방향별 흐름+LLDP+switch telemetry를 운영 반영한다. 대상은 Afterglow·관측 수집기로 한정한다. 새 read-only LLDP 관측으로 SG3210X-M2(`50:3d:d1:7a:dc:17`, 광고 management `192.168.0.2`)와 SG3428X-M2(`8c:86:dd:9f:6e:61`, `192.168.0.3`) 및 실제 controller/compute/storage 포트 근거를 얻었다. Operator와 controller1에서 해당 management HTTP/HTTPS 접근은 불가이며 controller1은 `mybr0`/gateway`172.30.0.1` 경로에서 timeout이었다. 검토한 operator globals/Afterglow secrets와 SSH alias에는 SNMP/Omada 권한이 없다. LLDP 광고 주소를 reachable/인증된 관리 endpoint로 단정하지 않고, 관리 경로·읽기 자격과 actual switch port/LLDP-MIB source를 확보한 뒤 운영 계측을 검증한다. BTF 존재만으로 collector 호환·packet accounting 정확성을 선언하지 않는다.

## Capabilities

### New Capabilities

- 운영자 고정·읽기 전용 국가 대역 DB의 출처/revision/유효 상태와 국가 판정 실패 사유.
- 신뢰된 원본 IP와 클러스터 CIDR에 근거한 내부/외부/미확인 요청 origin 집계 및 origin 필터.
- 사용자 승인 collector가 실제 계측한 방향별 호스트 flow counter와 그 측정 범위.
- Controller-core radial mesh, 통합 evidence layer와 node/edge inspector.

### Modified Capabilities

- Traffic 집계는 source 분리·finite cardinality·atomic Redis update·TTL·HMAC/HLL·dedupe·drop coverage를 유지하면서 origin을 추가한다. HTTP path category를 호출 주체라고 표시하지 않는다.
- 기존 infrastructure topology auth/generation fence/10초 refresh·30초 stale 의미, 비특권 observer, trace allowlist와 TCP probe 경계를 유지한다. 새 flow 수집이 실패해도 기존 관측을 정상인 flow 0으로 둔갑시키지 않는다.

## Impact

### Reviewed evidence

- Retained production activation proof: `~/.local/share/afterglow-proofs/activate-observation-20261014T143303Z/traffic-final-native.json`와 기존 handoff. Geo source unconfigured, frontend client trust=false, 18 node/34 directed TCP probe. 이전 활성화/acceptance를 재실행하지 않았다.
- Source: `backend/app/services/traffic_geo.py:268-316`, `backend/app/models/traffic_analytics.py`, `backend/app/middleware/traffic_analytics.py`, `backend/app/services/traffic_analytics.py`, `frontend/src/lib/server/trafficReporter.ts`, `backend/app/rate_limit.py`, `backend/app/api/monitoring/host_observations.py`, Kolla public route/defaults.
- Local throwaway execution exercised current lookup and route categorization: empty country table→XX; synthetic IPv4/IPv6 known prefix→US; private/missing address→XX; health/reports/jobs all→`/api/monitoring`; exit0. This is local/source evidence, not an operating GeoIP dataset or a production origin attribution test.
- New read-only production prerequisites on representative compute1/controller1/storage1: kernels 6.8.0-111/6.8.0-142/5.15.0-194; BTF readable on all three; bpftool present on first two, absent on storage1. All three report an assigned `172.30.0.0/16` interface network. These are representative observations, not qualification of all18 nodes or confirmation that every RFC1918 address is internal. Host `ovs-vsctl` absence is not proof that containerized OVS is absent.

### Affected areas and safety

Backend traffic settings/models/lookup/aggregation/API/middleware; frontend server reporter/types/traffic UI; host observer and independently approved collector; infrastructure model/service/frontend graph; generator/examples/Helm/Compose/Kolla; deterministic boundary regression tests and actual runtime/browser checks. Existing Redis history/keys/identity secrets and application auth binding must not be silently discarded or rotated. New SQL schema is not required for these observations; Redis format/mixed-version writer compatibility still needs qualification.

Work remains on `dev`, preserving concurrent work and index. No app code, image, secret, running observer or production ingress setting has been changed during this investigation. This proposal is not deployment acceptance. Finish the approved implementation and consumer migration, exercise genuine collector traffic and browser interaction, update architecture/API/deployment/testing/changelog, stamp/guard the isolated exact source, and archive only after every acceptance item is proven. A production release/cutover needs its explicit authorized scope and recovery point.
