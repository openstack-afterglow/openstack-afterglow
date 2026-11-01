## Context

사용자는 native CLI/API까지 집행하는 Nova 전용 확장, 도메인 공용 풀, manager 또는 system-scope admin에 의한 선택적 프로젝트 상한, 표준 flavor 자동 생성을 선택했다. 기존 프로젝트 GPU SQL ledger와 native project limit 합계 budget은 요청한 사용량 풀과 다르다. Stock oslo.limit strict-two-level은 stable/2025.2와 조사한 master 모두 미구현이므로 이를 설정으로 켜는 방안은 배제한다.

## Goals / Non-Goals

**Goals:**
- 같은 native domain의 프로젝트들이 CPU(VCPU+PCPU), MEMORY_MB, GPU 모델별 PCI resource class의 사용량 한도를 공유한다.
- 선택적 프로젝트 상한은 domain manager 또는 fresh system-scope admin만 설정하며 도메인 한도 이하이다. 상한의 합계를 allocation budget으로 계산하지 않는다.
- Afterglow는 동일 authority의 UI/조회/사전검증을 제공하고 native Nova가 직접 호출 및 비동기 자원 claim 이후 재검사까지 집행한다.
- 하드웨어가 지원하는 bounded standard CPU/GPU flavor를 안정적으로 생성·관리하고 native alias/audio mapping·실제 권한·사양 readback을 검증한다.

**Non-Goals:**
- 운영 도입/계정·기존 datastore/VM/volume/config의 자동 변경. 사용자 승인 전 live rollout은 하지 않는다.
- hypervisor의 순간 free capacity를 flavor 규격으로 삼거나 cross-host CPU/RAM/GPU 최대값을 합성하지 않는다.
- flavor metadata를 quota 또는 native authorization 집행으로 오인하지 않는다. 기존 manual flavor를 이름만으로 소유/삭제하지 않는다.

## Decisions

### Native-readable authority

Keystone domain extra `afterglow_compute_pool`에 versioned 정책을 저장한다: `{schema:1, revision:int, enabled:bool, limits:{CPU|MEMORY_MB|CUSTOM_PCI_*:int}, project_limits:{project_id:{resource:int}}}`. 정책은 엄격한 native ID 검증·manager/system auth·공유 graph lease·revision compare·native readback을 통해 갱신한다. 프로젝트 limit 누락은 domain pool을 공유하며 explicit0은 거부다. Managed resource 누락·정책/usage 불명은 허용으로 보정하지 않는다. 기존 개인/서비스 domain을 암묵적으로 pool로 전환하지 않는다. System admin의 명시적 transition만 허용하고 legacy GPU/project allocation limit의 전환 preview와 mixed-version 조건을 드러낸다.

### Nova-specific enforcement

`services/nova-domain-quota`에 별도 package와 version-checked build-time native integration을 둔다. 전역 oslo.limit/Keystone enforcement model 변경이나 runtime monkeypatch/sitecustomize를 사용하지 않는다. Nova native precheck·Placement claim 이후 recheck를 모두 포괄해야 한다. Complete native project directory로 exact target domain을 검증하고 Placement usage(이주 allocation 포함)를 합산한다. CPU budget은 VCPU와 PCPU를 함께 센다. GPU quota는 실제 PCI class이며 audio를 GPU로 세지 않는다. Native project의 unrelated local/server quota는 보존한다. `recheck_quota`와 native PCI accounting 선행 조건을 확인하며 미지원 hook/version/accounting은 차단한다. 설치 marker나 domain enabled metadata만으로 deployed enforcement를 증명하지 않는다.

