<script lang="ts">
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/network-pages';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	let {
		open = $bindable(),
		creating,
		error,
		onCreate,
	}: {
		open: boolean;
		creating: boolean;
		error: string;
		onCreate: (form: { name: string; description: string }) => Promise<boolean>;
	} = $props();

	let form = $state({ name: '', description: '' });

	async function handleCreate() {
		const ok = await onCreate(form);
		if (ok) {
			form = { name: '', description: '' };
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }} class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; }}
		role="dialog" aria-modal="true" tabindex="-1">
		<div class="motion-pop bg-surface-sunken border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4" onclick={(e) => e.stopPropagation()} role="none">
			<h3 class="text-lg font-semibold text-ink-0 mb-4">{t('securityGroupCreate.title')}</h3>
			<div class="space-y-3 mb-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1">{t('securityGroupCreate.name')}
						<input bind:value={form.name} placeholder={t('securityGroupCreate.namePlaceholder')}
							class="w-full bg-surface-selected border border-line-2 rounded px-3 py-2 text-sm text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none mt-1" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">{t('securityGroupCreate.description')}
						<input bind:value={form.description} placeholder={t('securityGroupCreate.descriptionPlaceholder')}
							class="w-full bg-surface-selected border border-line-2 rounded px-3 py-2 text-sm text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none mt-1" />
					</label>
				</div>
			</div>
			{#if error}
				<p class="text-xs text-red-400 mb-3">{error}</p>
			{/if}
			<div class="flex gap-2">
				<button onclick={handleCreate} disabled={creating || !form.name.trim()} aria-busy={creating}
					class="flex-1 inline-flex items-center justify-center gap-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm py-2 rounded transition-colors">
					{#if creating}<ActivityIndicator size="xs" tone="ink" />{/if}{creating ? t('securityGroupCreate.creating') : t('securityGroupCreate.create')}
				</button>
				<button onclick={() => { open = false; }}
					class="flex-1 bg-surface-selected hover:bg-surface-selected text-ink-2 text-sm py-2 rounded transition-colors">{t('securityGroupCreate.cancel')}</button>
			</div>
		</div>
	</div>
{/if}
