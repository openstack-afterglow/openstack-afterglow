---
layout: default
title: VM 생성 workflow
parent: Frontend 리소스 workflow
grand_parent: 클래스 다이어그램
nav_order: 1
---

# VM 생성 workflow

**진입점:** `frontend/src/lib/components/VmCreatePanel.svelte`는 `createVmCreateStore()`를 만들고 wizard context에 제공한다. `VmCreateStore.deploy()`는 사용자 또는 관리자 일반 VM 생성과 SSE 진행 상태를 담당한다. 공개 squashfs/library consume와 비동작 HA 선택은 제거했으며 독립 관리자 Palimpsest 빌드·소비는 이 wizard 밖에 있다.

## Sequence

```mermaid
sequenceDiagram
actor User
participant Panel as VmCreatePanel
participant Store as VmCreateStore
participant Wizard as wizard state
participant API as /api/v1 instances async
participant Progress as SSE response body
participant UI as toast + goto

User->>Panel: wizard 입력 후 배포
Panel->>Store: deploy()
Store->>Wizard: image/flavor/network/mount 선택값 읽기
Store->>API: POST /api/v1/instances/async 또는 /api/v1/admin/instances/async
loop data: progress event
  API-->>Progress: step, progress, message, error
  Progress-->>Store: state 갱신
end
Store-->>UI: success/error toast
Store->>Wizard: resetWizard() + closeWizard()
Store->>UI: goto(/dashboard 또는 /admin/instances)
```

## 시나리오 클래스

```mermaid
classDiagram
class VmCreatePanelModule["frontend/src/lib/components/VmCreatePanel.svelte"] {
  <<component>>
}
class VmCreateStoreModule["frontend/src/lib/stores/vmCreateStore.svelte.ts"] {
  <<module>>
  +createVmCreateStore()
  +deploy()
}
class WizardModule["frontend/src/lib/stores/wizard.ts"] {
  <<module>>
}
class ProgressMessage["frontend/src/lib/stores/vmCreateStore.svelte.ts::ProgressMessage"] {
  <<interface>>
  +step: string
  +progress: number
  +message: string
}
class InstanceAsyncEndpoint["/api/v1/instances/async"] {
  <<HTTP endpoint>>
}

VmCreatePanelModule --> VmCreateStoreModule : creates and provides
VmCreateStoreModule --> WizardModule : reads selection
VmCreateStoreModule --> InstanceAsyncEndpoint : POST and streams
InstanceAsyncEndpoint --> ProgressMessage : emits
```

## 근거

- `vmCreateStore.svelte.ts::deploy`는 일반 경로에서 `/api/v1/instances/async` 또는 `/api/v1/admin/instances/async`에 `fetch` POST하고 SSE-like `data:` line을 소비한다.
- 일반 VM 입력은 이미지/기존 부팅 볼륨, flavor·network·SSH·GPU·직접 데이터 mount를 유지하며 library/squashfs consume와 HA payload를 보내지 않는다.
- 완료 시 wizard reset/close와 `goto()`를 수행한다.
