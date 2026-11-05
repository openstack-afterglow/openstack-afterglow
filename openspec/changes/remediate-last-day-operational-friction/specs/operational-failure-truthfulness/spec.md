## ADDED Requirements

### Requirement: Scoped native reads distinguish absence from unavailability
시스템은 SHALL 이번 cutover 대상인 Trove owner/detail·Manila detail·소비자/관리자 Zun detail·Swift object/container metadata/preflight 읽기에서 native401/403/404만 정적 opaque404로 유지하고, 그 밖의 native HTTP·transport·예상 밖 실패는 원문과 native header 없이503으로 구분한다. Strict로 전환한 Trove inventory/subresource와 Swift inventory/trash/account 읽기는 실패를 정상 빈 목록 또는0으로 합성하지 않는다. 문서에 명시한 Swift 계정 미초기화/권한 부재와 trash 부재의 빈 목록 계약, service-disabled 계약은 유지한다.

#### Scenario: Native outage is not a missing container
- **WHEN** 현재 권위가 검증된 관리자 또는 소비자의 Zun 단건 native 조회가503으로 실패한다
- **THEN** source 응답은 정제된503이며404 또는 자원 삭제 성공으로 표시하지 않는다

#### Scenario: Native absence and denial remain opaque
- **WHEN** cutover 대상 단건 native 조회가401/403/404를 반환한다
- **THEN** 정적404만 반환하고 provider 본문·header·대상 존재 여부를 추가 공개하지 않는다

#### Scenario: Failed inventory is distinct from a valid empty inventory
- **WHEN** strict Trove/Swift 조회가 실패하거나 native200이 실제 빈 배열을 반환한다
- **THEN** 실패는5xx로 전파하고 실제 정상 빈 응답만 빈 inventory로 수용하며 과거 fake-empty cache와 새 조회의 namespace를 분리한다

### Requirement: Full quota optional-service usage has explicit availability
시스템은 SHALL full dashboard quota의 Trove·Swift 통계를 독립 strict 조회하고 실제 정상0·조회 불가·비활성을 nullable 값과 명시 section 목록으로 구분한다. 선택 서비스 실패는 정상 core quota·기간 보고서를 버리지 않으며 과거 fake0 cache를 새 namespace에서 제공하지 않는다. 관련 quota/pool 변경은 새 cache를 무효화하고 기존 native admission·quota write·권위는 유지한다.

#### Scenario: Independent optional-service outage
- **WHEN** Trove 또는 Swift가 활성 상태에서 native 읽기에 실패한다
- **THEN** 해당 값은 `null`과 `unavailable_sections`로 표시하고 정상 sibling/core 값은 유지하며 UI는0 대신 조회 불가를 표시한다

#### Scenario: Disabled and genuine-zero optional usage
- **WHEN** 선택 서비스가 비활성이거나 strict native 응답에서 실제0이 확인된다
- **THEN** 비활성은 조회 없이 `null`과 `disabled_sections`, 정상0은0과 빈 unavailable 목록으로 구분한다


### Requirement: Independent administrative service failures preserve known values
시스템은 SHALL 관리자 resource-policy/runtime-setting 합성 조회에서 정상 local/다른 서비스 값을 유지하고 실패한 native service와 numeric HTTP status를 별도 errors로 반환한다. 중앙 권위·local store/connection 실패는 원래 top-level 거부를 유지한다. UI는 미설정/null·명시 false·조회 불가를 구분하고 조회만으로 업무 설정을 변경하지 않는다.

#### Scenario: One native policy service is unavailable
- **WHEN** 한 native 서비스 조회는503이고 local 또는 독립 서비스 조회는 성공한다
- **THEN** 정상 값을 보존하고 실패한 service/status만 errors로 알리며 실패를 권한 허용·명시 OFF·정상 부재로 해석하지 않는다

### Requirement: Diagnostics never retry business effects or disclose raw failure content
시스템은 SHALL 진단 실패·취소·응답 유실 때문에 원 업무 native 호출·SMTP DATA·일회용 동의 요청을 replay하거나 업무 terminal을 강등하지 않는다. Secret-safe API/worker 로그는 source/process/runtime·유한 stage/reason·known numeric driver code만 보존하고 원문 SQL·credential·입력·DOM·채팅·terminal·임의 exception 내용을 진단에 추가하지 않는다.

#### Scenario: Completion observation is cancelled after SMTP acceptance
- **WHEN** SMTP 결과가 반환되고 completion 진단 중 취소가 도착한다
- **THEN** 이미 기록된 업무 terminal을 유지하며 accepted 메일을 unknown으로 바꾸거나 재전송하지 않는다

#### Scenario: Cancellation is hidden by diagnostic shielding
- **WHEN** 소유 scope가 취소됐지만 반환 관측의 shield 때문에 취소 전달이 보류된다
- **THEN** 이미 반환된 native 결과는 보존하고 다음 SDK 작업 전에 취소를 드러내며 실제 SDK 종료까지 소유 admission/connection/lease를 유지한다

### Requirement: Synchronous metric provider reads do not stall the application loop
시스템은 SHALL instance metrics 단일·batch·summary의 동기 Nova 상세 및 조건부 flavor 조회를 application event loop 밖에서 실행한다. 기존 소유권·오류·native-first 계약을 유지하고 취소된 요청도 실제 provider 작업 종료 전 연결의 소유 lifecycle을 끝내거나 native 호출을 재전송하지 않는다.

#### Scenario: Native resolution is waiting on an HTTP response
- **WHEN** metric 요청의 Nova 상세 또는 summary flavor 조회가 아직 native HTTP 응답을 기다린다
- **THEN** 독립 application coroutine은 계속 실행되고 반환된 server의 원래 프로젝트 소유권 검사는 생략하지 않는다

#### Scenario: Request cancellation arrives during the native read
- **WHEN** 동기 Nova 읽기가 실행 중인 요청이 취소된다
- **THEN** 실제 native 반환까지 기존 completion-drain을 유지하고 새 provider 호출이나 retry를 시작하지 않는다

### Requirement: Operational containment and qualification remain separate
시스템은 SHALL 승인된 wrong-key local consumer 중지와 불확실한 Hub claim 원장을 보존하고 source/local 검증을 운영 복구·native IAM·사람 인지·전체 서비스 readiness의 증거로 승격하지 않는다. 원래 key·정합 release/schema·복구 조건·현재 사람 권위와 별도 승인이 없으면 native 배포·unknown 재실행·운영 SQL107/수집/보존 삭제를 활성화하지 않는다.

#### Scenario: Local qualification succeeds while native prerequisites remain missing
- **WHEN** 격리 compiled browser/API/worker/SQL과 전체 gate가 통과했지만 운영 native 전제가 충족되지 않았다
- **THEN** 검증된 경계와 열린 blocker를 각각 기록하고 전체 운영 복구 또는 change archive로 표시하지 않는다
