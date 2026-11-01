## Why
VM 생성 첫 화면이 아직 리소스/GPU 선택 데이터를 기다리면서 빈 slider와 폼을 먼저 노출한다. 사용자는 초기 준비 동안 여러 loading 메시지로 현재 일을 안내하고 준비 후 선택 화면을 보여 달라고 요청했다.

## What Changes
- 최초 flavor 단계에서 resource/GPU snapshot, 기존 flavor inventory, 저장 구성 이력이 준비될 때까지 폼/stepper/footer 대신 preparation surface.
- 실제 pending 작업 중 headline을 순환하고 각 작업의 pending/done/failed를 표시. 거짓 퍼센트·최소 대기 없음.
- 실패는 preparation 안에서 explicit retry, 닫기 유지. 정상 background refresh는 폼을 가리지 않는다.
- 관리자 target chooser, actor/scope fences, existing native save/create 검증과 request graph 유지.

## Capabilities
### New Capabilities
없음.
### Modified Capabilities
VM 초기 리소스 선택의 loading UX.

## Impact
Frontend panel와 준비 component 및 9locale 문구/behavior regression만 변경. API/native/DB/schema/config 배포 영향 없음. 격리 compiled UI에서 지연·실패·회복·두 모드를 확인한다.
