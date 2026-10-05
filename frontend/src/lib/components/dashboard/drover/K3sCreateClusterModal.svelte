<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	import RichText from '$lib/i18n/RichText.svelte';
	import { api } from '$lib/api/client';
	import type { K3sFlavor, K3sNetwork, K3sKeypair, K3sClusterTemplate } from '$lib/types/k3s';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';

	let {
		open = $bindable(false),
		token,
		projectId,
		createError = '',
		creating = false,
		onCreate,
	}: {
		open?: boolean;
		token?: string;
		projectId?: string;
		createError?: string;
		creating?: boolean;
		onCreate: (form: {
			name: string;
			agent_count: number;
			agent_flavor_id: string;
			network_id: string;
			key_name: string;
			os_type: string;
			template_id?: string;
			master_count: number;
			stampede_enabled: boolean;
		}) => void;
	} = $props();

	let form = $state({ name: '', agent_count: 1, agent_flavor_id: '', network_id: '', key_name: '', os_type: 'ubuntu', template_id: '', master_count: 1, stampede_enabled: false });
	let flavors = $state<K3sFlavor[]>([]);
	let networks = $state<K3sNetwork[]>([]);
	let keypairs = $state<K3sKeypair[]>([]);
	let templates = $state<K3sClusterTemplate[]>([]);

	$effect(() => {
		if (open) {
			form = { name: '', agent_count: 1, agent_flavor_id: '', network_id: '', key_name: '', os_type: 'ubuntu', template_id: '', master_count: 1, stampede_enabled: false };
			void loadDeps();
		}
	});

	async function loadDeps() {
		try {
			[flavors, networks, keypairs, templates] = await Promise.all([
				api.get<K3sFlavor[]>('/api/v1/flavors', token, projectId),
				api.get<K3sNetwork[]>('/api/v1/networks', token, projectId),
				api.get<K3sKeypair[]>('/api/v1/keypairs', token, projectId),
				api.get<K3sClusterTemplate[]>('/api/v1/k3s/cluster-templates', token, projectId).catch(() => []),
			]);
			if (form.network_id && !networks.some(n => n.is_external && n.id === form.network_id)) form.network_id = '';
		} catch {
			flavors = []; networks = []; keypairs = [];
			form.network_id = '';
		}
	}

	function applyTemplate(templateId: string) {
		form.template_id = templateId;
		const tmpl = templates.find(template => template.id === templateId);
		if (!tmpl) return;
		if (tmpl.default_node_count !== undefined) form.agent_count = tmpl.default_node_count;
		if (tmpl.default_agent_flavor_id) form.agent_flavor_id = tmpl.default_agent_flavor_id;
		if (tmpl.os_type) form.os_type = tmpl.os_type;
	}

</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }} class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; }}
		role="dialog" aria-modal="true" tabindex="-1"
