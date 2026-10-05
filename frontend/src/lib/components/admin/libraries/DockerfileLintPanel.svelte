<script module lang="ts">
	export interface DockerfileLintDiagnostic { line: number | null; message: string }
	export interface DockerfileLintCompletion { ref: string; id: string; name: string; ubuntu_base: string; created_at: string | null }
	export interface DockerfileLintResponse {
		valid: boolean;
		diagnostics: DockerfileLintDiagnostic[];
		warnings: DockerfileLintDiagnostic[];
		from: {
			line: number | null; ref: string | null; kind: 'glance_name' | 'glance_id' | 'ubuntu_tag' | 'palimpsest' | null;
			image: { id: string; name: string; ubuntu_base: string; min_disk: number; visibility: string } | null;
			parent: { id: number; name: string; blob_digest: string | null; ubuntu_base: string; base_image_name: string | null; chain_depth: number } | null;
			completions: DockerfileLintCompletion[]; error: string | null; note: string | null;
		};
		layers: { new: number; inherited: number; total: number; limit: number; by_instruction: Record<string, number> };
	}
</script>

<script lang="ts">
  import { t } from '$lib/i18n/ns/palimpsest-admin';
	import { onDestroy } from 'svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let { lint, loading, requestError }: { lint: DockerfileLintResponse | null; loading: boolean; requestError: string } = $props();
	let copiedRef = $state('');
	let copyError = $state('');
	let resetTimer: ReturnType<typeof setTimeout> | undefined;

	async function copyRef(ref: string) {
		copyError = '';
		copiedRef = '';
		if (resetTimer) clearTimeout(resetTimer);
		try {
			await navigator.clipboard.writeText(`FROM ${ref}`);
			copiedRef = ref;
			resetTimer = setTimeout(() => { copiedRef = ''; }, 1500);
		} catch {
			copyError = t('lint.copyFailed');
		}
	}
	onDestroy(() => { if (resetTimer) clearTimeout(resetTimer); });
</script>

<section aria-label={t('lint.title')} class="min-w-0 space-y-3 rounded-lg border border-line-2 bg-surface-base p-3 text-xs">
	<div class="flex flex-wrap items-center justify-between gap-2">
		<h3 class="font-semibold text-ink-0">{t('lint.title')}</h3>
		{#if loading}
			<Pill tone="neutral">{t('lint.checking')}</Pill>
		{:else if requestError}
			<Pill tone="danger">{t('lint.failed')}</Pill>
		{:else if lint?.diagnostics.length}
			<Pill tone="danger">{t('lint.errors', { count: lint.diagnostics.length })}</Pill>
		{:else if lint?.from.error}
			<Pill tone="warning">{t('lint.unresolved')}</Pill>
		{:else if lint?.valid}
			<Pill tone="success">{t('lint.valid', { count: lint.layers.total })}</Pill>
		{:else}
			<Pill tone="neutral">{t('lint.waiting')}</Pill>
		{/if}
	</div>
	{#if requestError}
		<Alert tone="danger">{t('lint.requestFailed', { detail: requestError })}</Alert>
	{/if}
	{#if lint}
		{#if lint.diagnostics.length}
			<Alert tone="danger" title={t('lint.syntaxError')}>
				<ul class="space-y-1">
					{#each lint.diagnostics as diagnostic}
						<li class="break-words">{#if diagnostic.line !== null}<code class="font-mono">L{diagnostic.line}</code> {/if}{diagnostic.message}</li>
					{/each}
				</ul>
			</Alert>
		{/if}
		{#if lint.from.kind === 'palimpsest' && lint.from.parent}
			<p class="break-words text-ink-1">{t('lint.parent', { name: lint.from.parent.name, id: lint.from.parent.id, base: lint.from.parent.ubuntu_base, count: lint.from.parent.chain_depth })}</p>
		{:else if lint.from.image}
			<div class="space-y-1 text-ink-1">
				<p class="break-words">{t('lint.image', { ref: lint.from.ref, name: lint.from.image.name, base: lint.from.image.ubuntu_base, id: lint.from.image.id.slice(0, 8), disk: lint.from.image.min_disk, visibility: lint.from.image.visibility })}</p>
				{#if lint.from.note}<p class="text-ink-2">{lint.from.note}</p>{/if}
			</div>
		{/if}
		{#if lint.from.error}
			<Alert tone="warning" title={t('lint.fromFailed')}>
				<p class="break-words">{lint.from.error}</p>
				{#if lint.from.completions.length}
					<p class="mt-2">{t('lint.availableFrom')}</p>
					<ul class="mt-1 space-y-2">
						{#each lint.from.completions as completion (completion.id)}
							<li class="flex min-w-0 flex-wrap items-center gap-2 border-b border-line-2 pb-2 last:border-0 last:pb-0">
								<code class="min-w-0 break-all select-all font-mono">FROM {completion.ref}</code>
								<span class="min-w-0 break-words text-ink-2">{completion.name} · {completion.ubuntu_base}{completion.created_at ? ` · ${completion.created_at.slice(0, 10)}` : ''}</span>
								<Button variant="subtle" size="xs" onclick={() => copyRef(completion.ref)}>{copiedRef === completion.ref ? t('lint.copied') : t('lint.copy')}</Button>
							</li>
						{/each}
					</ul>
					{#if copyError}<p class="mt-2 text-xs" role="alert">{copyError}</p>{/if}
				{/if}
			</Alert>
		{/if}
		<p class="break-words text-ink-1">{t('lint.layerEstimate', { newCount: lint.layers.new, instructions: Object.entries(lint.layers.by_instruction).map(([name, count]) => `${name} ${count}`).join(' · '), hasInherited: lint.layers.inherited > 0 ? 'yes' : 'no', inherited: lint.layers.inherited, total: lint.layers.total, limit: lint.layers.limit })}</p>
		{#if lint.warnings.length}
			<Alert tone="warning">
				<ul class="space-y-1">{#each lint.warnings as warning}<li class="break-words">{warning.message}</li>{/each}</ul>
			</Alert>
		{/if}
	{:else if !loading && !requestError}
		<p class="text-xs text-ink-2">{t('lint.help')}</p>
	{/if}
</section>
