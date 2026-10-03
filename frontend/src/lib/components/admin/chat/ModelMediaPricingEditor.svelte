<script lang="ts">
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
		<Field label="{MODEL_LABELS[kind]} 과금 기준" for="{prefix}-billing-basis">
			<SelectInput id="{prefix}-billing-basis" bind:value={draft.basis} {disabled}>
				<option value="">기존 기본값 ({kind === 'image' ? '이미지 단위' : '시간'})</option>
				{#if kind === 'image'}<option value="unit">이미지 단위</option>{:else}<option value="duration">입력/출력 음성 시간</option>{/if}
				{#if kind === 'realtime'}<option value="session">세션 시간</option>{/if}
				{#if kind === 'tts'}<option value="characters">문자</option>{/if}
				<option value="tokens">토큰</option>
			</SelectInput>
		</Field>
		<p class="text-xs leading-relaxed text-ink-2">선택한 기준만 실행 요금에 사용됩니다. 토큰·도구 요금을 이미지·시간·문자·세션 요금에 자동으로 더하지 않습니다. 기준이나 시간 단위를 바꿔도 다른 저장 단가는 삭제되지 않습니다.</p>
		{#if basis === 'tokens'}
			<Field label="요청 전체 예약 상한" for="{prefix}-reservation-usd" help="USD · 0보다 큰 최대 자금 예약액, 사용 단가가 아닙니다.">
				<TextInput id="{prefix}-reservation-usd" inputmode="decimal" bind:value={draft.rates.reservation_usd} {disabled} />
			</Field>
			<p class="text-xs leading-relaxed text-ink-2">실제 공급자의 모달리티별 토큰 사용량으로만 정산합니다. 상세 사용량이 없으면 추정 청구하지 않으며 예약 금액이 미확정 상태로 남을 수 있습니다. OpenAI TTS 바이너리 응답은 토큰 사용량을 제공하지 않아 토큰 과금을 지원하지 않습니다. 단가 설정은 공급자 지원이나 실행 경로를 보장하지 않습니다.</p>
		{:else if draft.rates.reservation_usd}
			<Field label="저장된 요청 전체 예약 상한" for="{prefix}-reservation-usd" help="USD · 토큰 과금에서만 사용">
				<TextInput id="{prefix}-reservation-usd" inputmode="decimal" bind:value={draft.rates.reservation_usd} {disabled} />
			</Field>
		{/if}
		{#if kind === 'image'}
			<Field label="이미지 기본 단가" for="{prefix}-image_per_unit" help="USD / 이미지 1장 · 이미지 단위 과금에서만 사용">
				<TextInput id="{prefix}-image_per_unit" inputmode="decimal" bind:value={draft.rates.image_per_unit} {disabled} />
			</Field>
			<p class="text-xs text-ink-2">이미지 단위 과금의 현재 실행 경로는 정확한 size:quality variant 단가가 필요합니다 (USD / 장). 기본 단가만으로는 실행되지 않으며 토큰 과금에는 별도 예약 상한을 사용합니다.</p>
			{#each draft.variants as row (row.id)}
				<div class="flex flex-wrap gap-2">
					<TextInput ariaLabel="이미지 variant 이름" placeholder="1024x1024:high" bind:value={row.name} {disabled} />
					<TextInput ariaLabel="이미지 variant 단가" placeholder="USD / 이미지 1장" inputmode="decimal" bind:value={row.price} {disabled} />
					<Button variant="ghost" size="xs" {disabled} onclick={() => (draft.variants = draft.variants.filter((item) => item.id !== row.id))}>삭제</Button>
				</div>
			{/each}
			<Button variant="secondary" size="sm" {disabled} onclick={() => (draft.variants = [...draft.variants, { id: Math.max(-1, ...draft.variants.map((row) => row.id)) + 1, name: '', price: '' }])}>+ variant 추가</Button>
		{:else}
			{#if kind === 'realtime'}
				{@const key = `realtime_session_per_${draft.sessionUnit}`}
				<p class="text-sm font-semibold text-ink-1">세션 시간 단가</p>
				<p class="text-xs leading-relaxed text-ink-2">공급자에 연결된 세션의 실제 경과 시간으로 한 번만 정산하며 분 단위로 올림하지 않습니다. 음성 입력/출력 시간의 합과 다릅니다. 최대 세션 시간만큼 예약합니다. 이 설정은 미지원 모델의 실행 경로를 추가하지 않습니다.</p>
				<div class="grid gap-3 sm:grid-cols-2">
					<Field label="세션 시간 단위" for="{prefix}-session-time-unit">
						<SelectInput id="{prefix}-session-time-unit" bind:value={draft.sessionUnit} {disabled}>
							<option value="second">초</option><option value="minute">분</option><option value="hour">시간</option>
						</SelectInput>
					</Field>
					<Field label="세션 시간 단가" for="{prefix}-{key}" help="USD / {draft.sessionUnit} · 세션 과금에서만 사용">
						<TextInput id="{prefix}-{key}" inputmode="decimal" bind:value={draft.rates[key]} {disabled} />
					</Field>
				</div>
			{/if}
			<p class="text-sm font-semibold text-ink-1">입력/출력 음성 시간 단가</p>
			{#each directions as direction}
				{@const key = `${timePrefix}_${direction}_per_${direction === 'input' ? draft.inputUnit : draft.outputUnit}`}
				<div class="grid gap-3 sm:grid-cols-2">
					<Field label="{direction === 'input' ? '입력' : '출력'} 시간 단위" for="{prefix}-{direction}-time-unit">
						<SelectInput id="{prefix}-{direction}-time-unit" value={direction === 'input' ? draft.inputUnit : draft.outputUnit} {disabled} onchange={(event) => { const unit = (event.target as HTMLSelectElement).value as PricingDraft['inputUnit']; if (direction === 'input') draft.inputUnit = unit; else draft.outputUnit = unit; }}>
							<option value="second">초</option><option value="minute">분</option><option value="hour">시간</option>
						</SelectInput>
					</Field>
					<Field label="{direction === 'input' ? '입력' : '출력'} 시간 단가" for="{prefix}-{key}" help="USD / {direction === 'input' ? draft.inputUnit : draft.outputUnit} · 변환 없이 저장">
						<TextInput id="{prefix}-{key}" inputmode="decimal" bind:value={draft.rates[key]} {disabled} />
					</Field>
				</div>
			{/each}
			{#each storedTimeKeys as key (key)}
				<Field label="기존 시간 단가 · {key}" for="{prefix}-{key}" help="기존 값 유지 · 다른 단위와 충돌하면 명시적으로 비워 주세요. 자동 변환하지 않습니다.">
					<TextInput id="{prefix}-{key}" inputmode="decimal" bind:value={draft.rates[key]} {disabled} />
				</Field>
			{/each}
			{#if kind === 'tts'}
				<Field label="음성 생성 문자 단가" for="{prefix}-audio_per_character" help="USD / 글자 · 문자 과금에서만 사용">
					<TextInput id="{prefix}-audio_per_character" inputmode="decimal" bind:value={draft.rates.audio_per_character} {disabled} />
				</Field>
			{/if}
		{/if}
	{/if}
	<p class="text-xs leading-relaxed text-ink-2">토큰 단가는 USD / 1M tokens입니다. 빈 값은 미설정이며 명시적인 0과 다릅니다. 각 모달리티의 입력·캐시 입력·출력은 독립적입니다. 텍스트 단가는 별도 기존 열에 저장합니다.</p>
	{#each ['image', 'audio'] as modality}
		<div class="border-t border-line pt-3" role="group" aria-labelledby="{prefix}-{modality}-tokens">
			<p id="{prefix}-{modality}-tokens" class="text-sm font-semibold text-ink-1">{modality === 'image' ? '이미지' : '오디오'} 토큰 단가</p>
			<div class="mt-3 grid gap-3 sm:grid-cols-3">
				{#each TOKEN_FIELDS as field (field.key)}
					<Field label="{modality === 'image' ? '이미지' : '오디오'} {field.label}" for="{prefix}-{modality}-{field.key}" help="USD / 1M tokens">
						<TextInput id="{prefix}-{modality}-{field.key}" inputmode="decimal" bind:value={draft.tokens[modality as 'image' | 'audio'][field.key]} {disabled} />
					</Field>
				{/each}
			</div>
		</div>
	{/each}
</div>
