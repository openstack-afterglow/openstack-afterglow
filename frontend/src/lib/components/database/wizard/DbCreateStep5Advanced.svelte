<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { useDbCreate } from '$lib/stores/dbCreateStore.svelte';
	const s = useDbCreate();
</script>

<div class="space-y-4">
	<div>
		<label class={s.labelCls} for="field-dbcreatestep5advanced-8">{tr('wizard.configuration')}</label>
		<select id="field-dbcreatestep5advanced-8" bind:value={s.configurationId} class={s.inputCls}>
			<option value="">{tr('options.none')}</option>
			{#each s.configurations as cfg}
				<option value={cfg.id}>{cfg.name} ({cfg.datastore_name})</option>
			{/each}
		</select>
	</div>
	<div>
		<label class={s.labelCls} for="field-dbcreatestep5advanced-18">{tr('wizard.restoreSource')}</label>
		<select id="field-dbcreatestep5advanced-18" bind:value={s.restoreBackupId} class={s.inputCls}>
			<option value="">{tr('wizard.newInstance')}</option>
			{#each s.backups as b}
				<option value={b.id}>{b.name}</option>
			{/each}
		</select>
	</div>
	<div>
		<label class={s.labelCls} for="field-dbcreatestep5advanced-28">{tr('wizard.replicaSource')}</label>
		<select id="field-dbcreatestep5advanced-28" bind:value={s.replicaOf} class={s.inputCls}>
			<option value="">{tr('options.none')}</option>
			{#each s.instances as inst}
				<option value={inst.id}>{inst.name}</option>
			{/each}
		</select>
	</div>
	{#if s.replicaOf}
		<div>
			<label class={s.labelCls} for="field-dbcreatestep5advanced-38">{tr('wizard.replicaCount')}</label>
			<input id="field-dbcreatestep5advanced-38" type="number" bind:value={s.replicaCount} min="1" max="10" class={s.inputCls} />
		</div>
	{/if}
	<div>
		<label class={s.labelCls} for="field-dbcreatestep5advanced-43">{tr('wizard.locality')}</label>
		<select id="field-dbcreatestep5advanced-43" bind:value={s.locality} disabled={!s.replicaOf} class={s.inputCls}>
			<option value="">{tr('options.none')}</option>
			<option value="affinity">{tr('wizard.affinity')}</option>
			<option value="anti-affinity">{tr('wizard.antiAffinity')}</option>
		</select>
		{#if !s.replicaOf}
			<p class="text-xs text-ink-2 mt-1">{tr('wizard.localityHelp')}</p>
		{/if}
	</div>
</div>
