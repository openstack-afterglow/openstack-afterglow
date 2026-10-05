<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import RichText from '$lib/i18n/RichText.svelte';
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

{#snippet required(text: string)}<span class="text-red-400">{text}</span>{/snippet}
{#snippet hint(text: string)}<span class="text-ink-2">{text}</span>{/snippet}

<div class="space-y-3">
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-27">{t('notion.form.label')}</label>
		<input id="field-notiontargetformfields-27" bind:value={form.label} type="text" placeholder={t('notion.form.labelPlaceholder')} class={inputClass} />
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-31">
			<RichText segments={t.rich(mode === 'add' ? 'notion.form.apiKeyAdd' : 'notion.form.apiKeyEdit')} tags={{ required, hint }} />
		</label>
		<input id="field-notiontargetformfields-31"
			bind:value={form.apiKey}
			type="password"
			placeholder={t(mode === 'add' ? 'notion.form.apiKeyPlaceholder' : 'notion.form.apiKeyEditPlaceholder')}
			class={monoInputClass}
		/>
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-47">
			<RichText segments={t.rich(mode === 'add' ? 'notion.form.instanceDatabaseAdd' : 'notion.form.instanceDatabaseEdit')} tags={{ required }} />
		</label>
		<input id="field-notiontargetformfields-47" bind:value={form.databaseId} type="text" placeholder={t('notion.form.uuidPlaceholder')} class={monoInputClass} />
	</div>
	<div class="grid grid-cols-2 gap-3">
		<div>
			<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-55"><RichText segments={t.rich('notion.form.usersDatabase')} tags={{ hint }} /></label>
			<input id="field-notiontargetformfields-55" bind:value={form.usersDatabaseId} type="text" placeholder={t('notion.form.usersDatabasePlaceholder')} class={monoInputClass} />
		</div>
		<div>
			<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-59"><RichText segments={t.rich('notion.form.hypervisorsDatabase')} tags={{ hint }} /></label>
			<input id="field-notiontargetformfields-59" bind:value={form.hypervisorsDatabaseId} type="text" placeholder={t('notion.form.hypervisorsDatabasePlaceholder')} class={monoInputClass} />
		</div>
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-64"><RichText segments={t.rich('notion.form.gpuDatabase')} tags={{ hint }} /></label>
		<input id="field-notiontargetformfields-64" bind:value={form.gpuSpecDatabaseId} type="text" placeholder={t('notion.form.gpuDatabasePlaceholder')} class={monoInputClass} />
	</div>
	<div class="flex gap-4 items-end">
		<div>
			<label class="block text-xs text-ink-2 mb-1" for="field-notiontargetformfields-69">{t('notion.form.interval')}</label>
			<input id="field-notiontargetformfields-69" bind:value={form.intervalMinutes} type="number" min="1" max="1440"
				class="w-24 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
		</div>
		<label class="flex items-center gap-2 cursor-pointer pb-2">
			<input bind:checked={form.enabled} type="checkbox"
				class="w-4 h-4 rounded border-line-2 bg-surface-sunken text-blue-600 focus:ring-line-2" />
			<span class="text-sm text-ink-2">{t('notion.form.enabled')}</span>
		</label>
	</div>
</div>
