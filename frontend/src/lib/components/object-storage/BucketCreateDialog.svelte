<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import { validateBucketName } from '$lib/utils/bucketName';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	let {
		open = $bindable(),
		onCreate,
	}: {
		open: boolean;
		onCreate: (name: string) => Promise<string | true>;
	} = $props();

	let name = $state('');
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		if (!open) {
			name = '';
			error = '';
			creating = false;
		}
	});

	async function submit() {
		const trimmed = name.trim();
		if (!trimmed) return;
		const validationError = validateBucketName(trimmed);
		if (validationError) {
			error = validationError;
			return;
		}
		creating = true;
		error = '';
		const result = await onCreate(trimmed);
		creating = false;
		if (result === true) {
			open = false;
		} else {
			error = result;
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => (open = false)}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('buckets.createDialog.title')}</h2>
			<div class="space-y-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1" for="field-bucketcreatedialog-62">{t('buckets.createDialog.name')}</label>
					<input id="field-bucketcreatedialog-62"
						type="text"
						bind:value={name}
						placeholder={t('buckets.createDialog.placeholder')}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-indigo-500"
						onkeydown={(e) => e.key === 'Enter' && submit()}
					/>
				</div>
				{#if error}
					<p class="text-red-400 text-xs">{error}</p>
				{/if}
			</div>
			<div class="flex justify-end gap-2 mt-5">
				<button
					onclick={() => (open = false)}
					class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg transition-colors"
				>{t('buckets.createDialog.cancel')}</button>
				<button
					onclick={submit}
					disabled={creating || !name.trim()}
					class="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-500 disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 rounded-lg transition-colors"
				>{creating ? t('buckets.createDialog.creating') : t('buckets.createDialog.create')}</button>
			</div>
		</div>
	</div>
{/if}
