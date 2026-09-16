<script lang="ts">
	import { untrack } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import CreateProjectDialog from './CreateProjectDialog.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import {
		buildWorkspacePayload,
		countConversationsInWorkspace,
		emptyWorkspaceForm,
		workspaceToForm,
		type Workspace,
		type WorkspaceForm,
		type WorkspacePayload
	} from '$lib/api/chatWorkspaces';

	interface Conversation {
		id: string;
		title: string | null;
		model_name: string | null;
		workspace_id: number | null;
		updated_at: string | null;
	}

	interface Props {
		conversations: Conversation[];
		workspaces: Workspace[];
		initialMode?: Mode;
		initialWorkspaceId?: number | null;
		onCreate: (payload: WorkspacePayload) => Promise<boolean>;
		onUpdate: (id: number, payload: WorkspacePayload) => Promise<boolean>;
		onDelete: (w: Workspace) => Promise<boolean>;
		onAssign: (conv: Conversation, workspaceId: number | null) => void;
		onOpenConversation: (conv: Conversation) => void;
		onNewInProject: (workspaceId: number) => void;
		onNavigate?: (workspaceId: number | null) => void;
	}
	let {
		conversations,
		workspaces,
		initialMode = 'grid',
		initialWorkspaceId = null,
		onCreate,
		onUpdate,
		onDelete,
		onAssign,
		onOpenConversation,
		onNewInProject,
		onNavigate,
	}: Props = $props();

	type Mode = 'grid' | 'create' | 'detail';
	let mode = $state<Exclude<Mode, 'create'>>(untrack(() => (initialWorkspaceId === null ? 'grid' : 'detail')));
	let selectedId = $state<number | null>(untrack(() => initialWorkspaceId));
	let query = $state('');
	let form = $state<WorkspaceForm>(emptyWorkspaceForm());
	let saving = $state(false);
	let createDialogOpen = $state(untrack(() => initialWorkspaceId === null && initialMode === 'create'));
	const selected = $derived(workspaces.find((w) => w.id === selectedId) ?? null);

	$effect(() => {
		if (initialWorkspaceId === null) return;
		selectedId = initialWorkspaceId;
		mode = 'detail';
	});
	const canSubmit = $derived(form.name.trim().length > 0 && !saving);

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		if (!q) return workspaces;
		return workspaces.filter(
			(w) =>
				w.name.toLowerCase().includes(q) ||
				(w.description ?? '').toLowerCase().includes(q)
		);
	});

	// 상세로 진입할 때 폼을 대상 프로젝트로 초기화한다.
	// 목록(workspaces)이 갱신돼도 편집 중 폼을 덮어쓰지 않도록 selectedId/mode 만 추적하고
	// 프로젝트 조회는 untrack 으로 감싼다.
	$effect(() => {
		const id = selectedId;
		if (mode !== 'detail' || id === null) return;
		untrack(() => {
			const w = workspaces.find((x) => x.id === id);
			if (w) form = workspaceToForm(w);
		});
	});

	const projectConvs = $derived(
		selectedId === null ? [] : conversations.filter((c) => c.workspace_id === selectedId)
	);
	const assignable = $derived(
		selectedId === null ? [] : conversations.filter((c) => c.workspace_id !== selectedId)
	);

	function openDetail(w: Workspace) {
		if (onNavigate) {
			onNavigate(w.id);
			return;
		}
		selectedId = w.id;
		mode = 'detail';
	}
	function openCreate() {
		createDialogOpen = true;
	}
	function closeCreate() {
		createDialogOpen = false;
	}
	async function createProject(name: string): Promise<boolean> {
		return onCreate({ name });
	}
	function backToGrid() {
		if (onNavigate) {
			onNavigate(null);
			return;
		}
		mode = 'grid';
		selectedId = null;
	}

	async function submitUpdate() {
		if (!canSubmit || selectedId === null) return;
		saving = true;
		try {
			await onUpdate(selectedId, buildWorkspacePayload(form));
		} finally {
			saving = false;
		}
	}

	async function removeSelected() {
		if (!selected) return;
		const ok = await onDelete(selected);
		if (ok) backToGrid();
	}
</script>

