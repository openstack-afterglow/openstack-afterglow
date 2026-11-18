<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { chatDomainScope } from '$lib/stores/chatDomainScope';
	import { api, ApiError } from '$lib/api/client';
	import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
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
	import { resolveCatalogModel } from '$lib/api/modelCatalog';
	import { t } from '$lib/i18n/ns/chat-studio';

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
	let loadedAgentScope = $state(-1);
	const agentScope = $derived($chatDomainScope.revision);
	let loadGeneration = 0;
	let destroyed = false;
	onDestroy(() => { destroyed = true; });
	let mode = $state<'list' | 'form'>('list');
	let editingId = $state<number | null>(null);
	let form = $state<AgentForm>(emptyAgentForm());
	let saving = $state(false);

	async function load() {
		if (!token || !projectId || !$authReady || $projectSwitching || !$chatDomainScope.key) return;
		const requestScope = agentScope;
		const request = ++loadGeneration;
		const current = () => !destroyed && requestScope === agentScope && request === loadGeneration;
		const includePrivate = $serviceCapabilities('lumen-agents_editor');
		loading = true;
		try {
			const [ags, ms, ts] = await Promise.all([
				api.get<Agent[]>(`/api/v1/chat/agents${includePrivate ? '?include_private=true' : ''}`, token, projectId),
				api.get<AgentExtension[]>('/api/v1/chat/mcp-servers', token, projectId),
				api.get<AgentExtension[]>('/api/v1/chat/custom-tools', token, projectId)
			]);
			if (!current() || (includePrivate && $serviceDenials('lumen-agents_editor'))) return;
			agents = ags;
			mcps = ms;
			tools = ts;
			loadedAgentScope = requestScope;
		} catch {
			if (current()) toast.error(t('agentManager.loadFailed'));
		} finally {
			if (current()) loading = false;
		}
	}

	let openScope = -1;
	let includedPrivate = false;
	$effect(() => {
		const ready = $authReady && !$projectSwitching;
		const scope = agentScope;
		const granted = $serviceCapabilities('lumen-agents_editor');
		const denied = $serviceDenials('lumen-agents_editor');
		if (!open) { openScope = -1; return; }
		if (!ready) return;
		untrack(() => {
			if (openScope !== scope) {
				openScope = scope;
				mode = 'list';
				editingId = null;
				form = emptyAgentForm();
				agents = []; mcps = []; tools = []; saving = false;
			} else if (!(granted && !includedPrivate) && !(denied && includedPrivate)) return;
			if (denied) { agents = []; mode = 'list'; editingId = null; form = emptyAgentForm(); }
			includedPrivate = granted;
			void load();
		});
	});

	function startCreate() {
		if (!$serviceCapabilities('lumen-agents_editor')) return;
		form = emptyAgentForm();
		editingId = null;
		mode = 'form';
	}
	function startEdit(a: Agent) {
		if (!$serviceCapabilities('lumen-agents_editor')) return;
		form = agentToForm(a);
		editingId = a.id;
		mode = 'form';
	}

	async function submit() {
		if (!$serviceCapabilities('lumen-agents_editor')) return;
		if (!token || !projectId || !$authReady || $projectSwitching) return;
		const requestScope = agentScope;
		const current = () => !destroyed && requestScope === agentScope;
		saving = true;
		try {
			const selected = resolveCatalogModel(models, form.model_row_id, form.model_name);
			const payload = buildAgentPayload(selected ? { ...form, model_name: selected.model_name, model_row_id: selected.id } : form);
			if (editingId !== null && !selected && form.model_row_id !== null) {
				// Preserve an unavailable or ambiguous legacy pin when editing unrelated fields.
				delete payload.model_name;
				delete payload.model_row_id;
			}
			if (editingId !== null) {
				await api.patch(`/api/v1/chat/agents/${editingId}`, payload, token, projectId);
				if (!current()) return;
				toast.success(t('agentManager.updated'));
			} else {
				await api.post('/api/v1/chat/agents', payload, token, projectId);
				if (!current()) return;
				toast.success(t('agentManager.created'));
			}
			mode = 'list';
			await load();
			if (current()) onChanged?.();
		} catch (e) {
			if (current()) toast.error(e instanceof ApiError ? e.message : t('agentManager.saveFailed'));
		} finally {
			if (current()) saving = false;
		}
	}

	async function remove(a: Agent) {
		if (!token) return;
		const requestScope = agentScope;
		const current = () => !destroyed && requestScope === agentScope;
		if (!(await confirmDialog(t('agentManager.deleteConfirm', { name: a.name })))) return;
		if (!current() || !$authReady || $projectSwitching || !$serviceCapabilities('lumen-resources_admin')) return;
		try {
			await api.delete(`/api/v1/chat/agents/${a.id}`, token, projectId);
			if (!current()) return;
			await load();
			if (!current()) return;
			onChanged?.();
			toast.success(t('agentManager.deleted'));
		} catch {
			if (current()) toast.error(t('agentManager.deleteFailed'));
		}
	}
