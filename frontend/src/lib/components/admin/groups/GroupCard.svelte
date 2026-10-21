<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { Group, GroupMember, User } from '$lib/types/adminGroup';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface Props {
		group: Group;
		expanded: boolean;
		members: GroupMember[];
		membersLoading: boolean;
		membersError?: string;
		usersError?: string;
		allUsers: User[];
		addError: string;
		addSaving: boolean;
		onToggleMembers: () => void;
		onEdit: () => void;
		onDelete: () => void;
		onAddMember: (userId: string) => Promise<boolean>;
		onRemoveMember: (userId: string) => Promise<void>;
	}

	let {
		group,
		expanded,
		members,
		membersLoading,
		membersError = '',
		usersError = '',
		allUsers,
		addError,
		addSaving,
		onToggleMembers,
		onEdit,
		onDelete,
		onAddMember,
		onRemoveMember
	}: Props = $props();

	let addMemberSearchText = $state('');
	let removingMemberId = $state<string | null>(null);

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
		const ok = await onAddMember(userId);
		if (ok) {
			addMemberSearchText = '';
		}
	}
</script>

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
					<div class="space-y-1 mb-3">
						{#each members as m}
              <div class="flex flex-wrap items-center justify-between gap-2 bg-surface-sunken/50 rounded px-3 py-1.5">
                <div class="min-w-0 break-words">
                  <span class="text-sm text-ink-0">{m.name}</span>
                  {#if m.email}<span class="block break-all text-xs text-ink-2">{m.email}</span>{/if}
								</div>
								<Button variant="danger-outline" size="xs" ariaBusy={removingMemberId === m.id} disabled={removingMemberId !== null} onclick={() => handleRemoveMember(m.id)}>{#if removingMemberId === m.id}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('state.removing')}</span>{:else}{t('actions.remove')}{/if}</Button>
							</div>
						{/each}
					</div>
				{/if}
				<div class="border-t border-line-2/50 pt-3">
					{#if usersError}<Alert tone="danger">{usersError}</Alert>{/if}
					{#if addError}
						<div class="text-xs text-[var(--color-state-danger)] mb-2">{addError}</div>
					{/if}
					<div class="text-xs text-ink-2 mb-2">{t('groupCard.userSearch')}</div>
					{#if addSaving}<div class="mb-2"><ActivityIndicator size="xs" label={t('groupCard.addingMember')} /></div>{/if}
					<div class="relative">
						<input
							type="text"
							aria-label={t('groupCard.userSearch')}
							placeholder={t('groupCard.searchPlaceholder')}
							bind:value={addMemberSearchText}
							class="w-full bg-surface-sunken border border-line-2 text-ink-0 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-action-warm"
						/>
						{#if addMemberSearchText.trim().length > 0}
							{@const existingIds = new Set(members.map(m => m.id))}
							{@const filtered = allUsers.filter(u => !existingIds.has(u.id) && u.name.toLowerCase().includes(addMemberSearchText.toLowerCase())).slice(0, 8)}
							{#if filtered.length > 0}
								<div class="absolute z-10 left-0 right-0 mt-1 bg-surface-raised border border-line-2 rounded-lg shadow-[var(--shadow-popover)] overflow-hidden max-h-56 overflow-y-auto">
									{#each filtered as u}
										<div class="flex items-center justify-between px-4 py-2.5 hover:bg-surface-selected border-b border-line-2/50 last:border-0 transition-colors">
											<span class="text-sm text-ink-1">{u.name}</span>
											<Button
												size="sm"
												onclick={() => handleAddMember(u.id)}
												disabled={addSaving}
												ariaBusy={addSaving}
												class="ml-4 shrink-0"
											>{t('actions.add')}</Button>
										</div>
									{/each}
								</div>
							{:else}
								<div class="absolute z-10 left-0 right-0 mt-1 bg-surface-raised border border-line-2 rounded-lg px-4 py-3 text-sm text-ink-2">
									{t('groupCard.noMatchingUsers')}
								</div>
							{/if}
						{/if}
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>
