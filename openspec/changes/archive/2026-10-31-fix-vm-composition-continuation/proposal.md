## Why

VM 생성 직접 구성 단계에 inline 저장/계속과 footer 다음이 동시에 존재한다. 사용자는 구성 저장 POST의409 `Another role change is in progress`, default network404, aria-hidden backdrop focus 경고를 보고했다.

## What Changes

- 한 footer primary action이 직접 구성의 저장과 성공 후 다음 단계 이동을 소유한다. 저장 실패/unknown·scope 전환·중복 submit 보호와 기존/저장 flavor 선택을 유지한다.
- 구성 저장409의 실제 lease 경로를 추적하고 원인을 수정한다. 권한·graph serialization을 우회하거나 공유 Redis lock을 삭제하지 않는다.
- default network404와 backdrop focus 경고를 별도로 분류하고 실제 원인이 확인된 결함만 최소 수정한다.
- focused 회귀와 실제 current-source 브라우저·격리 API smoke를 수행하고 docs/architecture에 정확한 경계를 기록한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

VM flavor composition continuation 및 현재 graph lease 사용.

## Impact

Frontend wizard/store, composition service와 해당 테스트/문서. 현재 공유 dev의 기존 변경과 운영 DB·Redis·Keystone/Nova 설정은 보존한다. 운영 배포·공유 자원 생성/삭제·강제 lease 해제는 포함하지 않는다. 현재 사용자의 화면은 오류 증거로 사용하며 확인을 위한 실패 요청 재전송을 하지 않는다.
