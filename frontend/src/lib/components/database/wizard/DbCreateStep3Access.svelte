<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { useDbCreate } from '$lib/stores/dbCreateStore.svelte';
	const s = useDbCreate();
</script>

<div class="space-y-4">
	<label class="flex items-center gap-3 cursor-pointer">
		<input type="checkbox" bind:checked={s.isPublic} class="accent-amber-500" />
		<span class="text-sm text-ink-0">{tr('wizard.public')}</span>
	</label>
	<p class="text-xs text-ink-2">
		{tr('wizard.publicHelp')}
	</p>
	{#if s.isPublic}
		<div class="flex items-start gap-2 bg-surface-selected/20 border border-action-warm/50 rounded-lg px-3 py-2.5 text-xs text-warm-text">
			<svg class="w-3.5 h-3.5 mt-0.5 shrink-0" viewBox="0 0 20 20" fill="currentColor">
				<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
			</svg>
			{tr('wizard.floatingHelp')}
		</div>
	{/if}
	<div>
		<label class={s.labelCls} for="field-dbcreatestep3access-23">{tr('wizard.allowedCidrs')}</label>
		<input id="field-dbcreatestep3access-23"
			type="text"
			bind:value={s.allowedCidrs}
			placeholder="10.0.0.0/24, 192.168.1.0/24"
			class={s.inputCls}
		/>
	</div>
</div>
