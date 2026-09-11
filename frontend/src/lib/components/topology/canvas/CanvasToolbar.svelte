<script lang="ts">
	// 캔버스 상단 툴바: 검색, 패킷 흐름(옵트인 시뮬레이션), 화면 맞춤, 배치 초기화.
	import Button from '$lib/components/ui/Button.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';

	interface Props {
		query?: string;
		flowOn?: boolean;
		/** prefers-reduced-motion: 패킷 흐름을 하드 off 하고 안내 문구를 보여준다 */
		reducedMotion?: boolean;
		/** 검색어가 없으면 null */
		matchCount?: number | null;
		searchElement?: HTMLInputElement | null;
		onfit: () => void;
		onreset: () => void;
		onsearchkeydown?: (event: KeyboardEvent) => void;
	}

	let {
		query = $bindable(''),
		flowOn = $bindable(false),
		reducedMotion = false,
		matchCount = null,
		searchElement = $bindable(null),
		onfit,
		onreset,
		onsearchkeydown,
	}: Props = $props();

	const flowHintId = 'topology-canvas-flow-hint';
</script>

<div class="toolbar">
	<div class="search">
		<TextInput
			bind:value={query}
			bind:element={searchElement}
			type="search"
			ariaLabel="토폴로지 검색"
			placeholder="이름 · IP · CIDR · MAC 검색…"
			class="search-input"
			onkeydown={onsearchkeydown}
		/>
		{#if matchCount != null}
			<span class="search-count" aria-hidden="true">{matchCount}건</span>
		{/if}
	</div>
	<label class="check" class:is-disabled={reducedMotion}>
		<input type="checkbox" bind:checked={flowOn} disabled={reducedMotion} aria-describedby={reducedMotion ? flowHintId : undefined} />
		패킷 흐름 <span class="hint">(시뮬레이션)</span>
	</label>
	{#if reducedMotion}
		<span class="hint" id={flowHintId}>시스템 '동작 줄이기' 설정으로 패킷 애니메이션이 비활성화됩니다</span>
	{/if}
	<div class="actions">
		<Button variant="secondary" size="sm" onclick={onfit}>화면 맞춤</Button>
		<Button variant="secondary" size="sm" onclick={onreset}>배치 초기화</Button>
	</div>
</div>

<style>
	.toolbar { display: flex; flex-wrap: wrap; gap: 0.5rem 0.75rem; align-items: center; }
	.search { position: relative; flex: 1 1 16rem; min-width: 12rem; }
	.search :global(.search-input) { padding-right: 3.5rem; font-size: 0.8125rem; }
	.search-count {
		position: absolute;
		right: 0.625rem;
		top: 50%;
		transform: translateY(-50%);
		font-size: 0.75rem;
		color: var(--color-ink-2);
		pointer-events: none;
	}
	.check {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.75rem;
		color: var(--color-ink-1);
		cursor: pointer;
		user-select: none;
	}
	.check input { accent-color: var(--color-accent); width: 0.875rem; height: 0.875rem; margin: 0; }
	.check input:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: 2px; }
	.check.is-disabled { opacity: 0.5; cursor: not-allowed; }
	.hint { font-size: 0.75rem; color: var(--color-ink-2); }
	.actions { display: flex; gap: 0.5rem; align-items: center; margin-left: auto; }
	@media (max-width: 767px) {
		.search { flex-basis: 100%; }
		.actions { margin-left: 0; }
	}
</style>
