<script module lang="ts">
	export type CreateKind = 'network' | 'router' | 'instance' | 'loadbalancer' | 'database';
</script>

<script lang="ts">
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/topology';
	// 검색·화면 조작·범례는 고정 그룹으로 유지하고 구조 애니메이션은 명시적으로 켠다.
	import Button from '$lib/components/ui/Button.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import { compileRegexSearch } from '$lib/utils/regexSearch';

	interface Props {
		query?: string;
		flowOn?: boolean;
		/** prefers-reduced-motion: 패킷 흐름을 하드 off 하고 안내 문구를 보여준다 */
		reducedMotion?: boolean;
		/** 검색어가 없으면 null */
		matchCount?: number | null;
		searchElement?: HTMLInputElement | null;
		editable?: boolean;
		oncreate?: (kind: CreateKind) => void;
		createContextName?: string | null;
		onfit: () => void;
		onreset: () => void;
		onzoomin?: () => void;
		onzoomout?: () => void;
		onoverview?: () => void;
		ownershipOverview?: boolean;
		onlegend?: () => void;
		legendOpen?: boolean;
		oncreatenetwork?: () => void;
		oncreaterouter?: () => void;
		oncreateinstance?: () => void;
		oncreateloadbalancer?: () => void;
		oncreatedatabase?: () => void;
		onsearchkeydown?: (event: KeyboardEvent) => void;

	}
	let {
		query = $bindable(''),
		flowOn = $bindable(false),
		reducedMotion = false,
		matchCount = null,
		searchElement = $bindable(null),
		editable = false,
		oncreate,
		createContextName = null,
		onfit,
		onreset,
		onzoomin,
		onzoomout,
		onoverview,
		ownershipOverview = false,
		onlegend,
		legendOpen = false,
		oncreatenetwork,
		oncreaterouter,
		oncreateinstance,
		oncreateloadbalancer,
		oncreatedatabase,
		onsearchkeydown,
	}: Props = $props();

	const flowHintId = 'topology-canvas-flow-hint';
	const compiled = $derived(compileRegexSearch(query));
</script>


<div class="toolbar">
	<div class="search">
		<Field for="topology-canvas-search" label={t('toolbar.searchLabel')} help={tc('table.regexHelp')} error={compiled.error ? tc('table.regexError') : undefined}>
		<TextInput
			id="topology-canvas-search"
			ariaInvalid={compiled.error}
			bind:value={query}
			bind:element={searchElement}
			type="search"
			ariaLabel={t('toolbar.searchLabel')}
			placeholder={t('toolbar.search')}
			class="search-input"
			onkeydown={onsearchkeydown}
		/>
		</Field>
		{#if matchCount != null}
			<span class="search-count" aria-hidden="true">{t('toolbar.matchCount', { count: matchCount })}</span>
		{/if}
	</div>
	<div class="view-actions" role="group" aria-label={t('toolbar.viewControls')}>
		{#if onoverview}<Button variant="secondary" size="sm" ariaPressed={ownershipOverview} onclick={onoverview}>{t('overview.title')}</Button>{/if}
		{#if onzoomin}<Button variant="secondary" size="sm" ariaLabel={t('canvas.zoomIn')} onclick={onzoomin}>+</Button>{/if}
		{#if onzoomout}<Button variant="secondary" size="sm" ariaLabel={t('canvas.zoomOut')} onclick={onzoomout}>−</Button>{/if}
		<Button variant="secondary" size="sm" onclick={onfit}>{t('toolbar.fit')}</Button>
		{#if onlegend}<Button variant="secondary" size="sm" dataTour="topology-legend-toggle" ariaExpanded={legendOpen} onclick={onlegend}>{t('canvasLegend.label')}</Button>{/if}
	</div>
	<div class="animation">
		<label class="check" class:is-disabled={reducedMotion}>
			<input type="checkbox" bind:checked={flowOn} disabled={reducedMotion} aria-describedby={flowHintId} />
			{t('toolbar.packetFlow')}
		</label>
		<span class="hint" id={flowHintId}>{t(reducedMotion ? 'toolbar.reducedMotion' : 'toolbar.animationNote')}</span>
	</div>
	<div class="actions">
		{#if oncreate}
			<div class="create" role="group" aria-label={t('toolbar.createLabel')}>
				<span class="hint">{t('toolbar.create')}</span>
				<Button variant="primary" size="sm" onclick={() => oncreate?.('network')}>{t('toolbar.network')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('router')}>{t('toolbar.router')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('instance')}>{t('toolbar.instance')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('loadbalancer')}>{t('toolbar.loadBalancer')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('database')}>{t('toolbar.database')}</Button>
				{#if createContextName}
					<span class="hint"><RichText segments={t.rich('toolbar.createContext', { name: createContextName })} /></span>
				{/if}
			</div>
		{:else if editable}
			<Button variant="primary" size="sm" onclick={oncreatenetwork}>{t('toolbar.network')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreaterouter}>{t('toolbar.router')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreateinstance}>{t('toolbar.instance')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreateloadbalancer}>{t('toolbar.loadBalancer')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreatedatabase}>{t('toolbar.database')}</Button>
		{/if}
		<Button variant="secondary" size="sm" onclick={onreset}>{t('toolbar.reset')}</Button>
	</div>
</div>

<style>
	.toolbar { display: flex; flex-wrap: wrap; gap: 0.5rem 0.75rem; align-items: center; }
	.search { position: relative; flex: 1 1 16rem; min-width: min(12rem, 100%); }
	.search :global(.search-input) { padding-right: 3.5rem; font-size: 0.875rem; }
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
		font-size: 0.8125rem;
		color: var(--color-ink-1);
		cursor: pointer;
		user-select: none;
		min-height: 36px;
	}
	.check input { accent-color: var(--color-accent); width: 0.875rem; height: 0.875rem; margin: 0; }
	.check input:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: 2px; }
	.check.is-disabled { opacity: 0.5; cursor: not-allowed; }
	.hint { font-size: 0.8125rem; color: var(--color-ink-2); }
	.view-actions { display: flex; flex-wrap: wrap; gap: 0.375rem; align-items: center; }
	.toolbar :global(.btn) { min-height: 36px; }
	.animation { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem 0.75rem; flex-basis: 100%; }
	.actions { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; width: 100%; }
	.create { display: flex; flex-wrap: wrap; gap: 0.375rem; align-items: center; }
	@media (max-width: 767px) {
		.search { flex-basis: 100%; }
		.check { min-height: 44px; }
		.toolbar :global(.btn) { min-height: 44px; }
		.actions { margin-left: 0; }
		.create { flex-basis: 100%; }
	}
</style>
