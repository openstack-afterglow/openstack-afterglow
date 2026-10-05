<script module lang="ts">
	export type CreateKind = 'network' | 'router' | 'instance' | 'loadbalancer' | 'database';
</script>

<script lang="ts">
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/topology';
	// 캔버스 상단 툴바: 검색, 패킷 흐름(기본 on 시뮬레이션), 화면 맞춤, 배치 초기화.
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
		editable?: boolean;
		oncreate?: (kind: CreateKind) => void;
		createContextName?: string | null;
		onfit: () => void;
		onreset: () => void;
		oncreatenetwork?: () => void;
		oncreaterouter?: () => void;
		oncreateinstance?: () => void;
		oncreateloadbalancer?: () => void;
		oncreatedatabase?: () => void;
		onsearchkeydown?: (event: KeyboardEvent) => void;

	}
	let {
		query = $bindable(''),
		flowOn = $bindable(true),
		reducedMotion = false,
		matchCount = null,
		searchElement = $bindable(null),
		editable = false,
		oncreate,
		createContextName = null,
		onfit,
		onreset,
		oncreatenetwork,
		oncreaterouter,
		oncreateinstance,
		oncreateloadbalancer,
		oncreatedatabase,
		onsearchkeydown,
	}: Props = $props();

	const flowHintId = 'topology-canvas-flow-hint';
</script>

{#snippet flowHint(text: string)}<span class="hint">{text}</span>{/snippet}

<div class="toolbar">
	<div class="search">
		<TextInput
			bind:value={query}
			bind:element={searchElement}
			type="search"
			ariaLabel={t('toolbar.searchLabel')}
			placeholder={t('toolbar.search')}
			class="search-input"
			onkeydown={onsearchkeydown}
		/>
		{#if matchCount != null}
			<span class="search-count" aria-hidden="true">{t('toolbar.matchCount', { count: matchCount })}</span>
		{/if}
	</div>
	<label class="check" class:is-disabled={reducedMotion}>
		<input type="checkbox" bind:checked={flowOn} disabled={reducedMotion} aria-describedby={reducedMotion ? flowHintId : undefined} />
		<RichText segments={t.rich('toolbar.packetFlow')} tags={{ hint: flowHint }} />
	</label>
	{#if reducedMotion}
		<span class="hint" id={flowHintId}>{t('toolbar.reducedMotion')}</span>
	{/if}
	<div class="actions">
		{#if oncreate}
			<div class="create" role="group" aria-label={t('toolbar.createLabel')}>
				<span class="hint">{t('toolbar.create')}</span>
				<Button variant="accent" size="sm" onclick={() => oncreate?.('network')}>{t('toolbar.network')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('router')}>{t('toolbar.router')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('instance')}>{t('toolbar.instance')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('loadbalancer')}>{t('toolbar.loadBalancer')}</Button>
				<Button variant="secondary" size="sm" onclick={() => oncreate?.('database')}>{t('toolbar.database')}</Button>
				{#if createContextName}
					<span class="hint"><RichText segments={t.rich('toolbar.createContext', { name: createContextName })} /></span>
				{/if}
			</div>
		{:else if editable}
			<Button variant="accent" size="sm" onclick={oncreatenetwork}>{t('toolbar.network')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreaterouter}>{t('toolbar.router')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreateinstance}>{t('toolbar.instance')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreateloadbalancer}>{t('toolbar.loadBalancer')}</Button>
			<Button variant="secondary" size="sm" onclick={oncreatedatabase}>{t('toolbar.database')}</Button>
		{/if}
		<Button variant="secondary" size="sm" onclick={onfit}>{t('toolbar.fit')}</Button>
		<Button variant="secondary" size="sm" onclick={onreset}>{t('toolbar.reset')}</Button>
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
	.create { display: flex; flex-wrap: wrap; gap: 0.375rem; align-items: center; }
	@media (max-width: 767px) {
		.search { flex-basis: 100%; }
		.actions { margin-left: 0; }
		.create { flex-basis: 100%; }
	}
</style>
