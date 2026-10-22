## Investigation
- [x] 관리자503의 actual native executor token/guard와 운영 stack frame을 대조한다.
- [x] actual SMTP STARTTLS/auth 성공과 signup policy revision0/defaultfalse를 확인한다.
- [x] local DMSLab-only provider/domain selectors와 production registry absent를 확인한다.
## Implementation
- [ ] 기존 관리자/domain-manager 이메일 admission 정책과 새 global/OIDC topology의 적용 범위를 확인한다.
- [ ] 이메일/OIDC 가입 동작과 signup button visibility를 독립 제어하는 관리자 설정/API/화면을 구현하고 경계 회귀를 검증한다.
- [ ] 승인된 이메일 가입 및 exact DMSLab domain OIDC/자동 참여 설정만 protected operator source로 반영한다.
## Verification
- [ ] issuer discovery·native protocol/mapping·실제 provider authorize 연결과 production callback을 검증한다.
- [ ] 정본 gate·exact-source commit/push/release 및 전체 native fleet reconfigure·설정/키 보존을 검증한다.
- [ ] 실제 public 화면·readiness와 미검증 mailbox/user terminal/native identity 경계를 보고하고 archive한다.
