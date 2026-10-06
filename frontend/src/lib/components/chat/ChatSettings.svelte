<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-settings';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
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
		initialSection?: ChatSettingsSection;
	}
	let { initialSection = 'usage' }: Props = $props();
	let section = $state<ChatSettingsSection>('usage');

	$effect(() => {
		section = initialSection;
	});

	const sections: { key: ChatSettingsSection; label: string }[] = [
		{ key: 'usage', get label() { return t('settings.sections.usage'); } },
		{ key: 'apikeys', get label() { return t('settings.sections.apiKeys'); } },
		{ key: 'memory', get label() { return t('settings.sections.memory'); } },
		{ key: 'mcp', get label() { return t('settings.sections.mcp'); } },
		{ key: 'tools', get label() { return t('settings.sections.tools'); } },
		{ key: 'skills', get label() { return t('settings.sections.skills'); } }
	];

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	let usage = $state<ChatUsage | null>(null);
	let usageGeneration = 0;

	async function loadUsage(
		expectedToken: string,
		expectedProjectId: string | undefined,
		generation: number
	) {
		try {
			const nextUsage = await api.get<ChatUsage>(
				'/api/v1/chat/usage',
				expectedToken,
				expectedProjectId
			);
			if (generation === usageGeneration) usage = nextUsage;
		} catch {
			if (generation === usageGeneration) usage = null;
		}
	}

	function selectSection(nextSection: ChatSettingsSection) {
		section = nextSection;
		void goto(`/dashboard/chat/settings?section=${nextSection}`, {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	}

	$effect(() => {
		const currentToken = token;
		const currentProjectId = projectId;
		const generation = ++usageGeneration;
		usage = null;
		if (currentToken) void loadUsage(currentToken, currentProjectId, generation);
	});

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
	let loadedMemoryScope = $state('');
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
			toast.error(t('settings.memory.loadFailed'));
		} finally {
			memLoading = false;
		}
	}

	async function copyMemoryDocument() {
		if (!memoryDocument) return;
		try {
			await navigator.clipboard.writeText(memoryDocument.content);
			toast.success(t('settings.memory.copied', { filename: 'memory.md' }));
		} catch {
			toast.error(t('settings.memory.copyFailed', { filename: 'memory.md' }));
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

	$effect(() => {
		const currentScope = `${token ?? ''}:${projectId ?? ''}`;
		if (section === 'memory' && token && loadedMemoryScope !== currentScope) {
			loadedMemoryScope = currentScope;
			void loadMemories();
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
				toast.success(t('settings.memory.updated'));
			} else {
				await api.post('/api/v1/chat/memories', { content }, token, projectId);
				toast.success(t('settings.memory.added'));
			}
			editingId = null;
			draft = '';
			await loadMemories();
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('settings.memory.saveFailed'));
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
			toast.error(t('settings.memory.toggleFailed'));
		}
	}

	async function removeMemory(m: Memory) {
		if (!token) return;
		if (!(await confirmDialog(t('settings.memory.deleteConfirm')))) return;
		try {
			await api.delete(`/api/v1/chat/memories/${m.id}`, token, projectId);
			if (editingId === m.id) cancelEdit();
			await loadMemories();
			toast.success(t('settings.memory.deleted'));
		} catch {
			toast.error(t('settings.memory.deleteFailed'));
		}
	}
</script>

<section class="settings-page">
	<header class="page-head">
		<p class="eyebrow">{t('settings.eyebrow')}</p>
		<h1>{t('settings.title')}</h1>
		<p>{t('settings.description')}</p>
	</header>

	<div class="panel">
		<div class="split">
			<nav class="nav" aria-label={t('settings.title')}>
				{#each sections as s (s.key)}
					<button
						type="button"
						class="nav-item"
						class:active={section === s.key}
						onclick={() => selectSection(s.key)}
					>
						{s.label}
					</button>
				{/each}
			</nav>

			<div class="content">
				{#if section === 'usage'}
					<section class="sec">
						<h3 class="sec-title">{t('settings.usage.title')}</h3>
						<div class="stats">
							<div class="stat">
								<span class="stat-val">{fmt(monthTokens)}</span>
								<span class="stat-lbl">{t('settings.usage.tokens')}</span>
							</div>
							<div class="stat">
								<span class="stat-val">{fmtCredit(credit)}</span>
								<span class="stat-lbl">{t('settings.usage.credits')}</span>
							</div>
							<div class="stat">
								<span class="stat-val">{fmt(requests)}</span>
								<span class="stat-lbl">{t('settings.usage.requests')}</span>
							</div>
						</div>
						{#if quotaMax > 0}
							<p class="sec-desc quota">
								{t('settings.usage.monthlyQuota', { used: fmt(quotaUsed), limit: fmt(quotaMax) })}
							</p>
						{/if}
						{#if (usage?.quota_weekly_max ?? 0) > 0}
							<p class="sec-desc quota">
								{t('settings.usage.weeklyQuota', { used: fmt(usage?.week_credited_cost ?? 0), limit: fmt(usage?.quota_weekly_max ?? 0) })}
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
							{t('settings.memory.description')}
						</p>
						{#if memLoading}
							<div class="memory-document motion-skeleton" role="status" aria-label={t('settings.memory.documentLoading', { filename: 'memory.md' })}>
								<span class="sr-only">{t('settings.memory.documentLoading', { filename: 'memory.md' })}</span>
							</div>
						{:else if memoryDocument}
							<div class="memory-document">
								<div class="memory-document-head">
									<code>{memoryDocument.filename}</code>
									<div class="memory-document-actions">
										<Button variant="ghost" size="sm" type="button" onclick={copyMemoryDocument}>{t('settings.memory.copy')}</Button>
										<Button variant="ghost" size="sm" type="button" onclick={downloadMemoryDocument}>{t('settings.memory.download')}</Button>
									</div>
								</div>
								<pre aria-label={t('settings.memory.documentContent', { filename: 'memory.md' })}>{memoryDocument.content}</pre>
							</div>
						{/if}
						<div class="divider"></div>
						<h4 class="memory-manage-title">{t('settings.memory.manageTitle')}</h4>
						<p class="sec-desc">{t('settings.memory.manageDescription')}</p>
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
								placeholder={t('settings.memory.placeholder')}
							></textarea>
							<div class="composer-actions">
								{#if editingId !== null}
									<Button variant="ghost" size="sm" type="button" onclick={cancelEdit}>{t('settings.memory.cancel')}</Button>
								{/if}
								<Button variant="accent" size="sm" type="submit" disabled={!canSubmit}>
									{saving ? t('settings.memory.saving') : editingId !== null ? t('settings.memory.saveChanges') : t('settings.memory.add')}
								</Button>
							</div>
						</form>

						<div class="divider"></div>

						{#if memLoading}
							<p class="sec-desc">{t('settings.memory.loading')}</p>
						{:else if memories.length === 0}
							<p class="sec-desc">{t('settings.memory.empty')}</p>
						{:else}
							<div class="cards">
								{#each memories as m (m.id)}
									<div class="mem-card" class:inactive={!m.is_active}>
										<div class="mem-main">
											<p class="mem-content">{m.content}</p>
											{#if !m.is_active}<span class="off-badge">{t('settings.memory.inactive')}</span>{/if}
										</div>
										<div class="mem-actions">
											<button
												type="button"
												class="act"
												onclick={() => toggleActive(m)}
												title={m.is_active ? t('settings.memory.deactivate') : t('settings.memory.activate')}
												aria-label={m.is_active ? t('settings.memory.deactivate') : t('settings.memory.activate')}
											>
												{#if m.is_active}
													<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>
												{:else}
													<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9" /></svg>
												{/if}
											</button>
											<button type="button" class="act" onclick={() => startEdit(m)} title={t('settings.memory.edit')} aria-label={t('settings.memory.edit')}>
												<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" stroke-linecap="round" stroke-linejoin="round" /></svg>
											</button>
											<button type="button" class="act danger" onclick={() => removeMemory(m)} title={t('settings.memory.delete')} aria-label={t('settings.memory.delete')}>
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
</section>


<style>
	.settings-page {
		width: 100%;
		height: 100%;
		min-height: 0;
		max-width: 72rem;
		margin: 0 auto;
		padding: clamp(1rem, 2.5vw, 2rem);
		display: flex;
		flex-direction: column;
	}
	.page-head {
		margin-bottom: 1rem;
	}
	.page-head h1 {
		margin: 0;
		font-size: clamp(1.45rem, 3vw, 2rem);
		font-weight: 700;
		letter-spacing: -0.025em;
		color: var(--color-ink-0);
	}
	.page-head p {
		margin: 0.35rem 0 0;
		color: var(--color-ink-2);
		font-size: 0.875rem;
	}
	.page-head .eyebrow {
		margin: 0 0 0.35rem;
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.14em;
		color: var(--color-accent);
	}
	.panel {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		border-radius: 0.9rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		overflow: hidden;
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
		color: var(--color-ink-2);
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
		color: var(--color-ink-2);
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
	.memory-document.motion-skeleton {
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
		color: var(--color-ink-2);
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
		color: var(--color-ink-2);
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