</script>

<Modal {open} {onClose} ariaLabel={t('agentManager.title')}>
	<div class="panel">
		<header class="head">
			<div class="head-title">
				{#if mode === 'form'}
					<button type="button" class="back" onclick={() => (mode = 'list')} aria-label={t('agentManager.backToList')}>
						<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6" stroke-linecap="round" stroke-linejoin="round" /></svg>
					</button>
					<h2>{editingId !== null ? t('agentManager.editTitle') : t('agentManager.createTitle')}</h2>
				{:else}
					<h2>{t('agentManager.myAgents')}</h2>
				{/if}
			</div>
			<button type="button" class="close" onclick={onClose} aria-label={t('agentManager.close')}>
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" /></svg>
			</button>
		</header>

		<div class="body">
			<LumenPermissionNotice leaves={['lumen-agents_editor', 'lumen-resources_admin']} />
			{#if mode === 'form'}
				<AgentBuilderForm
					bind:form
					{models}
					{mcps}
					{tools}
					editing={editingId !== null}
					saving={saving}
					disabled={!$serviceCapabilities('lumen-agents_editor')}
					onSubmit={submit}
					onCancel={() => (mode = 'list')}
				/>
			{:else if loading && loadedAgentScope !== agentScope}
				<LoadingState label={t('agentManager.loading')} />
			{:else}
				{#if loading}<LoadingState variant="inline" label={t('agentManager.loading')} />{/if}
				<div class="list-head">
					<span class="muted">{t('agentManager.count', { count: agents.length })}</span>
					<Button variant="accent" size="sm" disabled={!$serviceCapabilities('lumen-agents_editor')} onclick={startCreate}>{t('agentManager.create')}</Button>
				</div>
				{#if agents.length === 0}
					<div class="empty-box">
						<p>{t('agentManager.empty')}</p>
						<p class="muted">{t('agentManager.emptyHint')}</p>
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
											<span class="vis-badge">{t('agentManager.publicCloneCount', { count: a.clone_count ?? 0 })}</span>
										{/if}
									</div>
									{#if a.description}<div class="desc truncate">{a.description}</div>{/if}
								</div>
								<div class="card-actions">
									<button type="button" class="act" disabled={!$serviceCapabilities('lumen-agents_editor')} onclick={() => startEdit(a)} title={t('agentManager.edit')} aria-label={t('agentManager.edit')}>
										<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" stroke-linecap="round" stroke-linejoin="round" /></svg>
									</button>
									<button type="button" class="act danger" disabled={!$serviceCapabilities('lumen-resources_admin')} onclick={() => remove(a)} title={t('agentManager.delete')} aria-label={t('agentManager.delete')}>
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
		box-shadow: var(--shadow-restraint);
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
		color: var(--color-ink-2);
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
		color: var(--color-ink-2);
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
		color: var(--color-ink-2);
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
		color: var(--color-ink-2);
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
