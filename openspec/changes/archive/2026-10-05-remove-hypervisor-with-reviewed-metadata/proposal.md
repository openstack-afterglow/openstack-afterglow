## Why

관리자가 특정 컴퓨트 노드의 OpenStack 등록을 제거할 수 있어야 하지만, scheduling disable만으로 노드를 제거하거나 heartbeat down을 물리 종료로 오인하면 orphan compute records와 데이터 손실이 생긴다. 개별 호스트의 metadata, 현재/과거 workload와 Placement를 직접 점검·승인해야 한다.

## What Changes

- 기존 Nova hypervisor/service identity·host 서버 전체 페이지 조회를 공용 `backend/app/services/nova_hosts.py`로 이동한다. `get_hypervisor(conn, id)`, `get_compute_service(conn, hypervisor)`, `host_servers(conn, host, *, deleted=False)`; 기존 admin 경로는 이 정본을 재사용한다.
- `backend/app/services/hypervisor_removal.py`는 `inspect_host(conn, hypervisor_id)`로 실제 Nova/Placement를 조회한다. Hypervisor/service 정확한 매핑, host당 단일 compute node, disabled/down, last service update, 강제 down 여부, all-project 현재 서버(soft-deleted 포함), Nova 보존 삭제 서버·이주 이력, Placement root+child provider allocations를 점검한다. API/페이지/parse 실패는 unknown 또는 endpoint 실패이며 빈 목록으로 대체하지 않는다. forced_down=true는 heartbeat timeout을 증명하지 않으므로 제거 불가. 정상 live uptime은 정보이며 down-host uptime unavailable 자체만으로 제거를 차단하지 않는다.
- Nova는 2.59 migration 응답을 pagination 이후 hidden-filter하므로 빈 중간 페이지를 전체 조회 완료로 취급하지 않는다. 2.58 unpaged host-filtered visible history를 정본으로 읽고 2.59 UUID scan과 full identity를 대조한다. Cross-cell ID 중복은 허용하되 모순/구분 불가 기록은 unknown이다. 명시적 nullable source/dest는 유지하고 어느 한쪽은 대상 호스트와 정확히 일치해야 한다.
- 선택 호스트의 상세/점검에서 실제 성공한 uptime sample만 cloud+hypervisor+service에 묶어 Redis에 30일 보관한다. 현재 조회 실패 때 이전 관측값/관측 시간을 source=last_observed로 구분한다. 이 cache는 생존 판정·삭제 허용 근거가 아니며 최초 관측 전/Redis 유실 시 명시적으로 unavailable이다.
- `POST /api/v1/admin/hypervisors/{id}/removal-check`: 시스템 관리자만 fresh inspection을 수행한다. eligible일 때 사용자/project/cloud/hypervisor/service와 fingerprint에 묶인 5분 만료 one-use review token 발급. 응답 `report`+`review_token`+`expires_at`.
- `POST /api/v1/admin/hypervisors/{id}/remove`: `{review_token, confirm_hostname, reason, reviewed_metadata:true, compute_stopped:true}`. 사유·정확한 호스트명·metadata 검토·실제 nova-compute 중지 확인 필수. 호스트별 Redis lock 아래 token을 원자적으로 소비하고 fresh inspection이 여전히 eligible이며 review fingerprint와 같을 때만 Nova `DELETE /os-services/{verified_service_uuid}` (compute 2.53)를 호출한다. 실제 장비/다른 OpenStack 서비스/VM/storage를 삭제하지 않는다. 기존 scheduling/relocate도 같은 호스트 lock을 사용한다.
- Nova DELETE 후 service 및 hypervisor 부재, Placement provider tree 부재와 aggregate membership 제거를 검증한다. 204만으로 완료를 선언하지 않는다. 결과 `status: removed|removal_unverified`, `verified: boolean`, `hypervisor_id`, `hostname`, `service_id`, `detail`, `checks`를 반환하며 unverified는 UI에서 보고서를 보존한다. 감사 기록에는 대상·actor·사유·review/fresh checks·검증 결과를 남기고 token은 남기지 않는다.
- 호스트 상세에 독립된 제거 점검 UI를 추가한다. 새 점검 요청/새로고침, metadata·명시적 blocking reasons·현재/과거 인스턴스·provider 할당을 보여준다. 확인 checkbox·호스트명 입력·사유 후 하나씩 제거 승인. 점검 refresh/host/project 전환/상태 변경/만료/실패에서 승인 입력을 초기화하며 one-use token을 재사용하지 않는다. 자동 목록 갱신은 선택 상세도 갱신한다. 모바일 상세는 기존 SlidePanel의 modal/full-width 계약을 사용한다.

### Shared API contract

Inspection response:
```
{
  report: {
    hypervisor_id: string, hostname: string, checked_at: string,
    service: {id:string,host:string,binary:string,state:string,status:string,updated_at:string|null,forced_down:boolean|null,disabled_reason:string|null,zone:string|null},
    uptime: {status:'available'|'unavailable',value:string|null,host_time:string|null,source?:'live'|'last_observed'|'unavailable',observed_at?:string|null},
    servers: [{id:string,name:string,status:string,project_id:string,created_at:string|null}],
    history: {deleted_servers:[{id:string,name:string,status:string,project_id:string,created_at:string|null}], migrations:[{id:string,uuid:string,instance_uuid:string,source_compute:string|null,dest_compute:string|null,status:string,migration_type:string,created_at:string|null,updated_at:string|null}],note:string},
    placement: {providers:[{uuid:string,name:string,parent_provider_uuid:string|null,generation:number,allocations:Record<string,unknown>}]},
    checks: [{code:string,label:string,state:'pass'|'blocked'|'unknown',detail:string}],
    eligible:boolean
  },
  review_token:string|null, expires_at:string|null
}
```
`review_fingerprint(report)` hashes deterministic review metadata (identity/service updated_at/states, current+historical workloads, migration states and provider generations+allocations), excluding checked_at/uptime sampling. Inspection does not expose fingerprint. Verification function `verify_removal(conn, report)` returns `{status,verified,hypervisor_id,hostname,service_id,detail,checks}`; never mutates Placement manually. Public check unknowns are explicit; no raw upstream errors or credentials.

## Capabilities

### New Capabilities
- Single-host reviewed Nova compute service removal, fresh fail-closed gates and completion verification.

### Modified Capabilities
- Existing hypervisor scheduling/migration retains behavior, sharing identity lookup and host operation exclusion.

## Impact

Backend admin routes, shared Nova host lookup and removal inspection, administrator Svelte UI, focused behavioral pytest and browser smoke, admin API/architecture/design/changelog documentation. No DB migration, configuration/deployment/credentials or live cloud mutation. Nova 2.53 lookup/delete + 2.58 unpaged and 2.59 UUID migrations and Placement 1.14+ tree/allocation reads required. Retained deleted/migration history is incomplete historical evidence, never proof of a never-used host. Physical process shutdown is an explicit operator attestation, not remotely enforced by Afterglow.

Reference: https://docs.openstack.org/api-ref/compute/#delete-compute-service ; https://docs.openstack.org/api-ref/compute/#list-migrations .