정책 부재만 unmanaged이며 명시 enabled:false는 paused로 신규 allocation을 거부한다. GPU/audio 분류는 configured alias와 전체 compute-host sysfs class/BDF/sibling 증거이며 로컬 모델명 catalog는 표시용이다. 모든 nonempty Placement write는 net-zero/decrease도 postcheck한다. Consumer delete/recreate ABA 때문에 generation만으로 nonempty preimage 복원을 안전하다고 보지 않으며 실패는 explicit reconciliation이다. 새 consumer의 empty rollback만 generation/shape로 fence하고 safe peer cleanup은 계속한다. All-empty release는 authority outage 뒤 되살리지 않는다. Fleet qualification은 실제 loaded worker/census/hardware/source/config 증거가 필요하며 한 시간 read-only refresh는 exact rollout이 같을 때 30일 이내 native operation acceptance를 재사용할 수 있다. 통합 Nova 바깥 unrestricted Placement writer는 집행 범위가 아니므로 write policy를 통합 principal로 제한해야 한다.

### Automatic flavor lifecycle

vCPU=1/2/4/8/16/32/64/128, RAM/vCPU=2/4/8GiB, GPU=1/2/4/8의 bounded 표준 규격을 같은 eligible host의 supported inventory에만 맞춘다. Disk0은 기존 volume boot 계약을 사용한다. GPU alias와 audio 연결은 native configured evidence가 있을 때만 사용하며 unknown은 diagnostics로 노출한다. ID는 shape 기반으로 결정적이고 `afterglow:managed_by=domain-compute-v1` 소유 marker를 검증한다. GPU에는 `afterglow:access_mode=gpu_quota`, CPU에는 `domain_quota`를 넣되 marker는 native enforcement를 대신하지 않는다.

Native create는 private staging→specs→readback→자동 visibility/ACL publication 순서다. 새 프로젝트와 quota 변경을 포함해 자동 reconciliation하며 disable·authority drift·lease loss에서 늦은 쓰기를 fence한다. 수동 flavor·사용 중 VM 사양·불명 inventory를 파괴적으로 정리하지 않는다. 일시적으로 full인 호스트 때문에 flavor를 지우지 않는다. 장애 시 마지막 표시 snapshot과 오류를 구분하고 mutation은 차단한다.

### Console and integration

Admin domain 및 manager quota UI에서 pool/usage/remaining과 project cap을 분리한다. Admin flavor UI는 automation 상태·enable·명시 reconcile·managed specs를 제공한다. Existing API client·UI primitives·scope/revision/ABA guards를 재사용한다. User/admin create, resize, MCP, internal K3s, dashboard/report, tutorial에서 quota authority를 같은 경로로 맞춘다. Native Placement의 개별 atomic claim과 Nova의 domain pre/postcheck가 최종 집행 경계이며 domain 전체를 하나의 원자적 transaction으로 잠그거나 UI/사전검증을 reservation 보장으로 설명하지 않는다.

## Risks / Trade-offs

- Nova-specific extension → native upgrades마다 exact hook/version 및 native runtime compatibility를 검증한다. Afterglow source test만으로 qualification하지 않는다.
- Project/usage enumeration 비용 → 전체 directory 보증, bounded fanout/deadline과 explicit unavailable. 부분 합계를 quota로 쓰지 않는다.
- Native timeout/partial readback → 무조건 retry/rollback하지 않고 unknown을 반환한다. 운영 transition은 drain·backup·exact revision/readback·복구 계획이 필요하다.
- Shared policy 전환 → legacy native project quotas와 GPU overrides를 silent 합산하지 않는다. 활성화 전 현재 usage·기존 정책·native integration 상태를 표시한다.
- GPU passthrough alias와 Placement PCI accounting → 실제 Nova 설정/구성 capability 근거가 없으면 자동 GPU flavor publication을 차단한다.

## Verification

Behavior regressions for domain cross-project concurrency, CPU+PCPU, model GPU/audio, project caps/authority, unknown directory/usage, revision/write outcomes; actual native Nova integration smoke not fake import stubs; loopback HTTP SDK/backend actions; compiled console journeys including narrow/theme/locale/tutorial; canonical isolated full gate and multiarchitecture image/native integration builds when applicable. Production rollout and actual cloud workload acceptance remain separate and must not be fabricated.
