<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-chat';
	import type { Snippet } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import {
		effectiveBasis, imageBasis, imageFollowsMedia, imagePricingReady, imageReadinessMessage, imageReservationDerived, imageVariants, inputTokenOnly,
		IMAGE_TEXT_FIELDS, manualImagePrice, MODEL_LABELS, TOKEN_FIELDS, visibleImagePrice,
		type ImagePriceLeaf, type ImagePricingDraft, type ImagePricingReadiness, type ModelKind, type PricingDraft
	} from './modelPricing';
	let {
		kind, draft = $bindable(), imageDraft = $bindable(), useImageCatalog = false, hasImageAudio = false, providerType, readiness = null,
		prefix, disabled = false, textPricing, hasStoredTextPrices = false
	}: {
		kind: ModelKind; draft: PricingDraft; imageDraft?: ImagePricingDraft; useImageCatalog?: boolean; hasImageAudio?: boolean;
		providerType?: string; readiness?: ImagePricingReadiness | null; prefix: string; disabled?: boolean; textPricing?: Snippet; hasStoredTextPrices?: boolean
	} = $props();
	type Modality = 'text' | 'image' | 'audio';
	const modalities: Modality[] = ['text', 'image', 'audio'];
	const inputOnly = $derived(inputTokenOnly(kind));
	const primary = $derived<Modality>(kind === 'text' || inputOnly ? 'text' : 'audio');
	const basis = $derived(effectiveBasis(kind, draft));
	const orderedModalities = $derived<Modality[]>([primary, ...modalities.filter((modality) => modality !== primary)]);
	// Visibility is not a pricing mutation. Keep drafts and stored/unknown leaves intact.
	let selection = $state<{ kind: ModelKind; basis: string; values: Modality[] } | null>(null);
	const selected = $derived<Modality[]>(selection?.kind === kind && selection.basis === basis ? selection.values : modalities.filter((modality) =>
		(modality === primary && basis === 'tokens') || (modality === 'text' ? hasStoredTextPrices : Object.values(draft.tokens[modality]).some((value) => value !== ''))
	));
	function modalityLabel(modality: Modality): string {
		return modality === 'text' ? t('pricing.textTokenRates') : t('pricing.modalityTokenRates', { modality: modality === 'image' ? t('configuration.image') : t('pricing.audio') });
	}
	const timePrefix = $derived(kind === 'realtime' ? 'realtime' : 'audio');
	const directions = $derived(kind === 'tts' ? ['output'] : kind === 'stt' ? ['input'] : ['input', 'output']);
	const timeKeys = $derived([...directions.map((direction) => `${timePrefix}_${direction}_per_${direction === 'input' ? draft.inputUnit : draft.outputUnit}`), ...(kind === 'realtime' ? [`realtime_session_per_${draft.sessionUnit}`] : [])]);
	const storedTimeKeys = $derived(Object.keys(draft.rates).filter((key) => /_per_(second|minute|hour)$/.test(key) && draft.rates[key] !== '' && !timeKeys.includes(key)));
	function resetOfficial(field: ImagePriceLeaf, id: string) {
		field.manual = null;
		document.getElementById(id)?.focus();
	}
	const IMAGE_MODALITY = ['image'] as const;
	const IMAGE_AUDIO_MODALITIES = ['image', 'audio'] as const;
</script>

