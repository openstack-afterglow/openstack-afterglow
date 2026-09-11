<script lang="ts">
	import type { AvailableModel } from '$lib/api/chatTree';
	import Button from '$lib/components/ui/Button.svelte';
	import { toast } from '$lib/stores/toast';
	import ModelCapabilityBadges from './ModelCapabilityBadges.svelte';

	interface Props {
		open: boolean;
		models: AvailableModel[];
		value: string;
		onSelect: (modelName: string) => void;
		onClose: () => void;
	}
	let { open, models, value, onSelect, onClose }: Props = $props();

	let query = $state('');
	let activeProvider = $state<string | null>(null);

	interface Group {
		provider: string;
		models: AvailableModel[];
	}
	const providerCounts = $derived.by(() => {
		const counts = new Map<string, number>();
		for (const model of models) {
			const provider = model.provider ?? '기타';
			counts.set(provider, (counts.get(provider) ?? 0) + 1);
		}
		return counts;
	});
	const providers = $derived(
		[...providerCounts.keys()].sort((left, right) => left.localeCompare(right, 'ko'))
	);
	const showProviderNav = $derived(providers.length > 1);
	$effect(() => {
		if (activeProvider !== null && !providers.includes(activeProvider)) activeProvider = null;
	});

	function apiModelName(model: AvailableModel): string {
		return model.api_model_name || model.model_name;
	}

	function apiProvider(model: AvailableModel): string {
		return model.api_provider || model.provider || 'unknown';
	}
	const grouped = $derived.by((): Group[] => {
		const q = query.trim().toLowerCase();
		const match = (m: AvailableModel) =>
			(!q ||
				m.display_name.toLowerCase().includes(q) ||
				apiModelName(m).toLowerCase().includes(q) ||
				apiProvider(m).toLowerCase().includes(q) ||
				(m.provider ?? '').toLowerCase().includes(q)) &&
			(activeProvider === null || (m.provider ?? '기타') === activeProvider);
		const byProvider = new Map<string, AvailableModel[]>();
		for (const m of models) {
			if (!match(m)) continue;
			const key = m.provider ?? '기타';
			const arr = byProvider.get(key);
			if (arr) arr.push(m);
			else byProvider.set(key, [m]);
		}
		return [...byProvider.entries()].map(([provider, models]) => ({ provider, models }));
	});
	function providerCount(provider: string): number {
		return providerCounts.get(provider) ?? 0;
	}
	const total = $derived(grouped.reduce((n, g) => n + g.models.length, 0));

	function pick(m: AvailableModel) {
		onSelect(m.model_name);
		onClose();
	}

	async function copyModelName(modelName: string) {
		try {
			await navigator.clipboard.writeText(modelName);
			toast.success('API 모델 ID가 복사되었습니다');
		} catch {
			toast.error('모델 ID를 복사하지 못했습니다. 클립보드 권한을 확인해 주세요.');
		}
	}
</script>

<svelte:window onkeydown={(e) => open && e.key === 'Escape' && onClose()} />

