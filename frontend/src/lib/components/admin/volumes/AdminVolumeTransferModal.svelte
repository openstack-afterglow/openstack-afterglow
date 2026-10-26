<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, projectSwitching } from '$lib/stores/auth';
	import { adminInventoryScope } from '$lib/stores/adminInventoryScope';
	import { adminVolumeTransfers as api, VolumeTransferError, type IssuedVolumeTransfer, type VolumeTransfer, type VolumeTransferLookup } from '$lib/api/adminVolumeTransfers';
	import AdminProjectPicker from '$lib/components/admin/domains/AdminProjectPicker.svelte';
	import { Alert, Button, Card, Field, FormModal, SelectInput, TextInput } from '$lib/components/ui';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';
	import { t as v } from '$lib/i18n/ns/volume';
	import type { AdminVolume } from '$lib/types/volume';

	let { volume, initialMode = 'create', onClose, onSuccess }: {
		volume: Pick<AdminVolume, 'id' | 'name' | 'status'> | null; initialMode?: 'create' | 'receive'; onClose: () => void; onSuccess: () => void;
	} = $props();
	const sourceId = untrack(() => volume?.id ?? '');
	let sourceReady = $state(untrack(() => volume?.status === 'available'));
	const id = $props.id();
	let mode = $state(untrack(() => initialMode));
	let targetDomainId = $state('');
	let targetProjectId = $state('');
	let targetProjectName = $state('');
	let issued = $state<IssuedVolumeTransfer | null>(null);
	let transferId = $state('');
	let key = $state('');
	let lookup = $state<VolumeTransferLookup | null>(null);
	let pending = $state<VolumeTransfer[]>([]);
	let busy = $state(false);
	let error = $state('');
	let copied = $state<'id' | 'key' | null>(null);
	let invalid = $state(false);
	let uncertain = $state(false);
	let closed = $state(false);
	let alive = true;
	let generation = 0;
	const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
	const scope = () => { const a = get(auth); return JSON.stringify([a.sessionId, !!a.token, a.userId, a.projectId, a.domainId, a.identityDomainId, a.isSystemAdmin, get(adminInventoryScope).revision]); };
	const openedScope = scope();
	function discard() { generation += 1; issued = null; key = ''; transferId = ''; lookup = null; pending = []; error = ''; copied = null; busy = false; }
	function invalidate() { invalid = true; discard(); }
	const unsubscribeAuth = auth.subscribe(() => { if (scope() !== openedScope) invalidate(); });
	const unsubscribeInventory = adminInventoryScope.subscribe(() => { if (scope() !== openedScope) invalidate(); });
	const unsubscribeSwitch = projectSwitching.subscribe(switching => { if (switching) invalidate(); });
	onDestroy(() => { alive = false; discard(); unsubscribeAuth(); unsubscribeInventory(); unsubscribeSwitch(); });
	$effect(() => { if ((volume?.id ?? '') !== sourceId) untrack(invalidate); });
	const allowed = $derived(!invalid && !closed && !!$auth.token && $auth.isSystemAdmin && !$projectSwitching);
	function start() {
		if (!allowed || busy) return null;
		busy = true; error = ''; copied = null;
		return { generation: ++generation, token: get(auth).token!, projectId: get(auth).projectId ?? undefined };
	}
	function current(request: { generation: number }) { return alive && !closed && !invalid && generation === request.generation && scope() === openedScope; }
	function fail(cause: unknown, fallback: string) {
		if (cause instanceof VolumeTransferError && cause.uncertain) { uncertain = true; error = t('volumeTransfer.uncertain'); }
		else if (cause instanceof VolumeTransferError && cause.status === 403) error = t('volumeTransfer.denied');
		else error = cause instanceof VolumeTransferError && cause.detail ? cause.detail : fallback;
	}
	function close() { if (busy) return; closed = true; discard(); onClose(); }
	function editId(event: Event) {
		transferId = (event.target as HTMLInputElement).value;
		generation += 1; lookup = null; key = ''; error = ''; copied = null;
	}
	async function search() {
		if (!uuid.test(transferId.trim())) { error = v('transferModal.exactIdRequired'); return; }
		const request = start(); if (!request) return;
		lookup = null;
		try { const result = await api.lookup(request, transferId.trim()); if (current(request)) lookup = result; }
		catch (cause) { if (current(request)) fail(cause, v('transferModal.lookupFailed')); }
		finally { if (current(request)) busy = false; }
	}
	async function create() {
		if (!sourceId || !sourceReady || issued || uncertain) return;
		const request = start(); if (!request) return;
		try {
			const result = await api.create(request, sourceId);
			if (!current(request)) return;
			issued = result; transferId = result.id; onSuccess();
			try {
				const found = await api.lookup(request, result.id);
				if (current(request)) lookup = found;
			} catch (cause) { if (current(request)) fail(cause, v('transferModal.lookupFailed')); }
		} catch (cause) { if (current(request)) fail(cause, v('transferModal.createFailed')); }
		finally { if (current(request)) busy = false; }
	}
	async function accept() {
		if (!lookup || lookup.id !== transferId.trim() || !targetDomainId || !targetProjectId || !targetProjectName || uncertain || !(issued?.auth_key || key).trim()) return;
		const request = start(); if (!request) return;
		const secret = issued?.auth_key || key;
		key = '';
		try {
			await api.accept(request, lookup.id, secret, targetDomainId, targetProjectId);
			if (!current(request)) return;
			busy = false; onSuccess(); close();
		} catch (cause) { if (current(request)) fail(cause, v('transferModal.acceptFailed')); }
		finally { if (current(request)) busy = false; }
	}
	async function recover() {
		if (!sourceId) return;
		const request = start(); if (!request) return;
		try { const rows = await api.pending(request, sourceId); if (current(request)) pending = rows; }
		catch (cause) { if (current(request)) fail(cause, v('transferModal.listFailed')); }
		finally { if (current(request)) busy = false; }
	}
	async function cancel(transfer: VolumeTransfer) {
		if (uncertain) return;
		const request = start(); if (!request) return;
		try {
			await api.cancel(request, transfer.id);
			if (!current(request)) return;
			issued = null; lookup = null; key = ''; transferId = ''; pending = []; sourceReady = true; onSuccess();
		} catch (cause) { if (current(request)) fail(cause, v('transferModal.cancelFailed')); }
		finally { if (current(request)) busy = false; }
	}
	async function copy(kind: 'id' | 'key') {
		if (!issued) return;
		const request = start(); if (!request) return;
		try { await navigator.clipboard.writeText(kind === 'id' ? issued.id : issued.auth_key); if (current(request)) copied = kind; }
		catch { if (current(request)) error = v('transferModal.copyFailed'); }
		finally { if (current(request)) busy = false; }
	}
