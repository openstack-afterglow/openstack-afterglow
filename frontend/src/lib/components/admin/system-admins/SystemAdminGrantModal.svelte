<script lang="ts">
	import { untrack } from 'svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { domainsApi, domainPath, type AdminDomain } from '$lib/api/domains';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as domainT } from '$lib/i18n/ns/domain-admin';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	let {
		onClose,
		onGranted,
	}: {
		onClose: () => void;
		onGranted: () => void;
	} = $props();

	interface User {
		id: string;
		name: string;
		email: string;
		enabled: boolean;
	}

	const id = $props.id();
	let domains = $state<AdminDomain[]>([]);
	let domainId = $state('');
	let loadingDomains = $state(true);
	let domainsError = $state('');
	let loadedAuthority = $state('');
	let allUsers = $state<User[]>([]);
	let query = $state('');
	let loadingUsers = $state(false);
	let usersError = $state('');
	let nextMarker = $state<string | null>(null);
	let granting = $state(false);
	let grantError = $state('');
	let domainsGeneration = 0;
	let usersGeneration = 0;
	let grantGeneration = 0;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const authority = $derived(JSON.stringify([token, projectId]));
	const domainsReady = $derived(loadedAuthority === authority && !loadingDomains && !domainsError);
	const selectedDomain = $derived(domainsReady ? domains.find(domain => domain.id === domainId) : undefined);
	const filtered = $derived(
		query.trim()
			? allUsers.filter(user => `${user.name} ${user.email ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()))
			: allUsers,
	);

	function resetUsers() {
		usersGeneration++;
		grantGeneration++;
		allUsers = [];
		query = '';
		nextMarker = null;
		usersError = '';
		grantError = '';
		loadingUsers = false;
		granting = false;
	}

	async function loadDomains() {
		const generation = ++domainsGeneration;
		const requestAuthority = authority;
		const requestToken = token;
		const requestProjectId = projectId;
		loadedAuthority = '';
		domains = [];
		domainId = '';
		resetUsers();
		loadingDomains = true;
		domainsError = '';
		try {
			const result = await domainsApi.list({ token: requestToken, projectId: requestProjectId });
			if (generation !== domainsGeneration || requestAuthority !== authority) return;
			domains = result.items;
			loadedAuthority = requestAuthority;
		} catch (error) {
			if (generation === domainsGeneration && requestAuthority === authority) {
				domainsError = error instanceof Error ? error.message : domainT('scope.loadFailed');
			}
		} finally {
			if (generation === domainsGeneration && requestAuthority === authority) loadingDomains = false;
		}
	}

	async function loadUsers(append = false) {
		if (!selectedDomain || loadingUsers) return;
		const requestDomainId = domainId;
		const requestAuthority = authority;
		const requestToken = token;
		const requestProjectId = projectId;
		const marker = append ? nextMarker : null;
		const generation = ++usersGeneration;
		const current = () => generation === usersGeneration && requestAuthority === authority && requestDomainId === domainId;
		loadingUsers = true;
		usersError = '';
		try {
			const params = new URLSearchParams({ limit: '100' });
			if (marker) params.set('marker', marker);
			const result = await api.get<{ items: User[]; next_marker: string | null }>(
				domainPath(`/api/v1/admin/users?${params}`, requestDomainId), requestToken, requestProjectId,
			);
			if (!current()) return;
			allUsers = append ? [...allUsers, ...result.items] : result.items;
			nextMarker = result.next_marker;
		} catch (error) {
			if (current()) usersError = error instanceof Error ? error.message : domainT('users.loadFailed');
		} finally {
			if (current()) loadingUsers = false;
		}
	}

	function selectDomain(value: string) {
		domainId = value;
		resetUsers();
		void loadUsers();
	}

	async function grant(user: User) {
		if (!selectedDomain || loadingUsers || usersError || granting || !allUsers.some(item => item.id === user.id)) return;
		const requestAuthority = authority;
		const requestDomainId = domainId;
		const generation = ++grantGeneration;
		const current = () => generation === grantGeneration && requestAuthority === authority && requestDomainId === domainId;
		granting = true;
		grantError = '';
		try {
			await api.post('/api/v1/admin/identity/system-roles/grant', { user_id: user.id }, token, projectId);
			if (!current()) return;
			onGranted();
			onClose();
		} catch (error) {
			if (current()) grantError = error instanceof Error ? error.message : t('systemGrant.failed');
		} finally {
			if (current()) granting = false;
		}
	}

	$effect(() => {
		authority;
		untrack(() => { void loadDomains(); });
		return () => { domainsGeneration++; usersGeneration++; grantGeneration++; };
	});
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
	role="dialog" aria-modal="true"
	tabindex="-1"
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 max-h-[88dvh] overflow-y-auto shadow-[var(--shadow-restraint)]"
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('systemGrant.title')}</h2>

		<Field for={`${id}-domain`} label={domainT('scope.domain')}>
			<SearchSelect id={`${id}-domain`} value={domainsReady ? domainId : ''} options={domainsReady ? domains.map(domain => ({ value: domain.id, label: domain.name, description: domain.id })) : []} loading={loadingDomains} disabled={!domainsReady} placeholder={domainT('scope.choose')} ariaLabel={domainT('scope.domain')} onchange={selectDomain} />
		</Field>
		{#if domainsError}
			<Alert tone="danger" class="my-3">{domainsError}</Alert>
			<Button variant="secondary" size="sm" onclick={loadDomains}>{domainT('actions.refresh')}</Button>
		{:else if !selectedDomain}
			<p class="my-3 text-sm text-ink-2" role="status">{loadingDomains ? domainT('state.loading') : domainT('scope.required')}</p>
		{/if}

		{#if selectedDomain}
		{#if grantError}<Alert tone="danger" class="my-3">{grantError}</Alert>{/if}
		{#if usersError}
			<Alert tone="danger" class="my-3">{usersError}</Alert>
			<Button variant="secondary" size="sm" onclick={() => loadUsers(!!nextMarker)}>{domainT('actions.refresh')}</Button>
		{/if}

		<input
			bind:value={query}
			type="text"
			placeholder={t('systemGrant.searchPlaceholder')}
			aria-label={t('systemGrant.searchPlaceholder')}
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm my-3"
		/>

		{#if granting}<div class="mb-3"><ActivityIndicator size="xs" label={t('systemGrant.granting')} /></div>{/if}
		<div aria-busy={granting || loadingUsers} class="overflow-y-auto max-h-72 rounded-lg border border-line-2">
			{#if loadingUsers && allUsers.length === 0}
				<div class="text-ink-2 text-sm px-4 py-6 text-center"><ActivityIndicator size="sm" label={t('systemGrant.loading')} /></div>
			{:else if !usersError && filtered.length === 0}
				<div class="text-ink-2 text-sm px-4 py-6 text-center">{t('systemGrant.empty')}</div>
			{:else}
        <ResponsiveTable>
          {#snippet cards()}
            {#each filtered as u (u.id)}
              <CompactResourceCard>
                <strong class="break-words text-sm">{u.name}</strong>
                <p class="break-all text-xs text-ink-2">{u.email || '-'}</p>
                {#snippet actions()}<Button variant="secondary" size="sm" disabled={granting || loadingUsers || !!usersError} onclick={() => grant(u)}>{domainT('systemGrant.grant')}</Button>{/snippet}
                {#snippet details()}<dl class="text-xs"><dt class="text-ink-2">{t('systemTable.userId')}</dt><dd class="break-all font-mono">{u.id}</dd></dl>{/snippet}
              </CompactResourceCard>
            {/each}
          {/snippet}
				<table class="w-full text-sm">
					<tbody>
						{#each filtered as u (u.id)}
							<tr class="border-b border-line/50 hover:bg-surface-sunken/50 transition-colors">
								<td class="px-4 py-2 text-ink-0 text-xs">{u.name}</td>
								<td class="px-4 py-2 text-ink-2 text-xs">{u.email || '-'}</td>
								<td class="px-4 py-2 text-ink-2 font-mono text-xs">{u.id.slice(0, 8)}</td>
								<td class="px-4 py-2"><Button variant="secondary" size="sm" disabled={granting || loadingUsers || !!usersError} onclick={() => grant(u)}>{domainT('systemGrant.grant')}</Button></td>
							</tr>
						{/each}
					</tbody>
				</table>
        </ResponsiveTable>
			{/if}
		</div>
		{#if nextMarker}
			<Alert tone="info" class="my-3">{domainT('systemGrant.partial')}</Alert>
			<Button variant="secondary" size="sm" disabled={loadingUsers || granting} onclick={() => loadUsers(true)}>
				{#if loadingUsers}<ActivityIndicator size="xs" />{/if}{domainT('systemGrant.loadMore')}
			</Button>
		{/if}
		{/if}

		<div class="flex justify-end mt-4">
			<button
				onclick={onClose}
				disabled={granting}
				class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg"
			>
				{t('systemGrant.cancel')}
			</button>
		</div>
	</div>
</div>
