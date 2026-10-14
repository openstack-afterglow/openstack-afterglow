<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, canWrite, projectSwitching } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { t } from '$lib/i18n/ns/volume';
	import { Alert, Button, Card, Field, Modal, TextInput } from '$lib/components/ui';

	interface Transfer {
		id: string;
		name: string;
		volume_id: string;
		created_at: string | null;
	}
	interface IssuedTransfer extends Transfer { auth_key: string; }
	interface TransferLookup extends Transfer {
		volume_name: string;
		size: number;
		volume_type: string | null;
		status: 'awaiting-transfer';
		source_project: { id: string; name: string };
		source_domain: { id: string; name: string };
	}

	let { volumeId = '', volumeName = '', initialMode = 'create', onClose, onChanged, onTransferred }: {
		volumeId?: string;
		volumeName?: string;
		initialMode?: 'create' | 'receive' | 'list';
		onClose: () => void;
		onChanged?: () => void;
		onTransferred?: () => void;
	} = $props();

	const targetId = untrack(() => volumeId);
	const entryMode = untrack(() => initialMode);
	let issued = $state<IssuedTransfer | null>(null);
	let transferName = $state('');
	let transferId = $state('');
	let authKey = $state('');
	let result = $state<TransferLookup | null>(null);
	let transfers = $state<Transfer[]>([]);
	let busy = $state<'create' | 'lookup' | 'accept' | 'list' | 'cancel' | 'copy' | null>(null);
	let error = $state('');
	let copied = $state<'id' | 'key' | null>(null);
	let scopeChanged = $state(false);
	let closed = $state(false);
	let live = true;
	let generation = 0;
	const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
	const title = $derived(issued ? t('transferModal.createdTitle') : entryMode === 'create' ? t('transferModal.createTitle') : entryMode === 'receive' ? t('transferModal.receiveTitle') : t('transferModal.listTitle'));
	const allowed = $derived(!scopeChanged && !closed && $canWrite && !!$auth.token && !!$auth.projectId && !$projectSwitching);

	// Store subscriptions invalidate synchronously, including A → B → A transitions
	// occurring before Svelte effects flush. A mounted task never retargets itself.
	function scope() {
		const state = get(auth);
		return JSON.stringify([state.token, state.userId, state.projectId, state.canWrite]);
	}
	const openedScope = scope();
	function discard() {
		generation += 1;
		issued = null;
		result = null;
		authKey = '';
		transferId = '';
		transferName = '';
		transfers = [];
		copied = null;
		error = '';
		busy = null;
	}
	function invalidate() {
		scopeChanged = true;
		discard();
	}
	const unsubscribeAuth = auth.subscribe(() => { if (scope() !== openedScope) invalidate(); });
	let previousWrite = get(canWrite);
	const unsubscribeWrite = canWrite.subscribe((write) => {
		if (write !== previousWrite) invalidate();
		previousWrite = write;
	});
	const unsubscribeSwitch = projectSwitching.subscribe((switching) => { if (switching) invalidate(); });
	onDestroy(() => {
		live = false;
		discard();
		unsubscribeAuth();
		unsubscribeWrite();
		unsubscribeSwitch();
	});
	$effect(() => { if (volumeId !== targetId || initialMode !== entryMode) untrack(invalidate); });

	function start(operation: NonNullable<typeof busy>) {
		if (!allowed || busy) return null;
		const state = get(auth);
		const request = { generation: ++generation, token: state.token!, projectId: state.projectId! };
		busy = operation;
		error = '';
		copied = null;
		return request;
	}
	function current(request: { generation: number }) {
		return live && !closed && !scopeChanged && request.generation === generation && scope() === openedScope && get(canWrite) && !get(projectSwitching);
	}
	function close() {
		if (busy) return;
		closed = true;
		discard();
		onClose();
	}
	function failure(cause: unknown, fallback: 'transferModal.createFailed' | 'transferModal.acceptFailed' | 'transferModal.lookupFailed' | 'transferModal.listFailed' | 'transferModal.cancelFailed') {
		return cause instanceof ApiError ? cause.message : t(fallback);
	}
	function changeId(event: Event) {
		transferId = (event.target as HTMLInputElement).value;
		generation += 1;
		result = null;
		authKey = '';
		error = '';
		busy = null;
	}
	async function search() {
		if (!uuid.test(transferId.trim())) { error = t('transferModal.exactIdRequired'); return; }
		const request = start('lookup');
		if (!request) return;
		const id = transferId.trim();
		result = null;
		authKey = '';
		try {
			const found = await api.get<TransferLookup>(`/api/v1/volumes/transfer/${encodeURIComponent(id)}`, request.token, request.projectId);
			if (!current(request)) return;
			result = found;
		} catch (cause) {
			if (current(request)) error = cause instanceof ApiError && cause.status === 404 ? t('transferModal.notFound') : failure(cause, 'transferModal.lookupFailed');
		} finally {
			if (current(request)) busy = null;
		}
	}
	async function create() {
		if (!targetId) return;
		const request = start('create');
		if (!request) return;
		try {
			const created = await api.post<IssuedTransfer>(`/api/v1/volumes/${encodeURIComponent(targetId)}/transfer`, { name: transferName.trim() || null }, request.token, request.projectId);
			if (!current(request)) return;
			issued = created;
			onChanged?.(); // Refresh source inventory without dismissing its one-time key.
		} catch (cause) {
			if (current(request)) error = failure(cause, 'transferModal.createFailed');
		} finally {
			if (current(request)) busy = null;
		}
	}
	async function accept() {
		if (!result || result.id.toLowerCase() !== transferId.trim().toLowerCase() || !authKey.trim()) return;
		const request = start('accept');
		if (!request) return;
		const id = result.id;
		const key = authKey;
		authKey = '';
		try {
			await api.post(`/api/v1/volumes/transfer/${encodeURIComponent(id)}/accept`, { auth_key: key }, request.token, request.projectId);
			if (!current(request)) return;
			busy = null;
			onTransferred?.();
			close();
		} catch (cause) {
			if (!current(request)) return;
			if (cause instanceof ApiError && cause.status === 404) {
				result = null;
				error = t('transferModal.notFound');
			} else error = failure(cause, 'transferModal.acceptFailed');
		} finally {
			if (current(request)) busy = null;
		}
	}
	async function load() {
		const request = start('list');
		if (!request) return;
		try {
			const pending = await api.get<Transfer[]>('/api/v1/volumes/transfers', request.token, request.projectId);
			if (current(request)) transfers = pending;
		} catch (cause) {
			if (current(request)) error = failure(cause, 'transferModal.listFailed');
		} finally {
			if (current(request)) busy = null;
		}
	}
	async function cancel(id: string) {
		const request = start('cancel');
		if (!request) return;
		try {
			await api.delete(`/api/v1/volumes/transfer/${encodeURIComponent(id)}`, request.token, request.projectId);
			if (!current(request)) return;
			transfers = transfers.filter((transfer) => transfer.id !== id);
			onChanged?.();
		} catch (cause) {
			if (current(request)) error = failure(cause, 'transferModal.cancelFailed');
		} finally {
			if (current(request)) busy = null;
		}
	}
	async function copy(kind: 'id' | 'key') {
		if (!issued) return;
		const request = start('copy');
		if (!request) return;
		try {
			await navigator.clipboard.writeText(kind === 'id' ? issued.id : issued.auth_key);
			if (current(request)) copied = kind;
		} catch {
			if (current(request)) error = t('transferModal.copyFailed');
		} finally {
			if (current(request)) busy = null;
		}
	}
	$effect(() => { if (entryMode === 'list') untrack(() => { void load(); }); });
