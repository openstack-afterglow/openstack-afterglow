## Why
실제 member의 Waygate 생성이 execution token scope 오류로 거부되고 Drover 생성의 quota·단계·진행 표시와 background 추적이 사용자에게 부정확하다. 관리자 버전 정보도 시스템 정보 위치로 옮긴다.

## What Changes
- 실제 native 역할과 제한 credential을 보존하면서 Waygate member 생성 실패를 해결한다.
- 시스템 버전 정보를 관리자 메인에서 시스템 정보로 이동한다.
- Drover 보안 그룹 quota 부족을 native 한도·소유권과 시스템 필요량에 근거해 처리한다.
- 로딩바 너비와 단계별 진행 상태를 실제 작업 상태에 맞추고, 완료 전 최소화는 가능하되 닫히지 않는 지속 상태 표시를 제공한다.
- 기존 리소스, provider 권위, 불명 결과 재전송 금지와 project/auth 경계를 보존한다.

## Capabilities
### New Capabilities
- `cluster-operation-visibility`: 실제 quota와 native 작업 상태를 일관되게 표시·추적한다.

### Modified Capabilities
없음.

## Impact
Afterglow frontend 및 backend, Waygate/Drover native 서비스와 관련 검증·문서. 운영 리소스 삭제나 quota 강제 상향은 포함하지 않는다.