<div class="projects">
	{#if mode === 'grid'}
		<header class="head">
			<h1 class="title">프로젝트</h1>
			<div class="head-actions">
				<div class="search">
					<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
					<input type="text" placeholder="프로젝트 검색" bind:value={query} />
				</div>
				<Button variant="accent" size="sm" onclick={openCreate}>+ 새 프로젝트</Button>
			</div>
		</header>

		{#if workspaces.length === 0}
			<EmptyState
				icon="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
				headline="아직 프로젝트가 없어요"
				description="관련된 대화를 프로젝트로 묶고, 프로젝트 공통 지침으로 톤과 규칙을 한 번에 지정하세요."
			>
				{#snippet cta()}
					<Button variant="accent" size="sm" onclick={openCreate}>+ 새 프로젝트 만들기</Button>
				{/snippet}
			</EmptyState>
		{:else if filtered.length === 0}
			<p class="muted pad">검색 결과가 없습니다.</p>
		{:else}
			<div class="grid">
				{#each filtered as w (w.id)}
					<button type="button" class="card" onclick={() => openDetail(w)}>
						<span class="card-icon">
							<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" stroke-linejoin="round" /></svg>
						</span>
						<span class="card-name truncate">{w.name}</span>
						{#if w.description}
							<span class="card-desc">{w.description}</span>
						{/if}
						<span class="card-meta">
							<span class="badge">{countConversationsInWorkspace(conversations, w.id)}개 대화</span>
							{#if (w.instructions ?? '').trim()}
								<span class="badge badge-soft">지침</span>
							{/if}
						</span>
					</button>
				{/each}
			</div>
		{/if}
	{:else if selected}
		<header class="head">
			<button type="button" class="back" onclick={backToGrid} aria-label="목록으로">
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6" stroke-linecap="round" stroke-linejoin="round" /></svg>
			</button>
			<h1 class="title truncate">{selected.name}</h1>
			<div class="head-actions">
				<Button variant="accent" size="sm" onclick={() => onNewInProject(selected.id)}>
					+ 이 프로젝트에서 새 채팅
				</Button>
			</div>
		</header>

		<div class="detail-body">
			<section class="block">
				<h2 class="block-title">프로젝트 설정</h2>
				<form
					class="form"
					onsubmit={(e) => {
						e.preventDefault();
						void submitUpdate();
					}}
				>
					{@render fields()}
					<div class="form-actions">
						<Button variant="accent" type="submit" disabled={!canSubmit}>
							{saving ? '저장 중…' : '변경 저장'}
						</Button>
					</div>
				</form>
			</section>

			<section class="block">
				<h2 class="block-title">소속 대화 <span class="count">{projectConvs.length}</span></h2>
				{#if projectConvs.length === 0}
					<p class="muted">아직 이 프로젝트에 배정된 대화가 없습니다.</p>
				{:else}
					<div class="conv-list">
						{#each projectConvs as conv (conv.id)}
							<div class="conv-row">
								<button type="button" class="conv-open" onclick={() => onOpenConversation(conv)}>
									<span class="truncate">{conv.title || '새 대화'}</span>
								</button>
								<button
									type="button"
									class="conv-unassign"
									onclick={() => onAssign(conv, null)}
									title="프로젝트에서 해제"
									aria-label="프로젝트에서 해제"
								>
									<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" /></svg>
								</button>
							</div>
						{/each}
					</div>
				{/if}

				{#if assignable.length > 0}
					<label class="assign">
						<span class="assign-lbl">대화 배정</span>
						<select
							value=""
							onchange={(e) => {
								const id = e.currentTarget.value;
								if (!id) return;
								const conv = conversations.find((c) => c.id === id);
								if (conv && selected) onAssign(conv, selected.id);
								e.currentTarget.value = '';
							}}
						>
							<option value="">대화 선택…</option>
							{#each assignable as conv (conv.id)}
								<option value={conv.id}>{conv.title || '새 대화'}</option>
							{/each}
						</select>
					</label>
				{/if}
			</section>

			<section class="block">
				<Button variant="danger-outline" size="sm" onclick={removeSelected}>프로젝트 삭제</Button>
				<p class="muted danger-hint">삭제해도 대화는 유지되며 미분류로 이동합니다.</p>
			</section>
		</div>
	{:else}
		<EmptyState
			icon="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
			headline="프로젝트를 찾을 수 없습니다"
			description="삭제되었거나 접근할 수 없는 프로젝트입니다."
		>
			{#snippet cta()}
				<Button variant="secondary" size="sm" onclick={backToGrid}>프로젝트 목록</Button>
			{/snippet}
		</EmptyState>
	{/if}
</div>

<CreateProjectDialog open={createDialogOpen} onClose={closeCreate} onCreate={createProject} />

{#snippet fields()}
	<label class="field">
		<span class="lbl">이름 <span class="req">*</span></span>
		<input class="inp" bind:value={form.name} maxlength="100" placeholder="프로젝트 이름" required />
	</label>
	<label class="field">
		<span class="lbl">설명</span>
		<input class="inp" bind:value={form.description} maxlength="500" placeholder="이 프로젝트에 대한 짧은 설명" />
	</label>
	<label class="field">
		<span class="lbl">공통 지침 <span class="hint">이 프로젝트의 모든 대화에 적용</span></span>
		<textarea class="inp ta" bind:value={form.instructions} rows="6" maxlength="20000" placeholder="예: 답변은 항상 한국어로, 코드에는 주석을 달아라."></textarea>
	</label>
{/snippet}

<style>
	.projects {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		background: var(--color-surface-base);
	}
	.head {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 1.1rem 1.4rem;
		border-bottom: 1px solid var(--color-line);
		position: sticky;
		top: 0;
		background: var(--color-surface-base);
		z-index: 1;
	}
	.title {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 650;
		color: var(--color-ink-0);
		min-width: 0;
	}
	.head-actions {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.4rem 0.6rem;
		border-radius: 0.55rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		color: var(--color-ink-2);
	}
	.search input {
		flex: 1;
		border: none;
		outline: none;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		min-width: 8rem;
	}
	.search input::placeholder {
		color: var(--color-ink-3);
	}
	.back {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border: none;
		border-radius: 0.5rem;
		background: transparent;
		color: var(--color-ink-2);
		cursor: pointer;
		transition: background 0.12s, color 0.12s;
		flex-shrink: 0;
	}
	.back:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 0.85rem;
		padding: 1.4rem;
	}
	.card {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.4rem;
		padding: 1rem;
		border-radius: 0.8rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		text-align: left;
		cursor: pointer;
		transition: border-color 0.15s, background 0.15s;
	}
	.card:hover {
		border-color: var(--color-line-2);
		background: var(--color-surface-sunken);
	}
	.card-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.2rem;
		height: 2.2rem;
		border-radius: 0.6rem;
		background: var(--color-surface-sunken);
		border: 1px solid var(--color-line);
		color: var(--color-ink-2);
	}
	.card-name {
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--color-ink-0);
		max-width: 100%;
	}
	.card-desc {
		font-size: 0.78rem;
		color: var(--color-ink-2);
		line-height: 1.4;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.card-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin-top: 0.2rem;
	}
	.badge {
		font-size: 0.68rem;
		font-weight: 550;
		padding: 0.12rem 0.45rem;
		border-radius: 999px;
		background: var(--color-surface-sunken);
		color: var(--color-ink-2);
		border: 1px solid var(--color-line);
	}
	.badge-soft {
		background: color-mix(in oklab, var(--color-accent) 14%, transparent);
		color: var(--color-accent);
		border-color: transparent;
	}
	.detail-body {
		display: flex;
		flex-direction: column;
		gap: 1.4rem;
		padding: 1.4rem;
		max-width: 44rem;
		width: 100%;
	}
	.block {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	.block-title {
		margin: 0;
		font-size: 0.85rem;
		font-weight: 650;
		color: var(--color-ink-1);
	}
	.count {
		color: var(--color-ink-2);
		font-weight: 550;
	}
	.form {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		min-width: 0;
	}
	.lbl {
		font-size: 0.75rem;
		font-weight: 550;
		color: var(--color-ink-2);
	}
	.hint {
		font-weight: 400;
		color: var(--color-ink-2);
	}
	.req {
		color: var(--color-state-danger);
	}
	.inp {
		width: 100%;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
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
		min-height: 6rem;
		line-height: 1.5;
		font-family: inherit;
	}
	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}
	.conv-list {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.conv-row {
		display: flex;
		align-items: center;
		border-radius: 0.55rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		transition: border-color 0.12s;
	}
	.conv-row:hover {
		border-color: var(--color-line-2);
	}
	.conv-open {
		flex: 1;
		min-width: 0;
		text-align: left;
		padding: 0.55rem 0.7rem;
		border: none;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		cursor: pointer;
	}
	.conv-open:hover {
		color: var(--color-ink-0);
	}
	.conv-unassign {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		margin-right: 0.2rem;
		border: none;
		border-radius: 0.45rem;
		background: transparent;
		color: var(--color-ink-2);
		cursor: pointer;
		transition: background 0.12s, color 0.12s;
		flex-shrink: 0;
	}
	.conv-unassign:hover {
		color: var(--color-state-danger);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
	}
	.assign {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.3rem;
	}
	.assign-lbl {
		font-size: 0.75rem;
		color: var(--color-ink-2);
	}
	.assign select {
		flex: 1;
		max-width: 20rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		padding: 0.4rem 0.55rem;
		font-size: 0.8rem;
		color: var(--color-ink-1);
		cursor: pointer;
	}
	.muted {
		font-size: 0.8rem;
		color: var(--color-ink-2);
	}
	.pad {
		padding: 1.4rem;
	}
	.danger-hint {
		margin: 0;
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
