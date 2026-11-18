<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { currentBillingSession, displayDomainCredit, domainBillingErrorMessage, lumenBrowserPath, validDomainCredit, type DomainPool } from '$lib/api/chatDomainBilling';
	import { domainsApi, type AdminDomain } from '$lib/api/domains';
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
		const ids = new Set([...(poolById.keys()), ...domains.filter((domain) => domain.enabled && domain.kind !== 'account').map((domain) => domain.id)]);
		return [...ids].map((domainId) => ({ domainId, name: domainById.get(domainId)?.name || domainId, pool: poolById.get(domainId) }));
	});
	type Row = (typeof rows)[number];
	type Topup = { amount_credits: string; note: string | null };
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
	// An unconfirmed response is retried only with this exact operation and header.
	let attempt = $state<{ key: string; body: Topup } | null>(null);

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

	onMount(() => { void load(); });

	function start(row: Row, nextMode: typeof mode) {
		if (!session() || busy || denied || !pools || attempt) return;
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

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		const selection = target;
		if (!selection || !session() || busy || denied) return;
		const domainId = selection.domainId;
		const resource = `${path}/${encodeURIComponent(domainId)}`;
		const isTopup = mode === 'topup';
		const limit = ceiling.trim();
		const body = attempt?.body ?? { amount_credits: amount.trim(), note: note.trim() || null };
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
				const message = t('domainBilling.confirmTopup', { domain: domainId, amount: displayDomainCredit(body.amount_credits), note: body.note ?? t('domainBilling.noNote') });
				if (!(await confirmDialog(message, { confirmLabel: t('domainBilling.topup'), confirmVariant: 'accent' }))) return;
			}
			const owner = session();
			if (!owner || denied) return;
			if (isTopup) attempt ??= { key: crypto.randomUUID(), body };
			const next = isTopup
				? await api.post<DomainPool>(`${resource}/topups`, body, owner.token, owner.projectId, { ...mutation, idempotencyKey: attempt!.key })
				: await api.patch<DomainPool>(resource, { admin_ceiling_credits: limit || null, is_active: active }, owner.token, owner.projectId, mutation);
			if (!session() || denied) return;
			apply(next, domainId);
			attempt = null;
			open = false;
			toast.success(t('domainBilling.saved'));
		} catch (cause) {
			if (!session()) return;
			if (cause instanceof ApiError && cause.status === 403) { denied = true; pools = null; attempt = null; open = false; return; }
			if (isTopup && cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 408) attempt = null;
			saveError = domainBillingErrorMessage(cause) ?? t(isTopup && attempt ? 'domainBilling.topupUnconfirmed' : 'domainBilling.saveFailed');
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
	{#if attempt && !open}
		<Alert class="mb-2" flat tone="warning">{t('domainBilling.topupUnconfirmed')}</Alert>
		<Button class="mb-3" variant="secondary" size="sm" onclick={() => { open = true; }}>{t('domainBilling.resumeTopup')}</Button>
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
							<Button size="sm" variant="secondary" disabled={busy || !!attempt} onclick={() => start(row, 'topup')}>{t('domainBilling.topup')}</Button>
							<Button size="sm" variant="ghost" disabled={busy || !!attempt} onclick={() => start(row, 'edit')}>{t('domainBilling.editPool')}</Button>
						</div>
					</div>
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
						<TextInput id={`${id}-amount`} bind:element={amountInput} bind:value={amount} inputmode="decimal" ariaInvalid={!!fieldError} disabled={busy || !!attempt} oninput={() => { fieldError = ''; }} />
					</Field>
					<Field for={`${id}-note`} label={t('domainBilling.note')}>
						<TextareaInput id={`${id}-note`} bind:value={note} maxlength={1000} disabled={busy || !!attempt} rows={3} />
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
				<Button type="submit" form={`${id}-submit`} disabled={busy} ariaBusy={busy}>{t(mode === 'edit' ? 'apiKeys.save' : attempt ? 'domainBilling.resumeTopup' : 'domainBilling.reviewTopup')}</Button>
			{/snippet}
		</FormModal>
	{/if}
{/if}
