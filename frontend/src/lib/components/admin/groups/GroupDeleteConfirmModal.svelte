<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { Group } from '$lib/types/adminGroup';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as tc } from '$lib/i18n/ns/common';

	interface Props {
		target: Group | null;
		deleting: boolean;
		error: string;
		onConfirm: () => Promise<void>;
	}

	let { target = $bindable(), deleting, error, onConfirm }: Props = $props();
</script>

{#snippet nameTag(text: string)}<span class="text-ink-0 font-medium">{text}</span>{/snippet}

{#if target}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (target = null) }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (() => { target = null; })(); }}
		role="dialog" aria-modal="true"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('groupDelete.title')}</h2>
			<p class="text-sm text-ink-2 mb-4"><RichText segments={t.rich('groupDelete.body', { name: target.name })} tags={{ name: nameTag }} /></p>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="flex justify-end gap-3">
				<button onclick={() => { target = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{tc('actions.cancel')}</button>
				<button aria-busy={deleting} onclick={onConfirm} disabled={deleting} class="px-4 py-2 bg-[var(--color-state-danger)]/10 hover:bg-[var(--color-state-danger)]/20 text-[var(--color-state-danger-text)] text-sm font-medium rounded-lg disabled:opacity-30">{#if deleting}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('state.deleting')}</span>{:else}{t('actions.delete')}{/if}</button>
			</div>
		</div>
	</div>
{/if}
