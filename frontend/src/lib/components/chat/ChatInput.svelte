<script lang="ts">
	import { tick, type Snippet } from 'svelte';
	import type { ContextState, ModelCapabilities } from '$lib/api/chatContracts';
	import { effortLabel, effortOptionsFor } from '$lib/api/chatEffort';
	import {
		completeChatAttachment,
		isChatDocumentMime,
		isChatImageMime,
		uploadChatAttachment,
		type ChatAttachment
	} from '$lib/api/chatAttachments';
	import { toast } from '$lib/stores/toast';
	import ModelCapabilityBadges from './ModelCapabilityBadges.svelte';
	import UsageRing from '$lib/components/ui/UsageRing.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ChatContextPanel from './ChatContextPanel.svelte';

	export type ComposerCommand = {
		id: string;
		name: string;
		description: string;
		disabled?: boolean;
		disabledReason?: string;
		onSelect: () => void;
	};

	interface Props {
		value: string;
		streaming?: boolean;
		disabled?: boolean;
		/** Block sending without disabling draft editing or attachment controls. */
		sendDisabled?: boolean;
		placeholder?: string;
		contextState?: ContextState | null;
		hasContextScope?: boolean;
		contextLoading?: boolean;
		contextPhase?: 'ready' | 'compacting' | 'compacted' | 'failed';
		contextCause?: 'automatic' | 'manual' | null;
		contextBeforeTokens?: number | null;
		contextAfterTokens?: number | null;
		contextError?: string | null;
		/** 현재 모델 능력 — effort 선택기·배지·첨부 게이팅. */
		modelCaps?: ModelCapabilities | null;
		searchEnabled?: boolean;
	/** 선택된 thinking effort(auto=provider 기본, none=명시적 비활성). */
	effort?: string | null;
		/** 첨부(bindable) — 업로드 진행/완료 아이템. 부모가 전송 시 refs 로 변환·초기화. */
		attachments?: ChatAttachment[];
		/** 대화별 tool/MCP 선택 — null=활성 전체(기본), 배열=해당 id 만. tool_call 지원 모델만 노출. */
		availableTools?: { id: number; name: string }[];
		availableMcp?: { id: number; name: string }[];
		selectedToolIds?: number[] | null;
		selectedMcpIds?: number[] | null;
		/** 스킬 선택 — opt-in(기본 미선택 [], 선택된 것만 주입). 모든 모델에서 사용 가능(프롬프트 주입). */
		availableSkills?: { id: number; name: string }[];
		selectedSkillIds?: number[];
		/** @ mention으로 바인딩할 수 있는 현재 프로젝트 에이전트. */
		availableAgents?: { id: number; name: string }[];
		onSelectAgent?: (agentId: number) => void;
		composerCommands?: ComposerCommand[];
		token?: string;
		projectId?: string;
		onSend: () => void;
		onStop: () => void;
		children?: Snippet;
	}
	let {
		value = $bindable(''),
		streaming = false,
		disabled = false,
		sendDisabled = false,
		contextState = null,
		hasContextScope = false,
		contextLoading = false,
		contextPhase = 'ready',
		contextCause = null,
		contextBeforeTokens = null,
		contextAfterTokens = null,
		contextError = null,
		placeholder = '메시지를 입력하세요  (Enter 전송 · Shift+Enter 줄바꿈)',
		modelCaps = null,
		searchEnabled = $bindable(false),
		effort = $bindable(null),
		attachments = $bindable([]),
		availableTools = [],
		availableMcp = [],
		selectedToolIds = $bindable(null),
		selectedMcpIds = $bindable(null),
		availableSkills = [],
		selectedSkillIds = $bindable([]),
		availableAgents = [],
		composerCommands = [],
		onSelectAgent,
		token,
		projectId,
		onSend,
		onStop,
		children
	}: Props = $props();

	let ta = $state<HTMLTextAreaElement | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);
	let effortOpen = $state(false);
	let plusOpen = $state(false);
	let contextInfoOpen = $state(false);
	let dragOver = $state(false);
	const searchGate = $derived(modelCaps?.feature_gates?.web_search);
	const hasNativeSearch = $derived(Boolean(modelCaps?.web_search) && searchGate?.mode === 'native');
	const searchRequired = $derived(Boolean(modelCaps?.web_search_required));
	const searchAvailable = $derived(searchGate?.available === true && searchGate?.pricing_available === true);
	const searchTitle = $derived(!searchAvailable
		? '웹 검색 요금 또는 제공 경로가 준비되지 않았습니다. 관리자에게 문의하세요.'
		: searchRequired ? '이 모델은 웹 검색을 기본으로 사용합니다' : '웹 검색을 사용해 답변하고 출처를 표시합니다');

	// The backend disables these gates when the scanned S3/ClamAV pipeline is unavailable.
	const canAttachImage = $derived(
		Boolean(modelCaps?.vision) && (modelCaps?.feature_gates?.image_input?.available ?? true)
	);
	const canAttachDocument = $derived(
		Boolean(modelCaps?.feature_gates?.document_input?.available)
	);
	const canAttach = $derived(canAttachImage || canAttachDocument);
	// tool_call 지원 + 사용 가능한 tool/MCP 가 있을 때만 도구 선택 노출.
	const canUseTools = $derived(
		Boolean(modelCaps?.tool_call) && availableTools.length + availableMcp.length > 0
	);
	// 스킬은 프롬프트 주입이라 tool_call 없이도 사용 가능.
	const canUseSkills = $derived(availableSkills.length > 0);
	const hasPlus = $derived(canAttach || canUseTools || canUseSkills);

	type ComposerQuickAction = {
		kind: 'quick-action';
		id: string;
		name: string;
		description: string;
		disabled?: boolean;
		disabledReason?: string;
		onSelect: () => void;
	};
	type ComposerShortcut =
		| { kind: 'agent' | 'skill'; id: number; name: string }
		| ({ kind: 'command' } & ComposerCommand)
		| ComposerQuickAction;

	let shortcutMenu = $state<HTMLDivElement | null>(null);
	let activeShortcutIndex = $state(0);
	let dismissedShortcutValue = $state<string | null>(null);

	const attachmentUnavailableReason = $derived.by(() => {
		if (!modelCaps) return '모델 기능을 확인하는 중입니다';
		const imageGate = modelCaps.feature_gates?.image_input;
		const documentGate = modelCaps.feature_gates?.document_input;
		if (
			imageGate?.reason_code === 'asset_pipeline_unavailable' ||
			documentGate?.reason_code === 'asset_pipeline_unavailable'
		) {
			return '첨부 저장소와 보안 검사기가 설정되지 않았습니다. 관리자에게 문의하세요.';
		}
		return '선택한 모델은 이미지 또는 PDF 입력을 지원하지 않습니다';
	});
	const plusTitle = $derived(hasPlus ? '첨부·도구' : attachmentUnavailableReason);
	const quickActions = $derived.by((): ComposerQuickAction[] => [
		{
			kind: 'quick-action',
			id: 'attach-file',
			name: '파일 첨부',
			description: canAttach ? '개인 프로젝트 기본 버킷에 이미지 또는 PDF를 자동 저장합니다' : attachmentUnavailableReason,
			disabled: !canAttach,
			disabledReason: canAttach ? undefined : attachmentUnavailableReason,
			onSelect: () => fileInput?.click()
		},
		{
			kind: 'quick-action',
			id: 'features',
			name: '도구 및 스킬',
			description: '사용할 도구와 스킬을 선택합니다',
			disabled: !canUseTools && !canUseSkills,
			disabledReason: !canUseTools && !canUseSkills ? '현재 사용할 수 있는 도구나 스킬이 없습니다' : undefined,
			onSelect: () => (plusOpen = true)
		}
	]);
	const shortcutTrigger = $derived(value.match(/(?:^|\s)([@/])([^\n]*)$/));
	const composerShortcuts = $derived.by((): ComposerShortcut[] => {
		if (!shortcutTrigger || dismissedShortcutValue === value) return [];
		const [, prefix, query] = shortcutTrigger;
		const normalized = query.trim().toLocaleLowerCase();
		if (prefix === '@') {
			const actions = quickActions.filter((action) =>
				`${action.name} ${action.description}`.toLocaleLowerCase().includes(normalized)
			);
			const agents = availableAgents
				.filter((agent) => agent.name.toLocaleLowerCase().includes(normalized))
				.map((agent) => ({ kind: 'agent' as const, id: agent.id, name: agent.name }));
			return [...actions, ...agents].slice(0, 7);
		}
		const commandShortcuts = composerCommands
			.filter((command) =>
				`${command.id} ${command.name} ${command.description}`
					.toLocaleLowerCase()
					.includes(normalized)
			)
			.slice(0, 7)
			.map((command) => ({ kind: 'command' as const, ...command }));
		const skillShortcuts = availableSkills
			.filter((skill) => skill.name.toLocaleLowerCase().includes(normalized))
			.slice(0, 5)
			.map((skill) => ({ kind: 'skill' as const, id: skill.id, name: skill.name }));
		return [...commandShortcuts, ...skillShortcuts];
	});
	const shortcutMenuLabel = $derived(
		shortcutTrigger?.[1] === '@' ? '채팅 추가 제안' : '채팅 명령 제안'
	);
	const shortcutSignature = $derived(
		composerShortcuts.map((shortcut) => `${shortcut.kind}:${shortcut.id}`).join('|')
	);
	const shortcutsVisible = $derived(!streaming && composerShortcuts.length > 0);

	function shortcutDisabled(shortcut: ComposerShortcut): boolean {
		return (shortcut.kind === 'command' || shortcut.kind === 'quick-action') && Boolean(shortcut.disabled);
	}
	function firstEnabledShortcut(): number {
		const index = composerShortcuts.findIndex((shortcut) => !shortcutDisabled(shortcut));
		return index === -1 ? 0 : index;
	}
	$effect(() => {
		void shortcutSignature;
		activeShortcutIndex = firstEnabledShortcut();
	});

	async function scrollActiveShortcut() {
		await tick();
		const active = shortcutMenu?.querySelector<HTMLElement>(
			`[data-shortcut-index="${activeShortcutIndex}"]`
		);
		active?.scrollIntoView?.({ block: 'nearest' });
	}
	function moveShortcut(direction: -1 | 1) {
		const enabled = composerShortcuts
			.map((shortcut, index) => ({ shortcut, index }))
			.filter(({ shortcut }) => !shortcutDisabled(shortcut))
			.map(({ index }) => index);
		if (enabled.length === 0) return;
		const position = enabled.indexOf(activeShortcutIndex);
		const next = position === -1 ? 0 : (position + direction + enabled.length) % enabled.length;
		activeShortcutIndex = enabled[next];
		void scrollActiveShortcut();
	}
	function clearShortcutTrigger() {
		value = value.replace(/(^|\s)[@/][^\n]*$/, '$1');
	}
	async function applyShortcut(shortcut: ComposerShortcut) {
		if (shortcutDisabled(shortcut)) return;
		if (shortcut.kind === 'command' || shortcut.kind === 'quick-action') {
			clearShortcutTrigger();
			ta?.focus();
			await tick();
			shortcut.onSelect();
			return;
		}
		if (shortcut.kind === 'agent') {
			onSelectAgent?.(shortcut.id);
		} else if (!selectedSkillIds.includes(shortcut.id)) {
			selectedSkillIds = [...selectedSkillIds, shortcut.id];
		}
		clearShortcutTrigger();
		ta?.focus();
	}
	function autocompleteShortcut(shortcut: ComposerShortcut) {
		if (shortcut.kind !== 'command' || shortcut.disabled) {
			void applyShortcut(shortcut);
			return;
		}
		value = value.replace(/(^|\s)\/[^\n]*$/, `$1/${shortcut.name} `);
		ta?.focus();
	}
	async function executeTypedCommand(): Promise<boolean> {
		const typed = value.trim().match(/^\/(.+)$/)?.[1]?.trim().toLocaleLowerCase();
		if (!typed) return false;
		const command = composerCommands.find(
			(candidate) =>
				candidate.name.toLocaleLowerCase() === typed || candidate.id.toLocaleLowerCase() === typed
		);
		if (!command) return false;
		if (command.disabled) return true;
		clearShortcutTrigger();
		await tick();
		command.onSelect();
		return true;
	}

	function isOn(id: number, selected: number[] | null): boolean {
		return selected === null ? true : selected.includes(id);
	}
	function toggleTool(id: number) {
		const cur = selectedToolIds ?? availableTools.map((t) => t.id);
		selectedToolIds = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
	}
	function toggleMcp(id: number) {
		const cur = selectedMcpIds ?? availableMcp.map((m) => m.id);
		selectedMcpIds = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
	}
	// 스킬은 opt-in — 빈 목록에서 시작해 선택 시 추가.
	function toggleSkill(id: number) {
		selectedSkillIds = selectedSkillIds.includes(id)
			? selectedSkillIds.filter((x) => x !== id)
			: [...selectedSkillIds, id];
	}

	async function addFiles(files: FileList | File[]) {
		if (!canAttach) return;
		for (const file of Array.from(files)) {
			const image = isChatImageMime(file.type);
			const document = isChatDocumentMime(file.type);
			if ((!image && !document) || (image && !canAttachImage) || (document && !canAttachDocument)) {
				toast.error('선택한 모델에서 지원하지 않는 첨부입니다');
				continue;
			}
			const item: ChatAttachment = {
				mime: file.type,
				name: file.name || (document ? 'document.pdf' : 'image'),
				previewUrl: image ? URL.createObjectURL(file) : undefined,
				status: 'uploading'
			};
			attachments.push(item);
			const pending = attachments.at(-1)!;
			try {
				const ref = await uploadChatAttachment(file, { token, projectId });
				if (!isChatImageMime(ref.mime_type) && !isChatDocumentMime(ref.mime_type)) {
					throw new Error('업로드한 파일이 지원되는 이미지 또는 PDF로 확인되지 않았습니다');
				}
				attachments = attachments.map((attachment) =>
					attachment === pending ? completeChatAttachment(attachment, ref) : attachment
				);
			} catch (e) {
				pending.status = 'error';
				attachments = attachments.filter((attachment) => attachment !== pending);
				if (pending.previewUrl) URL.revokeObjectURL(pending.previewUrl);
				toast.error(e instanceof Error ? e.message : '첨부 업로드 실패');
			}
		}
	}
	function removeAttachment(item: ChatAttachment) {
		attachments = attachments.filter((a) => a !== item);
		if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
	}
	function onFilePick(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		if (input.files?.length) void addFiles(input.files);
		input.value = '';
		plusOpen = false;
	}
	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		if (e.dataTransfer?.files?.length) void addFiles(e.dataTransfer.files);
	}

	const effortOptions = $derived(effortOptionsFor(modelCaps));
	const showEffort = $derived(effortOptions.length > 0);

	// 내용에 맞춰 높이 자동 조절(최대 12rem)
	function autoGrow() {
		const el = ta;
		if (!el) return;
		el.style.height = 'auto';
		el.style.height = `${Math.min(el.scrollHeight, 192)}px`;
	}
	$effect(() => {
		void value;
		autoGrow();
	});

	async function onKeydown(e: KeyboardEvent) {
		if (shortcutsVisible) {
			if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
				e.preventDefault();
				moveShortcut(e.key === 'ArrowDown' ? 1 : -1);
				return;
			}
			if (e.key === 'Tab') {
				e.preventDefault();
				autocompleteShortcut(composerShortcuts[activeShortcutIndex] ?? composerShortcuts[0]);
				return;
			}
			if (e.key === 'Escape') {
				e.preventDefault();
				dismissedShortcutValue = value;
				return;
			}
			if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
				e.preventDefault();
				await applyShortcut(composerShortcuts[activeShortcutIndex] ?? composerShortcuts[0]);
				return;
			}
		}
		if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
			e.preventDefault();
			if (!streaming && (await executeTypedCommand())) return;
			if (canSend) onSend();
		}
	}
	function chooseEffort(v: string) {
		effort = v;
		effortOpen = false;
	}

	const canSend = $derived(!disabled && !sendDisabled && !streaming && value.trim().length > 0);

	const format = new Intl.NumberFormat('ko-KR');
	const knownContext = $derived(
		hasContextScope &&
			!contextError &&
			contextState !== null &&
			contextState.measurement !== 'unknown' &&
			contextState.input_budget !== null &&
			contextState.input_tokens !== null &&
			contextState.utilization !== null
			&& contextState.breakdown?.complete !== false
	);
	const contextPercent = $derived(
		Math.max(0, Math.round((contextState?.utilization ?? 0) * 100))
	);
	const contextRingPercent = $derived(Math.min(100, contextPercent));
	const contextRemaining = $derived(
		knownContext ? Math.max(0, contextState!.input_budget! - contextState!.input_tokens!) : null
	);
	const contextMeasurementLabel = $derived(
		contextState?.reason_code === 'token_counter_failed'
			? '추정치 (토큰 계수 실패)'
			: contextState?.measurement === 'estimated'
				? '추정치'
				: '토큰 계수'
	);
	const contextValueText = $derived(
		knownContext
			? `${contextMeasurementLabel} ${format.format(contextState!.input_tokens!)} / ${format.format(contextState!.input_budget!)} 토큰 · ${format.format(contextRemaining!)} 남음 · ${Math.round((contextState!.utilization ?? 0) * 100)}%`
			: '컨텍스트 한도를 확인할 수 없습니다'
	);
	const contextDetail = $derived.by(() => {
		if (knownContext) {
			if (contextState?.reason_code === 'token_counter_failed') {
				return `${contextValueText}. LiteLLM 토큰 계수에 실패해 텍스트 길이 기반 추정치를 표시합니다.`;
			}
			if (contextState?.measurement === 'estimated') {
				return `${contextValueText}. 제공되는 토크나이저 식별 정보가 없어 추정치를 표시합니다.`;
			}
			return `${contextValueText}. 모델 토크나이저로 계산한 입력 예산 사용량입니다.`;
		}
		if (contextError) return contextError;
		if (contextState?.breakdown?.complete === false) return '일부 입력이 아직 계수되지 않았습니다. 포함된 항목과 미계수 항목을 확인하세요.';
		switch (contextState?.reason_code) {
			case 'context_window_unknown':
				return '선택한 모델의 입력 한도가 확인되지 않아 남은 컨텍스트 용량을 계산할 수 없습니다.';
			case 'token_count_unavailable':
				return '현재 메시지 또는 첨부의 토큰 수를 안전하게 셀 수 없어 컨텍스트 사용량을 표시하지 않습니다.';
			case 'invalid_budget':
				return '모델 한도에서 응답 및 안전 여유분을 제외한 입력 예산이 0 이하입니다. 모델 또는 출력 설정을 확인하세요.';
			case 'context_request_invalid':
				return '컨텍스트 요청 설정이 올바르지 않아 사용량을 계산할 수 없습니다.';
			default:
				return '컨텍스트 사용량 정보를 아직 사용할 수 없습니다.';
		}
	});
	function toggleContextDetails(event: MouseEvent) {
		(event.currentTarget as HTMLButtonElement).focus();
		contextInfoOpen = !contextInfoOpen;
	}
	$effect(() => {
		if (contextLoading || contextPhase === 'compacting') contextInfoOpen = false;
	});
	const contextStatus = $derived.by(() => {
		if (contextPhase === 'compacting') {
			return contextCause === 'automatic' ? '컨텍스트 자동 압축 중' : '컨텍스트 압축 중';
		}
		if (contextPhase === 'compacted' && contextBeforeTokens !== null && contextAfterTokens !== null) {
			return `압축 ${format.format(contextBeforeTokens)} → ${format.format(contextAfterTokens)}`;
		}
		if (contextError) return '컨텍스트 조회 실패';
		if (contextState?.breakdown?.complete === false) return '컨텍스트 일부 미계수';
		if (knownContext) return `컨텍스트 ${contextPercent}%`;
		if (contextLoading) return '컨텍스트 확인 중';
		return '컨텍스트 확인 불가';
	});
