## Release
- [x] 현재 dev 변경과 이전 exact-source gate·배포 증거를 확인한다.
- [x] 1.30.20 metadata와 문서·architecture를 동기화하고 정본 gate·staged guard를 통과한다.
- [ ] 완료된 변경을 dev에 커밋하고 origin/dev로 정상 push한다.
- [ ] 정확한 SHA의 CI 성공 뒤 불변v1.30.20을 발행하고 version/latest artifact를 확인한다.
- [ ] 실제 inventory·native schema·복구 지점과 기존 service release/config/key 보존을 확인한다.
- [ ] canonical Kolla genconfig/pull/prechecks/reconfigure로 배포하고 readiness·running revision/digest를 확인한다.
- [ ] public HTTPS 화면·인증 경계를 확인하고 결과·검증 한계를 기록한다.