>
		<div data-tour="drover-create-form" class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg max-h-[calc(100dvh-2rem)] overflow-y-auto mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()} role="none">
			<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('cluster.createTitle')}</h2>
			<div class="space-y-4">
				{#if templates.length > 0}
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('create.template')}
						<select
							value={form.template_id}
							onchange={(e) => applyTemplate((e.target as HTMLSelectElement).value)}
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
						>
							<option value="">{t('create.noTemplate')}</option>
							{#each templates as template}
								<option value={template.id}>{template.name}{template.description ? ` — ${template.description}` : ''}</option>
							{/each}
						</select>
					</label>
				</div>
				{/if}
				<div data-tour="drover-name">
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('create.name')}
						<input bind:value={form.name} type="text" placeholder={t('create.namePlaceholder')}
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
				<div data-tour="drover-os">
					<span class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('form.osType')}</span>
					<div class="flex gap-2 mt-1.5">
						<button type="button"
							onclick={() => form.os_type = 'ubuntu'}
							class="flex-1 flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors {form.os_type === 'ubuntu' ? 'border-action-warm bg-surface-selected/30 text-ink-0' : 'border-line-2 bg-surface-sunken text-ink-2 hover:border-line-2'}">
							<span class="text-base">🐧</span>
							<div class="text-left">
								<div class="font-medium leading-none">Ubuntu</div>
								<div class="text-xs text-ink-2 mt-0.5">cloud-init</div>
							</div>
						</button>
						<button type="button"
							onclick={() => form.os_type = 'fcos'}
							class="flex-1 flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors {form.os_type === 'fcos' ? 'border-orange-500 bg-orange-900/30 text-ink-0' : 'border-line-2 bg-surface-sunken text-ink-2 hover:border-line-2'}">
							<span class="text-base">🔴</span>
							<div class="text-left">
								<div class="font-medium leading-none">CoreOS</div>
								<div class="text-xs text-ink-2 mt-0.5">Ignition</div>
							</div>
						</button>
					</div>
					{#if form.os_type === 'fcos'}
						<div class="mt-2 text-xs text-orange-400/80 bg-orange-900/10 border border-orange-800/40 rounded px-2.5 py-1.5">
							<RichText segments={t.rich('create.fcosHelp')} classes={{ code: 'font-mono' }} />
						</div>
					{/if}
				</div>
				<div data-tour="drover-masters">
						<span class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('create.masters')}</span>
						<div class="flex gap-2 mt-1.5">
							<button type="button"
								onclick={() => form.master_count = 1}
								class="flex-1 px-3 py-2 rounded-lg border text-sm transition-colors {form.master_count === 1 ? 'border-action-warm bg-surface-selected/30 text-ink-0' : 'border-line-2 bg-surface-sunken text-ink-2 hover:border-line-2'}">
								{t('create.singleMaster')}
							</button>
							<button type="button"
								onclick={() => form.master_count = 3}
								class="flex-1 px-3 py-2 rounded-lg border text-sm transition-colors {form.master_count === 3 ? 'border-purple-500 bg-purple-900/30 text-ink-0' : 'border-line-2 bg-surface-sunken text-ink-2 hover:border-line-2'}">
								3 (HA)
							</button>
						</div>
						{#if form.master_count === 3}
							<p class="mt-1.5 text-xs text-purple-400/80">
								{t('create.haHelp')}
							</p>
						{/if}
					</div>
				<div data-tour="drover-agents">
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('create.agents')}
						<input bind:value={form.agent_count} type="number" min="0" max="10"
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
				<div data-tour="drover-flavor">
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('create.flavor')}
						<select bind:value={form.agent_flavor_id}
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
							<option value="">{t('create.defaultFlavor')}</option>
							{#each flavors as f}
								<option value={f.id} disabled={f.eligibility ? !f.eligibility.selectable : false}>
									{t(f.eligibility && !f.eligibility.selectable ? 'create.flavorExceeded' : 'create.flavorOption', { name: f.name, cpus: f.vcpus, ram: Math.round(f.ram/1024) })}
								</option>
							{/each}
						</select>
					</label>
				</div>
				<div>
					<Field label={t('create.providerNetwork')} for="drover-provider-network"
						help={t('create.providerHelp')}>
						<SelectInput id="drover-provider-network" bind:value={form.network_id}>
							<option value="">{t('create.defaultNetwork')}</option>
							{#each networks.filter(n => n.is_external) as n}
								<option value={n.id}>{n.name || n.id.slice(0,12)}</option>
							{/each}
						</SelectInput>
					</Field>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('create.keypair')}
						<select bind:value={form.key_name}
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
							<option value="">{t('state.none')}</option>
							{#each keypairs as kp}
								<option value={kp.name}>{kp.name}</option>
							{/each}
						</select>
					</label>
				</div>

				<!-- Stampede 오토스케일 모드 -->
				<div class="border border-line-2 rounded-lg p-3 bg-surface-sunken/50">
					<div class="flex items-center justify-between">
						<div class="flex items-center gap-2">
							<span class="text-sm font-medium text-ink-1">{t('create.stampedeMode')}</span>
							<span class="text-xs bg-yellow-900/60 text-yellow-400 border border-yellow-700/50 rounded px-1.5 py-0.5 leading-none">{t('state.development')}</span>
						</div>
						<button
							type="button"
							role="switch"
							aria-checked={form.stampede_enabled}
							aria-label={t('create.stampedeMode')}
							onclick={() => form.stampede_enabled = !form.stampede_enabled}
							class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:shadow-[var(--focus-ring)] {form.stampede_enabled ? 'bg-action-warm' : 'bg-surface-selected'}"
						>
							<span
								class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-surface-base shadow ring-0 transition duration-200 ease-in-out {form.stampede_enabled ? 'translate-x-4' : 'translate-x-0'}"
							></span>
						</button>
					</div>
					<p class="mt-1.5 text-xs text-ink-2">
						{t('create.stampedeHelp')}
					</p>
					{#if form.stampede_enabled}
						<div class="mt-2 text-xs text-yellow-400/90 bg-yellow-900/10 border border-yellow-800/40 rounded px-2.5 py-1.5">
							<RichText segments={t.rich('create.stampedeWarning')} classes={{ code: 'font-mono' }} />
						</div>
					{/if}
				</div>
			</div>
			{#if createError}
				<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{createError}</div>
			{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => open = false}
					class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('actions.cancel')}</button>
				<button data-tour="drover-create-submit" onclick={() => { open = false; onCreate({...form, template_id: form.template_id || undefined}); }} disabled={creating}
					class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
					{t('actions.create')}
				</button>
			</div>
		</div>
	</div>
{/if}
