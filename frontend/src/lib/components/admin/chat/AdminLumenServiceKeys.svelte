<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { currentBillingSession, lumenBrowserPath, type ServiceKey, type ServiceKeyInventory } from '$lib/api/chatDomainBilling';
	import { t } from '$lib/i18n/ns/chat-settings';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';

	let { scopeKey }: { scopeKey: string } = $props();
	const id = $props.id();
	const path = `${lumenBrowserPath}/admin/service-keys`;
	let alive = true;
	onDestroy(() => { alive = false; });
	let filter = $state('');
	let verifiedFilter = $state('');
	let rows = $state<ServiceKey[]>([]);
	let next = $state<number | null>(null);
	let loaded = $state(false);
	let loading = $state(false);
	let error = $state('');
	let denied = $state(false);

	const session = () => alive ? currentBillingSession(scopeKey, 'admin') : null;
	async function load(domain: string, before: number | null = null) {
		const owner = session();
		if (!owner || loading || denied) return;
		loading = true;
		error = '';
		const params = new URLSearchParams({ limit: '50' });
		if (domain) params.set('owner_domain_id', domain);
		if (before !== null) params.set('before_id', String(before));
		try {
			const result = await api.get<ServiceKeyInventory>(`${path}?${params}`, owner.token, owner.projectId, { cache: 'no-store', suppressAuthRedirect: true });
			if (!session()) return;
			const visible = result.items.filter((row) => row.key_kind === 'service' && (!domain || row.owner_domain_id === domain));
			rows = before === null ? visible : [...rows, ...visible];
			next = result.next_before_id;
			verifiedFilter = domain;
			loaded = true;
		} catch (cause) {
			if (!session()) return;
			if (cause instanceof ApiError && cause.status === 403) { denied = true; rows = []; }
			else error = t('apiKeys.toast.loadFailed');
		} finally {
			if (session()) loading = false;
		}
	}
	onMount(() => { void load(''); });
</script>

{#if denied}
	<Alert flat tone="danger">{t('domainBilling.adminDenied')}</Alert>
{:else}
	<form class="mb-4 flex flex-wrap items-end gap-2" role="search" aria-label={t('domainBilling.inventoryTitle')} onsubmit={(event) => { event.preventDefault(); void load(filter.trim()); }}>
		<div class="w-full sm:w-72">
			<Field for={`${id}-domain`} label={t('domainBilling.domainId')}>
				<TextInput id={`${id}-domain`} bind:value={filter} type="search" maxlength={64} disabled={loading} />
			</Field>
		</div>
		<Button variant="secondary" type="submit" disabled={loading}>{t('domainBilling.filter')}</Button>
	</form>
	{#if error}<Alert class="mb-3" flat tone="danger">{error}</Alert>{/if}
	{#if loading}<LoadingState variant="inline" label={t('apiKeys.loading')} />{/if}
	{#if loaded && rows.length === 0}<p class="text-sm text-ink-2">{t('apiKeys.serviceEmpty')}</p>{/if}
	{#if rows.length > 0}
		<ul class="divide-y divide-line border-y border-line">
			{#each rows as row (row.id)}
				<li class="grid gap-2 py-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
					<div class="min-w-0">
						<h2 class="break-words text-sm font-semibold text-ink-1">{row.name || t('apiKeys.unnamed')}</h2>
						<code class="break-all text-xs text-ink-2">{row.key_prefix}…</code>
					</div>
					<div class="min-w-0">
						<p class="text-xs text-ink-2">{t('domainBilling.domainId')}</p>
						<code class="break-all text-xs text-ink-1">{row.owner_domain_id}</code>
					</div>
					<div class="min-w-0">
						<p class="text-xs text-ink-2">{t('domainBilling.creator')}</p>
						<code class="break-all text-xs text-ink-1">{row.created_by_user_id ?? t('domainBilling.unavailable')}</code>
					</div>
					<div class="min-w-0">
						<Pill>{t(!row.is_active ? 'apiKeys.revoked' : row.expires_at && Date.parse(row.expires_at) <= Date.now() ? 'apiKeys.expired' : 'domainBilling.active')}</Pill>
						{#if row.last_used_at}<p class="mt-1 text-xs text-ink-2">{t('apiKeys.lastUsed', { date: new Date(row.last_used_at).toLocaleString(intlLocale()) })}</p>{/if}
					</div>
				</li>
			{/each}
		</ul>
	{/if}
	{#if next !== null}
		<Button class="mt-3" variant="secondary" disabled={loading} onclick={() => load(verifiedFilter, next)}>{t('domainBilling.loadMore')}</Button>
	{/if}
{/if}
