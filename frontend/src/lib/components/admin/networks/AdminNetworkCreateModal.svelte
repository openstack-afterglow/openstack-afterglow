<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
	import RichText from '$lib/i18n/RichText.svelte';
		import { dialogFocus } from '$lib/utils/dialogFocus';

	let {
		open = $bindable(),
		onCreate,
	}: {
		open: boolean;
		onCreate: (form: { name: string; cidr: string; is_external: boolean; is_shared: boolean; enable_dhcp: boolean }) => Promise<string | true>;
	} = $props();

	let form = $state({ name: '', cidr: '', is_external: false, is_shared: false, enable_dhcp: true });
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		if (!open) {
			form = { name: '', cidr: '', is_external: false, is_shared: false, enable_dhcp: true };
			error = '';
			creating = false;
		}
	});

	async function submit() {
		creating = true;
		error = '';
		const result = await onCreate({ ...form });
		if (result === true) {
			open = false;
		} else {
			error = result;
		}
		creating = false;
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (() => { open = false; })(); }}
		role="dialog" aria-modal="true"
		tabindex="-1"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('adminNetworkCreateModal.title')}</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminnetworkcreatemodal-48">{t('adminNetworkCreateModal.name')}</label>
					<input id="field-adminnetworkcreatemodal-48" bind:value={form.name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div>
					{#snippet cidrHelp(text: string)}<span class="text-ink-2">{text}</span>{/snippet}
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminnetworkcreatemodal-52"><RichText segments={t.rich('adminNetworkCreateModal.cidrLabel')} tags={{ help: cidrHelp }} /></label>
					<input id="field-adminnetworkcreatemodal-52" bind:value={form.cidr} type="text" placeholder={t('adminNetworkCreateModal.cidrPlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div class="flex items-center gap-4">
					<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
						<input type="checkbox" bind:checked={form.is_external} class="rounded" /> {t('adminNetworkCreateModal.externalNetwork')}
					</label>
					<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
						<input type="checkbox" bind:checked={form.is_shared} class="rounded" /> {t('adminNetworkCreateModal.shared')}
					</label>
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('adminNetworkCreateModal.cancel')}</button>
				<button onclick={submit} disabled={creating || !form.name} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">
					{creating ? t('adminNetworkCreateModal.creating') : t('adminNetworkCreateModal.create')}
				</button>
			</div>
		</div>
	</div>
{/if}
