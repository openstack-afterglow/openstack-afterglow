<script lang="ts">
	import { useDbCreate } from '$lib/stores/dbCreateStore.svelte';
	const s = useDbCreate();
</script>

<div class="space-y-4">
	<div>
		<label class={s.labelCls} for="field-dbcreatestep4init-8">초기 데이터베이스 (쉼표 구분)</label>
		<input id="field-dbcreatestep4init-8"
			type="text"
			bind:value={s.initDatabases}
			placeholder="mydb, testdb"
			class={s.inputCls}
		/>
		<p class="text-xs text-ink-3 mt-1">생성 시 자동으로 만들어질 데이터베이스 목록</p>
	</div>
	<div class="border border-line-2 rounded-lg p-4">
		<h4 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">초기 관리자</h4>
		<div class="grid grid-cols-3 gap-2 mb-2">
			<div>
				<label class={s.labelCls} for="field-dbcreatestep4init-21">사용자명</label>
				<input id="field-dbcreatestep4init-21" type="text" bind:value={s.userDraft.name} placeholder="admin" class={s.inputCls} />
			</div>
			<div>
				<label class={s.labelCls} for="field-dbcreatestep4init-25">암호</label>
				<input id="field-dbcreatestep4init-25"
					type="password"
					bind:value={s.userDraft.password}
					placeholder="••••••••"
					class={s.inputCls}
				/>
			</div>
			<div>
				<label class={s.labelCls} for="field-dbcreatestep4init-34">허용 호스트</label>
				<input id="field-dbcreatestep4init-34" type="text" bind:value={s.userDraft.host} placeholder="%" class={s.inputCls} />
			</div>
		</div>
		<button
			onclick={s.addUser}
			disabled={!s.userDraft.name.trim() || !s.userDraft.password}
			class="text-xs text-action-warm hover:text-action-warm-hover disabled:text-ink-3"
		>
			+ 추가
		</button>
		{#if s.users.length}
			<div class="mt-3 space-y-1">
				{#each s.users as u, i}
					<div class="flex items-center justify-between bg-surface-sunken rounded px-3 py-1.5 text-xs">
						<span class="text-ink-0 font-mono">{u.name}@{u.host}</span>
						<button onclick={() => s.removeUser(i)} class="text-red-400 hover:text-red-300">제거</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
