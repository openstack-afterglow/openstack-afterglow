<script lang="ts">
	import { useFsWizard } from '$lib/stores/fileStorageWizardStore.svelte';
	import { t } from '$lib/i18n/ns/file-storage';
	import { ActivityIndicator, Alert, Button } from '$lib/components/ui';

	const s = useFsWizard();
</script>

<div class="flex items-center gap-2 mb-4">
	<span class="motion-pop w-5 h-5 rounded-full border border-[var(--color-state-success)] bg-[color-mix(in_oklab,var(--color-state-success)_14%,transparent)] flex items-center justify-center text-[var(--color-state-success-text)]" aria-hidden="true">
		<svg class="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<path class="motion-draw" pathLength="1" d="M3.5 8.5l3 3 6-7" />
		</svg>
	</span>
	<h2 class="text-base font-semibold text-ink-0">{t('wizard.access.created', { name: s.createdFs!.name })}</h2>
</div>

{#if s.createdFs!.export_locations && s.createdFs!.export_locations.length > 0}
	<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 mb-4">
		<p class="text-xs text-ink-2 mb-1">{t('wizard.access.exportLocation')}</p>
		<div class="flex items-center gap-2">
			<code class="text-xs text-green-300 font-mono flex-1 truncate">{s.createdFs!.export_locations[0]}</code>
			<button onclick={() => s.copyExport(s.createdFs!.export_locations[0], s.createdFs!.id)}
				class="shrink-0 text-ink-2 hover:text-ink-2 text-xs px-2 py-1 rounded border border-line-2 transition-colors">
				{s.copiedExport === s.createdFs!.id ? t('wizard.actions.copied') : t('wizard.actions.copy')}
			</button>
		</div>
	</div>
{/if}

<div class="mb-4">
	<p class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('wizard.access.addRule')}</p>
	<div class="flex gap-2 items-end">
		<div class="flex-1">
			<label class="block text-xs text-ink-2 mb-1">
				{s.createdFs!.share_proto === 'NFS' ? 'IP / CIDR' : 'CephX ID'}
				<input bind:value={s.ruleForm.access_to} type="text"
					placeholder={t('wizard.access.targetPlaceholder', { example: s.createdFs!.share_proto === 'NFS' ? '192.168.1.0/24' : 'my-client' })}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1 font-mono" />
			</label>
		</div>
		<div>
			<label class="block text-xs text-ink-2 mb-1">{t('wizard.access.permission')}
				<select bind:value={s.ruleForm.access_level}
					class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1">
					<option value="rw">{t('wizard.access.readWrite')}</option>
					<option value="ro">{t('wizard.access.readOnly')}</option>
				</select>
			</label>
		</div>
		<Button variant="accent" class="whitespace-nowrap mb-[1px]" onclick={s.addAccessRule} disabled={s.addingRule || !s.ruleForm.access_to.trim()} ariaBusy={s.addingRule}>
			{#if s.addingRule}<ActivityIndicator size="xs" tone="ink" />{t('wizard.actions.adding')}{:else}{t('wizard.actions.add')}{/if}
		</Button>
	</div>
	{#if s.ruleError}<Alert tone="danger" class="mt-2">{s.ruleError}</Alert>{/if}
</div>

{#if s.accessRules.length > 0}
	<div class="border border-line-2 rounded-lg overflow-hidden mb-4">
		<table class="w-full text-xs">
			<thead>
				<tr class="border-b border-line-2 text-ink-2 uppercase tracking-wide bg-surface-sunken/50">
					<th class="text-left px-3 py-2">{s.createdFs!.share_proto === 'NFS' ? 'IP/CIDR' : 'CephX ID'}</th>
					<th class="text-left px-3 py-2">{t('wizard.access.permission')}</th>
					<th class="text-left px-3 py-2">{t('wizard.access.status')}</th>
					{#if s.createdFs!.share_proto !== 'NFS'}<th class="text-left px-3 py-2">{t('wizard.access.accessKey')}</th>{/if}
				</tr>
			</thead>
			<tbody>
				{#each s.accessRules as rule (rule.id)}
					<tr class="border-b border-line last:border-0">
						<td class="px-3 py-2 font-mono text-ink-2">{rule.access_to}</td>
						<td class="px-3 py-2">
							<span class="px-1.5 py-0.5 rounded {rule.access_level === 'rw' ? 'bg-surface-selected/30 text-warm-text' : 'bg-surface-sunken text-ink-2'}">{rule.access_level}</span>
						</td>
						<td class="px-3 py-2 text-ink-2">{rule.state}</td>
						{#if s.createdFs!.share_proto !== 'NFS'}
							<td class="px-3 py-2">
								{#if rule.access_key}
									<div class="flex items-center gap-1.5">
										<code class="text-ink-2 font-mono truncate max-w-[120px]">{rule.access_key.slice(0, 12)}…</code>
										<button onclick={() => s.copyKey(rule.access_key!, rule.id)}
											class="text-ink-2 hover:text-ink-2 transition-colors">
											{s.copiedKey === rule.id ? '✓' : '⎘'}
										</button>
									</div>
								{:else}
									<span class="text-ink-2">{t('wizard.access.pending')}</span>
								{/if}
							</td>
						{/if}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<p class="text-xs text-ink-2 mb-4">{t('wizard.access.empty')}</p>
{/if}

<div class="flex justify-end gap-3 mt-2">
	<button onclick={s.closeWizard} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('wizard.actions.skip')}</button>
	<button onclick={s.closeWizard} class="px-5 py-2 bg-green-700 hover:bg-green-600 text-ink-0 text-sm font-medium rounded-lg transition-colors">{t('wizard.actions.finish')}</button>
</div>
