<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { NetworkInfo } from '$lib/types/networks';
	import AdminProjectPicker from '$lib/components/admin/domains/AdminProjectPicker.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/admin-network';
	import RichText from '$lib/i18n/RichText.svelte';

	let {
		open = $bindable(),
		allNetworks,
		creating,
		error,
		onCreate,
	}: {
		open: boolean;
		allNetworks: NetworkInfo[];
		creating: boolean;
		error: string;
		onCreate: (form: { network_id: string; name: string; project_id: string; fixed_ip: string }) => Promise<boolean>;
	} = $props();

	let form = $state({ network_id: '', name: '', project_id: '', fixed_ip: '' });
	let targetDomainId = $state('');

	// Reset form when modal opens
	$effect(() => {
		if (open) {
			form = { network_id: '', name: '', project_id: '', fixed_ip: '' };
			targetDomainId = '';
		}
	});


	async function handleCreate() {
		const success = await onCreate({ ...form });
		if (success) {
			form = { network_id: '', name: '', project_id: '', fixed_ip: '' };
			targetDomainId = '';
		}
	}
</script>

{#snippet optionalText(text: string)}<span class="text-ink-2">{text}</span>{/snippet}

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
			<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('portCreateModal.title')}</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-portcreatemodal-72">{t('portCreateModal.networkLabel')}</label>
					<select id="field-portcreatemodal-72" bind:value={form.network_id} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
						<option value="">{t('portCreateModal.networkPlaceholder')}</option>
						{#each allNetworks as n (n.id)}
							<option value={n.id}>{n.name || n.id.slice(0, 12)}</option>
						{/each}
					</select>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-portcreatemodal-81">{t('portCreateModal.nameLabel')}</label>
					<input id="field-portcreatemodal-81" bind:value={form.name} type="text" placeholder={t('portCreateModal.namePlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<AdminProjectPicker domainId={targetDomainId} projectId={form.project_id} disabled={creating}
					emptyProjectLabel={t('portCreateModal.projectPlaceholder')}
					onchange={(domainId, projectId) => { targetDomainId = domainId; form.project_id = projectId; }} />
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-portcreatemodal-108"><RichText segments={t.rich('portCreateModal.fixedIpLabel')} tags={{ optional: optionalText }} /></label>
					<input id="field-portcreatemodal-108" bind:value={form.fixed_ip} type="text" placeholder={t('portCreateModal.fixedIpPlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('portCreateModal.cancel')}</button>
				<button aria-busy={creating} onclick={handleCreate} disabled={creating || !form.network_id || (!!targetDomainId && !form.project_id)} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{#if creating}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('portCreateModal.creating')}</span>{:else}{t('portCreateModal.create')}{/if}</button>
			</div>
		</div>
	</div>
{/if}
