<script lang="ts">
	import type { Group, GroupMember, User } from '$lib/types/adminGroup';

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
				<div class="text-xs text-ink-3">{group.description || '-'}</div>
			</div>
			<div class="text-xs text-ink-3 font-mono hidden sm:block">{group.id.slice(0, 8)}</div>
		</div>
		<div class="flex items-center gap-1 ml-4 shrink-0">
			<button
				onclick={onToggleMembers}
				class="px-2 py-0.5 text-xs {expanded ? 'bg-action-warm text-ink-0' : 'bg-surface-selected/40 text-action-warm'} hover:bg-action-warm-hover rounded transition-colors"
			>멤버</button>
			<button
				onclick={onEdit}
				class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded"
			>수정</button>
			<button
				onclick={onDelete}
				class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
			>삭제</button>
		</div>
	</div>

	{#if expanded}
		<div class="border-t border-line bg-surface-base/50 px-4 py-4">
			{#if membersLoading}
				<div class="text-xs text-ink-3 py-2">로딩 중...</div>
			{:else}
				<div class="text-xs text-ink-2 uppercase tracking-wide mb-2">멤버</div>
				{#if members.length === 0}
					<div class="text-xs text-ink-3 mb-3">멤버가 없습니다</div>
				{:else}
					<div class="space-y-1 mb-3">
						{#each members as m}
							<div class="flex items-center justify-between bg-surface-sunken/50 rounded px-3 py-1.5">
								<div>
									<span class="text-sm text-ink-0">{m.name}</span>
									{#if m.email}<span class="text-xs text-ink-3 ml-2">{m.email}</span>{/if}
								</div>
								<button onclick={() => onRemoveMember(m.id)} class="text-xs text-red-400 hover:text-red-300">제거</button>
							</div>
						{/each}
					</div>
				{/if}
				<div class="border-t border-line-2/50 pt-3">
					{#if addError}
						<div class="text-xs text-red-400 mb-2">{addError}</div>
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
								<div class="absolute z-10 left-0 right-0 mt-1 bg-gray-850 border border-line-2 rounded-lg shadow-[var(--shadow-restraint)] overflow-hidden max-h-56 overflow-y-auto" style="background:#1a1f2e;">
									{#each filtered as u}
										<div class="flex items-center justify-between px-4 py-2.5 hover:bg-surface-selected border-b border-line-2/50 last:border-0 transition-colors">
											<span class="text-sm text-ink-1">{u.name}</span>
											<button
												onclick={() => handleAddMember(u.id)}
												disabled={addSaving}
												class="text-xs px-3 py-1 bg-action-warm hover:bg-action-warm-hover text-action-on-warm rounded-md disabled:opacity-30 ml-4 shrink-0"
											>추가</button>
										</div>
									{/each}
								</div>
							{:else}
								<div class="absolute z-10 left-0 right-0 mt-1 border border-line-2 rounded-lg px-4 py-3 text-sm text-ink-3" style="background:#1a1f2e;">
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
