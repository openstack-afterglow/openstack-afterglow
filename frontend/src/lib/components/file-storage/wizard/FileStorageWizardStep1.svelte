<script lang="ts">
	import { useFsWizard } from '$lib/stores/fileStorageWizardStore.svelte';
	import { t } from '$lib/i18n/ns/file-storage';
	import { ActivityIndicator, Alert, Button, ProgressTrack } from '$lib/components/ui';

	const s = useFsWizard();
</script>

<h2 class="text-base font-semibold text-ink-0 mb-4">{t('wizard.basic.title')}</h2>
<div class="space-y-4">
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.form.name')}
			<input bind:value={s.fsForm.name} type="text" placeholder="my-file-storage"
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
		</label>
	</div>
	<div>
		<span class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.basic.size')}</span>
		<div class="flex gap-2 mb-2">
			{#each [10, 20, 50, 100] as preset}
				<button type="button" onclick={() => (s.fsForm.size_gb = preset)}
					class="flex-1 py-1.5 text-xs rounded-lg border transition-colors {s.fsForm.size_gb === preset ? 'border-action-warm bg-surface-selected/30 text-warm-text' : 'border-line-2 text-ink-2 hover:border-line-2'}">
					{preset} GB
				</button>
			{/each}
		</div>
		<input bind:value={s.fsForm.size_gb} type="number" min="1" placeholder={t('wizard.basic.customSizePlaceholder')}
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.basic.shareType')}
			{#if s.shareTypes.length > 0}
				<select bind:value={s.fsForm.share_type} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
					{#each s.shareTypes as st}<option value={st.name}>{st.is_default ? t('wizard.basic.defaultShareType', { name: st.name }) : st.name}</option>{/each}
				</select>
			{:else}
				<input bind:value={s.fsForm.share_type} type="text" placeholder={t('wizard.basic.shareTypePlaceholder')}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono mt-1.5" />
			{/if}
		</label>
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('wizard.basic.protocol')}
			<select bind:value={s.fsForm.share_proto} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
				{#each s.allowedProtos as p (p)}
					<option value={p}>{p === 'CEPHFS' ? 'CephFS' : 'NFS'}</option>
				{/each}
			</select>
			{#if s.allowedProtos.length === 1 && s.currentShareType}
				<span class="block text-xs text-ink-2 mt-1">{t('wizard.basic.supportedProtocol', { protocol: s.allowedProtos[0] })}</span>
			{/if}
		</label>
	</div>
	<div>
		<div class="flex items-center justify-between mb-2">
			<span class="block text-xs text-ink-2 uppercase tracking-wide">{t('wizard.basic.metadata')}</span>
			<button type="button" onclick={s.addMeta} class="text-xs text-warm-text hover:text-warm-text-hover transition-colors">{t('wizard.actions.add')}</button>
		</div>
		<div class="space-y-2">
			{#each s.metaEntries as meta, i (i)}
				<div class="flex gap-2 items-center">
					<input bind:value={meta.key} type="text" placeholder={t('wizard.basic.metadataKeyPlaceholder')}
						class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
					<span class="text-ink-2 text-xs">=</span>
					<input bind:value={meta.value} type="text" placeholder={t('wizard.basic.metadataValuePlaceholder')}
						class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
					<button type="button" onclick={() => s.removeMeta(i)} class="text-ink-2 hover:text-red-400 transition-colors text-xs px-1">✕</button>
				</div>
			{/each}
		</div>
	</div>
</div>
{#if s.wizardError}<Alert tone="danger" class="mt-4">{s.wizardError}</Alert>{/if}
{#if s.creating}<ProgressTrack value={null} active label={t('wizard.mutation.createFileStorage')} class="mt-4" />{/if}
<div class="flex justify-end gap-3 mt-6">
	<button onclick={s.closeWizard} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('wizard.actions.cancel')}</button>
	<Button onclick={s.goStep2} disabled={s.creating} ariaBusy={s.creating}>
		{#if s.creating}<ActivityIndicator size="xs" tone="ink" />{t('wizard.actions.creating')}{:else}{(!s.dhssEnabled || s.fsForm.share_proto === 'CEPHFS') ? t('wizard.actions.create') : t('wizard.actions.next')}{/if}
	</Button>
</div>
