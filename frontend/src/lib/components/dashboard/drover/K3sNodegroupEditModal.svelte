<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { api, ApiError } from '$lib/api/client';
	import type { K3sFlavor, K3sNodegroup } from '$lib/types/k3s';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	let {
		clusterId,
		nodegroup,
		token,
		projectId,
		onClose,
		onSaved,
	}: {
		clusterId: string;
		nodegroup: K3sNodegroup;
		token?: string;
		projectId?: string;
		onClose: () => void;
		onSaved: (ng: K3sNodegroup) => void;
	} = $props();

	let form = $state({
		flavor_id: '',
		stampede_enabled: false,
		min_size: 0,
		max_size: 0,
	});
	let flavors = $state<K3sFlavor[]>([]);
	let saving = $state(false);
	let error = $state('');

	$effect(() => {
		form = {
			flavor_id: nodegroup.flavor_id ?? '',
			stampede_enabled: nodegroup.stampede_enabled,
			min_size: nodegroup.min_size,
			max_size: nodegroup.max_size,
		};
	});

	$effect(() => {
		void api.get<K3sFlavor[]>('/api/v1/flavors', token, projectId).then(f => { flavors = f; }).catch(() => {});
	});

	function flavorGpuCount(flavor: K3sFlavor): number {
		const direct = Number(flavor.gpu_count ?? flavor.extra_specs?.gpu_count ?? 0);
		if (Number.isFinite(direct) && direct > 0) return direct;
		const alias = flavor.extra_specs?.['pci_passthrough:alias'] ?? '';
		return alias.split(',').reduce((sum, entry) => {
			const [name, count] = entry.trim().split(':');
			if (!name || name.toLowerCase().includes('audio')) return sum;
			const parsed = Number(count ?? 1);
			return sum + (Number.isFinite(parsed) ? parsed : 1);
		}, 0);
	}

	async function save() {
		if (form.min_size > form.max_size) {
			error = t('nodegroupEdit.invalidRange');
			return;
		}
		if (form.stampede_enabled && !form.flavor_id) {
			error = t('nodegroupEdit.flavorRequired');
			return;
		}
		saving = true;
		error = '';
		try {
			const body: Record<string, unknown> = {
				flavor_id: form.flavor_id || null,
				stampede_enabled: form.stampede_enabled,
				min_size: Number(form.min_size),
				max_size: Number(form.max_size),
			};
			const ng = await api.patch<K3sNodegroup>(
				`/api/v1/k3s/clusters/${clusterId}/nodegroups/${nodegroup.id}`,
				body,
				token,
				projectId,
			);
			onSaved(ng);
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('nodegroupEdit.failed');
		} finally {
			saving = false;
		}
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={onClose}
	role="dialog" aria-modal="true"
	tabindex="-1"
>
	<div
		class="motion-enter bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
		onclick={(e) => e.stopPropagation()}
		role="none"
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-1">{t('nodegroupEdit.title')}</h2>
		<p class="text-xs text-ink-2 mb-5">{nodegroup.name}</p>

		<div class="space-y-4">
			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				{t(form.stampede_enabled ? 'nodegroup.flavorRequired' : 'nodegroup.flavorOptional')}
				<select
					bind:value={form.flavor_id}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
				>
					<option value="">{t('nodegroup.notSelected')}</option>
					{#each flavors as f}
						<option value={f.id}>{t('nodegroup.flavorOption', { name: f.name, cpus: f.vcpus, ram: Math.round(f.ram / 1024), gpu: flavorGpuCount(f) > 0 ? ` / GPU ${flavorGpuCount(f)}` : '' })}</option>
					{/each}
				</select>
			</label>

			<!-- Stampede 오토스케일 -->
			<div class="border border-line-2 rounded-lg p-3 bg-surface-sunken/50">
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2">
						<span class="text-sm font-medium text-ink-1">{t('nodegroup.autoscale')}</span>
						<span class="text-xs bg-yellow-900/60 text-yellow-400 border border-yellow-700/50 rounded px-1.5 py-0.5 leading-none">{t('state.development')}</span>
					</div>
					<button
						type="button"
						role="switch"
						aria-checked={form.stampede_enabled}
						aria-label={t('nodegroup.autoscale')}
						onclick={() => form.stampede_enabled = !form.stampede_enabled}
						class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-[var(--motion-duration-fast)] focus:outline-none focus-visible:shadow-[var(--focus-ring)] {form.stampede_enabled ? 'bg-accent' : 'bg-surface-selected'}"
					>
						<span class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-surface-base shadow ring-0 transition-transform duration-[var(--motion-duration-base)] {form.stampede_enabled ? 'translate-x-4' : 'translate-x-0'}"></span>
					</button>
				</div>
				<div class="mt-3 grid grid-cols-2 gap-3">
					<label class="block text-xs text-ink-2 uppercase tracking-wide">
						{t('nodegroup.minimum')}
						<input bind:value={form.min_size} type="number" min="0" max={form.max_size}
							disabled={!form.stampede_enabled}
							class="w-full bg-surface-selected border border-line-2 rounded px-2 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1 disabled:opacity-40" />
					</label>
					<label class="block text-xs text-ink-2 uppercase tracking-wide">
						{t('nodegroup.maximum')}
						<input bind:value={form.max_size} type="number" min={form.min_size} max="20"
							disabled={!form.stampede_enabled}
							class="w-full bg-surface-selected border border-line-2 rounded px-2 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1 disabled:opacity-40" />
					</label>
				</div>
				{#if form.stampede_enabled}
					<p class="mt-2 text-xs text-ink-2">{t('nodegroupEdit.scaleHelp', { min: form.min_size, max: form.max_size })}</p>
					{#if Number(form.min_size) === 0}
						<div class="mt-2 text-xs text-warm-text/90 bg-surface-selected/10 border border-action-warm/40 rounded px-2.5 py-1.5">
							{t('nodegroup.zeroWarning')}
						</div>
					{/if}
				{/if}
			</div>
		</div>

		{#if error}
			<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
		{/if}

		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} disabled={saving} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0">{t('actions.cancel')}</button>
			<button
				onclick={save}
				disabled={saving}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg"
			>
				{#if saving}<ActivityIndicator size="xs" label={t('state.saving')} />{:else}{t('actions.save')}{/if}
			</button>
		</div>
	</div>
</div>
