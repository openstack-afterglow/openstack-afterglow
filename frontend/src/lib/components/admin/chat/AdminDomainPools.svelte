<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { currentBillingSession, displayDomainCredit, domainBillingErrorMessage, lumenBrowserPath, validDomainCredit, type DomainPool } from '$lib/api/chatDomainBilling';
	import { domainsApi, type AdminDomain } from '$lib/api/domains';
	import { clearPendingTopup, pendingTopups, savePendingTopup, type PendingTopup } from '$lib/api/topupRecovery';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { t } from '$lib/i18n/ns/chat-settings';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
	import DomainPoolMetrics from '$lib/components/chat/DomainPoolMetrics.svelte';

	let { scopeKey }: { scopeKey: string } = $props();
	const id = $props.id();
	const path = `${lumenBrowserPath}/admin/domain-pools`;
	let alive = true;
	onDestroy(() => { alive = false; });
	let pools = $state<DomainPool[] | null>(null);
	let domains = $state<AdminDomain[]>([]);
	let poolError = $state(false);
	let directoryError = $state(false);
	let loading = $state(false);
	let denied = $state(false);
	const rows = $derived.by(() => {
		const poolById = new Map(pools?.map((pool) => [pool.domain_id, pool]));
		const domainById = new Map(domains.map((domain) => [domain.id, domain]));
		const ids = new Set([...(poolById.keys()), ...Object.keys(pending), ...domains.filter((domain) => domain.enabled && domain.kind !== 'account').map((domain) => domain.id)]);
		return [...ids].map((domainId) => ({ domainId, name: domainById.get(domainId)?.name || domainId, pool: poolById.get(domainId) }));
	});
	type Row = (typeof rows)[number];
	let target = $state<{ domainId: string; name: string } | null>(null);
	let mode = $state<'topup' | 'edit'>('topup');
	let open = $state(false);
	let busy = $state(false);
	let amount = $state('');
	let note = $state('');
	let ceiling = $state('');
	let active = $state(true);
	let amountInput = $state<HTMLInputElement | null>(null);
	let ceilingInput = $state<HTMLInputElement | null>(null);
	let fieldError = $state('');
	let saveError = $state('');
	// Persisted per admin and domain; a retry reuses the exact recorded key and body.
	let pending = $state<Record<string, PendingTopup>>({});
	let rechecked = $state<Record<string, boolean>>({});
	let pendingError = $state<Record<string, string>>({});

	const session = () => alive ? currentBillingSession(scopeKey, 'admin') : null;
	function requireCurrent() {
		if (!session() || denied) throw new DOMException('Billing authority changed', 'AbortError');
	}
	const mutation = { replayOnUnauthorized: false, beforeDispatch: requireCurrent };

	async function load() {
		const owner = session();
		if (!owner || loading || denied) return;
		loading = true;
		poolError = false;
		directoryError = false;
		const [poolResult, directory] = await Promise.allSettled([
			api.get<{ items: DomainPool[] }>(path, owner.token, owner.projectId, { cache: 'no-store', suppressAuthRedirect: true }),
			domainsApi.list(owner, { refresh: true })
		]);
		if (!session()) return;
		loading = false;
		if (poolResult.status === 'fulfilled') pools = poolResult.value.items;
		else if (poolResult.reason instanceof ApiError && poolResult.reason.status === 403) { denied = true; pools = null; return; }
		else { poolError = true; pools = null; }
		if (directory.status === 'fulfilled') domains = directory.value.items;
		else { directoryError = true; domains = []; }
	}

	onMount(() => {
		const owner = session();
		if (owner) pending = Object.fromEntries(pendingTopups(owner.userId).map((record) => [record.domainId, record]));
		void load();
	});

	function start(row: Row, nextMode: typeof mode) {
		if (!session() || busy || denied || !pools || (nextMode === 'topup' && pending[row.domainId])) return;
		target = { domainId: row.domainId, name: row.name };
		mode = nextMode;
		amount = '';
		note = '';
		ceiling = row.pool?.admin_ceiling_credits ?? '';
		active = row.pool?.is_active ?? true;
		fieldError = '';
		saveError = '';
		open = true;
	}

	function apply(next: DomainPool, domainId: string) {
		if (next.domain_id !== domainId) throw new Error('Domain pool owner mismatch');
		pools = [...(pools ?? []).filter((pool) => pool.domain_id !== domainId), next];
	}

	function forget(record: PendingTopup) {
		const { [record.domainId]: _removed, ...rest } = pending;
		pending = rest;
		rechecked = { ...rechecked, [record.domainId]: false };
		pendingError = { ...pendingError, [record.domainId]: '' };
		clearPendingTopup(record);
	}

	// Lumen applies one Idempotency-Key at most once, so resending this record cannot double-credit.
	async function sendTopup(record: PendingTopup, resend = false): Promise<'applied' | 'rejected' | 'unsaved' | 'unknown' | 'stale'> {
		const owner = session();
		if (!owner || denied || owner.userId !== record.userId) return 'stale';
		// Without a durable record a lost reply could be resent under a new key after reload.
		if (!savePendingTopup(record)) {
			saveError = t('domainBilling.recoveryUnavailable');
			if (!open) toast.error(saveError);
			return 'unsaved';
		}
		pending = { ...pending, [record.domainId]: record };
		try {
			const next = await api.post<DomainPool>(`${path}/${encodeURIComponent(record.domainId)}/topups`,
				{ amount_credits: record.amount_credits, note: record.note }, owner.token, owner.projectId, { ...mutation, idempotencyKey: record.key });
			if (!session() || denied) return 'stale';
			apply(next, record.domainId);
			forget(record);
			toast.success(t('domainBilling.saved'));
			return 'applied';
		} catch (cause) {
			if (!session()) return 'stale';
			const status = cause instanceof ApiError ? cause.status : 0;
			if (status === 403) { denied = true; pools = null; open = false; }
			// A first send rejected by the client boundary never applied. A resend's rejection may
			// never have reached Lumen's idempotency check, so it says nothing about the first send;
			// only Lumen's own balance-overflow refusal proves the recorded key never committed.
			const overflow = cause instanceof ApiError && (cause.code ?? cause.message) === 'domain_credit_balance_overflow';
			if (resend ? overflow : status >= 400 && status < 500 && status !== 408 && status !== 429) {
				forget(record);
				saveError = domainBillingErrorMessage(cause) ?? t('domainBilling.saveFailed');
				if (!open) toast.error(saveError);
				return 'rejected';
			}
			pendingError = { ...pendingError, [record.domainId]: domainBillingErrorMessage(cause) ?? t('domainBilling.topupUnconfirmed') };
			return 'unknown';
		}
	}

	function confirmTopup(record: Pick<PendingTopup, 'domainId' | 'amount_credits' | 'note'>) {
		return confirmDialog(
			t('domainBilling.confirmTopup', { domain: record.domainId, amount: displayDomainCredit(record.amount_credits), note: record.note ?? t('domainBilling.noNote') }),
			{ confirmLabel: t('domainBilling.topup'), confirmVariant: 'accent' },
		);
	}

	async function retryPending(record: PendingTopup) {
		if (!session() || busy || denied) return;
		busy = true;
		try {
			if (await confirmTopup(record)) await sendTopup(record, true);
		} finally {
			if (session()) busy = false;
		}
	}

	async function recheck(domainId: string) {
		if (busy || loading) return;
		await load();
		if (session() && !poolError) rechecked = { ...rechecked, [domainId]: true };
	}

	async function discardPending(record: PendingTopup) {
		if (!session() || busy || !rechecked[record.domainId]) return;
		if (await confirmDialog(t('domainBilling.discardConfirm'), { confirmLabel: t('domainBilling.discardPending') }) && session()) forget(record);
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		const selection = target;
		if (!selection || !session() || busy || denied) return;
		const domainId = selection.domainId;
		const resource = `${path}/${encodeURIComponent(domainId)}`;
		const isTopup = mode === 'topup';
		const limit = ceiling.trim();
		const body = { amount_credits: amount.trim(), note: note.trim() || null };
		fieldError = '';
		saveError = '';
		if (isTopup ? !validDomainCredit(body.amount_credits, true) : !!limit && !validDomainCredit(limit)) {
			fieldError = t(isTopup ? 'domainBilling.invalidAmount' : 'domainBilling.invalidLimit');
			await tick();
			(isTopup ? amountInput : ceilingInput)?.focus();
			return;
		}
		busy = true;
		try {
			if (isTopup) {
				if (!(await confirmTopup({ domainId, ...body }))) return;
			}
			const owner = session();
			if (!owner || denied) return;
			if (isTopup) {
				const outcome = await sendTopup({ v: 1, userId: owner.userId, domainId, key: crypto.randomUUID(), ...body, created_at: new Date().toISOString() });
				// An unknown outcome is recovered from the domain row, never from a new draft.
				if (outcome !== 'rejected' && outcome !== 'unsaved') open = false;
				return;
			}
			const next = await api.patch<DomainPool>(resource, { admin_ceiling_credits: limit || null, is_active: active }, owner.token, owner.projectId, mutation);
			if (!session() || denied) return;
			apply(next, domainId);
			open = false;
			toast.success(t('domainBilling.saved'));
		} catch (cause) {
			if (!session()) return;
			if (cause instanceof ApiError && cause.status === 403) { denied = true; pools = null; open = false; return; }
			saveError = domainBillingErrorMessage(cause) ?? t('domainBilling.saveFailed');
		} finally {
			if (session()) busy = false;
		}
	}
