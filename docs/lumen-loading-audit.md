# Lumen chat/image/audio 대기 포맷 조사

2026-11-01 공유 working tree 읽기 전용 조사. 구현 파일은 변경하지 않았다. frontend/src/lib/components/chat의 LoadingState 정적 사용은24파일96줄이다. import를 포함한 검색 수이며 runtime 인스턴스 수가 아니다. 실제 authenticated/provider/media 실행이 아닌 source와 mocked UI tests 증거다.

## 포맷 지도

|분야|상태|현재 표현·소스|
|---|---|---|
|chat|최초 대화/이력 조회|ChatWindow.svelte244 surface;240 재조회 inline;265 기록 inline|
|chat|첫 토큰/응답 streaming|ChatMessage.svelte196 inline;MarkdownMessage.svelte86 장식 inline. 다른 실제 진행 표시가 있으면 중복 첫 토큰 표시 억제|
|chat|추론/도구/문맥 압축|ThinkingBlock25;ExecutionTimeline98/125/127;ToolCallCard71/116;ChatWindow300/305/311|
|chat|제목 요약/첨부/입력부|ChatSidebar315/389/392;ChatInput605/733/795. 중지 동작 유지|
|chat|도구 승인|ChatToolApproval70 control; 권한 차단과 pending 혼합 문제 아래 참고|
|chat|사용자 응답 전송|InteractionCard31–36 pending 시 비활성화만, 공통 로딩/aria-busy 없음|
|image|권한/모델/옵션/업로드/제출|ImageStudio444/492/469/486, notice 또는 inline/control|
|image|작업 조회/큐/실행/리소스 대기/최종화|ImageStudio525–535 실제 상태 이름+section, 경과 시간/크기/취소|
|image|실패/취소|ImageStudio537–538 danger/neutral Alert|
|image|결과 다운로드|ImageStudio545–547 URL 없으면 section;실패 상태 별도 분기 없음|
|image|입력/결과/스타일/첨부 이미지|ImageStudio466/511/546,ChatInput596 native img; native load/error 테마 없음|
|audio|TTS/STT 모델/옵션|AudioStudio545/605 inline;실패/미지원/준비 별도 상태|
|audio|음성 생성/권한/녹음/업로드/전사|AudioStudio558–569/585/589/595/614–619. 요청은 inline/control, 녹음은 실제 상태 텍스트|
|audio|생성/입력 음원 재생|AudioStudio560/597 native audio controls; 버퍼링/디코딩/error authored 상태 없음|
|realtime|모델/연결/연결 완료|RealtimeVoice289/290/291; 연결 수명 문제 아래 참고|
|realtime|전사/응답/재생|RealtimeVoice293 일반 대기 문구,178–190 PCM queue. 별도 응답대기/발화/버퍼링 렌더 없음|
|기타|모델 목록/권한|ModelPickerOverlay112–121 refreshing 텍스트;LumenPermissionNotice10–19 공통 로더·오류·거부 분리|

## 수정 필요 사항

1. **이미지 실패가 계속 로딩으로 보임.** `ImageStudio.svelte:248–261`은 미리보기 다운로드 실패를 전역 오류로만 기록한다. `545–547`은 URL 부재만 검사하므로 실패한 셀에도 “이미지 불러오는 중”이 남는다. 상단 오류와 재확인 버튼은 존재한다. 셀별 다운로드·디코딩·준비·실패 상태를 분리해야 한다.
2. **실시간 음성 연결 표시가 일찍 끝남.** `RealtimeVoice.svelte:257`에서 소켓을 만든 직후 `finally:268`이 connecting을 해제한다. 실제 connected 설정은 session.ready 이후 AudioWorklet 준비가 끝난 `209`에서 이뤄진다. 그 사이 로딩이 사라지고 시작 버튼이 다시 활성화될 수 있다. 실제 네트워크·기기에서 재현한 결과는 아니다.
3. **도구 권한 차단을 처리 중으로 표시.** `ChatPanel.svelte:2714`는 승인 요청뿐 아니라 권한 불가도 busy에 포함한다. `ChatToolApproval.svelte:70`은 이를 모두 처리 중 로더로 표시한다. 작업 중과 비활성 상태를 분리해야 한다.
4. **브라우저 미디어 준비 상태는 테마 밖에 있음.** 이미지 load/error와 오디오 loadstart/waiting/stalled/canplay/error에 대응하는 공통 상태 표시가 없다. 실제 콘텐츠는 보존하고 주변 대기·오류 포맷만 통일할 후보다.
5. **작은 표현 공백이 남아 있음.** InteractionCard는 전송 중 비활성화만 한다. 이미지 취소·파일 다운로드에는 별도 대기 표시가 없고, 실시간 음성 입력·출력 전사 대기는 일반 문구다. 각각의 의미를 유지하면서 inline/control 표현을 추가할 수 있다.

