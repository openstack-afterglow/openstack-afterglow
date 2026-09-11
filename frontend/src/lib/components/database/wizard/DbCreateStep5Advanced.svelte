<script lang="ts">
	import { useDbCreate } from '$lib/stores/dbCreateStore.svelte';
	const s = useDbCreate();
</script>

<div class="space-y-4">
	<div>
		<label class={s.labelCls} for="field-dbcreatestep5advanced-8">Configuration group</label>
		<select id="field-dbcreatestep5advanced-8" bind:value={s.configurationId} class={s.inputCls}>
			<option value="">없음</option>
			{#each s.configurations as cfg}
				<option value={cfg.id}>{cfg.name} ({cfg.datastore_name})</option>
			{/each}
		</select>
	</div>
	{#if s.databaseBackupsEnabled}
		<div>
			<label class={s.labelCls} for="field-dbcreatestep5advanced-18">백업에서 복원 (초기 상태 원본)</label>
			<select id="field-dbcreatestep5advanced-18" bind:value={s.restoreBackupId} class={s.inputCls}>
				<option value="">새 인스턴스</option>
				{#each s.backups as b}
					<option value={b.id}>{b.name}</option>
				{/each}
			</select>
		</div>
	{/if}
	<div>
		<label class={s.labelCls} for="field-dbcreatestep5advanced-28">복제 원본 인스턴스</label>
		<select id="field-dbcreatestep5advanced-28" bind:value={s.replicaOf} class={s.inputCls}>
			<option value="">없음</option>
			{#each s.instances as inst}
				<option value={inst.id}>{inst.name}</option>
			{/each}
		</select>
	</div>
	{#if s.replicaOf}
		<div>
			<label class={s.labelCls} for="field-dbcreatestep5advanced-38">복제 개수</label>
			<input id="field-dbcreatestep5advanced-38" type="number" bind:value={s.replicaCount} min="1" max="10" class={s.inputCls} />
		</div>
	{/if}
	<div>
		<label class={s.labelCls} for="field-dbcreatestep5advanced-43">배치 정책 (Locality)</label>
		<select id="field-dbcreatestep5advanced-43" bind:value={s.locality} disabled={!s.replicaOf} class={s.inputCls}>
			<option value="">없음</option>
			<option value="affinity">Affinity</option>
			<option value="anti-affinity">Anti-Affinity</option>
		</select>
		{#if !s.replicaOf}
			<p class="text-xs text-ink-3 mt-1">복제 인스턴스 생성 시에만 적용됩니다.</p>
		{/if}
	</div>
</div>