{#if open}
	<button
		type="button"
		class="overlay"
		tabindex="-1"
		aria-label="닫기"
		onclick={onClose}
	></button>
	<div class="panel" role="dialog" aria-label="모델 선택" aria-describedby="model-picker-help" aria-modal="true">
		<header class="head">
			<h2>모델 선택</h2>
			<button type="button" class="close" onclick={onClose} aria-label="닫기">
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round" /></svg>
			</button>
		</header>

		<div class="search">
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
			<!-- svelte-ignore a11y_autofocus -->
			<input type="text" placeholder="모델 검색 (이름·API ID·프로바이더)" bind:value={query} autofocus />
		</div>
		<p id="model-picker-help" class="help">API ID를 <code>model</code>에 사용하세요. 같은 ID가 여러 경로에 있으면 provider도 함께 지정하세요.</p>

		<div class="picker-body" class:with-providers={showProviderNav}>
			{#if showProviderNav}
				<nav class="provider-nav" aria-label="모델 프로바이더">
					<button
						type="button"
						class:active={activeProvider === null}
						aria-pressed={activeProvider === null}
						onclick={() => (activeProvider = null)}
					>
						<span>전체 모델</span>
						<span class="provider-count">{models.length}</span>
					</button>
					{#each providers as provider (provider)}
						<button
							type="button"
							class:active={activeProvider === provider}
							aria-pressed={activeProvider === provider}
							onclick={() => (activeProvider = provider)}
						>
							<span>{provider}</span>
							<span class="provider-count">{providerCount(provider)}</span>
						</button>
					{/each}
				</nav>
			{/if}
			<div class="list">
				{#if total === 0}
					<p class="empty">검색 결과가 없습니다</p>
				{:else}
					{#each grouped as g (g.provider)}
						<div class="group-label">{g.provider}</div>
						{#each g.models as m (m.model_name)}
							<div class="model-row" class:active={m.model_name === value}>
								<button
									type="button"
									class="model-select"
									aria-label={`${m.display_name} 모델 선택`}
									aria-pressed={m.model_name === value}
									onclick={() => pick(m)}
								>
									<span class="model-main">
										<span class="model-name" title={m.display_name}>{m.display_name}</span>
										<span class="model-id">API ID: <code>{apiModelName(m)}</code></span>
										<span class="model-provider">provider: <code>{apiProvider(m)}</code></span>
									</span>
									<span class="model-caps"><ModelCapabilityBadges caps={m.capabilities} size="xs" /></span>
									{#if m.model_name === value}
										<svg class="check" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>
									{/if}
								</button>
								<Button
									variant="ghost"
									size="sm"
									class="min-h-11 shrink-0"
									ariaLabel={`${apiModelName(m)} API 모델 ID 복사`}
									title={`API model: ${apiModelName(m)}`}
									onclick={() => copyModelName(apiModelName(m))}
								>
									ID 복사
								</Button>
							</div>
						{/each}
					{/each}
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in oklab, var(--color-ink-0) 55%, transparent);
		z-index: 50;
		border: none;
	}
	/* 다크 테마에서는 밝은 ink 토큰이 아닌 canvas를 섞어 회색 막을 방지한다. */
	:global(:root:not(.light)) .overlay {
		background: color-mix(in oklab, var(--color-surface-canvas) 68%, transparent);
	}
	.panel {
		position: fixed;
		inset: 50% auto auto 50%;
		transform: translate(-50%, -50%);
		width: min(56rem, 94vw);
		height: min(80vh, 44rem);
		background: var(--color-surface-base);
		border: 1px solid var(--color-line);
		border-radius: 1rem;
		z-index: 51;
		display: flex;
		flex-direction: column;
		box-shadow: 0 24px 64px color-mix(in oklab, var(--color-ink-0) 30%, transparent);
		overflow: hidden;
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.1rem 0.7rem;
	}
	.head h2 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.close {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border-radius: 0.45rem;
		border: none;
		background: transparent;
		color: var(--color-ink-3);
		cursor: pointer;
	}
	.close:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0 1.1rem 0.6rem;
		padding: 0.6rem 0.8rem;
		border-radius: 0.7rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		color: var(--color-ink-3);
	}
	.search input {
		flex: 1;
		min-width: 0;
		border: none;
		outline: none;
		background: transparent;
		color: var(--color-ink-0);
		font-size: 0.9rem;
	}
	.search input::placeholder {
		color: var(--color-ink-3);
	}
	.help {
		margin: 0 1.1rem 0.6rem;
		font-size: 0.75rem;
		color: var(--color-ink-2);
	}
	.picker-body {
		display: flex;
		flex: 1;
		min-height: 0;
		flex-direction: column;
	}
	.provider-nav {
		display: flex;
		max-height: 7rem;
		flex-shrink: 0;
		flex-wrap: wrap;
		gap: 0.25rem;
		overflow-y: auto;
		padding: 0.15rem 0.75rem 0.65rem;
		border-bottom: 1px solid var(--color-line);
	}
	.provider-nav button {
		display: inline-flex;
		min-height: 2.5rem;
		max-width: 100%;
		flex-shrink: 0;
		align-items: center;
		justify-content: space-between;
		gap: 0.65rem;
		padding: 0.45rem 0.65rem;
		border: 1px solid transparent;
		border-radius: 0.55rem;
		background: transparent;
		color: var(--color-ink-2);
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
		white-space: nowrap;
	}
	.provider-nav button > span:first-child {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.provider-nav button:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.provider-nav button:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.provider-nav button.active {
		border-color: var(--color-line-strong);
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
	}
	.provider-count {
		color: var(--color-ink-3);
		font-family: var(--font-mono);
		font-size: 0.68rem;
		flex-shrink: 0;
	}
	.list {
		flex: 1;
		min-width: 0;
		min-height: 0;
		overflow-y: auto;
		padding: 0 0.6rem 0.8rem;
	}
	.empty {
		padding: 2rem;
		text-align: center;
		color: var(--color-ink-3);
		font-size: 0.85rem;
	}
	.group-label {
		padding: 0.7rem 0.6rem 0.35rem;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-ink-3);
	}
	.model-row {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		width: 100%;
		padding: 0.25rem 0.5rem 0.25rem 0;
		border: 1px solid transparent;
		border-radius: 0.6rem;
		background: transparent;
	}
	.model-row:hover {
		background: var(--color-surface-sunken);
	}
	.model-row.active {
		background: var(--color-surface-raised);
		border-color: var(--color-accent);
	}
	.model-select {
		flex: 1;
		min-width: 0;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.7rem;
		border: none;
		border-radius: 0.5rem;
		background: transparent;
		cursor: pointer;
		text-align: left;
	}
	.model-select:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.model-caps {
		grid-column: 1;
		grid-row: 2;
	}
	.model-caps:empty {
		display: none;
	}
	.model-main {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.model-name {
		font-size: 0.88rem;
		font-weight: 600;
		color: var(--color-ink-0);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.model-id {
		font-size: 0.75rem;
		color: var(--color-ink-2);
		overflow-wrap: anywhere;
	}
	.model-id code {
		font-family: var(--font-mono);
	}
	.model-provider {
		font-size: 0.7rem;
		color: var(--color-ink-3);
		overflow-wrap: anywhere;
	}
	.model-provider code {
		font-family: var(--font-mono);
	}
	.check {
		grid-column: 2;
		grid-row: 1 / 3;
		flex-shrink: 0;
		color: var(--color-accent);
	}
	@media (min-width: 768px) {
		.picker-body.with-providers {
			display: grid;
			grid-template-columns: 12rem minmax(0, 1fr);
		}
		.provider-nav {
			min-width: 0;
			flex-direction: column;
			max-height: none;
			flex-wrap: nowrap;
			overflow-x: visible;
			overflow-y: auto;
			padding: 0.25rem 0.6rem 0.8rem;
			border-right: 1px solid var(--color-line);
			border-bottom: none;
		}
		.provider-nav button {
			width: 100%;
		}
		.model-select {
			display: flex;
			gap: 0.7rem;
		}
		.model-caps {
			flex-shrink: 0;
		}
	}
</style>
