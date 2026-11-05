## ADDED Requirements

### Requirement: Typed semantic experience observations
시스템은 SHALL 소스 고정 action/component ID와 버전된 strict 사건 계약으로 화면 진입·상태·조작·검증 거부·메시지·결과 적용/폐기·노출 관측을 기록하고 자유 입력/DOM 원문을 기록하지 않는다.

#### Scenario: 조작 식별의 안정성
- **WHEN** 번역이나 DOM 순서가 바뀐 화면에서 같은 의미의 작업을 실행한다
- **THEN** 동일한 source action ID와 해당 build revision을 기록하고 순번/표시 문구를 사건 정체성으로 사용하지 않는다

#### Scenario: 클라이언트 필드 위조
- **WHEN** browser payload에 임의 actor/project/server-success 또는 정의되지 않은 필드를 보낸다
- **THEN** strict validator가 거부하고 입력 원문이나 credential을 오류에 반사하지 않는다

### Requirement: Explicit asynchronous causality and owner segmentation
시스템은 SHALL action/request/operation/worker의 명시적 인과관계, 탭별 구간, 순서와 attempt를 보존하며 token 값이나 last-click timer를 연결 권위로 사용하지 않는다.

#### Scenario: await 이후의 분기 요청
- **WHEN** 한 action이 비동기 검증 뒤 여러 API와 장기 operation을 시작하고 후속 readback을 수행한다
- **THEN** 각 request/attempt는 별개로 식별되며 모두 원 action/operation과 연결되고 unrelated 동시 action은 섞이지 않는다

#### Scenario: 사용자 또는 프로젝트 전환과 ABA
- **WHEN** actor/home/project가 A→B→A로 바뀌거나 로그아웃한다
- **THEN** 이전 pending 사건과 응답을 새 구간으로 재귀속하지 않으며 정상 same-owner bearer rotation만 기존 구간을 유지한다

#### Scenario: 익명 로그인 전환
- **WHEN** 익명 구간 이후 검증된 로그인이 성공한다
- **THEN** 새 구간과 명시 전환 관계를 만들고 익명 사건의 actor를 확인된 사용자로 소급 변경하지 않는다

### Requirement: Separate authoritative results and presentation evidence
시스템은 SHALL 접수/running/성공/실패/취소 요청/실제 취소/결과 불명을 별도 기록하고, browser 수신/적용/DOM 반영/노출/폐기를 서버 업무 결과와 분리한다.

#### Scenario: HTTP 성공 이후 작업 실패
- **WHEN** API가202로 접수하거나 SSE200을 연 뒤 실제 operation이 실패 또는 unknown으로 끝난다
- **THEN** viewer는 접수와 terminal을 구분하며 HTTP 성공으로 업무 완료를 합성하지 않는다

#### Scenario: 서버 성공 이후 화면 반영 없음
- **WHEN** 서버 readback은 성공했지만 탭이 닫히거나 scope가 바뀐다
- **THEN** 서버 성공은 유지하고 browser 결과는 미확인 또는 고정 사유의 폐기로 표시하며 사람이 결과를 봤다고 주장하지 않는다

#### Scenario: 취소와 외부 호출 종료
- **WHEN** 사용자가 취소했으나 native 호출이 아직 종료되지 않았다
- **THEN** cancel_requested와 실제 drain/정리 완료를 구분하고 성공/취소 확정을 앞당기지 않는다

#### Scenario: Initial direct-detail route and owner replacement
- **WHEN** 컨테이너 또는 파일 스토리지 상세로 직접 진입하거나 같은 mounted route에서 자원·논리 owner·권위·API base가 바뀐다
- **THEN** 실제 최초/후속 읽기에 명시 context를 전달하고 source state 적용과 guarded DOM commit을 구분하며 이전 owner의 늦은 결과·오류·cleanup을 새 화면에 적용하지 않는다

#### Scenario: Verified same-owner renewal
- **WHEN** 같은 논리 owner의 검증된 bearer 갱신이 열린 상세에 반영된다
- **THEN** 정상 state·독립 in-flight 읽기를 보존하고 이후 읽기는 새 credential을 사용하며 계측 때문에 업무 GET이나 mutation을 반복하지 않는다


### Requirement: Historical locale and message fidelity
시스템은 SHALL message key, 실제 표시 locale, catalog/build revision과 허용된 비민감 parameter로 당시 문구를 재구성하며 복원 불가 영역을 명시한다.

#### Scenario: 언어 변경과 기존 안내
- **WHEN** 언어를 변경했지만 기존 state의 오류 문구는 이전 언어로 남아 있다
- **THEN** 현재 선택 언어로 과거 메시지를 덮어 추정하지 않고 실제 메시지 locale을 보존한다

#### Scenario: 일회용 인증 flow 계측
- **WHEN** 열린 복구 결과/provider 확인/MCP 선택에서 언어 또는 테마를 변경한다
- **THEN** 계측 때문에 route를 remount하거나 proof 검사/동의/native 요청을 반복하지 않는다

#### Scenario: 과거 catalog 부재
- **WHEN** 해당 revision의 문구 또는 민감 parameter를 복원할 수 없다
- **THEN** 현재 문구를 당시 원문이라고 표시하지 않고 복원 불가/마스킹을 명시한다