## 실제 검증

ChatWindow, ImageStudio, AudioStudio, RealtimeVoice, ChatInput의 UI 테스트를 실행했다. **119개 중 114개 통과, 5개 실패**다. 실패는 AudioStudio 3개, ImageStudio 1개, ChatInput 1개이며 모두 상태 영역의 전체 textContent를 기존 문구와 정확하게 비교한다. 새 LoadingState의 aria-hidden 문자 `[~]`도 DOM textContent에 포함되어 기대값과 다르다. 이는 접근성 트리에서 장식이 낭독된다는 증거는 아니다. 상태 문구와 장식을 분리해 검사할 필요가 있다. 일부 기존 jsdom Canvas 미구현 경고도 발생했다.

이번 증거는 소스와 모의 UI 테스트에 한정된다. 실제 로그인, SSE, 유료 provider 요청, 마이크, 미디어 디코딩·버퍼링은 검증하지 않았다. 이 보고서 외 구현 코드·테스트·배포는 변경하지 않았다.

## 공통 LoadingState 사용처 전체 정적 목록

```text
frontend/src/lib/components/chat/AudioStudio.svelte:12:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/AudioStudio.svelte:545:						{#if loading.tts || capabilityLoading.tts}<LoadingState variant="inline" label={t('audioStudio.speechChecking')} />{:else if errors.tts}<Alert tone="danger">{errors.tts} <Button variant="subtle" disabled={!audioAllowed} onclick={() => scope && loadModels('tts', scope, generation)}>{t('audioStudio.reloadModels')}</Button></Alert>{:else if !models.tts.length}<Alert tone="warning">{t('audioStudio.noSpeechModels')}</Alert>{:else if ttsReadiness}<Alert tone="warning">{ttsReadiness}</Alert>{:else if audioAllowed}<p role="status" class="ready">{t('audioStudio.speechReady')}</p>{/if}
frontend/src/lib/components/chat/AudioStudio.svelte:558:							{#if busyTts}<LoadingState variant="inline" label={t('audioStudio.speechGenerating')} />{/if}
frontend/src/lib/components/chat/AudioStudio.svelte:569:							<Button type="submit" size="lg" disabled={!ttsReady}>{#if busyTts}<LoadingState variant="control" label={t('audioStudio.speechGenerating')} />{:else}{t('audioStudio.generateSpeech')}{/if}</Button>
frontend/src/lib/components/chat/AudioStudio.svelte:585:								<Button variant="secondary" disabled={!recording && (!uploadAllowed || busyStt || permissionPending)} onclick={() => recording ? stopMic() : void startRecording()}>{#if permissionPending}<LoadingState variant="control" label={t('audioStudio.microphonePermissionChecking')} />{:else}{recording ? t('audioStudio.stopRecording') : t('audioStudio.recordMicrophone')}{/if}</Button>
frontend/src/lib/components/chat/AudioStudio.svelte:595:									{#if uploading}<LoadingState variant="inline" label={t('audioStudio.uploading')} />{:else if assetId}<p role="status" class="muted">{t('audioStudio.scannedInput', { name: assetName })}</p>{/if}
frontend/src/lib/components/chat/AudioStudio.svelte:605:						{#if loading.stt || capabilityLoading.stt}<LoadingState variant="inline" label={t('audioStudio.transcriptionChecking')} />{:else if errors.stt}<Alert tone="danger">{errors.stt} <Button variant="subtle" disabled={!audioAllowed} onclick={() => scope && loadModels('stt', scope, generation)}>{t('audioStudio.reloadModels')}</Button></Alert>{:else if !models.stt.length}<Alert tone="warning">{t('audioStudio.noTranscriptionModels')}</Alert>{:else if sttReadiness}<Alert tone="warning">{sttReadiness}</Alert>{:else if audioAllowed}<p role="status" class="ready">{t('audioStudio.transcriptionReady')}</p>{/if}
frontend/src/lib/components/chat/AudioStudio.svelte:614:						<Button size="lg" disabled={!sttReady} onclick={() => void transcribe()}>{#if transcribing}<LoadingState variant="control" label={t('audioStudio.processingAudio')} />{:else}{t('audioStudio.convertToText')}{/if}</Button>
frontend/src/lib/components/chat/AudioStudio.svelte:615:						{#if transcribing}<LoadingState variant="inline" label={t('audioStudio.processingAudio')} />{/if}
frontend/src/lib/components/chat/ChatToolApproval.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatToolApproval.svelte:70:				<Button variant="primary" size="sm" disabled={busy} onclick={() => onDecision(approval.callId, 'approve')}>{#if busy}<LoadingState variant="control" label={t('approval.processing')} />{:else}{t('approval.approve')}{/if}</Button>
frontend/src/lib/components/chat/ToolCategoryGroup.svelte:4:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ToolCategoryGroup.svelte:30:			<LoadingState variant="inline" label={t('toolCategoryGroup.running')} />
frontend/src/lib/components/chat/ChatSidebar.svelte:8:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatSidebar.svelte:315:						<span class="truncate">{#if !conversation.title && conversation.title_status === 'pending'}<LoadingState variant="control" label={conversationLabel(conversation)} />{:else}{conversationLabel(conversation)}{/if}</span>
frontend/src/lib/components/chat/ChatSidebar.svelte:389:			<span class="item-title">{#if !conv.title && conv.title_status === 'pending'}<LoadingState variant="control" label={conversationLabel(conv)} />{:else}{conversationLabel(conv)}{/if}</span>
frontend/src/lib/components/chat/ChatSidebar.svelte:392:					<LoadingState variant="control" label="">{#snippet children()}<span class="sr-only">{t('sidebar.generatingResponse')}</span>{/snippet}</LoadingState>
frontend/src/lib/components/chat/CreateProjectDialog.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/CreateProjectDialog.svelte:68:					{#if saving}<LoadingState variant="control" label={t('createProject.creating')} />{:else}{t('createProject.title')}{/if}
frontend/src/lib/components/chat/ChatWindow.svelte:6:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatWindow.svelte:240:		<div class="load-bar"><LoadingState variant="inline" label={t('window.loading')} /></div>
frontend/src/lib/components/chat/ChatWindow.svelte:244:			<LoadingState variant="surface" label={t('window.loading')} />
frontend/src/lib/components/chat/ChatWindow.svelte:265:					<div class="history-loading"><LoadingState variant="inline" label={t('window.historyLoading')} /></div>
frontend/src/lib/components/chat/ChatWindow.svelte:300:						<LoadingState variant="inline" label="" aria-hidden="true" />
frontend/src/lib/components/chat/ChatWindow.svelte:305:						<LoadingState variant="inline" label="" aria-hidden="true" />
frontend/src/lib/components/chat/ChatWindow.svelte:311:						<LoadingState variant="inline" label="" aria-hidden="true" />
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:420:			<Button onclick={addMcp} disabled={addingMcp || !canMcp}>{#if addingMcp}<LoadingState variant="control" label={t('extensions.actions.adding')} />{:else}{t('extensions.mcp.add')}{/if}</Button>
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:423:	{#if loading && catalogLoaded}<LoadingState variant="inline" label={t('extensions.mcp.loading')} />{/if}
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:425:		<LoadingState label={t('extensions.mcp.loading')} />
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:452:											<LoadingState variant="control" label={t('extensions.oauth.preparing')} />
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:511:			<Button onclick={addTool} disabled={addingTool || !canAssets}>{#if addingTool}<LoadingState variant="control" label={t('extensions.actions.adding')} />{:else}{t('extensions.tools.add')}{/if}</Button>
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:514:	{#if loading && catalogLoaded}<LoadingState variant="inline" label={t('extensions.tools.loading')} />{/if}
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:516:		<LoadingState label={t('extensions.tools.loading')} />
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:581:			<Button onclick={addSkill} disabled={addingSkill || !canAssets}>{#if addingSkill}<LoadingState variant="control" label={t('extensions.actions.adding')} />{:else}{t('extensions.skills.add')}{/if}</Button>
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:584:	{#if loading && catalogLoaded}<LoadingState variant="inline" label={t('extensions.skills.loading')} />{/if}
frontend/src/lib/components/chat/ChatExtensionsManager.svelte:586:		<LoadingState label={t('extensions.skills.loading')} />
frontend/src/lib/components/chat/RealtimeVoice.svelte:7:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/RealtimeVoice.svelte:289:			{#if error}<Alert tone="danger">{error}</Alert>{:else if loading || capabilityLoading}<LoadingState variant="inline" label={t('realtimeVoice.checking')} />{:else if readiness}<Alert tone="warning">{readiness}</Alert>{:else if audioAllowed}<Alert tone="success">{t('realtimeVoice.ready')}</Alert>{/if}
frontend/src/lib/components/chat/RealtimeVoice.svelte:290:			<div class="actions"><Button disabled={!audioAllowed || Boolean(readiness) || loading || capabilityLoading || connecting || connected} onclick={() => void start()}>{#if connecting}<LoadingState variant="control" label={t('realtimeVoice.connecting')} />{:else}{t('realtimeVoice.startSession')}{/if}</Button><Button variant="secondary" disabled={!connected || (!audioAllowed && muted)} onclick={toggleMute}>{muted ? t('realtimeVoice.microphoneOn') : t('realtimeVoice.microphoneOff')}</Button><Button variant="secondary" disabled={!connected} onclick={interrupt}>{activeProvider === 'gemini' ? t('realtimeVoice.interruptAndEnd') : t('realtimeVoice.interrupt')}</Button><Button variant="danger-outline" disabled={!connected && !connecting} onclick={() => stop()}>{t('realtimeVoice.endSession')}</Button></div>
frontend/src/lib/components/chat/ChatMcpCatalogue.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatMcpCatalogue.svelte:201:				{:else if cloudLoading}<LoadingState variant="inline" label={t('extensions.catalogue.loading')} />
frontend/src/lib/components/chat/ChatMcpCatalogue.svelte:215:		<LoadingState label={t('extensions.mcp.loading')} />
frontend/src/lib/components/chat/ChatMcpCatalogue.svelte:259:		<Button variant="primary" onclick={approve} disabled={busy || !consentValid}>{#if busy}<LoadingState variant="control" label={t('extensions.catalogue.approving')} />{:else}{t('extensions.catalogue.approve')}{/if}</Button>
frontend/src/lib/components/chat/ChatSettings.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatSettings.svelte:279:						{#if memLoading && memorySnapshotScope === memoryScope}<LoadingState variant="inline" label={t('settings.memory.loading')} />{/if}
frontend/src/lib/components/chat/ChatSettings.svelte:281:							<LoadingState label={t('settings.memory.documentLoading', { filename: 'memory.md' })} />
frontend/src/lib/components/chat/ChatSettings.svelte:317:									{#if saving}<LoadingState variant="control" label={t('settings.memory.saving')} />{:else}{editingId !== null ? t('settings.memory.saveChanges') : t('settings.memory.add')}{/if}
frontend/src/lib/components/chat/ChatSettings.svelte:325:							<LoadingState label={t('settings.memory.loading')} />
frontend/src/lib/components/chat/LumenPermissionNotice.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/LumenPermissionNotice.svelte:11:	<LoadingState variant="inline" label={t('permissions.loading')} />
frontend/src/lib/components/chat/AgentBuilderForm.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/AgentBuilderForm.svelte:156:			{#if saving}<LoadingState variant="control" label={t('agentBuilder.actions.saving')} />{:else}{editing ? t('agentBuilder.actions.saveChanges') : t('agentBuilder.actions.create')}{/if}
frontend/src/lib/components/chat/ChatMessage.svelte:10:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatMessage.svelte:196:				<LoadingState variant="inline" label={t('message.preparingResponse')} />
frontend/src/lib/components/chat/ChatProjectsView.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatProjectsView.svelte:219:							{#if saving}<LoadingState variant="control" label={t('projects.saving')} />{:else}{t('projects.saveChanges')}{/if}
frontend/src/lib/components/chat/AgentManagerModal.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/AgentManagerModal.svelte:163:				<LoadingState label={t('agentManager.loading')} />
frontend/src/lib/components/chat/AgentManagerModal.svelte:165:				{#if loading}<LoadingState variant="inline" label={t('agentManager.loading')} />{/if}
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:565:	{#if loading && keyListLoaded}<LoadingState variant="inline" label={t('apiKeys.loading')} />{/if}
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:567:		<LoadingState label={t('apiKeys.loading')} />
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:609:									<Button variant="accent" size="sm" type="submit" disabled={savingEdit || !$serviceCapabilities('lumen-keys_editor')}>{#if savingEdit}<LoadingState variant="control" label={t('apiKeys.save')} />{:else}{t('apiKeys.save')}{/if}</Button>
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:650:								<Button variant="accent" size="sm" type="submit" disabled={savingEdit || !$serviceCapabilities('lumen-keys_editor')}>{#if savingEdit}<LoadingState variant="control" label={t('apiKeys.save')} />{:else}{t('apiKeys.save')}{/if}</Button>
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:664:			<LoadingState label={t('apiKeys.guide.loading')} />
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:869:		{#if targetLoading}<LoadingState variant="inline" label={t('apiKeys.target.loading')} />
frontend/src/lib/components/chat/ChatApiKeysManager.svelte:876:		<Button onclick={create} disabled={creating || !canIssue} ariaBusy={creating}>{#if creating}<LoadingState variant="control" label={t('apiKeys.creating')} />{:else}{t('apiKeys.create')}{/if}</Button>
frontend/src/lib/components/chat/AgentHubModal.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/AgentHubModal.svelte:98:			{#if loading && loadedAgentScope === agentScope}<LoadingState variant="inline" label={t('agentHub.loading')} />{/if}
frontend/src/lib/components/chat/AgentHubModal.svelte:100:				<LoadingState label={t('agentHub.loading')} />
frontend/src/lib/components/chat/AgentHubModal.svelte:133:										{#if cloningId === a.id}<LoadingState variant="control" label={t('agentHub.cloning')} />{:else}{t('agentHub.clone')}{/if}
frontend/src/lib/components/chat/ToolCallCard.svelte:4:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ToolCallCard.svelte:71:			<LoadingState variant="control" label="" aria-hidden="true" />
frontend/src/lib/components/chat/ToolCallCard.svelte:116:									<LoadingState variant="inline" label={t('toolCall.downloading')} />
frontend/src/lib/components/chat/ThinkingBlock.svelte:3:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ThinkingBlock.svelte:25:			<LoadingState variant="inline" label={t('thinkingBlock.active')} />
frontend/src/lib/components/chat/ChatInput.svelte:21:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatInput.svelte:605:							<LoadingState variant="inline" label={t('input.uploading')} />
frontend/src/lib/components/chat/ChatInput.svelte:733:							<LoadingState variant="inline" label={contextStatus} />
frontend/src/lib/components/chat/ChatInput.svelte:795:					<LoadingState variant="inline" label={t('sidebar.generatingResponse')} />
frontend/src/lib/components/chat/ExecutionTimeline.svelte:4:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ExecutionTimeline.svelte:98:				<LoadingState variant="inline" label={t('executionTimeline.inProgress')} />
frontend/src/lib/components/chat/ExecutionTimeline.svelte:125:							<p class="stage-label">{#if isLive(entry.item)}<LoadingState variant="inline" label="" aria-hidden="true" /> {/if}{contextLabel(entry.item)}</p>
frontend/src/lib/components/chat/ExecutionTimeline.svelte:127:							<p class="stage-label">{#if isLive(entry.item)}<LoadingState variant="inline" label="" aria-hidden="true" /> {/if}{stageLabel(entry.item)}</p>
frontend/src/lib/components/chat/ImageStudio.svelte:8:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ImageStudio.svelte:469:						{#if uploading}<LoadingState variant="inline" label={t('imageStudio.uploading')} />{:else if inputAssetId}<p role="status" class="muted">{t('imageStudio.uploadComplete', { name: inputFileName })}</p>{/if}
frontend/src/lib/components/chat/ImageStudio.svelte:486:					<Button type="submit" variant="primary" size="lg" class="composer-submit" disabled={!canSubmit}>{#if submitting}<LoadingState variant="control" label={t('imageStudio.submitting')} />{:else}{t('imageStudio.createImage')}{/if}</Button>
frontend/src/lib/components/chat/ImageStudio.svelte:492:					{#if modelsLoading || capabilitiesLoading || (!modelsLoaded && !modelsError)}<LoadingState variant="inline" label={t('imageStudio.checkingOptions')} />
frontend/src/lib/components/chat/ImageStudio.svelte:525:					{#if loadingRun && !currentRun}<LoadingState label={t('imageStudio.checkingJob')} />{/if}
frontend/src/lib/components/chat/ImageStudio.svelte:530:								<LoadingState variant="section" label={displayStatus(currentRun.status)} />
frontend/src/lib/components/chat/ImageStudio.svelte:547:											{:else}<LoadingState variant="section" label={t('imageStudio.loadingImage')} />{/if}
frontend/src/lib/components/chat/ChatUsagePanel.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/ChatUsagePanel.svelte:152:			<LoadingState label={t('usage.trendLoading')} />
frontend/src/lib/components/chat/MarkdownMessage.svelte:2:	import LoadingState from '$lib/components/ui/LoadingState.svelte';
frontend/src/lib/components/chat/MarkdownMessage.svelte:86:{#if streaming && content.length > 0}<LoadingState variant="inline" label="" aria-hidden="true" />{/if}
```
