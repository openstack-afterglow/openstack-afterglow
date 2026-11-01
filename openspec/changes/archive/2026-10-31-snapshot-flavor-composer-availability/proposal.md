## Why
VM 자원 선택마다 조건부 옵션 GET을 다시 실행해 사용자가 CPU/RAM/GPU 선택 후 각각 native quota/Placement 조회를 기다린다. 사용자 요청대로 창 초기화 때 전체 가능 조합을 받고 선택은 브라우저에서 즉시 반영한다. 추가 요청에 따라 vCPU는2·4·6…128만 선택한다.

## What Changes
- 기존 consumer/admin composer-options를 전체 CPU/RAM-only·승인 GPU profile/count snapshot으로 전환한다. 동일 root·실제 잔량·inventory min/step/max·primary/companion·native/domain/project quota를 함께 만족하는 correlated region을 압축 반환한다. Host/provider 식별자와 Cartesian flavor 목록은 반환하지 않는다.
- 클라이언트는 scope-local memory snapshot으로 exact 옵션·preview를 계산한다. 편집은 GET/로딩 대기를 유발하지 않으며 초기/주기/수동 조회가 완료되면 현재 최신 tuple에 적용한다. 재조회 실패·권한 전환·불명 저장 fence를 유지한다.
- vCPU 입력·slider·API composition을2의 배수로 제한하고 명시 최소 reset은2CPU로 한다. 과거 홀수 초안은 조용히 다른 사양으로 바꾸지 않으며 직접 수정하도록 표시한다. 기존 native standard/catalog/VM의1CPU 등 사양·UUID는 그대로다.
- 저장/VM create는 현재 native quota/host admission을 다시 읽는다. Snapshot은 예약/허가가 아니며 구형 backend/frontend wire 호환 shim은 두지 않는다. Backend/frontend는 함께 배포해야 한다.

## Scope and Safety
Source/backend/frontend/tests/docs만 변경한다. DB/schema/config/키/공유 서비스·운영 cloud/quota/scheduler 설정을 변경하거나 배포하지 않는다. Native deterministic identity·private history·unknown-write non-replay·권한/scope/ABA fence는 유지한다. 운영 apply는 별도 승인이다.

## Acceptance
수동/주기 갱신을 제외하고 연속 CPU/RAM/GPU 선택 시 composer-options 요청 증가0. 최소두 host의 CPU/RAM tradeoff와 GPU primary/companion·project/domain/native quota를 검증한다. 초기 응답 중 편집/새 scope/late response, 홀수CPU 저장 차단·6CPU허용·reset2·legacy identity 보존을 검증한다. 실제 API runtime+compiled browser, 관련 target/check/build/gate를 실행하고 실행/합성 경계와 실패를 증거에 기록한다.
