<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	interface Props {
		type: 'live' | 'cold';
		onClose: () => void;
	}

	let { type, onClose }: Props = $props();

	const s = useInstanceDetailController();

	let migrateHost = $state('');

	// CPU 모델 안내 문구
	const cpuModelHint = $derived(
		type === 'cold'
			? t('migrate.allHostsHint')
			: s.migrateHosts.length > 0 && s.migrateHosts[0].cpu_model
				? t('migrate.compatibleHostsHint', { cpuModel: s.migrateHosts[0].cpu_model })
				: null
	);

	async function handleMigrate() {
		const ok = await s.doMigrate(type, migrateHost);
		if (ok) onClose();
	}
</script>

{#snippet hostHint(text: string)}<span class="text-ink-2">{text}</span>{/snippet}

<Modal open={true} onClose={onClose} labelledBy="instance-migrate-title">
	<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h2 id="instance-migrate-title" class="text-lg font-semibold text-ink-0 mb-1">
			{type === 'live' ? t('migrate.liveTitle') : t('migrate.coldTitle')}
		</h2>
		<p class="text-xs text-ink-2 mb-5">
			{type === 'live' ? t('migrate.liveDescription') : t('migrate.coldDescription')}
		</p>
		{#if s.migrateError}
			<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{s.migrateError}</div>
		{/if}
		<div class="space-y-4">
			<div>
				<div class="flex items-baseline justify-between mb-1.5">
					<label for="migrate-host" class="text-xs text-ink-2 uppercase tracking-wide">
						<RichText segments={t.rich('migrate.targetHost')} tags={{ hint: hostHint }} />
					</label>
					{#if cpuModelHint}
						<span class="text-xs text-ink-2">{cpuModelHint}</span>
					{/if}
				</div>
				{#if s.migrateHosts.length === 0}
					<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-xs text-ink-2">
						{t('migrate.noCompatibleHosts')}
					</div>
				{:else}
					<select id="migrate-host" bind:value={migrateHost} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
						<option value="">{t('migrate.automatic')}</option>
						{#each s.migrateHosts as h}
							<option value={h.name}>{h.name}</option>
						{/each}
					</select>
				{/if}
			</div>
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('migrate.cancel')}</button>
			<button onclick={handleMigrate} disabled={s.migrateLoading} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg disabled:opacity-30">
				{#if s.migrateLoading}<ActivityIndicator size="xs" label={t('migrate.migrating')} />{:else}{t('migrate.submit')}{/if}
			</button>
		</div>
	</div>
</Modal>
