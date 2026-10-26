<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { Group, GroupMember, User } from '$lib/types/adminGroup';
	import type { AdminDomain } from '$lib/api/domains';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface Props {
		group: Group;
		expanded: boolean;
		members: GroupMember[];
		membersLoading: boolean;
		membersError?: string;
		usersError?: string;
		usersLoading: boolean;
		allUsers: User[];
		userDomainId?: string;
		sourceGeneration?: number;
		sourceDomains?: AdminDomain[];
		sourceDomainsLoading?: boolean;
		sourceDomainsError?: string;
		onSelectUserDomain?: (id: string) => Promise<void>;
		onRetrySourceDomains?: () => Promise<void>;
		addError: string;
		addSaving: boolean;
		onToggleMembers: () => void;
		onEdit: () => void;
		onDelete: () => void;
		onAddMember: (userId: string) => Promise<boolean>;
		onRemoveMember: (userId: string) => Promise<void>;
		onRetryUsers: () => Promise<void>;
	}

	let {
		group,
		expanded,
		members,
		membersLoading,
		membersError = '',
		usersError = '',
		usersLoading,
		allUsers,
		userDomainId = '',
		sourceGeneration = 0,
		sourceDomains = [],
		sourceDomainsLoading = false,
		sourceDomainsError = '',
		onSelectUserDomain,
		onRetrySourceDomains,
		addError,
		addSaving,
		onToggleMembers,
		onEdit,
		onDelete,
		onAddMember,
		onRemoveMember,
		onRetryUsers
	}: Props = $props();

	let addMemberSearchText = $state('');
	let removingMemberId = $state<string | null>(null);
	const sourceOptions = $derived([
		{ value: '', label: t('groupCard.sourceDefault'), description: group.domain_id ?? undefined },
		...sourceDomains.map((domain) => ({ value: domain.id, label: domain.name, description: domain.id })),
	]);
	let searchGeneration: number | undefined;
	let searchDomain: string | undefined;
	let searchExpanded: boolean | undefined;
	$effect(() => {
		if (searchGeneration === sourceGeneration && searchDomain === userDomainId && searchExpanded === expanded) return;
		searchGeneration = sourceGeneration;
		searchDomain = userDomainId;
		searchExpanded = expanded;
		addMemberSearchText = '';
	});
	const searchQuery = $derived(addMemberSearchText.trim().toLowerCase());
	const candidateUsers = $derived.by(() => {
		const existingIds = new Set(members.map((member) => member.id));
		return allUsers.filter((user) => user.enabled && !existingIds.has(user.id)
			&& [user.name, user.email, user.id, user.domain_id].some((value) => value?.toLowerCase().includes(searchQuery)));
	});

	async function handleRemoveMember(userId: string) {
		if (removingMemberId) return;
		removingMemberId = userId;
		try {
			await onRemoveMember(userId);
		} finally {
			removingMemberId = null;
		}
	}

	async function handleAddMember(userId: string) {
		const generation = sourceGeneration;
		const source = userDomainId;
		const ok = await onAddMember(userId);
		if (ok && expanded && generation === sourceGeneration && source === userDomainId) {
			addMemberSearchText = '';
		}
	}
</script>

