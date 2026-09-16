## Implementation Tasks

- [x] 모델 선택 overlay에 API ID 표시, 선택과 분리된 복사 버튼, 성공/실패 피드백을 구현한다.
- [x] Chromium에서 실제 컴포넌트의 정확한 복사 값, 선택 불변, 오류, 검색·키보드·닫기 및 mobile/tablet/desktop 양 테마를 검증하고 관련 기존 검사를 실행한다.
- [x] 기존 API 문서와 변경 기록에 사용법 및 검증 결과를 반영하고 임시 검증 자산을 제거한다.

## Verification

- 실제 Vite가 컴파일한 `ModelPickerOverlay.svelte`, 공용 `Button`/`Toast`, `layout.css`를 전용 Chromium 페이지에서 mount했다. 소스 대체나 복사 함수 mock 없이 native clipboard에 `openai/gpt-5.6-sol` 및 `gpt-6-astra`가 기록되는 것을 읽어 확인했다. fixture의 내부 숫자 ID와 표시 이름은 API ID와 다르게 설정했다.
- 선택되지 않은 모델의 ID 복사 후 기존 선택 유지, 선택 callback 0회, 닫기 callback 0회를 확인했다. 권한 거부 및 Clipboard API 부재를 각각 주입해 성공 알림 없이 오류 알림만 발생하고 선택/닫기가 변하지 않는 것을 확인했다.
- 표시 이름/API ID/provider 검색 및 빈 결과, Tab 순서, Space 복사, Enter 선택 및 정확한 `model_name` callback, Escape/닫기 버튼/backdrop 닫기를 확인했다. 키보드 focus-visible의 3px ring을 확인했다.
- 320/390/820/1440px에서 light/dark 모두 수평 overflow 및 선택 버튼과 복사 버튼 겹침이 없고, 복사 버튼 높이 44px임을 확인했다. 390/820/1440px 양 테마 screenshot을 시각 확인했다.
- `npm run test:target -- frontend:src/lib/components/chat/__tests__/ChatPanel.test.ts frontend:src/lib/design/__tests__/visualDebt.test.ts`: visual-debt 4 tests 통과. ChatPanel suite는 이 작업에서 수정하지 않은 기존 dirty `ChatPanel.svelte:2085`의 `Unexpected token` 컴파일 오류로 실행 불가.
- `npm run test:target -- design`: 17 files / 85 tests 통과.
- 검증 공백: 기존 ChatPanel 구문 오류로 전체 채팅 페이지 및 실제 메시지 전송 통합 시나리오는 검증하지 못했다. 해당 별도 작업 파일을 변경하거나 테스트를 무력화하지 않았다. 전체 gate, live API 호출, 커밋·푸시·배포는 실행하지 않았다.
- 전용 smoke 페이지와 임시 screenshot 6개를 제거했다. 저장소에 테스트 전용 route/script를 생성하지 않았고 기존 dev server 및 Chromium 세션은 유지했다.