</script>

<Modal open={!closed} onClose={close} dismissible={!busy} ariaLabel={title}>
	<Card surface="modal" padding="none" class="flex max-h-[calc(100dvh-2rem)] w-[min(36rem,calc(100vw-2rem))] flex-col">
		<header class="shrink-0 border-b border-line p-4 sm:p-6">
			<h2 class="text-lg font-semibold text-ink-0">{title}</h2>
		</header>
		<div class="min-h-0 space-y-4 overflow-y-auto p-4 sm:p-6">
			{#if scopeChanged || !allowed}
				<Alert tone="warning">{t('transferModal.scopeChanged')}</Alert>
			{:else if issued}
				<Alert tone="warning">{t('transferModal.createdHelp')}</Alert>
				<dl class="space-y-3 text-sm">
					<div><dt class="text-xs text-ink-2">{t('transferModal.idLabel')}</dt><dd class="break-all font-mono">{issued.id}</dd></div>
					<div><dt class="text-xs text-ink-2">{t('transferModal.authKeyLabel')}</dt><dd class="break-all font-mono">{issued.auth_key}</dd></div>
				</dl>
				<div class="flex flex-wrap gap-2">
					<Button variant="outline" disabled={!!busy} onclick={() => copy('id')}>{copied === 'id' ? t('transferModal.copied') : t('transferModal.copyId')}</Button>
					<Button variant="outline" disabled={!!busy} onclick={() => copy('key')}>{copied === 'key' ? t('transferModal.copied') : t('transferModal.copyKey')}</Button>
				</div>
			{:else if entryMode === 'create'}
				<p class="text-sm text-ink-2">{t('transferModal.createHelp')}</p>
				<p class="break-words text-sm text-ink-0">{volumeName}</p>
				<p class="break-all font-mono text-xs text-ink-2">{targetId}</p>
				<Field label={t('transferModal.nameLabel')} for="transfer-name">
					<TextInput id="transfer-name" bind:value={transferName} disabled={!!busy} maxlength={255} />
				</Field>
			{:else if entryMode === 'receive'}
				<p class="text-sm text-ink-2">{t('transferModal.receiveHelp')}</p>
				<Card surface="sunken" padding="sm">
					<p class="text-xs text-ink-2">{t('transferModal.destination')}</p>
					<p class="break-words text-sm">{$auth.projectName || $auth.projectId}</p>
					<p class="break-all font-mono text-xs text-ink-2">{$auth.projectId}</p>
				</Card>
				<form onsubmit={(event) => { event.preventDefault(); void search(); }} class="space-y-2">
					<Field label={t('transferModal.idLabel')} for="transfer-id" help={t('transferModal.exactIdHelp')}>
						<TextInput id="transfer-id" value={transferId} oninput={changeId} autocomplete="off" disabled={!!busy && busy !== 'lookup'} />
					</Field>
					<Button type="submit" variant="outline" disabled={!!busy || !transferId.trim()}>{t('transferModal.search')}</Button>
				</form>
				{#if result}
					<Card surface="sunken" padding="sm">
						<dl class="space-y-3 text-sm">
							<div><dt class="text-xs text-ink-2">{t('transferModal.volumeLabel')}</dt><dd class="break-words">{result.volume_name || result.volume_id}</dd><dd class="break-all font-mono text-xs text-ink-2">{result.volume_id}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('transferModal.volumeInfo')}</dt><dd class="break-words">{t('transferModal.size', { size: result.size })} · {result.volume_type || '—'}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('transferModal.idLabel')}</dt><dd class="break-all font-mono text-xs">{result.id}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('transferModal.sourceDomain')}</dt><dd class="break-words">{result.source_domain.name}</dd><dd class="break-all font-mono text-xs text-ink-2">{result.source_domain.id}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('transferModal.sourceProject')}</dt><dd class="break-words">{result.source_project.name}</dd><dd class="break-all font-mono text-xs text-ink-2">{result.source_project.id}</dd></div>
						</dl>
					</Card>
					<Field label={t('transferModal.authKeyLabel')} for="transfer-key">
						<TextInput id="transfer-key" type="password" bind:value={authKey} autocomplete="off" maxlength={255} disabled={!!busy} />
					</Field>
				{/if}
			{:else if entryMode === 'list'}
				<p class="text-sm text-ink-2">{t('transferModal.listHelp')}</p>
				{#if !busy && !error && transfers.length === 0}<p class="text-sm text-ink-2">{t('transferModal.empty')}</p>{/if}
				{#each transfers as transfer (transfer.id)}
					<Card surface="sunken" padding="sm">
						<p class="break-words text-sm">{transfer.name}</p>
						<dl class="my-3 space-y-2 text-xs">
							<div><dt class="text-ink-2">{t('transferModal.idLabel')}</dt><dd class="break-all font-mono">{transfer.id}</dd></div>
							<div><dt class="text-ink-2">{t('transferModal.volumeLabel')}</dt><dd class="break-all font-mono">{transfer.volume_id}</dd></div>
						</dl>
						<Button variant="danger-outline" disabled={!!busy} onclick={() => cancel(transfer.id)} ariaLabel={t('transferModal.cancelNamed', { id: transfer.id })}>{t('transferModal.cancel')}</Button>
					</Card>
				{/each}
			{/if}
			{#if error}<Alert>{error}</Alert>{/if}
			{#if busy}<Alert tone="info">{t('transferModal.busy')}</Alert>{/if}
		</div>
		<footer class="flex shrink-0 flex-wrap justify-end gap-2 border-t border-line p-4">
			<Button variant="secondary" disabled={!!busy} onclick={close}>{t('transferModal.close')}</Button>
			{#if allowed && !issued}
				{#if entryMode === 'create'}
					<Button variant="primary" disabled={!!busy || !targetId} onclick={create}>{t('transferModal.createTitle')}</Button>
				{:else if entryMode === 'receive'}
					<Button variant="primary" disabled={!!busy || !result || !authKey.trim()} onclick={accept}>{t('transferModal.receiveTitle')}</Button>
				{:else}
					<Button variant="outline" disabled={!!busy} onclick={load}>{t('transferModal.refresh')}</Button>
				{/if}
			{/if}
		</footer>
	</Card>
</Modal>