{#snippet userIdentity(user: User | GroupMember)}
	<div class="min-w-0 flex-1 space-y-1">
		<div class="break-all text-sm text-ink-0">{user.name || '-'}</div>
		<dl class="space-y-1 text-xs text-ink-2">
			<div><dt>{t('groupCard.email')}</dt><dd class="break-all">{user.email || t('groupCard.noEmail')}</dd></div>
			<div><dt>{t('groupCard.userId')}</dt><dd class="break-all font-mono">{user.id}</dd></div>
			<div><dt>{t('groupCard.homeDomain')}</dt><dd class="break-all font-mono">{user.domain_id || t('groupCard.unknownDomain')}</dd></div>
		</dl>
	</div>
{/snippet}

<div class="bg-surface-base border border-line rounded-xl">
  <div class="flex flex-wrap items-start justify-between gap-3 px-3 py-3 lg:px-4">
    <div class="min-w-0 flex-1">
      <div class="min-w-0">
        <div class="break-words text-sm font-medium text-ink-0">{group.name}</div>
        <details class="mt-1 text-xs text-ink-2">
          <summary class="flex min-h-11 cursor-pointer items-center lg:min-h-0">{t('form.description')}</summary>
          <p class="whitespace-pre-wrap break-words">{group.description || '-'}</p>
          <p class="break-all font-mono mt-2">{group.id}</p>
          <p class="tabular-nums mt-1">{t('groupCard.createdAt', { date: group.created_at ? new Date(group.created_at).toLocaleDateString(intlLocale(), { timeZone: 'UTC' }) : t('groupCard.unknownDate') })}</p>
        </details>
      </div>
		</div>
    <div class="flex flex-wrap items-center gap-1 [&_button]:min-h-11 lg:[&_button]:min-h-0">
			<Button variant={expanded ? 'primary' : 'ghost'} size="xs" onclick={onToggleMembers}>{t('groupCard.members')}</Button>
			<Button variant="subtle" size="xs" onclick={onEdit}>{t('actions.edit')}</Button>
			<Button variant="danger-outline" size="xs" onclick={onDelete}>{t('actions.delete')}</Button>
		</div>
	</div>

	{#if expanded}
		<div class="border-t border-line bg-surface-base/50 px-4 py-4">
			{#if membersLoading}
				<div class="text-xs text-ink-2 py-2"><ActivityIndicator size="xs" label={t('state.loading')} /></div>
			{:else if membersError}
				<Alert tone="danger">{membersError}</Alert>
			{:else}
				<div class="text-xs text-ink-2 uppercase tracking-wide mb-2">{t('groupCard.membersHeading')}</div>
				{#if members.length === 0}
					<div class="text-xs text-ink-2 mb-3">{t('groupCard.noMembers')}</div>
				{:else}
					<ul class="space-y-1 mb-3" aria-label={t('groupCard.membersHeading')}>
						{#each members as m (m.id)}
							<li data-group-member-id={m.id} class="flex flex-wrap items-start justify-between gap-2 bg-surface-sunken/50 rounded px-3 py-2">
								{@render userIdentity(m)}
								<Button variant="danger-outline" size="xs" class="min-h-11 shrink-0 lg:min-h-0" ariaBusy={removingMemberId === m.id} disabled={removingMemberId !== null} onclick={() => handleRemoveMember(m.id)}>{#if removingMemberId === m.id}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('state.removing')}</span>{:else}{t('actions.remove')}{/if}</Button>
							</li>
						{/each}
					</ul>
				{/if}
				<div class="border-t border-line-2/50 pt-3">
					{#if addError}<Alert tone="danger" class="mb-2">{addError}</Alert>{/if}
					<div class="mb-3 min-w-0 space-y-2">
						<Field for={`group-user-domain-${group.id}`} label={t('groupCard.sourceDomain')} help={t('groupCard.sourceHelp')}>
							<SearchSelect id={`group-user-domain-${group.id}`} ariaLabel={t('groupCard.sourceDomain')}
								value={userDomainId} options={sourceOptions} loading={sourceDomainsLoading} disabled={addSaving}
								searchPlaceholder={t('groupCard.sourceSearch')} onchange={(id) => { void onSelectUserDomain?.(id); }} />
						</Field>
						{#if userDomainId}<p class="break-all font-mono text-xs text-ink-2">{userDomainId}</p>{/if}
						<p class="text-xs text-ink-2">{t('groupCard.sourcePermissionHelp')}</p>
						{#if sourceDomainsError}
							<Alert tone="danger">
								<p>{t('groupCard.sourceDomainsFailed')}</p>
								<p class="mt-1 break-words">{sourceDomainsError}</p>
								{#snippet actions()}<Button variant="secondary" size="sm" onclick={onRetrySourceDomains}>{t('groupCard.retrySourceDomains')}</Button>{/snippet}
							</Alert>
						{/if}
					</div>
					<Field for={`group-user-search-${group.id}`} label={t('groupCard.userSearch')}>
						<TextInput id={`group-user-search-${group.id}`} type="search" placeholder={t('groupCard.searchPlaceholder')} bind:value={addMemberSearchText} />
					</Field>
					{#if addSaving}<div class="mt-2"><ActivityIndicator size="xs" label={t('groupCard.addingMember')} /></div>{/if}
					{#if usersLoading}
						<div class="mt-2" role="status"><ActivityIndicator size="xs" label={t('groupCard.usersLoading')} /></div>
					{:else if usersError}
						<Alert tone="danger" class="mt-2">
							<p>{t('groupCard.usersFailed')}</p>
							<p class="mt-1 break-words">{usersError}</p>
							{#snippet actions()}
								<Button variant="secondary" size="sm" onclick={onRetryUsers}>{t('groupCard.retryUsers')}</Button>
							{/snippet}
						</Alert>
					{:else if searchQuery}
						{#if candidateUsers.length > 0}
							<div class="mt-2 max-h-72 overflow-y-auto rounded-lg border border-line" role="region" aria-label={t('groupCard.candidates')}>
								<ul>
									{#each candidateUsers as user (user.id)}
										<li data-group-candidate-id={user.id} class="flex flex-wrap items-start justify-between gap-2 border-b border-line px-3 py-2 last:border-0">
											{@render userIdentity(user)}
											<Button size="sm" onclick={() => handleAddMember(user.id)} disabled={addSaving} ariaBusy={addSaving} class="min-h-11 shrink-0 lg:min-h-0">{t('actions.add')}</Button>
										</li>
									{/each}
								</ul>
							</div>
						{:else}
							<p class="mt-2 text-sm text-ink-2" role="status">{t('groupCard.noMatchingUsers')}</p>
						{/if}
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>
