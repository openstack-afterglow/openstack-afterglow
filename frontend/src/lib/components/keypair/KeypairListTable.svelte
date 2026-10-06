<script lang="ts">
	import type { Keypair } from '$lib/types/keypair';
	import { t } from '$lib/i18n/ns/images-keys';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	let {
		keypairs,
		deleting,
		copiedFingerprint,
		onCopy,
		onDelete,
	}: {
		keypairs: Keypair[];
		deleting: string | null;
		copiedFingerprint: string | null;
		onCopy: (fp: string) => void;
		onDelete: (name: string) => Promise<void>;
	} = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg overflow-hidden">
	<div class="grid grid-cols-[1fr_auto] md:grid-cols-[1.2fr_140px_2fr_120px] px-4 py-2.5 border-b border-line text-xs uppercase tracking-wider text-ink-2 font-medium">
		<div>{t('keypairTable.columns.name')}</div>
		<div class="hidden md:block">{t('keypairTable.columns.type')}</div>
		<div class="hidden md:block">{t('keypairTable.columns.fingerprint')}</div>
		<div class="text-right">{t('keypairTable.columns.actions')}</div>
	</div>
	{#each keypairs as kp, i (kp.name)}
		<div class="motion-enter grid grid-cols-[1fr_auto] md:grid-cols-[1.2fr_140px_2fr_120px] px-4 py-3 text-[13px] items-center {i < keypairs.length - 1 ? 'border-b border-line' : ''} hover:bg-surface-sunken/30 transition-colors" style="--motion-index: {i}">
			<div class="text-ink-0 font-medium flex items-center gap-2.5 min-w-0">
				<svg class="w-4 h-4 text-violet-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
				</svg>
				<span class="truncate">{kp.name}</span>
			</div>
			<div class="hidden md:block">
				<span class="text-xs font-mono px-2 py-0.5 rounded-md bg-violet-900/25 border border-violet-800 text-violet-400">{kp.type}</span>
			</div>
			<div class="hidden md:block text-ink-2 font-mono text-xs truncate">{kp.fingerprint}</div>
			<div class="flex gap-1.5 justify-end">
				<button
					onclick={() => onCopy(kp.fingerprint)}
					class="text-xs px-2 py-1 rounded-md bg-surface-sunken hover:bg-surface-selected text-ink-1 border border-line-2 transition-colors"
				>{copiedFingerprint === kp.fingerprint ? t('keypairTable.actions.copied') : t('keypairTable.actions.copy')}</button>
				<button
					onclick={() => onDelete(kp.name)}
					disabled={deleting === kp.name}
					class="text-xs px-2 py-1 rounded-md bg-transparent hover:bg-red-950/40 text-red-400 border border-red-900 disabled:text-ink-3 disabled:border-line-2 transition-colors"
				>{#if deleting === kp.name}<ActivityIndicator size="xs" label={t('keypairTable.actions.deleting')} />{:else}{t('keypairTable.actions.delete')}{/if}</button>
			</div>
		</div>
	{/each}
</div>
