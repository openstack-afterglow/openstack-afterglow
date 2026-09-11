<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import AgentBuilderForm from './AgentBuilderForm.svelte';
	import {
		agentToForm,
		buildAgentPayload,
		emptyAgentForm,
		isAvatarUrl,
		type Agent,
		type AgentExtension,
		type AgentForm
	} from '$lib/api/chatAgents';
	import type { AvailableModel } from '$lib/api/chatTree';

	interface Props {
		open: boolean;
		models: AvailableModel[];
		onClose: () => void;
		onChanged?: () => void;
	}
	let { open, models, onClose, onChanged }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let agents = $state<Agent[]>([]);
	let mcps = $state<AgentExtension[]>([]);
	let tools = $state<AgentExtension[]>([]);
	let loading = $state(true);
	let mode = $state<'list' | 'form'>('list');
	let editingId = $state<number | null>(null);
	let form = $state<AgentForm>(emptyAgentForm());
	let saving = $state(false);

	async function load() {
		if (!token) return;
		loading = true;
		try {
			const [ags, ms, ts] = await Promise.all([
				api.get<Agent[]>('/api/v1/chat/agents', token, projectId),
				api.get<AgentExtension[]>('/api/v1/chat/mcp-servers', token, projectId),
				api.get<AgentExtension[]>('/api/v1/chat/custom-tools', token, projectId)
			]);
			agents = ags;
			mcps = ms;
			tools = ts;
		} catch {
			toast.error('에이전트 목록을 불러오지 못했습니다');
		} finally {
			loading = false;
		}
	}

	// 모달이 열릴 때 로드하고 목록 뷰로 초기화
	$effect(() => {
		if (open) {
			mode = 'list';
			editingId = null;
			void load();
		}
	});

	function startCreate() {
		form = emptyAgentForm();
		editingId = null;
		mode = 'form';
	}
	function startEdit(a: Agent) {
		form = agentToForm(a);
		editingId = a.id;
		mode = 'form';
	}

	async function submit() {
		if (!token) return;
		saving = true;
		try {
			const payload = buildAgentPayload(form);
			if (editingId !== null) {
				await api.patch(`/api/v1/chat/agents/${editingId}`, payload, token, projectId);
				toast.success('에이전트를 수정했습니다');
			} else {
				await api.post('/api/v1/chat/agents', payload, token, projectId);
				toast.success('에이전트를 생성했습니다');
			}
			mode = 'list';
			await load();
			onChanged?.();
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '저장에 실패했습니다');
		} finally {
			saving = false;
		}
	}

	async function remove(a: Agent) {
		if (!token) return;
		if (!(await confirmDialog(`'${a.name}' 에이전트를 삭제하시겠습니까?`))) return;
		try {
			await api.delete(`/api/v1/chat/agents/${a.id}`, token, projectId);
			await load();
			onChanged?.();
			toast.success('삭제했습니다');
		} catch {
			toast.error('삭제에 실패했습니다');
		}
	}
</script>

<Modal {open} {onClose} ariaLabel="에이전트 관리">
	<div class="panel">
		<header class="head">
			<div class="head-title">
				{#if mode === 'form'}
					<button type="button" class="back" onclick={() => (mode = 'list')} aria-label="목록으로">
						<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6" stroke-linecap="round" stroke-linejoin="round" /></svg>
					</button>
					<h2>{editingId !== null ? '에이전트 편집' : '새 에이전트'}</h2>
				{:else}
					<h2>내 에이전트</h2>
				{/if}
			</div>
			<button type="button" class="close" onclick={onClose} aria-label="닫기">
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" /></svg>
			</button>
		</header>

		<div class="body">
			{#if mode === 'form'}
				<AgentBuilderForm
					bind:form
					{models}
					{mcps}
					{tools}
					editing={editingId !== null}
					{saving}
					onSubmit={submit}
					onCancel={() => (mode = 'list')}
				/>
			{:else if loading}
				<p class="muted">불러오는 중…</p>
			{:else}
				<div class="list-head">
					<span class="muted">{agents.length}개</span>
					<Button variant="accent" size="sm" onclick={startCreate}>+ 새 에이전트</Button>
				</div>
				{#if agents.length === 0}
					<div class="empty-box">
						<p>아직 에이전트가 없습니다.</p>
						<p class="muted">자주 쓰는 프롬프트·모델·도구를 묶어 에이전트로 저장하세요.</p>
					</div>
				{:else}
					<div class="cards">
						{#each agents as a (a.id)}
							<div class="card">
								<span class="avatar">
									{#if isAvatarUrl(a.avatar)}
										<img src={a.avatar} alt="" />
									{:else}
										{a.avatar || '🤖'}
									{/if}
								</span>
								<div class="card-main">
									<div class="card-title">
										<span class="name truncate">{a.name}</span>
										{#if a.visibility === 'public'}
											<span class="vis-badge">공개 · {a.clone_count ?? 0}</span>
										{/if}
									</div>
									{#if a.description}<div class="desc truncate">{a.description}</div>{/if}
								</div>
								<div class="card-actions">
									<button type="button" class="act" onclick={() => startEdit(a)} title="편집" aria-label="편집">
										<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" stroke-linecap="round" stroke-linejoin="round" /></svg>
									</button>
									<button type="button" class="act danger" onclick={() => remove(a)} title="삭제" aria-label="삭제">
										<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" stroke-linecap="round" stroke-linejoin="round" /></svg>
									</button>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			{/if}
		</div>
	</div>
</Modal>

<style>
	.panel {
		width: min(94vw, 46rem);
		max-height: 88vh;
		display: flex;
		flex-direction: column;
		border-radius: 0.9rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		box-shadow: 0 24px 64px rgba(0, 0, 0, 0.4);
		overflow: hidden;
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.9rem 1.1rem;
		border-bottom: 1px solid var(--color-line);
	}
	.head-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.head-title h2 {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.back,
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
		transition: background 0.12s, color 0.12s;
	}
	.back:hover,
	.close:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.body {
		padding: 1.1rem;
		overflow-y: auto;
	}
	.muted {
		font-size: 0.8rem;
		color: var(--color-ink-3);
	}
	.list-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}
	.empty-box {
		padding: 2.5rem 1rem;
		text-align: center;
	}
	.empty-box p {
		margin: 0.2rem 0;
		font-size: 0.85rem;
		color: var(--color-ink-1);
	}
	.cards {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.card {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.7rem 0.85rem;
		border-radius: 0.65rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
	}
	.avatar {
		flex-shrink: 0;
		width: 2.4rem;
		height: 2.4rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.6rem;
		background: var(--color-surface-sunken);
		border: 1px solid var(--color-line);
		font-size: 1.15rem;
		overflow: hidden;
	}
	.avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.card-main {
		flex: 1;
		min-width: 0;
	}
	.card-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.name {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-ink-0);
	}
	.vis-badge {
		flex-shrink: 0;
		font-size: 0.68rem;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		background: color-mix(in oklab, var(--color-accent) 14%, transparent);
		color: var(--color-accent);
	}
	.desc {
		font-size: 0.78rem;
		color: var(--color-ink-3);
		margin-top: 0.1rem;
	}
	.card-actions {
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
		transition: background 0.12s, color 0.12s;
	}
	.act:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.act.danger:hover {
		color: var(--color-state-danger);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
