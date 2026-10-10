<script lang="ts">
	import { t } from '$lib/i18n/ns/account';
	import { betaFeatures, setBetaFeature } from '$lib/stores/betaFeatures';

	const validatingFeatures = [
		{ key: 'keyManager', get label() { return t('beta.keyManagerLabel'); }, get description() { return t('beta.keyManagerDescription'); } },
		{ key: 'volumeSnapshots', get label() { return t('beta.volumeSnapshotsLabel'); }, get description() { return t('beta.volumeSnapshotsDescription'); } },
		{ key: 'fileStorageSnapshots', get label() { return t('beta.fileStorageSnapshotsLabel'); }, get description() { return t('beta.fileStorageSnapshotsDescription'); } },
		{ key: 'fileStorageShareNetworks', get label() { return t('beta.shareNetworksLabel'); }, get description() { return t('beta.shareNetworksDescription'); } },
		{ key: 'fileStorageSecurityServices', get label() { return t('beta.securityServicesLabel'); }, get description() { return t('beta.securityServicesDescription'); } },
	] as const;
</script>

<section class="motion-fade bg-surface-base border border-line rounded-xl p-5">
	<div class="mb-5">
		<p class="text-sm font-semibold text-ink-0">{t('beta.title')}</p>
		<p class="text-xs text-ink-2 mt-1">
			{t('beta.localOnly')}
		</p>
	</div>

	<div class="space-y-6">
		<div class="space-y-4">
			<label class="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface-canvas/40 px-4 py-3">
				<span>
					<span class="block text-sm font-medium text-ink-1">{t('beta.libraryLabel')}</span>
					<span class="block text-xs text-ink-2 mt-1">{t('beta.libraryDescription')}</span>
				</span>
				<input
					type="checkbox"
					aria-label={t('beta.libraryLabel')}
					class="mt-1 h-4 w-4 rounded border-line-2 bg-surface-sunken text-blue-600 focus:ring-line-2"
					checked={$betaFeatures.libraryConsume}
					onchange={(event) => setBetaFeature('libraryConsume', event.currentTarget.checked)}
				/>
			</label>

			<label class="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface-canvas/40 px-4 py-3">
				<span>
					<span class="block text-sm font-medium text-ink-1">{t('beta.haLabel')}</span>
					<span class="block text-xs text-ink-2 mt-1">{t('beta.haDescription')}</span>
				</span>
				<input
					type="checkbox"
					aria-label={t('beta.haLabel')}
					class="mt-1 h-4 w-4 rounded border-line-2 bg-surface-sunken text-blue-600 focus:ring-line-2"
					checked={$betaFeatures.haDeploy}
					onchange={(event) => setBetaFeature('haDeploy', event.currentTarget.checked)}
				/>
			</label>
		</div>

		<div class="space-y-4">
			<div>
				<p class="text-sm font-semibold text-ink-0">{t('beta.validatingTitle')}</p>
				<p class="beta-feature-description text-xs mt-1">{t('beta.validatingDescription')}</p>
			</div>

			{#each validatingFeatures as feature}
				<label class="beta-feature-card flex items-start justify-between gap-4 rounded-lg px-4 py-3">
					<span>
						<span class="beta-feature-title block text-sm font-medium">{feature.label}</span>
						<span class="beta-feature-description block text-xs mt-1">{feature.description}</span>
					</span>
					<input
						type="checkbox"
						aria-label={feature.label}
						class="beta-feature-checkbox mt-1 h-4 w-4 rounded"
						checked={$betaFeatures[feature.key]}
						onchange={(event) => setBetaFeature(feature.key, event.currentTarget.checked)}
					/>
				</label>
			{/each}
		</div>
	</div>
</section>

<style>
	.beta-feature-card {
		border: 1px solid color-mix(in oklab, var(--color-warm) 24%, var(--color-line));
		background: color-mix(in oklab, var(--color-warm) 7%, var(--color-surface-raised));
	}

	.beta-feature-title {
		color: var(--color-ink-0);
	}

	.beta-feature-description {
		color: var(--color-ink-2);
	}

	.beta-feature-checkbox {
		border-color: var(--color-line-2);
		background: var(--color-surface-sunken);
		color: var(--color-warm);
		--tw-ring-color: color-mix(in oklab, var(--color-warm) 45%, transparent);
	}
</style>
