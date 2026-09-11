<script lang="ts">
	import { useDbInstanceDetailController } from '$lib/stores/dbInstanceDetailController.svelte';

	const s = useDbInstanceDetailController();

	let showDbForm = $state(false);
	let newDbName = $state('');

	async function handleCreateDb() {
		if (!newDbName.trim()) return;
		const ok = await s.createDb(newDbName.trim());
		if (ok) {
			showDbForm = false;
			newDbName = '';
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">데이터베이스</h2>
		<button onclick={() => { showDbForm = !showDbForm; s.dbError = ''; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showDbForm ? '취소' : '+ 추가'}
		</button>
	</div>
	{#if showDbForm}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newDbName} placeholder="database_name"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if s.dbError}<p class="text-red-400 text-xs">{s.dbError}</p>{/if}
			<button onclick={handleCreateDb} disabled={s.creatingDb || !newDbName.trim()}
				class="text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{s.creatingDb ? '생성 중...' : '생성'}
			</button>
		</div>
	{/if}
	{#if s.databases.length === 0}
		<div class="text-ink-3 text-xs">데이터베이스가 없습니다</div>
	{:else}
		<div class="space-y-1">
			{#each s.databases as db}
				<div class="flex items-center justify-between py-1.5 border-b border-line/50">
					<span class="text-ink-0 text-sm font-medium">{db.name}</span>
					<button onclick={() => s.deleteDb(db.name)} disabled={s.deletingDb === db.name}
						class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
						{s.deletingDb === db.name ? '...' : '삭제'}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
