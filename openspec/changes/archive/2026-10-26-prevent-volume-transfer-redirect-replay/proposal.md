## Why

관리자 볼륨 target 인증·owner readback 및401 재인증 replay 수정 뒤에도 installed Keystoneauth Session은 기본 redirect를 따르며 동일 method/body/headers를 Location에 다시 보낸다. Cinder create/accept의307/308은 두 번째 POST와 transfer auth key/native credential의 별도 origin 전달 경로가 된다. 이전 source 검증의401 차단은 이 경로의 증거가 아니므로 후속 수정과 독립 evidence를 남긴다.

## What Changes

- invocation-local Cinder transfer create/accept proxy의 request에 redirect=False를 추가한다. 최초 요청의 실제 target authentication·owner readback과 native 거부를 유지한다.
- 실제 SDK/loopback native source와 별도 redirect sink로 create/accept×307/308을 회귀 검증한다. Sink POST0·auth key/native token 전달0, 원래 endpoint의 제출1과 실제 owner/pending 불변을 확인한다.
- 실제 Uvicorn TCP smoke, focused/storage target, 격리 architecture/gate 결과와 문서·changelog를 갱신한다. 앞서 전체 gate 실패는 소급 성공으로 바꾸지 않는다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

볼륨 transfer native mutation의 single-submission과 one-time key 목적지 경계.

## Impact

Cinder wrapper2개와 기존 native HTTP fixture/test 및 문서만 변경한다. 새 API/config/schema/dependency/권한·자동 retry는 없다. Shared index·private 설정·다른 세션 WIP·운영 runtime/IAM·실제 volume 소유권을 보존하고 source-only로 작업한다.
