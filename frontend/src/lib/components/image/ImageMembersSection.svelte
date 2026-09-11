<script lang="ts">
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">공유 프로젝트 관리</h3>

	<div class="flex items-center gap-2 mb-4">
		<input
			bind:value={s.newMemberId}
			placeholder="프로젝트 ID 입력"
			class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono"
			onkeydown={(e) => e.key === 'Enter' && s.addMember()}
		/>
		<Button onclick={() => s.addMember()} disabled={s.addingMember || !s.newMemberId.trim()} size="sm">
			{s.addingMember ? '추가 중...' : '+ 추가'}
		</Button>
	</div>

	{#if s.memberError}
		<p class="text-red-400 text-xs mb-3">{s.memberError}</p>
	{/if}

	{#if s.loadingMembers}
		<p class="text-ink-3 text-xs">불러오는 중...</p>
	{:else if s.members.length === 0}
		<p class="text-ink-3 text-xs">공유된 프로젝트가 없습니다.</p>
	{:else}
		<div class="space-y-1">
			{#each s.members as m (m.member_id)}
				<div class="flex items-center justify-between px-3 py-2 bg-surface-sunken rounded-lg">
					<div>
						<span class="text-xs text-ink-2 font-mono">{m.member_id}</span>
						<span class="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-surface-selected text-ink-2">{m.status}</span>
					</div>
					<button
						onclick={() => s.removeMember(m.member_id)}
						disabled={s.removingMember === m.member_id}
						class="text-xs px-2 py-1 text-red-400 hover:text-red-300 disabled:text-ink-3 transition-colors"
					>
						{s.removingMember === m.member_id ? '삭제 중...' : '삭제'}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