</script>

<FormModal open={!closed} title={mode === 'receive' ? v('transferModal.receiveTitle') : t('volumeTransfer.title')} onClose={close} submitting={busy}>
	<div class="max-h-[60dvh] space-y-4 overflow-y-auto">
		{#if !allowed}<Alert tone="warning">{v('transferModal.scopeChanged')}</Alert>
		{:else}
			<Alert tone="info">{t('volumeTransfer.scopeHelp')}</Alert>
			{#if sourceId && !issued && !uncertain}
				<Field for={`${id}-mode`} label={t('volumeTransfer.mode')}>
					<SelectInput id={`${id}-mode`} value={mode} disabled={busy} onchange={(event) => { mode = (event.target as HTMLSelectElement).value as typeof mode; transferId = ''; key = ''; lookup = null; error = ''; }}><option value="create">{v('transferModal.createTitle')}</option><option value="receive">{v('transferModal.receiveTitle')}</option></SelectInput>
				</Field>
			{/if}
			{#if mode === 'create' && sourceId && !issued}
				<p class="break-all text-sm text-ink-0">{volume?.name || sourceId}</p>
				<p class="break-all font-mono text-xs text-ink-2">{sourceId}</p>
				<Button variant="primary" disabled={busy || uncertain || !sourceReady} onclick={create}>{v('transferModal.createTitle')}</Button>
				<Button variant="outline" disabled={busy} onclick={recover}>{t('volumeTransfer.recover')}</Button>
			{/if}
			{#if issued}
				<Alert tone="warning">{v('transferModal.createdHelp')}</Alert>
				<Card surface="sunken" padding="sm">
					<dl class="space-y-3 text-sm">
						<div><dt class="text-xs text-ink-2">{v('transferModal.idLabel')}</dt><dd class="break-all font-mono">{issued.id}</dd></div>
						<div><dt class="text-xs text-ink-2">{v('transferModal.authKeyLabel')}</dt><dd class="break-all font-mono">{issued.auth_key}</dd></div>
					</dl>
					<div class="mt-3 flex flex-wrap gap-2">
						<Button variant="outline" disabled={busy} onclick={() => copy('id')}>{copied === 'id' ? v('transferModal.copied') : v('transferModal.copyId')}</Button>
						<Button variant="outline" disabled={busy} onclick={() => copy('key')}>{copied === 'key' ? v('transferModal.copied') : v('transferModal.copyKey')}</Button>
					</div>
				</Card>
			{/if}
			{#if mode === 'receive' || issued}
				{#if !issued}<Field for={`${id}-transfer`} label={v('transferModal.idLabel')} help={v('transferModal.exactIdHelp')}><TextInput id={`${id}-transfer`} value={transferId} oninput={editId} disabled={busy} autocomplete="off" /></Field>{/if}
				{#if !lookup}<Button variant="outline" onclick={search} disabled={busy || !transferId.trim()}>{v('transferModal.search')}</Button>{/if}
				{#if lookup}
					<Card surface="sunken" padding="sm"><dl class="space-y-2 break-all text-sm">
						<div><dt class="text-xs text-ink-2">{v('transferModal.sourceDomain')}</dt><dd>{lookup.source_domain.name} · {lookup.source_domain.id}</dd></div>
						<div><dt class="text-xs text-ink-2">{v('transferModal.sourceProject')}</dt><dd>{lookup.source_project.name} · {lookup.source_project.id}</dd></div>
						<div><dt class="text-xs text-ink-2">{v('transferModal.volumeLabel')}</dt><dd>{lookup.volume_name || lookup.volume_id} · {v('transferModal.size', { size: lookup.size })}</dd></div>
					</dl></Card>
					<AdminProjectPicker domainId={targetDomainId} projectId={targetProjectId} selectProjectDomain disabled={busy || uncertain} excludedProjectIds={[lookup.source_project.id]} emptyProjectLabel={t('volumeTransfer.searchProject')} onchange={(domain, project, name) => { targetDomainId = domain; targetProjectId = project; targetProjectName = name; key = ''; error = ''; }} />
					{#if targetProjectId}<p class="break-all text-xs text-ink-2">{targetProjectName} · {targetDomainId} · {targetProjectId}</p>{/if}
					{#if !issued}<Field for={`${id}-key`} label={v('transferModal.authKeyLabel')}><TextInput id={`${id}-key`} type="password" bind:value={key} disabled={busy || uncertain} autocomplete="off" maxlength={512} /></Field>{/if}
					<Button variant="primary" disabled={busy || uncertain || !targetDomainId || !targetProjectId || !targetProjectName || !(issued?.auth_key || key).trim()} onclick={accept}>{v('transferModal.receiveTitle')}</Button>
				{/if}
			{/if}
			{#if pending.length}
				<Alert tone="warning">{t('volumeTransfer.recoveryHelp')}</Alert>
				<ResponsiveTable>
					{#snippet cards()}{#each pending as transfer (transfer.id)}<CompactResourceCard><p class="break-all font-mono text-xs">{transfer.id}</p><Button variant="danger" disabled={busy || uncertain} onclick={() => cancel(transfer)}>{v('transferModal.cancel')}</Button></CompactResourceCard>{/each}{/snippet}
					<table class="w-full text-sm"><thead><tr><th class="text-left">{v('transferModal.idLabel')}</th><th>{v('transferModal.cancel')}</th></tr></thead><tbody>{#each pending as transfer (transfer.id)}<tr><td class="break-all font-mono text-xs">{transfer.id}</td><td><Button variant="danger" disabled={busy || uncertain} onclick={() => cancel(transfer)}>{v('transferModal.cancel')}</Button></td></tr>{/each}</tbody></table>
				</ResponsiveTable>
			{/if}
		{/if}
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
	</div>
	{#snippet actions()}<Button variant="secondary" disabled={busy} onclick={close}>{v('transferModal.close')}</Button>{/snippet}
</FormModal>
