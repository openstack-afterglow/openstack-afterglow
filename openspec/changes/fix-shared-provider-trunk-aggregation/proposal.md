# Shared provider 트렁크 귀속 보완

## Why

`is_shared=true`인 private provider는 라우터의 `external_gateway_network_id`가 아니라 일반 interface로 연결될 수 있다. external gateway만 uplink로 분류하면 shared provider 전체 NIC 합이 해당 라우터 트렁크에 남아 다른 하위망 트래픽을 반복 표시한다.

## What Changes

- 트렁크 대상 네트워크의 graph tier가 `provider`이면 external/shared 구분 없이 provider uplink로 분류한다.
- provider uplink 합산에서는 연결된 provider 네트워크들을 제외하고 라우터가 직접 연결한 tenant 네트워크만 포함한다.
- external provider와 shared provider가 같은 helper, 배지 캡션, hit title 규칙을 사용한다.

## 완료 기준

- shared provider에 붙은 gateway 없는 라우터도 provider 전체값 대신 직접 연결된 tenant 네트워크 합을 표시한다.
- provider 네트워크 자체는 uplink 합산에 포함되지 않는다.
