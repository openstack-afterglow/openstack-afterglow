<script lang="ts">
	import type { DbUser } from '$lib/types/database';

	let {
		users,
		deletingUser,
		addError,
		creating,
		onAdd,
		onDelete,
	}: {
		users: DbUser[];
		deletingUser: string | null;
		addError: string;
		creating: boolean;
		onAdd: (form: { name: string; password: string; databases: string }) => Promise<boolean>;
		onDelete: (name: string) => Promise<void>;
	} = $props();

	let showForm = $state(false);
	let newUser = $state({ name: '', password: '', databases: '' });

	async function handleAdd() {
		const ok = await onAdd({ ...newUser });
		if (ok) {
			showForm = false;
			newUser = { name: '', password: '', databases: '' };
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">유저</h2>
		<button onclick={() => { showForm = !showForm; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showForm ? '취소' : '+ 추가'}
		</button>
	</div>
	{#if showForm}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newUser.name} placeholder="username"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			<input type="password" bind:value={newUser.password} placeholder="비밀번호"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			<input type="text" bind:value={newUser.databases} placeholder="DB 접근 권한 (쉼표 구분)"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if addError}<p class="text-red-400 text-xs">{addError}</p>{/if}
			<button onclick={handleAdd} disabled={creating || !newUser.name.trim() || !newUser.password}
				class="text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{creating ? '생성 중...' : '생성'}
			</button>
		</div>
	{/if}
	{#if users.length === 0}
		<div class="text-ink-3 text-xs">유저가 없습니다</div>
	{:else}
		<div class="space-y-1">
			{#each users as u}
				<div class="flex items-center justify-between py-1.5 border-b border-line/50">
					<div>
						<span class="text-ink-0 text-sm font-medium">{u.name}</span>
						{#if u.databases?.length}
							<span class="text-ink-3 text-xs ml-2">{u.databases.map(d => d.name).join(', ')}</span>
						{/if}
					</div>
					<button onclick={() => onDelete(u.name)} disabled={deletingUser === u.name}
						class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
						{deletingUser === u.name ? '...' : '삭제'}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
