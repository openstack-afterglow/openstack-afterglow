<script lang="ts">
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession, type IamInvitation } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { iamErrorMessage } from './iamError';
	import { enrollmentStatusLabel } from './enrollmentStatus';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	let live = true;
	let sequence = 0;
	let rows = $state<IamInvitation[]>([]);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let notice = $state('');
	function fail(cause: unknown) {
		if (!live) return;
		error = iamErrorMessage(cause, t('loadFailed'));
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	async function load() {
		const pending = ++sequence; loading = true; error = '';
		try { const result = await client.operations(); if (live && pending === sequence) rows = result.items; }
		catch (cause) { if (pending === sequence) fail(cause); }
		finally { if (live && pending === sequence) loading = false; }
	}
	async function recover(row: IamInvitation) {
		const pending = sequence;
		if (!live || blocked || busy || loading) return;
		if (!await confirmDialog(t('recoverConfirm', { email: row.email }), { confirmLabel: t('recover') })) return;
		if (!live || blocked || busy || loading || pending !== sequence || !rows.includes(row)) return;
		busy = true; error = ''; notice = '';
		try { await client.recoverOperation(row.id); if (live) { notice = t('recovered'); await load(); } }
		catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; sequence++; rows = []; });
</script>

<div class="space-y-4">
	<Alert tone="info">{t('recoveryHelp')}</Alert>
	<Button variant="secondary" disabled={busy || loading} onclick={load}>{t('refresh')}</Button>
	{#if loading || busy}<ActivityIndicator label={t('loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	<ResponsiveTable>
		{#snippet cards()}
			{#each rows as row (row.id)}<CompactResourceCard>
				<h3 class="text-sm font-medium break-all">{row.email}</h3><p class="text-xs">{enrollmentStatusLabel(row.status)} · <code>{row.kind}</code></p>
				{#snippet details()}<p class="text-xs">{t('created')}: {new Date(row.created_at).toLocaleString(intlLocale())}</p>{/snippet}
				{#snippet actions()}<Button variant="danger-outline" size="sm" disabled={blocked || busy || loading} onclick={() => recover(row)}>{t('recover')}</Button>{/snippet}
			</CompactResourceCard>{/each}
			{#if !loading && !error && !rows.length}<p class="text-sm text-ink-2">{t('emptyRecovery')}</p>{/if}
		{/snippet}
	<TableShell><table>
		<thead><tr><th>{t('email')}</th><th>{t('operationKind')}</th><th>{t('status')}</th><th>{t('created')}</th><th>{t('actions')}</th></tr></thead>
		<tbody>
			{#each rows as row (row.id)}<tr><td>{row.email}</td><td><code>{row.kind}</code></td><td>{enrollmentStatusLabel(row.status)}</td><td>{new Date(row.created_at).toLocaleString(intlLocale())}</td><td><Button variant="danger-outline" size="sm" disabled={blocked || busy || loading} onclick={() => recover(row)}>{t('recover')}</Button></td></tr>{/each}
			{#if !loading && !error && !rows.length}<tr><td colspan="5">{t('emptyRecovery')}</td></tr>{/if}
		</tbody>
	</table></TableShell>
	</ResponsiveTable>
</div>
