<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-chat';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import { effectiveBasis, MODEL_LABELS, TOKEN_FIELDS, type ModelKind, type PricingDraft } from './modelPricing';
	let { kind, draft = $bindable(), prefix, disabled = false }: { kind: ModelKind; draft: PricingDraft; prefix: string; disabled?: boolean } = $props();
	const basis = $derived(effectiveBasis(kind, draft));
	const timePrefix = $derived(kind === 'realtime' ? 'realtime' : 'audio');
	const directions = $derived(kind === 'tts' ? ['output'] : kind === 'stt' ? ['input'] : ['input', 'output']);
	const timeKeys = $derived([...directions.map((direction) => `${timePrefix}_${direction}_per_${direction === 'input' ? draft.inputUnit : draft.outputUnit}`), ...(kind === 'realtime' ? [`realtime_session_per_${draft.sessionUnit}`] : [])]);
	const storedTimeKeys = $derived(Object.keys(draft.rates).filter((key) => /_per_(second|minute|hour)$/.test(key) && draft.rates[key] !== '' && !timeKeys.includes(key)));
</script>

<div class="mt-4 space-y-4" data-testid="{prefix}-media-pricing">
	{#if kind !== 'text'}
		<Field label={t('pricing.billingBasis', { kind: MODEL_LABELS[kind] })} for="{prefix}-billing-basis">
			<SelectInput id="{prefix}-billing-basis" bind:value={draft.basis} {disabled}>
				<option value="">{t('pricing.defaultBasis', { basis: kind === 'image' ? t('pricing.imageUnit') : t('pricing.time') })}</option>
				{#if kind === 'image'}<option value="unit">{t('pricing.imageUnit')}</option>{:else}<option value="duration">{t('pricing.audioDuration')}</option>{/if}
				{#if kind === 'realtime'}<option value="session">{t('pricing.sessionDuration')}</option>{/if}
				{#if kind === 'tts'}<option value="characters">{t('pricing.characters')}</option>{/if}
				<option value="tokens">{t('pricing.tokens')}</option>
			</SelectInput>
		</Field>
		<p class="text-xs leading-relaxed text-ink-2">{t('pricing.basisHelp')}</p>
		{#if basis === 'tokens'}
			<Field label={t('pricing.reservationCap')} for="{prefix}-reservation-usd" help={t('pricing.reservationHelp')}>
				<TextInput id="{prefix}-reservation-usd" inputmode="decimal" bind:value={draft.rates.reservation_usd} {disabled} />
			</Field>
			<p class="text-xs leading-relaxed text-ink-2">{t('pricing.tokenBillingHelp')}</p>
		{:else if draft.rates.reservation_usd}
			<Field label={t('pricing.storedReservationCap')} for="{prefix}-reservation-usd" help={t('pricing.storedReservationHelp')}>
				<TextInput id="{prefix}-reservation-usd" inputmode="decimal" bind:value={draft.rates.reservation_usd} {disabled} />
			</Field>
		{/if}
		{#if kind === 'image'}
			<Field label={t('pricing.imageBaseRate')} for="{prefix}-image_per_unit" help={t('pricing.imageBaseHelp')}>
				<TextInput id="{prefix}-image_per_unit" inputmode="decimal" bind:value={draft.rates.image_per_unit} {disabled} />
			</Field>
			<p class="text-xs text-ink-2">{t('pricing.imageVariantHelp')}</p>
			{#each draft.variants as row (row.id)}
				<div class="flex flex-wrap gap-2">
					<TextInput ariaLabel={t('configuration.imageVariantName')} placeholder="1024x1024:high" bind:value={row.name} {disabled} />
					<TextInput ariaLabel={t('configuration.imageVariantRate')} placeholder={t('configuration.usdImage')} inputmode="decimal" bind:value={row.price} {disabled} />
					<Button variant="ghost" size="xs" {disabled} onclick={() => (draft.variants = draft.variants.filter((item) => item.id !== row.id))}>{t('configuration.delete')}</Button>
				</div>
			{/each}
			<Button variant="secondary" size="sm" {disabled} onclick={() => (draft.variants = [...draft.variants, { id: Math.max(-1, ...draft.variants.map((row) => row.id)) + 1, name: '', price: '' }])}>{t('configuration.addVariant')}</Button>
		{:else}
			{#if kind === 'realtime'}
				{@const key = `realtime_session_per_${draft.sessionUnit}`}
				<p class="text-sm font-semibold text-ink-1">{t('pricing.sessionRate')}</p>
				<p class="text-xs leading-relaxed text-ink-2">{t('pricing.sessionHelp')}</p>
				<div class="grid gap-3 sm:grid-cols-2">
					<Field label={t('pricing.sessionUnit')} for="{prefix}-session-time-unit">
						<SelectInput id="{prefix}-session-time-unit" bind:value={draft.sessionUnit} {disabled}>
							<option value="second">{t('pricing.second')}</option><option value="minute">{t('pricing.minute')}</option><option value="hour">{t('pricing.hour')}</option>
						</SelectInput>
					</Field>
					<Field label={t('pricing.sessionRate')} for="{prefix}-{key}" help={t('pricing.sessionRateHelp', { unit: t(`pricing.${draft.sessionUnit}`) })}>
						<TextInput id="{prefix}-{key}" inputmode="decimal" bind:value={draft.rates[key]} {disabled} />
					</Field>
				</div>
			{/if}
			<p class="text-sm font-semibold text-ink-1">{t('pricing.audioTimeRates')}</p>
			{#each directions as direction}
				{@const key = `${timePrefix}_${direction}_per_${direction === 'input' ? draft.inputUnit : draft.outputUnit}`}
				<div class="grid gap-3 sm:grid-cols-2">
					<Field label={t('pricing.directionUnit', { direction: direction === 'input' ? t('configuration.input') : t('configuration.output') })} for="{prefix}-{direction}-time-unit">
						<SelectInput id="{prefix}-{direction}-time-unit" value={direction === 'input' ? draft.inputUnit : draft.outputUnit} {disabled} onchange={(event) => { const unit = (event.target as HTMLSelectElement).value as PricingDraft['inputUnit']; if (direction === 'input') draft.inputUnit = unit; else draft.outputUnit = unit; }}>
							<option value="second">{t('pricing.second')}</option><option value="minute">{t('pricing.minute')}</option><option value="hour">{t('pricing.hour')}</option>
						</SelectInput>
					</Field>
					<Field label={t('pricing.directionRate', { direction: direction === 'input' ? t('configuration.input') : t('configuration.output') })} for="{prefix}-{key}" help={t('pricing.directionRateHelp', { unit: t(`pricing.${direction === 'input' ? draft.inputUnit : draft.outputUnit}`) })}>
						<TextInput id="{prefix}-{key}" inputmode="decimal" bind:value={draft.rates[key]} {disabled} />
					</Field>
				</div>
			{/each}
			{#each storedTimeKeys as key (key)}
				<Field label={t('pricing.storedTimeRate', { key })} for="{prefix}-{key}" help={t('pricing.storedTimeHelp')}>
					<TextInput id="{prefix}-{key}" inputmode="decimal" bind:value={draft.rates[key]} {disabled} />
				</Field>
			{/each}
			{#if kind === 'tts'}
				<Field label={t('configuration.speechGenerationCharacterRate')} for="{prefix}-audio_per_character" help={t('pricing.characterRateHelp')}>
					<TextInput id="{prefix}-audio_per_character" inputmode="decimal" bind:value={draft.rates.audio_per_character} {disabled} />
				</Field>
			{/if}
		{/if}
	{/if}
	<p class="text-xs leading-relaxed text-ink-2">{t('pricing.tokenRatesHelp')}</p>
	{#each ['image', 'audio'] as modality}
		<div class="border-t border-line pt-3" role="group" aria-labelledby="{prefix}-{modality}-tokens">
			<p id="{prefix}-{modality}-tokens" class="text-sm font-semibold text-ink-1">{t('pricing.modalityTokenRates', { modality: modality === 'image' ? t('configuration.image') : t('pricing.audio') })}</p>
			<div class="mt-3 grid gap-3 sm:grid-cols-3">
				{#each TOKEN_FIELDS as field (field.key)}
					<Field label={t('pricing.modalityDirection', { modality: modality === 'image' ? t('configuration.image') : t('pricing.audio'), direction: field.label })} for="{prefix}-{modality}-{field.key}" help={t('configuration.usd1mTokens')}>
						<TextInput id="{prefix}-{modality}-{field.key}" inputmode="decimal" bind:value={draft.tokens[modality as 'image' | 'audio'][field.key]} {disabled} />
					</Field>
				{/each}
			</div>
		</div>
	{/each}
</div>
