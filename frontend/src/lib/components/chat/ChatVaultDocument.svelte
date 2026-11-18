<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { vaultApi, type VaultDocument } from '$lib/api/chatVault';
	import { t } from '$lib/i18n/ns/chat-settings';
	import { toast } from '$lib/stores/toast';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';

	let { token, projectId, canRead, isCurrent }: { token: string; projectId: string; canRead: boolean; isCurrent: () => boolean } = $props();
	let snapshot = $state.raw<VaultDocument | null>(null);
	let loading = $state(true);
	let started = false;
	const lifetime = new AbortController();
	const current = () => !lifetime.signal.aborted && isCurrent();
	onDestroy(() => lifetime.abort());

	async function load() {
		if (!canRead || !current()) return;
		loading = true;
		try {
			const next = await vaultApi(token, projectId, lifetime.signal).document();
			if (current()) snapshot = next;
		} catch {
			if (current()) snapshot = null;
		} finally {
			if (current()) loading = false;
		}
	}

	$effect(() => {
		if (!canRead || started) return;
		started = true;
		void untrack(load);
	});

	async function copy(doc: VaultDocument) {
		try {
			await navigator.clipboard.writeText(doc.content);
			if (current()) toast.success(t('settings.memory.copied', { filename: doc.filename }));
		} catch {
			if (current()) toast.error(t('settings.memory.copyFailed', { filename: doc.filename }));
		}
	}

	function download(doc: VaultDocument) {
		const url = URL.createObjectURL(new Blob([doc.content], { type: `${doc.content_type};charset=utf-8` }));
		const link = document.createElement('a');
		link.href = url;
		link.download = doc.filename;
		link.click();
		setTimeout(() => URL.revokeObjectURL(url), 0);
	}
</script>

<section class="space-y-2 border-y border-[var(--color-line)] py-3">
	<header class="flex flex-wrap items-center justify-between gap-2">
		<h3 class="font-mono text-sm font-semibold">memory.md</h3>
		{#if snapshot}
			{@const doc = snapshot}
			<div class="flex flex-wrap gap-1">
				<Button variant="ghost" size="sm" onclick={() => copy(doc)}>{t('settings.memory.copy')}</Button>
				<Button variant="ghost" size="sm" onclick={() => download(doc)}>{t('settings.memory.download')}</Button>
			</div>
		{/if}
	</header>
	{#if loading}
		<LoadingState variant="inline" label={t('settings.memory.documentLoading', { filename: 'memory.md' })} />
	{:else if snapshot}
		<!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users must be able to scroll the bounded preview.) -->
		<pre class="max-h-56 overflow-auto whitespace-pre-wrap break-words bg-surface-sunken p-3 font-mono text-xs text-[var(--color-ink-1)]" tabindex="0" role="region" aria-label={t('settings.memory.documentContent', { filename: snapshot.filename })}>{snapshot.content}</pre>
	{:else}
		<Alert flat>{t('settings.vault.documentFailed')}</Alert>
		<Button variant="secondary" size="sm" onclick={load}>{t('settings.vault.retry')}</Button>
	{/if}
</section>
