<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ChatExtensionsManager from './ChatExtensionsManager.svelte';
	import ChatApiKeysManager from './ChatApiKeysManager.svelte';
	import ChatUsagePanel from './ChatUsagePanel.svelte';
	import type { ChatUsage } from '$lib/api/chatTree';
	import type { Memory } from '$lib/api/chatWorkspaces';

	export type ChatSettingsSection = 'usage' | 'apikeys' | 'memory' | 'mcp' | 'tools' | 'skills';

	interface MemoryDocument {
		filename: 'memory.md';
		content_type: 'text/markdown';
		content: string;
	}

	interface Props {
		open: boolean;
		onClose: () => void;
		usage: ChatUsage | null;
		initialSection?: ChatSettingsSection;
	}
	let { open, onClose, usage, initialSection = 'usage' }: Props = $props();
	let section = $state<ChatSettingsSection>('usage');

	$effect(() => {
		if (open) section = initialSection;
	});

	const sections: { key: ChatSettingsSection; label: string }[] = [
		{ key: 'usage', label: '사용량' },
		{ key: 'apikeys', label: 'API 키' },
		{ key: 'memory', label: '메모리' },
		{ key: 'mcp', label: 'MCP 서버' },
		{ key: 'tools', label: '도구' },
		{ key: 'skills', label: '스킬' }
	];

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);


	// --- 사용량 ---
	const monthTokens = $derived(
		(usage?.month_prompt_tokens ?? 0) + (usage?.month_completion_tokens ?? 0)
	);
	const credit = $derived(usage?.month_credited_cost ?? 0);
	const requests = $derived(usage?.month_request_count ?? 0);
	const quotaMax = $derived(usage?.quota_max ?? 0);
	const quotaUsed = $derived(usage?.quota_used ?? 0);
	function fmt(n: number): string {
		return n.toLocaleString('en-US');
	}
	function fmtCredit(n: number): string {
		return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
	}

	// --- 메모리 CRUD (설정 전용, 단일 사용) ---
	let memories = $state<Memory[]>([]);
	let memoryDocument = $state<MemoryDocument | null>(null);
	let memLoading = $state(true);
	let editingId = $state<number | null>(null);
	let draft = $state('');
	let saving = $state(false);
	let loadedOnce = $state(false);
	const canSubmit = $derived(draft.trim().length > 0 && !saving);

	async function loadMemories() {
		if (!token) return;
		memLoading = true;
		try {
			[memories, memoryDocument] = await Promise.all([
				api.get<Memory[]>('/api/v1/chat/memories', token, projectId),
				api.get<MemoryDocument>('/api/v1/chat/memories/document', token, projectId)
			]);
		} catch {
			toast.error('메모리를 불러오지 못했습니다');
		} finally {
			memLoading = false;
		}
	}

	async function copyMemoryDocument() {
		if (!memoryDocument) return;
		try {
			await navigator.clipboard.writeText(memoryDocument.content);
			toast.success('memory.md를 복사했습니다');
		} catch {
			toast.error('memory.md를 복사하지 못했습니다');
		}
	}

	function downloadMemoryDocument() {
		if (!memoryDocument) return;
		const blob = new Blob([memoryDocument.content], { type: `${memoryDocument.content_type};charset=utf-8` });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = memoryDocument.filename;
		link.click();
		setTimeout(() => URL.revokeObjectURL(url), 0);
	}

	// 메모리 섹션을 처음 열 때 한 번 로드한다(오버레이가 열려 있는 동안 캐시).
	$effect(() => {
		if (open && section === 'memory' && !loadedOnce) {
			loadedOnce = true;
			void loadMemories();
		}
	});
	// 오버레이가 닫히면 다음에 다시 로드하도록 초기화한다.
	$effect(() => {
		if (!open) {
			loadedOnce = false;
			editingId = null;
			draft = '';
		}
	});

	function startEdit(m: Memory) {
		editingId = m.id;
		draft = m.content;
	}
	function cancelEdit() {
		editingId = null;
		draft = '';
	}

	async function submitMemory() {
		if (!token || !canSubmit) return;
		saving = true;
		try {
			const content = draft.trim();
			if (editingId !== null) {
				await api.patch(`/api/v1/chat/memories/${editingId}`, { content }, token, projectId);
				toast.success('메모리를 수정했습니다');
			} else {
				await api.post('/api/v1/chat/memories', { content }, token, projectId);
				toast.success('메모리를 추가했습니다');
			}
			editingId = null;
			draft = '';
			await loadMemories();
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '저장에 실패했습니다');
		} finally {
			saving = false;
		}
	}

	async function toggleActive(m: Memory) {
		if (!token) return;
		try {
			await api.patch(`/api/v1/chat/memories/${m.id}`, { is_active: !m.is_active }, token, projectId);
			await loadMemories();
		} catch {
			toast.error('상태 변경에 실패했습니다');
		}
	}

	async function removeMemory(m: Memory) {
		if (!token) return;
		if (!(await confirmDialog('이 메모리를 삭제하시겠습니까?'))) return;
		try {
			await api.delete(`/api/v1/chat/memories/${m.id}`, token, projectId);
			if (editingId === m.id) cancelEdit();
			await loadMemories();
			toast.success('삭제했습니다');
		} catch {
			toast.error('삭제에 실패했습니다');
		}
	}
