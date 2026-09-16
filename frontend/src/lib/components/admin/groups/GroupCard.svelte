<script lang="ts">
	import type { Group, GroupMember, User } from '$lib/types/adminGroup';
	import Button from '$lib/components/ui/Button.svelte';

	interface Props {
		group: Group;
		expanded: boolean;
		members: GroupMember[];
		membersLoading: boolean;
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

	async function handleAddMember(userId: string) {
		const ok = await onAddMember(userId);
		if (ok) {
			addMemberSearchText = '';
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl">
	<div class="flex items-center justify-between px-4 py-3">
		<div class="flex items-center gap-4 min-w-0">
			<div>
				<div class="text-sm font-medium text-ink-0">{group.name}</div>
				<div class="text-xs text-ink-2">{group.description || '-'}</div>
			</div>
			<div class="text-xs text-ink-2 font-mono hidden sm:block">{group.id.slice(0, 8)}</div>
		</div>
		<div class="flex items-center gap-1 ml-4 shrink-0">
			<Button variant={expanded ? 'primary' : 'ghost'} size="xs" onclick={onToggleMembers}>멤버</Button>
			<Button variant="subtle" size="xs" onclick={onEdit}>수정</Button>
			<Button variant="danger-outline" size="xs" onclick={onDelete}>삭제</Button>
		</div>
	</div>

	{#if expanded}
		<div class="border-t border-line bg-surface-base/50 px-4 py-4">
			{#if membersLoading}
				<div class="text-xs text-ink-2 py-2">로딩 중...</div>
			{:else}
				<div class="text-xs text-ink-2 uppercase tracking-wide mb-2">멤버</div>
				{#if members.length === 0}
					<div class="text-xs text-ink-2 mb-3">멤버가 없습니다</div>
				{:else}
					<div class="space-y-1 mb-3">
						{#each members as m}
							<div class="flex items-center justify-between bg-surface-sunken/50 rounded px-3 py-1.5">
								<div>
									<span class="text-sm text-ink-0">{m.name}</span>
									{#if m.email}<span class="text-xs text-ink-2 ml-2">{m.email}</span>{/if}
								</div>
								<Button variant="danger-outline" size="xs" onclick={() => onRemoveMember(m.id)}>제거</Button>
							</div>
						{/each}
					</div>
				{/if}
				<div class="border-t border-line-2/50 pt-3">
					{#if addError}
						<div class="text-xs text-[var(--color-state-danger)] mb-2">{addError}</div>
					{/if}
					<div class="text-xs text-ink-2 mb-2">사용자 검색</div>
					<div class="relative">
						<input
							type="text"
							placeholder="이름으로 검색하여 멤버 추가..."
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
												class="ml-4 shrink-0"
											>추가</Button>
										</div>
									{/each}
								</div>
							{:else}
								<div class="absolute z-10 left-0 right-0 mt-1 bg-surface-raised border border-line-2 rounded-lg px-4 py-3 text-sm text-ink-2">
									일치하는 사용자가 없습니다
								</div>
							{/if}
						{/if}
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>
