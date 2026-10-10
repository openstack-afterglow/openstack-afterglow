<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('membersSection.title')}</h3>

	<div class="flex items-center gap-2 mb-4">
		<input
			bind:value={s.newMemberId}
			placeholder={t('membersSection.projectIdPlaceholder')}
			class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono"
			onkeydown={(e) => e.key === 'Enter' && s.addMember()}
		/>
		<Button onclick={() => s.addMember()} disabled={s.addingMember || !s.newMemberId.trim()} size="sm">
			{#if s.addingMember}<ActivityIndicator size="xs" label={t('membersSection.adding')} />{:else}{t('membersSection.add')}{/if}
		</Button>
	</div>

	{#if s.memberError}
		<p class="text-red-400 text-xs mb-3">{s.memberError}</p>
	{/if}

	{#if s.loadingMembers}
		<ActivityIndicator label={t('membersSection.loading')} />
	{:else if s.members.length === 0}
		<p class="text-ink-2 text-xs">{t('membersSection.empty')}</p>
	{:else}
		<div class="space-y-1">
			{#each s.members as m (m.member_id)}
				<div class="flex items-center justify-between px-3 py-2 bg-surface-sunken rounded-lg">
					<div>
						<span class="text-xs text-ink-2 font-mono">{m.member_id}</span>
						<span class="ml-2 text-xs px-1.5 py-0.5 rounded bg-surface-selected text-ink-2">{m.status}</span>
					</div>
					<button
						onclick={() => s.removeMember(m.member_id)}
						disabled={s.removingMember === m.member_id}
						class="text-xs px-2 py-1 text-red-400 hover:text-red-300 disabled:text-ink-3 transition-colors"
					>
						{#if s.removingMember === m.member_id}<ActivityIndicator size="xs" label={t('membersSection.deleting')} />{:else}{t('membersSection.delete')}{/if}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