</script>

<Modal {open} {onClose} ariaLabel="채팅 설정">
	<div class="panel">
		<header class="head">
			<h2>설정</h2>
			<button type="button" class="close" onclick={onClose} aria-label="닫기">
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" /></svg>
			</button>
		</header>

		<div class="split">
			<nav class="nav" aria-label="채팅 설정">
				{#each sections as s (s.key)}
					<button
						type="button"
						class="nav-item"
						class:active={section === s.key}
						onclick={() => (section = s.key)}
					>
						{s.label}
					</button>
				{/each}
			</nav>

			<div class="content">
				{#if section === 'usage'}
					<section class="sec">
						<h3 class="sec-title">이번 달 사용량</h3>
						<div class="stats">
							<div class="stat">
								<span class="stat-val">{fmt(monthTokens)}</span>
								<span class="stat-lbl">토큰 (입력+출력)</span>
							</div>
							<div class="stat">
								<span class="stat-val">{fmtCredit(credit)}</span>
								<span class="stat-lbl">크레딧</span>
							</div>
							<div class="stat">
								<span class="stat-val">{fmt(requests)}</span>
								<span class="stat-lbl">요청 수</span>
							</div>
						</div>
						{#if quotaMax > 0}
							<p class="sec-desc quota">
								월 쿼터 {fmt(quotaUsed)} / {fmt(quotaMax)}
							</p>
						{/if}
						{#if (usage?.quota_weekly_max ?? 0) > 0}
							<p class="sec-desc quota">
								주간 쿼터 {fmt(usage?.week_credited_cost ?? 0)} / {fmt(usage?.quota_weekly_max ?? 0)}
							</p>
						{/if}
						<div class="mt-4">
							<ChatUsagePanel />
						</div>
					</section>
				{:else if section === 'apikeys'}
					<section class="sec">
						<ChatApiKeysManager {usage} />
					</section>
				{:else if section === 'memory'}
					<section class="sec">
						<h3 class="sec-title">memory.md</h3>
						<p class="sec-desc">
							완료된 대화에서 안정적인 선호와 작업 맥락을 자동으로 추출해 갱신합니다. 원본 메모리는 암호화해 저장합니다.
						</p>
						{#if memLoading}
							<div class="memory-document skeleton" aria-label="memory.md 불러오는 중"></div>
						{:else if memoryDocument}
							<div class="memory-document">
								<div class="memory-document-head">
									<code>{memoryDocument.filename}</code>
									<div class="memory-document-actions">
										<Button variant="ghost" size="sm" type="button" onclick={copyMemoryDocument}>복사</Button>
										<Button variant="ghost" size="sm" type="button" onclick={downloadMemoryDocument}>다운로드</Button>
									</div>
								</div>
								<pre aria-label="memory.md 내용">{memoryDocument.content}</pre>
							</div>
						{/if}
						<div class="divider"></div>
						<h4 class="memory-manage-title">메모리 항목 직접 관리</h4>
						<p class="sec-desc">자동으로 정리된 항목을 추가하거나 수정하고, 필요 없는 항목을 비활성화할 수 있습니다.</p>
						<form
							class="composer"
							onsubmit={(e) => {
								e.preventDefault();
								void submitMemory();
							}}
						>
							<textarea
								class="inp ta"
								bind:value={draft}
								rows="3"
								maxlength="4000"
								placeholder="예: 나는 SvelteKit + TypeScript 로 개발한다. 답변은 간결하게."
							></textarea>
							<div class="composer-actions">
								{#if editingId !== null}
									<Button variant="ghost" size="sm" type="button" onclick={cancelEdit}>취소</Button>
								{/if}
								<Button variant="accent" size="sm" type="submit" disabled={!canSubmit}>
									{saving ? '저장 중…' : editingId !== null ? '변경 저장' : '+ 추가'}
								</Button>
							</div>
						</form>

						<div class="divider"></div>

						{#if memLoading}
							<p class="sec-desc">불러오는 중…</p>
						{:else if memories.length === 0}
							<p class="sec-desc">아직 저장된 메모리가 없습니다.</p>
						{:else}
							<div class="cards">
								{#each memories as m (m.id)}
									<div class="mem-card" class:inactive={!m.is_active}>
										<div class="mem-main">
											<p class="mem-content">{m.content}</p>
											{#if !m.is_active}<span class="off-badge">비활성</span>{/if}
										</div>
										<div class="mem-actions">
											<button
												type="button"
												class="act"
												onclick={() => toggleActive(m)}
												title={m.is_active ? '비활성화' : '활성화'}
												aria-label={m.is_active ? '비활성화' : '활성화'}
											>
												{#if m.is_active}
													<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>
												{:else}
													<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9" /></svg>
												{/if}
											</button>
											<button type="button" class="act" onclick={() => startEdit(m)} title="편집" aria-label="편집">
												<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" stroke-linecap="round" stroke-linejoin="round" /></svg>
											</button>
											<button type="button" class="act danger" onclick={() => removeMemory(m)} title="삭제" aria-label="삭제">
												<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" stroke-linecap="round" stroke-linejoin="round" /></svg>
											</button>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</section>
				{:else if section === 'mcp'}
					<section class="sec">
						<ChatExtensionsManager base="/api/v1/chat" only="mcp" />
					</section>
				{:else if section === 'tools'}
					<section class="sec">
						<ChatExtensionsManager base="/api/v1/chat" only="tools" />
					</section>
				{:else if section === 'skills'}
					<section class="sec">
						<ChatExtensionsManager base="/api/v1/chat" only="skills" />
					</section>
				{/if}
			</div>
		</div>
	</div>
</Modal>


<style>
	.panel {
		width: min(94vw, 52rem);
		height: min(86dvh, 40rem);
		max-height: calc(100dvh - 2rem);
		display: flex;
		flex-direction: column;
		border-radius: 0.9rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		overflow: hidden;
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.9rem 1.1rem;
		border-bottom: 1px solid var(--color-line);
		flex-shrink: 0;
	}
	.head h2 {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.close {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border: none;
		border-radius: 0.5rem;
		background: transparent;
		color: var(--color-ink-3);
		cursor: pointer;
		transition:
			background var(--motion-duration-fast) var(--motion-ease-standard),
			color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.close:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.split {
		display: flex;
		flex: 1;
		min-height: 0;
	}
	.nav {
		width: 11rem;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		padding: 0.75rem;
		border-right: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		overflow-y: auto;
	}
	.nav-item {
		text-align: left;
		display: block;
		padding: 0.5rem 0.65rem;
		border: none;
		border-radius: 0.55rem;
		background: transparent;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		font-weight: 550;
		text-decoration: none;
		cursor: pointer;
		transition:
			background var(--motion-duration-fast) var(--motion-ease-standard),
			color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.nav-item:hover {
		background: var(--color-surface-base);
		color: var(--color-ink-0);
	}
	.nav-item.active {
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
	}
	.content {
		flex: 1;
		min-width: 0;
		padding: 1.2rem 1.3rem;
		overflow-y: auto;
	}
	.sec {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.sec-title {
		margin: 0;
		font-size: 0.9rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.sec-desc {
		margin: 0;
		font-size: 0.78rem;
		color: var(--color-ink-3);
	}
	.stats {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
		gap: 0.6rem;
		margin-top: 0.4rem;
	}
	.stat {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		padding: 0.8rem 0.9rem;
		border-radius: 0.7rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
	}
	.stat-val {
		font-size: 1.05rem;
		font-weight: 650;
		color: var(--color-ink-0);
		font-variant-numeric: tabular-nums;
	}
	.stat-lbl {
		font-size: 0.72rem;
		color: var(--color-ink-3);
	}
	.quota {
		margin-top: 0.5rem;
		font-variant-numeric: tabular-nums;
	}
	.memory-document {
		margin-top: 0.45rem;
		overflow: hidden;
		border: 1px solid var(--color-line);
		border-radius: 0.65rem;
		background: var(--color-surface-base);
	}
	.memory-document.skeleton {
		min-height: 10rem;
		background: var(--color-surface-sunken);
	}
	.memory-document-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.45rem 0.65rem;
		border-bottom: 1px solid var(--color-line);
		color: var(--color-ink-2);
	}
	.memory-document-actions {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}
	.memory-document pre {
		max-height: 16rem;
		margin: 0;
		overflow: auto;
		padding: 0.75rem;
		color: var(--color-ink-1);
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
		font-size: 0.75rem;
		line-height: 1.55;
		white-space: pre-wrap;
		word-break: break-word;
	}
	.memory-manage-title {
		margin: 0;
		color: var(--color-ink-1);
		font-size: 0.8rem;
		font-weight: 650;
	}
	.composer {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		margin-top: 0.5rem;
	}
	.inp {
		width: 100%;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		padding: 0.5rem 0.65rem;
		font-size: 0.8125rem;
		color: var(--color-ink-1);
	}
	.inp:focus {
		outline: none;
		border-color: var(--color-accent);
	}
	.ta {
		resize: vertical;
		min-height: 3.5rem;
		line-height: 1.5;
		font-family: inherit;
	}
	.composer-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}
	.divider {
		height: 1px;
		background: var(--color-line);
		margin: 1rem 0;
	}
	.cards {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.mem-card {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.7rem 0.85rem;
		border-radius: 0.65rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
	}
	.mem-card.inactive {
		opacity: 0.6;
	}
	.mem-main {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.mem-content {
		margin: 0;
		font-size: 0.8125rem;
		line-height: 1.5;
		color: var(--color-ink-1);
		white-space: pre-wrap;
		word-break: break-word;
	}
	.off-badge {
		align-self: flex-start;
		font-size: 0.68rem;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		background: var(--color-surface-sunken);
		color: var(--color-ink-3);
	}
	.mem-actions {
		display: flex;
		gap: 0.15rem;
		flex-shrink: 0;
	}
	.act {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.9rem;
		height: 1.9rem;
		border: none;
		border-radius: 0.45rem;
		background: transparent;
		color: var(--color-ink-3);
		cursor: pointer;
		transition:
			background var(--motion-duration-fast) var(--motion-ease-standard),
			color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.act:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.act.danger:hover {
		color: var(--color-state-danger);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
	}
	@media (max-width: 767px) {
		.split {
			flex-direction: column;
		}
		.nav {
			width: 100%;
			flex-direction: row;
			overflow-x: auto;
			border-right: none;
			border-bottom: 1px solid var(--color-line);
		}
		.nav-item {
			flex-shrink: 0;
			white-space: nowrap;
		}
		.content {
			padding: 1rem;
		}
	}
</style>