</script>

{#if denied}
	<Alert flat tone="danger">{t('domainBilling.adminDenied')}</Alert>
{:else}
	{#if poolError || directoryError}
		<Alert class="mb-3" flat tone="danger">{t(poolError ? 'domainBilling.loadFailed' : 'domainBilling.directoryFailed')}</Alert>
	{/if}
	{#if Object.keys(pending).length}
		<Alert class="mb-3" flat tone="warning">{t('domainBilling.topupUnconfirmed')}</Alert>
	{/if}
	<Button class="mb-3" variant="secondary" size="sm" disabled={loading || busy} onclick={load}>{t('apiKeys.guide.reload')}</Button>
	{#if !pools && !poolError}
		<LoadingState label={t('domainBilling.loading')} />
	{:else if pools}
		{#if rows.length === 0}<p class="text-sm text-ink-2">{t('domainBilling.noPools')}</p>{/if}
		<div class="space-y-3">
			{#each rows as row (row.domainId)}
				<Card>
					<div class="mb-3 flex flex-wrap items-start justify-between gap-3">
						<div class="min-w-0">
							<h2 class="break-words text-base font-semibold text-ink-1">{row.name}</h2>
							{#if row.name !== row.domainId}<code class="break-all text-xs text-ink-2">{row.domainId}</code>{/if}
						</div>
						<div class="flex flex-wrap items-center gap-2">
							{#if row.pool}<Pill>{t(row.pool.is_active ? 'domainBilling.active' : 'domainBilling.inactiveLabel')}</Pill>{/if}
							<Button size="sm" variant="secondary" disabled={busy || !!pending[row.domainId]} onclick={() => start(row, 'topup')}>{t('domainBilling.topup')}</Button>
							<Button size="sm" variant="ghost" disabled={busy} onclick={() => start(row, 'edit')}>{t('domainBilling.editPool')}</Button>
						</div>
					</div>
					{#if pending[row.domainId]}
						{@const record = pending[row.domainId]}
						<Alert class="mb-3" flat tone="warning" title={t('domainBilling.pendingTopupTitle')}>
							<p>{t('domainBilling.pendingTopup', { amount: displayDomainCredit(record.amount_credits), note: record.note ?? t('domainBilling.noNote'), time: new Date(record.created_at).toLocaleString(intlLocale()) })}</p>
							{#if pendingError[row.domainId]}<p>{pendingError[row.domainId]}</p>{/if}
							{#if rechecked[row.domainId]}<p>{t('domainBilling.recheckHint')}</p>{/if}
						</Alert>
						<div class="mb-3 flex flex-wrap gap-2">
							<Button size="sm" variant="secondary" disabled={busy || loading} onclick={() => recheck(row.domainId)}>{t('domainBilling.recheck')}</Button>
							<Button size="sm" disabled={busy} onclick={() => retryPending(record)}>{t('domainBilling.resumeTopup')}</Button>
							<Button size="sm" variant="ghost" disabled={busy || !rechecked[row.domainId]} onclick={() => discardPending(record)}>{t('domainBilling.discardPending')}</Button>
						</div>
					{/if}
					{#if row.pool}<DomainPoolMetrics pool={row.pool} />
					{:else}<p class="text-sm text-ink-2">{t('domainBilling.notConfigured')}</p>{/if}
				</Card>
			{/each}
		</div>
	{/if}

	{#if target}
		<FormModal bind:open title={t(mode === 'topup' ? 'domainBilling.topup' : 'domainBilling.editPool')} submitting={busy}>
			<p class="mb-3 break-all text-sm text-ink-2">{target.name} <code>{target.domainId}</code></p>
			<form id={`${id}-submit`} class="space-y-3" method="post" aria-label={t(mode === 'topup' ? 'domainBilling.topup' : 'domainBilling.editPool')} onsubmit={submit}>
				{#if mode === 'topup'}
					<Field for={`${id}-amount`} label={t('domainBilling.amount')} error={fieldError || undefined}>
						<TextInput id={`${id}-amount`} bind:element={amountInput} bind:value={amount} inputmode="decimal" ariaInvalid={!!fieldError} disabled={busy} oninput={() => { fieldError = ''; }} />
					</Field>
					<Field for={`${id}-note`} label={t('domainBilling.note')}>
						<TextareaInput id={`${id}-note`} bind:value={note} maxlength={1000} disabled={busy} rows={3} />
					</Field>
				{:else}
					<Field for={`${id}-ceiling`} label={t('domainBilling.adminCeiling')} help={t('domainBilling.limitHelp')} error={fieldError || undefined}>
						<TextInput id={`${id}-ceiling`} bind:element={ceilingInput} bind:value={ceiling} inputmode="decimal" ariaInvalid={!!fieldError} disabled={busy} oninput={() => { fieldError = ''; }} />
					</Field>
					<label class="flex min-h-11 items-center gap-2 text-sm text-ink-1">
						<input type="checkbox" bind:checked={active} disabled={busy} /> {t('domainBilling.active')}
					</label>
				{/if}
				{#if saveError}<Alert flat tone="danger">{saveError}</Alert>{/if}
			</form>
			{#snippet actions()}
				<Button variant="secondary" onclick={() => { open = false; }} disabled={busy}>{t('apiKeys.cancel')}</Button>
				<Button type="submit" form={`${id}-submit`} disabled={busy} ariaBusy={busy}>{t(mode === 'edit' ? 'apiKeys.save' : 'domainBilling.reviewTopup')}</Button>
			{/snippet}
		</FormModal>
	{/if}
{/if}
