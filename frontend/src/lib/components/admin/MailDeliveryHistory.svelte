<script lang="ts">
	import { emailApi, type MailDelivery, type MailReceipt } from '$lib/api/email';
	import { createEmailOwner } from '$lib/utils/emailOwner';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/admin-email';
	import { formatIsoDateTime } from '$lib/utils/format';
	import { Alert, Button, Card } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	let { disabled = false, onbusy = (_busy: boolean) => {} }: { disabled?: boolean; onbusy?: (busy: boolean) => void } = $props();
	let items = $state<MailDelivery[]>([]), total = $state(0), offset = $state(0);
	let loading = $state(false), loaded = $state(false), error = $state('');
	let checking = $state<string | null>(null);
	let receipts = $state<Record<string, MailReceipt>>({});
	let receiptError = $state('');
	const blocked = $derived(disabled || loading || checking !== null || !$authReady || !$auth.token || !$auth.isSystemAdmin || $logoutInProgress || $projectSwitching);
	const owner = createEmailOwner(() => {
		items = []; total = 0; offset = 0; loading = false; loaded = false; error = ''; checking = null; receipts = {}; receiptError = ''; onbusy(false);
		void load(0);
	});
	async function load(next = offset) {
		const scope = owner.capture(); if (!scope || loading || checking) return;
		loading = true; error = '';
		try {
			const result = await emailApi.history(next, scope);
			if (scope.current()) { items = result.items; total = result.total; offset = next; loaded = true; }
		} catch { if (scope.current()) error = t('failed'); }
		finally { if (scope.current()) loading = false; }
	}
	async function receipt(id: string) {
		if (blocked) return;
		const scope = owner.capture(); if (!scope) return;
		checking = id; receiptError = ''; onbusy(true);
		try {
			const result = await emailApi.receipt(id, scope);
			if (scope.current()) receipts[id] = result;
		} catch { if (scope.current()) receiptError = t('failed'); }
		finally { if (scope.current()) { checking = null; onbusy(false); } }
	}
</script>
<Card padding="lg" class="space-y-4">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h2 class="text-base font-semibold text-ink-0">{t('history')}</h2>
		<Button variant="secondary" disabled={blocked} onclick={() => load()}>{t('refresh')}</Button>
	</div>
	<p class="text-sm text-ink-2">{t('proof')}</p>
	<p class="text-sm text-ink-2">{t('receiptHelp')}</p>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if receiptError}<Alert tone="danger">{receiptError}</Alert>{/if}
	{#if loading}<LoadingState variant="inline" label={t('loading')} />{/if}
	{#if loaded && !items.length}<p class="text-sm text-ink-2">{t('empty')}</p>{/if}
	<ul class="space-y-3" data-email-history>
		{#each items as item (item.id)}
			<li class="min-w-0 border-b border-line pb-3 space-y-2" data-delivery-id={item.id}>
				<div class="flex flex-wrap justify-between gap-2"><strong class="text-sm text-ink-0 [overflow-wrap:anywhere]">{item.subject}</strong><span class="text-sm text-ink-1">{t(`status.${item.status}`)}</span></div>
				<p class="text-sm text-ink-1 [overflow-wrap:anywhere]">{item.recipient_email}</p>
				<p class="text-xs font-mono text-ink-2 [overflow-wrap:anywhere]">{t('operation', { id: item.operation_id })}</p>
				<p class="text-xs text-ink-2 tabular-nums">{formatIsoDateTime(item.updated_at)}</p>
				{#if item.kind === 'test'}
					<Button variant="secondary" size="sm" disabled={blocked || (item.status !== 'accepted' && item.status !== 'unknown')} onclick={() => receipt(item.id)} ariaBusy={checking === item.id}>{t('receipt')}</Button>
					{#if receipts[item.id]}<Alert tone={receipts[item.id].status === 'confirmed' ? 'success' : 'info'}>{t(`status.${receipts[item.id].status}`)}</Alert>{/if}
				{/if}
			</li>
		{/each}
	</ul>
	<div class="flex flex-wrap items-center gap-3">
		<Button variant="secondary" disabled={blocked || offset === 0} onclick={() => load(Math.max(0, offset - 50))}>{t('previous')}</Button>
		<span class="text-sm text-ink-2 tabular-nums">{loaded ? `${items.length ? offset + 1 : 0}–${offset + items.length} / ${total}` : '—'}</span>
		<Button variant="secondary" disabled={blocked || !loaded || offset + items.length >= total} onclick={() => load(offset + 50)}>{t('next')}</Button>
	</div>
</Card>
