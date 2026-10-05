<script lang="ts">
	import { wizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import ToggleGroup, { type ToggleOption } from '$lib/components/ui/ToggleGroup.svelte';
	import { t } from '$lib/i18n/ns/vm-wizard';
	import RichText from '$lib/i18n/RichText.svelte';

	const s = useVmCreate();
	const squashfsEligible = $derived(s.squashfsEligible);
	const squashfsModeOptions: ToggleOption[] = $derived([
		{ value: 'profile', label: t('libraryStep.profileMode') },
		{ value: 'artifacts', label: t('libraryStep.artifactsMode') },
	]);

	function selectSquashfsMode(value: string) {
		if (value === 'profile' || value === 'artifacts') s.selectSquashfsMode(value);
	}

	$effect(() => {
		const hasLegacySelection =
			$wizard.libraries.length > 0 ||
			$wizard.templateName !== null ||
			$wizard.templateVersion !== null ||
			$wizard.strategy !== null;
		const hasInvalidSquashfsSelection = !squashfsEligible && $wizard.squashfsMode;
		if (!hasLegacySelection && !hasInvalidSquashfsSelection) return;
		wizard.update(w => ({
			...w,
			libraries: [],
			templateName: null,
			templateVersion: null,
			strategy: null,
			...(squashfsEligible ? {} : { squashfsMode: null, layerProfileName: null, layerArtifactIds: [] }),
		}));
	});
</script>

{#if squashfsEligible}
	{#snippet subtitle(text: string)}<span class="text-sm font-normal text-[var(--color-ink-2)]">{text}</span>{/snippet}
	<h2 class="mb-1 text-lg font-semibold text-[var(--color-ink-0)]"><RichText segments={t.rich('libraryStep.heading')} tags={{ subtitle }} /></h2>

	<div class="mb-5 rounded-xl border border-[var(--color-line-2)] bg-[var(--color-surface-raised)] p-4">
		<div class="flex items-start justify-between gap-4 mb-3">
			<div>
				<p class="text-sm font-semibold text-[var(--color-ink-0)]">{t('libraryStep.squashfsTitle')}</p>
				<p class="mt-1 text-xs leading-5 text-[var(--color-ink-2)]">{t('libraryStep.compatibilityDescription')}</p>
			</div>
			{#if $wizard.squashfsMode}
				<button
					class="shrink-0 text-xs text-[var(--color-ink-2)] transition-colors hover:text-[var(--color-ink-0)] focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
					onclick={() => s.clearSquashfsSelection()}
				>{t('libraryStep.clearSelection')}</button>
			{/if}
		</div>

		<ToggleGroup
			value={$wizard.squashfsMode}
			options={squashfsModeOptions}
			onchange={selectSquashfsMode}
			ariaLabel={t('libraryStep.selectionMethod')}
			fullWidth
		/>

		{#if $wizard.squashfsMode === 'profile'}
			<div class="space-y-2">
				{#each s.squashfsProfiles as profile (profile.name)}
					{@const baseId = profile.base_image?.base_image_id}
					{@const disabled = Boolean(baseId && baseId !== $wizard.imageId)}
					<button
						class="w-full rounded-lg border px-3 py-3 text-left transition-colors {profile.name === $wizard.layerProfileName ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10' : 'border-[var(--color-line)] bg-[var(--color-surface-base)]'} {disabled ? 'cursor-not-allowed opacity-50' : 'hover:border-[var(--color-line-2)]'}"
						disabled={disabled}
						onclick={() => s.selectSquashfsProfile(profile.name)}
					>
						<span class="block text-sm font-medium text-[var(--color-ink-0)]">{profile.name}</span>
						<span class="mt-1 block text-xs text-[var(--color-ink-2)]">{t('libraryStep.profileSummary', { count: profile.layers.length, baseImage: profile.base_image?.base_image_name ?? baseId ?? t('libraryStep.baseImageUnknown') })}</span>
					</button>
				{/each}
				{#if s.squashfsProfiles.length === 0}
					<p class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3 text-sm text-[var(--color-ink-2)]">{t('libraryStep.noProfiles')}</p>
				{/if}
			</div>
		{:else if $wizard.squashfsMode === 'artifacts'}
			<div class="space-y-2 max-h-72 overflow-y-auto pr-1">
				{#each s.squashfsArtifacts as artifact (artifact.id)}
					{@const disabled = Boolean(artifact.base_image_id && artifact.base_image_id !== $wizard.imageId)}
					<label class="flex items-start gap-3 rounded-lg border px-3 py-3 {disabled ? 'border-[var(--color-line)] bg-[var(--color-surface-base)] opacity-50' : 'border-[var(--color-line)] bg-[var(--color-surface-base)] hover:border-[var(--color-line-2)]'}">
						<input
							type="checkbox"
							class="mt-1 h-4 w-4 rounded border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] accent-[var(--color-accent)]"
							disabled={disabled}
							checked={$wizard.layerArtifactIds.includes(artifact.id)}
							onchange={() => s.toggleSquashfsArtifact(artifact.id)}
						/>
						<span>
							<span class="block text-sm font-medium text-[var(--color-ink-0)]">{artifact.name}</span>
							<span class="mt-1 block text-xs text-[var(--color-ink-2)]">{t('libraryStep.artifactSummary', { parent: artifact.parent_id ?? t('libraryStep.root'), baseImage: artifact.base_image_name ?? artifact.base_image_id ?? t('libraryStep.baseImageUnknown') })}</span>
						</span>
					</label>
				{/each}
				{#if s.squashfsArtifacts.length === 0}
					<p class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3 text-sm text-[var(--color-ink-2)]">{t('libraryStep.noArtifacts')}</p>
				{/if}
			</div>
		{:else}
			<p class="text-sm text-[var(--color-ink-2)]">{t('libraryStep.noModeDescription')}</p>
		{/if}

		{#if s.squashfsBaseMismatch}
			<p class="mt-3 text-xs text-[var(--color-state-danger)]">{t('libraryStep.baseMismatch')}</p>
		{/if}
	</div>
{/if}