</script>


<div class="composer">
	<input
		bind:this={fileInput}
		type="file"
		accept="image/jpeg,image/png,image/webp,application/pdf"
		multiple
		hidden
		onchange={onFilePick}
	/>
	{#if shortcutsVisible}
		<div
			class="shortcut-menu"
			id="chat-composer-shortcuts"
			bind:this={shortcutMenu}
			role="listbox"
			aria-label={shortcutMenuLabel}
		>
			{#each composerShortcuts as shortcut, index (shortcut.kind + shortcut.id)}
				<button
					type="button"
					id={`chat-composer-shortcut-${index}`}
					data-shortcut-index={index}
					role="option"
					aria-selected={index === activeShortcutIndex}
					class="shortcut-option"
					class:active={index === activeShortcutIndex}
					disabled={shortcutDisabled(shortcut)}
					title={shortcut.kind === 'command' || shortcut.kind === 'quick-action' ? shortcut.disabledReason : undefined}
					onpointerenter={() => (activeShortcutIndex = index)}
					onclick={() => applyShortcut(shortcut)}
				>
					<span class="shortcut-prefix">{shortcut.kind === 'command' || shortcut.kind === 'skill' ? '/' : '@'}</span>
					<span class="shortcut-copy">
						<span class="shortcut-name">{shortcut.name}</span>
						{#if shortcut.kind === 'command' || shortcut.kind === 'quick-action'}
							<span class="shortcut-description">{shortcut.description}</span>
						{/if}
					</span>
					<span class="shortcut-kind">
						{#if shortcut.kind === 'command' || shortcut.kind === 'quick-action'}
							{shortcut.disabled ? (shortcut.disabledReason ?? '사용 불가') : shortcut.kind === 'command' ? '명령' : '추가'}
						{:else}
							{shortcut.kind === 'agent' ? '에이전트' : '스킬'}
						{/if}
					</span>
				</button>
			{/each}
		</div>
	{/if}
	<div
		class="input-wrap"
		class:drag-over={dragOver}
		 role="group"
		ondragover={(e) => {
			if (canAttach) {
				e.preventDefault();
				dragOver = true;
			}
		}}
		ondragleave={() => (dragOver = false)}
		ondrop={onDrop}
	>
		{#if attachments.length}
			<div class="chips">
				{#each attachments as a (a.previewUrl ?? a.assetId ?? a.name)}
					<div class="chip" class:uploading={a.status === 'uploading'}>
						{#if a.previewUrl}
							<img src={a.previewUrl} alt={a.name} />
						{:else}
							<span class="chip-name">{a.name}</span>
						{/if}
						{#if a.status === 'uploading'}
							<span class="chip-spin"></span>
						{/if}
						<button type="button" class="chip-x" title="제거" aria-label="첨부 제거" onclick={() => removeAttachment(a)}>
							<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round" /></svg>
						</button>
					</div>
				{/each}
			</div>
		{/if}

		<textarea
			bind:this={ta}
			bind:value
			{placeholder}
			rows="1"
			disabled={disabled && !streaming}
			aria-controls={shortcutsVisible ? 'chat-composer-shortcuts' : undefined}
			aria-activedescendant={shortcutsVisible ? `chat-composer-shortcut-${activeShortcutIndex}` : undefined}
			onkeydown={onKeydown}
			oninput={() => {
				dismissedShortcutValue = null;
				autoGrow();
			}}
		></textarea>

		<div class="toolbar">
			<div class="tb-left">
				<div class="plus" title={!hasPlus ? attachmentUnavailableReason : undefined}>
					<button
						type="button"
						class="tool-shell"
						disabled={!hasPlus || streaming}
						title={plusTitle}
						aria-label="추가"
						aria-haspopup="menu"
						aria-expanded={plusOpen}
						onclick={() => (plusOpen = !plusOpen)}
					>
						<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M12 5v14M5 12h14" stroke-linecap="round" /></svg>
					</button>
					{#if plusOpen}
						<div class="scrim" role="button" tabindex="-1" aria-label="닫기" onclick={() => (plusOpen = false)} onkeydown={(e) => e.key === 'Escape' && (plusOpen = false)}></div>
						<div class="plus-menu" role="menu">
							{#if canAttach}
								<button type="button" class="plus-opt" role="menuitem" onclick={() => fileInput?.click()}>
									<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="2.6" /></svg>
									<span class="plus-opt-copy">
										<span class="plus-opt-name">파일 첨부</span>
										<span class="plus-opt-description">개인 프로젝트 기본 버킷에 자동 저장</span>
									</span>
								</button>
							{/if}
							{#if canUseTools}
								{#if canAttach}<div class="plus-sep"></div>{/if}
								<div class="plus-head">도구</div>
								{#each availableTools as t (t.id)}
									<button type="button" class="plus-opt toggle" role="menuitemcheckbox" aria-checked={isOn(t.id, selectedToolIds)} onclick={() => toggleTool(t.id)}>
										<span class="check" class:on={isOn(t.id, selectedToolIds)}>
											{#if isOn(t.id, selectedToolIds)}<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>{/if}
										</span>
										<span class="tool-name truncate">{t.name}</span>
									</button>
								{/each}
								{#if availableMcp.length}<div class="plus-head">MCP</div>{/if}
								{#each availableMcp as m (m.id)}
									<button type="button" class="plus-opt toggle" role="menuitemcheckbox" aria-checked={isOn(m.id, selectedMcpIds)} onclick={() => toggleMcp(m.id)}>
										<span class="check" class:on={isOn(m.id, selectedMcpIds)}>
											{#if isOn(m.id, selectedMcpIds)}<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>{/if}
										</span>
										<span class="tool-name truncate">{m.name}</span>
									</button>
								{/each}
							{/if}
							{#if canUseSkills}
								{#if canAttach || canUseTools}<div class="plus-sep"></div>{/if}
								<div class="plus-head">스킬</div>
								{#each availableSkills as s (s.id)}
									<button type="button" class="plus-opt toggle" role="menuitemcheckbox" aria-checked={selectedSkillIds.includes(s.id)} onclick={() => toggleSkill(s.id)}>
										<span class="check" class:on={selectedSkillIds.includes(s.id)}>
											{#if selectedSkillIds.includes(s.id)}<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>{/if}
										</span>
										<span class="tool-name truncate">{s.name}</span>
									</button>
								{/each}
							{/if}
						</div>
					{/if}
				</div>
				{#if hasNativeSearch}
					<Button
						variant={searchEnabled || searchRequired ? 'secondary' : 'ghost'}
						size="sm"
						class="min-h-11 md:min-h-8"
						ariaLabel="Search 웹 검색"
						ariaPressed={searchEnabled || searchRequired}
						disabled={disabled || streaming || searchRequired || !searchAvailable}
						title={searchTitle}
						onclick={() => (searchEnabled = !searchEnabled)}
					>
						<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.35-4.35" stroke-linecap="round" /></svg>
						Search{searchRequired ? ' · 기본' : ''}
					</Button>
				{/if}
				<ModelCapabilityBadges caps={modelCaps} size="sm" hideSearch={hasNativeSearch} />
			</div>

			<div class="tb-right">
				{#if hasContextScope}
					<div
						class="context-status"
						class:compacting={contextPhase === 'compacting'}
						role="status"
						aria-live="polite"
						aria-atomic="true"
					>
						{#if contextPhase === 'compacting' || (contextLoading && !knownContext)}
							<span class="context-spinner" aria-hidden="true"></span>
						{:else if knownContext}
							<button
								type="button"
								class="context-meter"
								aria-label="컨텍스트 용량 세부 정보"
								aria-controls="chat-context-detail"
								aria-expanded={contextInfoOpen}
								aria-haspopup="dialog"
								onclick={toggleContextDetails}
							>
								<UsageRing
									percent={contextRingPercent}
									thresholds={{ warning: 70, danger: 80 }}
									label="컨텍스트 입력 예산 사용률"
									valueText={contextValueText}
								/>
							</button>
						{:else}
							<button
								type="button"
								class="context-unavailable"
								aria-label="컨텍스트를 표시할 수 없는 이유"
								aria-controls="chat-context-detail"
								aria-expanded={contextInfoOpen}
								aria-haspopup="dialog"
								onclick={toggleContextDetails}
							><span class="context-reason-icon">?</span></button>
						{/if}
						<span class="context-status-text">{contextStatus}</span>
					</div>
				{/if}

				{#if showEffort}
					<div class="effort">
						<button
							type="button"
							class="effort-btn"
							class:on={effort !== 'auto'}
							onclick={() => (effortOpen = !effortOpen)}
							aria-haspopup="listbox"
							aria-expanded={effortOpen}
							title="추론 강도"
						>
							<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9.5 21h5M12 3a6 6 0 0 1 4 10.5c-.6.6-1 1.4-1 2.2V17H9v-1.3c0-.8-.4-1.6-1-2.2A6 6 0 0 1 12 3z" stroke-linecap="round" stroke-linejoin="round" /></svg>
							<span>{effortLabel(effort ?? 'auto')}</span>
						</button>
						{#if effortOpen}
							<div class="scrim" role="button" tabindex="-1" aria-label="닫기" onclick={() => (effortOpen = false)} onkeydown={(e) => e.key === 'Escape' && (effortOpen = false)}></div>
							<div class="effort-menu" role="listbox">
								<div class="effort-head">추론 강도</div>
								{#each effortOptions as v (v)}
									<button type="button" class="effort-opt" class:sel={effort === v} role="option" aria-selected={effort === v} onclick={() => chooseEffort(v)}>{effortLabel(v)}</button>
								{/each}
							</div>
						{/if}
					</div>
				{/if}

				{#if streaming}
					<button type="button" class="send stop" onclick={onStop} title="생성 중단" aria-label="생성 중단">
						<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="1.5" /></svg>
					</button>
				{:else}
					<button type="button" class="send" disabled={!canSend} onclick={onSend} title="전송" aria-label="전송">
						<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19V5M5 12l7-7 7 7" stroke-linecap="round" stroke-linejoin="round" /></svg>
					</button>
				{/if}
			</div>
		</div>
	</div>
	{#if children}
		<div class="composer-footer">{@render children()}</div>
	{/if}
	<p class="hint">AI 응답은 부정확할 수 있습니다. 중요한 내용은 확인하세요.</p>
</div>

{#if contextInfoOpen}
	<ChatContextPanel state={contextError ? null : contextState} explanation={contextDetail} onClose={() => (contextInfoOpen = false)} />
{/if}

<style>
	.composer {
		padding: 0.75rem 1rem 0.9rem;
	}
	.input-wrap {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		padding: 0.6rem 0.7rem 0.55rem;
		border-radius: 1rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		transition: border-color 0.15s, box-shadow 0.15s;
		box-shadow: 0 14px 32px color-mix(in oklab, var(--color-ink-0) 10%, transparent);
	}
	.toolbar {
		display: flex;
		flex-wrap: wrap;
		min-width: 0;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.input-wrap:focus-within {
		border-color: var(--color-accent);
		box-shadow: var(--focus-ring), 0 14px 32px color-mix(in oklab, var(--color-ink-0) 10%, transparent);
	}
	textarea {
		resize: none;
		border: none;
		outline: none;
		background: transparent;
		color: var(--color-ink-0);
		font-size: 0.9rem;
		line-height: 1.5;
		max-height: 12rem;
		padding: 0.15rem 0.2rem;
	}
	textarea::placeholder {
		color: var(--color-ink-3);
	}
	.shortcut-menu {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		max-height: min(18rem, 42dvh);
		overflow-y: auto;
		margin: 0 0 0.4rem;
		padding: 0.3rem;
		border: 1px solid var(--color-line);
		border-radius: 0.6rem;
		background: var(--color-surface-sunken);
	}
	.shortcut-option {
		display: grid;
		grid-template-columns: 1.1rem minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.35rem;
		width: 100%;
		padding: 0.42rem 0.48rem;
		border: none;
		border-radius: 0.42rem;
		background: transparent;
		color: var(--color-ink-1);
		cursor: pointer;
		font-size: 0.78rem;
		text-align: left;
	}
	.shortcut-option:hover,
	.shortcut-option:focus-visible,
	.shortcut-option.active {
		background: var(--color-surface-raised);
	}
	.shortcut-prefix {
		color: var(--color-accent);
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
		font-weight: 700;
	}
	.shortcut-copy {
		display: flex;
		min-width: 0;
		flex-direction: column;
		gap: 0.08rem;
	}
	.shortcut-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.shortcut-description {
		overflow: hidden;
		color: var(--color-ink-3);
		font-size: 0.68rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.shortcut-kind {
		max-width: 8rem;
		overflow: hidden;
		color: var(--color-ink-3);
		font-size: 0.68rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.shortcut-option:disabled {
		cursor: not-allowed;
		opacity: 0.58;
	}
	.shortcut-option:disabled:hover,
	.shortcut-option:disabled.active {
		background: transparent;
	}
	.context-status {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: 0.32rem;
		min-width: 0;
		color: var(--color-ink-2);
		font-size: 0.72rem;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.context-status.compacting { color: var(--color-accent); }
	.context-status-text {
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.context-spinner,
	.context-reason-icon {
		display: inline-flex;
		width: 1.125rem;
		height: 1.125rem;
		flex: 0 0 auto;
		align-items: center;
		justify-content: center;
	}
	.context-meter,
	.context-unavailable {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.75rem;
		height: 2.75rem;
		flex: 0 0 auto;
		padding: 0;
		border: none;
		border-radius: 50%;
		background: transparent;
		cursor: pointer;
	}
	.context-meter:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.context-spinner {
		border: 2px solid var(--color-line-2);
		border-top-color: currentColor;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	.context-reason-icon {
		padding: 0;
		border: 1px solid var(--color-line-2);
		border-radius: 50%;
		background: transparent;
		color: var(--color-ink-3);
		font-size: 0.7rem;
		font-weight: 700;
		cursor: pointer;
	}
	.context-unavailable:hover .context-reason-icon {
		border-color: var(--color-line-2);
		color: var(--color-ink-1);
	}
	.context-unavailable:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.tb-left {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
		min-width: 0;
		overflow: visible;
	}
	.tb-left :global(.badges) {
		flex-shrink: 0;
	}
	.tb-right {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
		margin-left: auto;
	}
	.input-wrap.drag-over {
		border-color: var(--color-accent);
		box-shadow: var(--focus-ring);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		padding: 0.15rem 0.2rem 0;
	}
	.chip {
		position: relative;
		width: 3.2rem;
		height: 3.2rem;
		border-radius: 0.5rem;
		overflow: hidden;
		border: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
	}
	.chip img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.chip.uploading img {
		opacity: 0.5;
	}
	.chip-spin {
		position: absolute;
		inset: 50% auto auto 50%;
		width: 1rem;
		height: 1rem;
		margin: -0.5rem 0 0 -0.5rem;
		border-radius: 50%;
		border: 2px solid var(--color-line-2);
		border-top-color: var(--color-accent);
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.chip-x {
		position: absolute;
		top: 0.1rem;
		right: 0.1rem;
		width: 1.1rem;
		height: 1.1rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: none;
		border-radius: 50%;
		background: color-mix(in oklab, var(--color-ink-0) 55%, transparent);
		color: var(--color-action-on-accent);
		cursor: pointer;
	}
	.plus {
		position: relative;
		flex-shrink: 0;
	}
	.tool-shell {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.9rem;
		height: 1.9rem;
		border-radius: 0.55rem;
		border: 1px solid var(--color-line);
		background: transparent;
		color: var(--color-ink-2);
		cursor: pointer;
		transition: background 0.12s, color 0.12s, border-color 0.12s;
	}
	.tool-shell:hover:not(:disabled) {
		color: var(--color-ink-0);
		border-color: var(--color-line-2);
		background: var(--color-surface-sunken);
	}
	.tool-shell:disabled {
		color: var(--color-ink-3);
		cursor: not-allowed;
		opacity: 0.5;
	}
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 20;
		border: none;
		background: transparent;
	}
	.plus-menu {
		position: absolute;
		bottom: calc(100% + 0.35rem);
		left: 0;
		z-index: 21;
		min-width: min(18rem, calc(100vw - 2rem));
		background: var(--color-surface-raised);
		border: 1px solid var(--color-line);
		border-radius: 0.6rem;
		box-shadow: 0 10px 28px color-mix(in oklab, var(--color-ink-0) 20%, transparent);
		padding: 0.3rem;
	}
	.composer-footer {
		width: 95%;
		margin: -1px auto 0;
	}
	.plus-opt {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		width: 100%;
		padding: 0.45rem 0.55rem;
		border: none;
		border-radius: 0.45rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.82rem;
		cursor: pointer;
		text-align: left;
	}
	.plus-opt-copy {
		display: flex;
		min-width: 0;
		flex-direction: column;
		gap: 0.1rem;
	}
	.plus-opt-name {
		font-weight: 600;
	}
	.plus-opt-description {
		color: var(--color-ink-3);
		font-size: 0.7rem;
		line-height: 1.35;
	}
	@media (min-width: 768px) and (max-width: 1023px) {
		.plus-menu {
			right: 0;
			left: auto;
		}
	}
	.plus-opt:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.plus-sep {
		height: 1px;
		margin: 0.25rem 0.2rem;
		background: var(--color-line);
	}
	.plus-head {
		padding: 0.35rem 0.55rem 0.2rem;
		font-size: 0.64rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--color-ink-3);
	}
	.plus-opt.toggle {
		gap: 0.45rem;
	}
	.check {
		flex-shrink: 0;
		width: 1rem;
		height: 1rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.28rem;
		border: 1px solid var(--color-line-2);
		color: var(--color-action-on-accent);
	}
	.check.on {
		background: var(--color-accent);
		border-color: var(--color-accent);
	}
	.tool-name {
		flex: 1;
		min-width: 0;
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.effort {
		position: relative;
	}
	.effort-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.28rem;
		padding: 0.32rem 0.6rem;
		border-radius: 0.55rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		color: var(--color-ink-2);
		font-size: 0.74rem;
		font-weight: 600;
		cursor: pointer;
		white-space: nowrap;
	}
	.effort-btn:hover {
		color: var(--color-ink-0);
		border-color: var(--color-line-2);
	}
	.effort-btn.on {
		color: color-mix(in oklab, var(--color-warm) 70%, var(--color-ink-1));
		border-color: color-mix(in oklab, var(--color-warm) 40%, var(--color-line));
	}
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 20;
		border: none;
		background: transparent;
	}
	.effort-menu {
		position: absolute;
		bottom: calc(100% + 0.3rem);
		right: 0;
		z-index: 21;
		min-width: 8rem;
		background: var(--color-surface-raised);
		border: 1px solid var(--color-line);
		border-radius: 0.6rem;
		box-shadow: 0 10px 28px color-mix(in oklab, var(--color-ink-0) 20%, transparent);
		padding: 0.3rem;
		display: flex;
		flex-direction: column;
		gap: 0.08rem;
	}
	.effort-head {
		padding: 0.3rem 0.55rem;
		font-size: 0.66rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--color-ink-3);
	}
	.effort-opt {
		text-align: left;
		padding: 0.4rem 0.55rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8rem;
		cursor: pointer;
	}
	.effort-opt:hover {
		background: var(--color-surface-sunken);
	}
	.effort-opt.sel {
		color: var(--color-accent);
		font-weight: 600;
	}
	.send {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.1rem;
		height: 2.1rem;
		border-radius: 0.7rem;
		border: none;
		background: var(--color-accent);
		color: var(--color-action-on-accent);
		cursor: pointer;
		transition: filter 0.15s, background 0.15s, opacity 0.15s;
	}
	.send:hover:not(:disabled) {
		filter: brightness(1.08);
	}
	.send:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.send.stop {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
		border: 1px solid var(--color-line);
	}
	.send.stop:hover {
		background: var(--color-surface-raised);
	}
	.hint {
		margin: 0.5rem 0 0;
		text-align: center;
		font-size: 0.6875rem;
		color: var(--color-ink-3);
	}

	@media (max-width: 47.9375rem) {
		.tool-shell,
		.send,
		.effort-btn {
			min-width: 2.75rem;
			min-height: 2.75rem;
		}
		.context-status-text {
			display: none;
		}
	}
</style>
