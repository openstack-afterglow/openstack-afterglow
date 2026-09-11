<script lang="ts">
	export interface NotionTargetForm {
		label: string;
		apiKey: string;
		databaseId: string;
		enabled: boolean;
		intervalMinutes: number;
		usersDatabaseId: string;
		hypervisorsDatabaseId: string;
		gpuSpecDatabaseId: string;
	}

	let {
		form,
		mode,
	}: {
		form: NotionTargetForm;
		mode: 'add' | 'edit';
	} = $props();

	const inputClass = 'w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm';
	const monoInputClass = inputClass + ' font-mono';
</script>

<div class="space-y-3">
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-27">레이블 (식별용)</label>
		<input id="field-notiontargetformfields-27" bind:value={form.label} type="text" placeholder="예: 운영팀 DB" class={inputClass} />
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-31">
			Notion API Key
			{#if mode === 'add'}
				<span class="text-red-400">*</span>
			{:else}
				<span class="text-ink-3">(변경 시에만 입력)</span>
			{/if}
		</label>
		<input id="field-notiontargetformfields-31"
			bind:value={form.apiKey}
			type="password"
			placeholder={mode === 'add' ? 'ntn_...' : '변경하지 않으면 비워두세요'}
			class={monoInputClass}
		/>
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-47">
			인스턴스 Database ID
			{#if mode === 'add'}<span class="text-red-400">*</span>{/if}
		</label>
		<input id="field-notiontargetformfields-47" bind:value={form.databaseId} type="text" placeholder="32자리 UUID" class={monoInputClass} />
	</div>
	<div class="grid grid-cols-2 gap-3">
		<div>
			<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-55">사용자 DB ID <span class="text-ink-3">(선택)</span></label>
			<input id="field-notiontargetformfields-55" bind:value={form.usersDatabaseId} type="text" placeholder="People DB" class={monoInputClass} />
		</div>
		<div>
			<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-59">하이퍼바이저 DB ID <span class="text-ink-3">(선택)</span></label>
			<input id="field-notiontargetformfields-59" bind:value={form.hypervisorsDatabaseId} type="text" placeholder="Hypervisor DB" class={monoInputClass} />
		</div>
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-64">GPU Spec DB ID <span class="text-ink-3">(선택)</span></label>
		<input id="field-notiontargetformfields-64" bind:value={form.gpuSpecDatabaseId} type="text" placeholder="GPU Spec DB" class={monoInputClass} />
	</div>
	<div class="flex gap-4 items-end">
		<div>
			<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-69">동기화 간격 (분)</label>
			<input id="field-notiontargetformfields-69" bind:value={form.intervalMinutes} type="number" min="1" max="1440"
				class="w-24 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
		</div>
		<label class="flex items-center gap-2 cursor-pointer pb-2">
			<input bind:checked={form.enabled} type="checkbox"
				class="w-4 h-4 rounded border-line-2 bg-surface-sunken text-blue-600 focus:ring-line-2" />
			<span class="text-sm text-ink-2">활성화</span>
		</label>
	</div>
</div>