{#snippet provenance(field: ImagePriceLeaf, follows: boolean, id: string, label: string)}
	{#if follows}
		<!-- Reserve the row for every catalog-backed field so sibling inputs stay aligned. -->
		<div class="flex min-h-9 min-w-0 flex-wrap items-center justify-between gap-x-1 text-xs">
			{#if field.official !== null}
				<span id="{id}-source" class="text-ink-2">{manualImagePrice(field) === null ? t('pricing.officialPrice') : t('pricing.manualPrice')}</span>
				{#if manualImagePrice(field) !== null}
					<Button type="button" variant="ghost" size="xs" {disabled} ariaLabel={t('pricing.resetOfficialField', { field: label })} onclick={() => resetOfficial(field, id)}>{t('pricing.resetOfficial')}</Button>
				{/if}
			{/if}
		</div>
	{/if}
{/snippet}

{#snippet imageRate(field: ImagePriceLeaf, follows: boolean, id: string, label: string, help: string)}
	<Field {label} for={id} {help}>
		<TextInput {id} inputmode="decimal" value={visibleImagePrice(field, follows)}
			placeholder={follows ? field.official ?? undefined : undefined}
			ariaDescribedBy={follows && field.official !== null ? `${id}-message ${id}-source` : undefined}
			oninput={(event) => { field.manual = (event.currentTarget as HTMLInputElement).value; }} {disabled} />
		{@render provenance(field, follows, id, label)}
	</Field>
{/snippet}

{#snippet imagePricing(prices: ImagePricingDraft)}
	{@const follows = imageFollowsMedia(prices, useImageCatalog)}
	{@const selectedBasis = imageBasis(prices, useImageCatalog)}
	{@const audio = hasImageAudio || Object.values(prices.tokens.audio).some((field) => visibleImagePrice(field, follows))}
	{#if prices.legacy}
		<div class="space-y-1 border-y border-line py-2 text-xs text-ink-2">
			<p class="font-semibold">{t('pricing.imageLegacyManual')}</p>
			<label class="flex min-h-9 cursor-pointer items-center gap-2">
				<input type="checkbox" bind:checked={prices.convert} {disabled} />
				{t('pricing.imageConvertOverrides')}
			</label>
		</div>
	{/if}
	<fieldset aria-describedby="{prefix}-basis-help">
		<legend class="text-sm font-semibold text-ink-1">{t('pricing.imageBillingBasis')}</legend>
		<div class="flex flex-wrap gap-x-4">
			{#each [{ value: 'tokens', label: t('pricing.imageTokenUnit') }, { value: 'unit', label: t('pricing.imageUnit') }] as option (option.value)}
				<label class="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-ink-1">
					<input type="radio" name="{prefix}-billing-basis" id="{prefix}-basis-{option.value}" value={option.value} checked={selectedBasis === option.value}
						{disabled} onchange={() => { prices.basis.manual = option.value; }} />
					{option.label}
				</label>
			{/each}
		</div>
		{@render provenance(prices.basis, follows, `${prefix}-basis-${prices.basis.official}`, t('pricing.imageBillingBasis'))}
		<p id="{prefix}-basis-help" class="text-xs leading-relaxed text-ink-2">{t('pricing.imageBasisHelp')}</p>
	</fieldset>
	{#if imageReadinessMessage(readiness)}
		<Alert tone="warning">{imageReadinessMessage(readiness)}</Alert>
	{/if}
	{#if selectedBasis === 'tokens'}
		<fieldset class="min-w-0 border-t border-line pt-2">
			<legend class="pr-2 text-sm font-semibold text-ink-1">{t('pricing.imageTextTokens')}</legend>
			<div class="grid gap-3 sm:grid-cols-2">
				{#each IMAGE_TEXT_FIELDS as field (field.key)}
					{@render imageRate(prices.text[field.key], useImageCatalog, `${prefix}-text-${field.key}`, field.label, t('configuration.usd1mTokens'))}
				{/each}
			</div>
		</fieldset>
		{#each audio ? IMAGE_AUDIO_MODALITIES : IMAGE_MODALITY as modality (modality)}
			<fieldset class="min-w-0 border-t border-line pt-2">
				<legend class="pr-2 text-sm font-semibold text-ink-1">{modality === 'image' ? t('pricing.imageTokens') : modalityLabel(modality)}</legend>
				<div class="grid gap-3 sm:grid-cols-3">
					{#each TOKEN_FIELDS as field (field.key)}
						{@render imageRate(prices.tokens[modality][field.key], follows, `${prefix}-${modality}-${field.key}`, field.label, t('configuration.usd1mTokens'))}
					{/each}
				</div>
				{#if modality === 'image'}
					<p id="{prefix}-image-cache-help" class="mt-2 text-xs leading-relaxed text-ink-2">{t('pricing.imageCachedInputHelp')}</p>
				{/if}
			</fieldset>
		{/each}
		<p class="text-xs leading-relaxed text-ink-2" class:font-semibold={!imagePricingReady(prices, useImageCatalog)}>{t('pricing.imageTokenReadiness')}</p>
		{@render imageRate(prices.rates.reservation_usd, follows, `${prefix}-reservation-usd`, t('pricing.reservationCap'),
			t(imageReservationDerived(providerType) ? 'pricing.imageDerivedReservation' : 'pricing.reservationHelp'))}
	{:else}
		{@render imageRate(prices.rates.image_per_unit, follows, `${prefix}-image_per_unit`, t('pricing.imageBaseRate'), t('pricing.imageBaseHelp'))}
		<p class="text-xs leading-relaxed text-ink-2" class:font-semibold={!imagePricingReady(prices, useImageCatalog)}>{t('pricing.imageVariantHelp')}</p>
		{#if readiness?.supported_variants.length}
			<p class="text-xs leading-relaxed text-ink-2">{t('pricing.imageSupportedVariants', { variants: readiness.supported_variants.join(', ') })}</p>
		{/if}
		{#if prices.stored?.reservation_usd && manualImagePrice(prices.basis) === 'unit'}
			<p class="text-xs text-ink-2">{t('pricing.imageUnitClearsReservation')}</p>
		{/if}
		{#each imageVariants(prices, follows) as row (row.id)}
			<div class="grid items-start gap-2 sm:grid-cols-[1fr_1fr_auto]">
				<Field label={t('configuration.imageVariantName')} for="{prefix}-variant-{row.id}-key"
					error={readiness?.unsupported_variants.includes(row.name.trim()) ? t('pricing.imageVariantUnsupported') : undefined}>
					<TextInput id="{prefix}-variant-{row.id}-key" placeholder="1024x1024:high" bind:value={row.name} disabled={disabled || (follows && row.rate.official !== null)}
						ariaInvalid={readiness?.unsupported_variants.includes(row.name.trim())} />
				</Field>
				{@render imageRate(row.rate, follows, `${prefix}-variant-${row.id}-price`, t('configuration.imageVariantRate'), t('configuration.usdImage'))}
				{#if !follows || row.rate.official === null}
					<Button type="button" variant="ghost" size="xs" class="mt-5" {disabled} onclick={() => { prices.variants = prices.variants.filter((item) => item.id !== row.id); }}>{t('configuration.delete')}</Button>
				{/if}
			</div>
		{/each}
		<Button type="button" variant="secondary" size="sm" {disabled} onclick={() => { prices.variants.push({ id: Math.max(-1, ...prices.variants.map((row) => row.id)) + 1, name: '', rate: { manual: '', official: null } }); }}>{t('configuration.addVariant')}</Button>
	{/if}
{/snippet}

<div class="mt-4 space-y-4" data-testid="{prefix}-media-pricing">
	{#if kind === 'image' && imageDraft}
		{@render imagePricing(imageDraft)}
	{:else}
	{#if !inputOnly}
		<fieldset>
			<legend class="text-xs leading-relaxed text-ink-2">{t('pricing.tokenRatesHelp')}</legend>
			<div class="mt-2 flex flex-wrap gap-x-4 gap-y-2">
				{#each orderedModalities as modality (modality)}
					<label class="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-ink-1 md:min-h-9">
						<input type="checkbox" checked={selected.includes(modality)} {disabled} aria-controls="{prefix}-{modality}-pricing" onchange={(event) => {
							selection = { kind, basis, values: event.currentTarget.checked ? [...selected, modality] : selected.filter((value) => value !== modality) };
						}} />
						{modalityLabel(modality)}
					</label>
				{/each}
			</div>
		</fieldset>
	{/if}
	{#if kind !== 'text' && !inputOnly}
		<Field label={t('pricing.billingBasis', { kind: MODEL_LABELS[kind] })} for="{prefix}-billing-basis">
			<SelectInput id="{prefix}-billing-basis" bind:value={draft.basis} {disabled}>
				<option value="">{t('pricing.defaultBasis', { basis: t('pricing.time') })}</option>
				<option value="duration">{t('pricing.audioDuration')}</option>
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
	{#each orderedModalities as modality (modality)}
		{#if inputOnly ? modality === 'text' : selected.includes(modality)}
			<div id="{prefix}-{modality}-pricing" class="border-t border-line pt-3" role="group" aria-labelledby="{prefix}-{modality}-tokens">
				<p id="{prefix}-{modality}-tokens" class="mb-3 text-sm font-semibold text-ink-1">{modalityLabel(modality)}</p>
				{#if modality === 'text'}
					{@render textPricing?.()}
				{:else}
				<div class="mt-3 grid gap-3 sm:grid-cols-3">
					{#each TOKEN_FIELDS as field (field.key)}
						<Field label={t('pricing.modalityDirection', { modality: modality === 'image' ? t('configuration.image') : t('pricing.audio'), direction: field.label })} for="{prefix}-{modality}-{field.key}" help={t('configuration.usd1mTokens')}>
						<TextInput id="{prefix}-{modality}-{field.key}" inputmode="decimal" bind:value={draft.tokens[modality as 'image' | 'audio'][field.key]} {disabled} />
						</Field>
					{/each}
				</div>
				{/if}
			</div>
		{/if}
	{/each}
	{/if}
</div>
