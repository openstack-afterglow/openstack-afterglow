<script lang="ts">
	import { useFsWizard } from '$lib/stores/fileStorageWizardStore.svelte';
	import { t } from '$lib/i18n/ns/file-storage';
	import RichText from '$lib/i18n/RichText.svelte';
	import { ActivityIndicator, Alert, Button, ProgressTrack } from '$lib/components/ui';

	const s = useFsWizard();
</script>

<h2 class="text-base font-semibold text-ink-0 mb-1">{t('wizard.network.title')}</h2>
<div class="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-blue-950/30 border border-action-warm/40 text-warm-text text-xs mb-4">
	<svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
		<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
	</svg>
	<span>{t('wizard.network.environmentNotice')}</span>
</div>
<div class="space-y-4">
	<div>
		{#if s.fsForm.share_proto === 'CEPHFS'}
			<div class="bg-surface-sunken/40 border border-line-2 rounded-lg px-3 py-2.5 text-xs text-ink-2">
				{t('wizard.network.cephfsNotice')}
			</div>
		{:else}
			<div class="flex items-center justify-between mb-1.5">
				<span class="text-xs text-ink-2 uppercase tracking-wide">{s.fsForm.share_proto === 'NFS' ? t('wizard.network.shareNetworkRequired') : t('wizard.network.shareNetworkOptional')}</span>
				<button type="button" onclick={() => { s.showInlineNetCreate = !s.showInlineNetCreate; s.inlineNetError = ''; }}
					class="text-xs text-warm-text hover:text-warm-text-hover transition-colors">
					{s.showInlineNetCreate ? t('wizard.network.collapse') : t('wizard.network.newNetwork')}
				</button>
			</div>
			{#if s.shareNetworks.length > 0}
				<select bind:value={s.selectedNetworkId} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
					<option value="">{s.fsForm.share_proto === 'NFS' ? t('wizard.network.useDefault') : t('wizard.network.useDefaultRecommended')}</option>
					{#each s.shareNetworks as net}<option value={net.id}>{net.name || net.id.slice(0, 8)}{net.status ? ` (${net.status})` : ''}</option>{/each}
				</select>
			{:else if !s.showInlineNetCreate}
				<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-2 text-sm">
					{#snippet createNetwork(text: string)}
						<button onclick={() => (s.showInlineNetCreate = true)} class="text-warm-text hover:text-warm-text-hover underline">{text}</button>
					{/snippet}
					<RichText segments={t.rich('wizard.network.empty')} tags={{ create: createNetwork }} />
				</div>
			{/if}
		{/if}
	</div>

	{#if s.showInlineNetCreate}
		<div class="border border-line-2 rounded-lg p-4 bg-surface-sunken/40 space-y-3">
			<p class="text-xs text-ink-2 font-medium uppercase tracking-wide">{t('wizard.network.createTitle')}</p>
			<div>
				<label class="block text-xs text-ink-2 mb-1">{t('wizard.form.name')}
					<input bind:value={s.inlineNetForm.name} type="text" placeholder="my-share-network"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1" />
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1">{t('wizard.network.description')}
					<input bind:value={s.inlineNetForm.description} type="text" placeholder={t('wizard.network.descriptionPlaceholder')}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1" />
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1">{t('wizard.network.neutronNetwork')}
					<select bind:value={s.inlineNetForm.neutron_net_id} onchange={s.onInlineNetworkChange}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1">
						<option value="">{t('wizard.network.selectNetwork')}</option>
						{#each s.neutronNetworks as net}<option value={net.id}>{net.name || net.id.slice(0, 12)} ({net.status})</option>{/each}
					</select>
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1">{t('wizard.network.subnet')}
					{#if s.loadingSubnets}
						<div class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 mt-1"><ActivityIndicator label={t('wizard.network.loadingSubnets')} /></div>
					{:else}
						<select bind:value={s.inlineNetForm.neutron_subnet_id} disabled={s.subnets.length === 0}
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1 disabled:text-ink-3">
							<option value="">{s.subnets.length === 0 ? t('wizard.network.selectNetworkFirst') : t('wizard.network.selectSubnet')}</option>
							{#each s.subnets as subnet}<option value={subnet.id}>{subnet.name || subnet.id.slice(0, 12)} {subnet.cidr ? `(${subnet.cidr})` : ''}</option>{/each}
						</select>
					{/if}
				</label>
			</div>
			{#if s.inlineNetError}<Alert tone="danger">{s.inlineNetError}</Alert>{/if}
			<div class="flex justify-end gap-2">
				<button onclick={() => { s.showInlineNetCreate = false; s.inlineNetError = ''; }} class="px-3 py-1.5 text-xs text-ink-2 hover:text-ink-0 transition-colors">{t('wizard.actions.cancel')}</button>
				<Button variant="accent" size="sm" onclick={s.createInlineNetwork} disabled={s.inlineNetCreating || !s.inlineNetForm.name.trim() || !s.inlineNetForm.neutron_net_id || !s.inlineNetForm.neutron_subnet_id} ariaBusy={s.inlineNetCreating}>
					{#if s.inlineNetCreating}<ActivityIndicator size="xs" tone="ink" />{t('wizard.actions.creating')}{:else}{t('wizard.network.create')}{/if}
				</Button>
			</div>
		</div>
	{/if}
</div>

{#if s.wizardError}<Alert tone="danger" class="mt-4">{s.wizardError}</Alert>{/if}
{#if s.creating}<ProgressTrack value={null} active label={t('wizard.mutation.createFileStorage')} class="mt-4" />{/if}
<div class="flex justify-between gap-3 mt-6">
	<button onclick={s.backToStep1} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('wizard.actions.previous')}</button>
	<div class="flex gap-3">
		<button onclick={s.closeWizard} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('wizard.actions.cancel')}</button>
		<Button onclick={s.createFileStorage} disabled={s.creating} ariaBusy={s.creating}>
			{#if s.creating}<ActivityIndicator size="xs" tone="ink" />{t('wizard.actions.creating')}{:else}{t('wizard.actions.create')}{/if}
		</Button>
	</div>
</div>
