<script lang="ts">
	import type { DbBackup } from '$lib/types/database';

	let {
		backups,
		deletingBackup,
		restoringBackup,
		addError,
		creating,
		onAdd,
		onDelete,
		onRestore,
	}: {
		backups: DbBackup[];
		deletingBackup: string | null;
		restoringBackup: string | null;
		addError: string;
		creating: boolean;
		onAdd: (form: { name: string; description: string }) => Promise<boolean>;
		onDelete: (id: string) => Promise<void>;
		onRestore: (id: string) => Promise<void>;
	} = $props();

	let showForm = $state(false);
	let newBackup = $state({ name: '', description: '' });

	async function handleAdd() {
		const ok = await onAdd({ ...newBackup });
		if (ok) {
			showForm = false;
			newBackup = { name: '', description: '' };
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">백업</h2>
		<button onclick={() => { showForm = !showForm; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showForm ? '취소' : '+ 백업 생성'}
		</button>
	</div>
	{#if showForm}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newBackup.name} placeholder="backup-name"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			<input type="text" bind:value={newBackup.description} placeholder="설명 (선택)"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if addError}<p class="text-red-400 text-xs">{addError}</p>{/if}
			<button onclick={handleAdd} disabled={creating || !newBackup.name.trim()}
				class="text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{creating ? '생성 중...' : '백업 생성'}
			</button>
		</div>
	{/if}
	{#if backups.length === 0}
		<div class="text-ink-3 text-xs">백업이 없습니다</div>
	{:else}
		<table class="w-full text-sm">
			<thead>
				<tr class="text-ink-3 text-xs">
					<th class="text-left py-2 font-medium">이름</th>
					<th class="text-left py-2 font-medium">상태</th>
					<th class="text-left py-2 font-medium">크기</th>
					<th class="text-left py-2 font-medium">생성일</th>
					<th class="text-right py-2 font-medium">액션</th>
				</tr>
			</thead>
			<tbody>
				{#each backups as b}
					<tr class="border-t border-line/50">
						<td class="py-2 text-ink-0">{b.name}</td>
						<td class="py-2 text-ink-2 text-xs">{b.status}</td>
						<td class="py-2 text-ink-2 text-xs">{b.size ? `${b.size} GB` : '-'}</td>
						<td class="py-2 text-ink-3 text-xs">{b.created_at ? b.created_at.slice(0, 10) : '-'}</td>
						<td class="py-2 text-right">
							<div class="flex justify-end gap-1">
								<button onclick={() => onRestore(b.id)} disabled={restoringBackup === b.id}
									class="text-action-warm hover:text-action-warm-hover disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-action-warm hover:border-action-warm transition-colors">
									{restoringBackup === b.id ? '...' : '복원'}
								</button>
								<button onclick={() => onDelete(b.id)} disabled={deletingBackup === b.id}
									class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
									{deletingBackup === b.id ? '...' : '삭제'}
								</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>
