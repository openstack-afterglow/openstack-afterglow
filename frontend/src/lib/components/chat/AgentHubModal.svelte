<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { isAvatarUrl, type Agent } from '$lib/api/chatAgents';

	interface Props {
		open: boolean;
		onClose: () => void;
		onCloned?: () => void;
	}
	let { open, onClose, onCloned }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let query = $state('');
	let agents = $state<Agent[]>([]);
	let loading = $state(true);
	let cloningId = $state<number | null>(null);
	let debounce: ReturnType<typeof setTimeout> | null = null;

	async function load() {
		if (!token) return;
		loading = true;
		try {
			const q = query.trim();
			const path = `/api/v1/chat/agents/hub?limit=50${q ? `&query=${encodeURIComponent(q)}` : ''}`;
			agents = await api.get<Agent[]>(path, token, projectId);
		} catch {
			toast.error('허브를 불러오지 못했습니다');
		} finally {
			loading = false;
		}
	}

	// 열릴 때 초기 로드
	$effect(() => {
		if (open) {
			query = '';
			void load();
		}
	});

	function onQueryInput() {
		if (debounce) clearTimeout(debounce);
		debounce = setTimeout(() => void load(), 300);
	}

	async function clone(a: Agent) {
		if (!token) return;
		cloningId = a.id;
		try {
			await api.post(`/api/v1/chat/agents/${a.id}/clone`, {}, token, projectId);
			toast.success(`'${a.name}' 을(를) 내 에이전트로 받아왔습니다`);
			onCloned?.();
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '복제에 실패했습니다');
		} finally {
			cloningId = null;
		}
	}

	function snippet(instr: string | null | undefined): string {
		if (!instr) return '';
		const s = instr.trim();
		return s.length > 140 ? `${s.slice(0, 140)}…` : s;
	}
</script>

<Modal {open} {onClose} ariaLabel="에이전트 허브">
	<div class="panel">
		<header class="head">
			<h2>에이전트 허브</h2>
			<button type="button" class="close" onclick={onClose} aria-label="닫기">
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" /></svg>
			</button>
		</header>

		<div class="search">
			<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
			<input bind:value={query} oninput={onQueryInput} placeholder="공개 에이전트 검색" />
		</div>

		<div class="body">
			{#if loading}
				<p class="muted">불러오는 중…</p>
			{:else if agents.length === 0}
				<div class="empty-box">
					<p>공개된 에이전트가 없습니다.</p>
					<p class="muted">{query.trim() ? '검색어를 바꿔보세요.' : '첫 공개 에이전트를 만들어보세요.'}</p>
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
									<span class="clones" title="복제 수">
										<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
										{a.clone_count ?? 0}
									</span>
								</div>
								{#if a.description}<div class="desc truncate">{a.description}</div>{/if}
								{#if a.instructions}<div class="preview">{snippet(a.instructions)}</div>{/if}
							</div>
							<div class="card-side">
								{#if a.is_owner}
									<span class="mine">내 에이전트</span>
								{:else}
									<Button variant="secondary" size="sm" disabled={cloningId === a.id} onclick={() => clone(a)}>
										{cloningId === a.id ? '받는 중…' : '받아오기'}
									</Button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
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
		transition: background 0.12s, color 0.12s;
	}
	.close:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0.9rem 1.1rem 0;
		padding: 0.5rem 0.7rem;
		border-radius: 0.55rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-3);
	}
	.search input {
		flex: 1;
		min-width: 0;
		border: none;
		outline: none;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
	}
	.search input::placeholder {
		color: var(--color-ink-3);
	}
	.body {
		padding: 0.9rem 1.1rem 1.1rem;
		overflow-y: auto;
	}
	.muted {
		font-size: 0.8rem;
		color: var(--color-ink-3);
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
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.75rem 0.85rem;
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
	.clones {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		font-size: 0.7rem;
		color: var(--color-ink-3);
	}
	.desc {
		font-size: 0.78rem;
		color: var(--color-ink-2);
		margin-top: 0.1rem;
	}
	.preview {
		margin-top: 0.35rem;
		font-size: 0.75rem;
		line-height: 1.5;
		color: var(--color-ink-3);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.card-side {
		flex-shrink: 0;
		display: flex;
		align-items: center;
	}
	.mine {
		font-size: 0.72rem;
		color: var(--color-ink-3);
		padding: 0.2rem 0.5rem;
		border-radius: 999px;
		border: 1px solid var(--color-line);
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
