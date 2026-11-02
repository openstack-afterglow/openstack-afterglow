## Why

사용자는 버전 상향이 항상 정식 release 발행까지 포함함을 명시했다. 1.32.2 metadata와 검증된 source는 이미 local dev에 있으나 아직 게시되지 않았다.

## What Changes

- 버전 상향의 완료 계약을 개발·배포 가이드에 기록한다.
- 검증된 1.32.2 source와 문서만 dev에 게시하고 exact-SHA CI 성공 뒤 불변 numeric tag·GitHub Release·image/alias·Helm을 검증한다.
- 다른 세션의 미커밋 변경과 운영 Kolla/native/schema 작업은 제외한다.

## Capabilities

### New Capabilities

없음. 기존 발행 절차 실행 및 완료 계약 명확화다.

### Modified Capabilities

없음. API/runtime 계약은 변경하지 않는다.

## Impact

Source baseline c4446dab89293f632f983690a775126f71843d04, checklist closeout 6bf79ca2bc1a19e01b3b58f326af8cc1bbf4288c. Source fingerprint c8d56bf68e9c4e37cf9bcf262881e1c6ab7e378cf2cc312ba9051e8d3ebd2b9f/3942 files; full gate와 실제 isolated runtime smoke는 기존 prepare proof에 있다. Main PR/merge는 pie_root 소유, 기존 tag는 이동하지 않는다.
