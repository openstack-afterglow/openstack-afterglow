# Proposal: 대화 삭제 시 사용자 확인(Confirmation Dialog) 추가

## Background
현재 대화 기록(사이드바)에서 대화 행의 휴지통 아이콘(삭제 버튼)을 클릭하면, `ChatPanel.svelte`의 `deleteConversation()`이 별도의 확인 절차 없이 즉시 `DELETE /api/v1/chat/conversations/{id}`를 호출하여 대화를 삭제합니다. 이로 인해 사용자가 실수로 삭제 버튼을 누를 경우 되돌릴 수 없는 대화 손실이 발생할 수 있습니다.

## Objectives
1. 대화 삭제 버튼 클릭 시 `confirmDialog`를 통해 사용자에게 삭제 여부를 확인받는 절차를 추가합니다.
   - 대화 제목이 있는 경우: `'<제목>' 대화를 삭제하시겠습니까?`
   - 대화 제목이 없는 경우: `대화를 삭제하시겠습니까?`
2. 사용자가 취소(Escape 또는 '취소' 버튼)할 경우 삭제 API 호출을 중단하고 대화를 보존합니다.
3. 사용자가 확인을 누른 경우에만 삭제 API를 호출하고 성공 시 `toast.success('대화를 삭제했습니다')` 피드백을 제공합니다.
4. 백그라운드에서 실행/응답 생성 중인 대화(`runningConversationIds.has(conv.id)`)는 사이드바에서 삭제 버튼을 비활성화(`disabled`)하고, `deleteConversation` 함수에서도 실행 중 삭제를 차단합니다.

## Scope
- `frontend/src/lib/components/chat/ChatPanel.svelte`: `deleteConversation`에 `confirmDialog`, `runningConversationIds` 가드 및 삭제 완료 토스트 추가
- `frontend/src/lib/components/chat/ChatSidebar.svelte`: `runningConversationIds`에 포함된 대화의 삭제 버튼 비활성화
- `frontend/src/lib/components/chat/__tests__/ChatPanel.test.ts` 또는 신규 테스트: 삭제 확인 대화상자 수락/취소 테스트
