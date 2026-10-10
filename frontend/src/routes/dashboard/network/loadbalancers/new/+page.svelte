<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { ActivityIndicator, Alert, Button, ProgressTrack } from '$lib/components/ui';

	import type { Network, SubnetDetail } from '$lib/types/networks';
	import { t } from '$lib/i18n/ns/network-pages';

	let networks = $state<Network[]>([]);
	let subnets = $state<SubnetDetail[]>([]);
	let form = $state({ name: '', vip_subnet_id: '', vip_network_id: '', description: '' });
	let creating = $state(false);
	let error = $state('');
	let loadingSubnets = $state(false);

	async function loadNetworks() {
		try {
			networks = await api.get<Network[]>('/api/v1/networks', $auth.token ?? undefined, $auth.projectId ?? undefined);
			const preset = $page.url.searchParams.get('network');
			if (preset && !form.vip_network_id && networks.some((n) => n.id === preset)) {
				form.vip_network_id = preset;
				await onNetworkChange();
			}
		} catch {
			// ignore
		}
	}

	async function onNetworkChange() {
		form.vip_subnet_id = '';
		subnets = [];
		if (!form.vip_network_id) return;
		loadingSubnets = true;
		try {
			const detail = await api.get<{ subnet_details: SubnetDetail[] }>(
				`/api/v1/networks/${form.vip_network_id}`,
				$auth.token ?? undefined, $auth.projectId ?? undefined
			);
			subnets = detail.subnet_details ?? [];
		} catch {
			subnets = [];
		} finally {
			loadingSubnets = false;
		}
	}

	async function createLb() {
		if (!form.name.trim() || !form.vip_subnet_id) {
			error = t('loadBalancerCreate.error.required');
			return;
		}
		creating = true;
		error = '';
		try {
			const lb = await api.post<{ id: string }>(
				'/api/v1/loadbalancers',
				{ name: form.name, vip_subnet_id: form.vip_subnet_id, description: form.description },
				$auth.token ?? undefined, $auth.projectId ?? undefined
			);
			goto(`/dashboard/network/loadbalancers/${lb.id}`);
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('loadBalancerCreate.error.createFailed');
		} finally {
			creating = false;
		}
	}

	$effect(() => {
		if ($auth.token) untrack(() => loadNetworks());
	});
</script>

<div class="p-4 md:p-8 max-w-lg">
	<div class="flex items-center gap-4 mb-8">
		<button onclick={() => goto('/dashboard/network/loadbalancers')} class="text-ink-2 hover:text-ink-0 transition-colors text-sm">
			{t('loadBalancerCreate.backToList')}
		</button>
		<h1 class="text-2xl font-bold text-ink-0">{t('loadBalancerCreate.title')}</h1>
	</div>

	<div class="bg-surface-base border border-line-2 rounded-xl p-6 space-y-5">
		{#if error}
			<Alert tone="danger">{error}</Alert>
		{/if}

		<div>
			<label for="lb-name" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('loadBalancerCreate.form.name.label')}</label>
			<input
				id="lb-name"
				bind:value={form.name}
				type="text"
				placeholder={t('loadBalancerCreate.form.name.placeholder')}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			/>
		</div>

		<div>
			<label for="lb-network" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('loadBalancerCreate.form.network.label')}</label>
			<select
				id="lb-network"
				bind:value={form.vip_network_id}
				onchange={onNetworkChange}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			>
				<option value="">{t('loadBalancerCreate.form.network.placeholder')}</option>
				{#each networks.filter(n => !n.is_external) as net}
					<option value={net.id}>{net.name}</option>
				{/each}
			</select>
		</div>

		{#if form.vip_network_id}
			<div>
				<label for="lb-subnet" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('loadBalancerCreate.form.subnet.label')}</label>
				{#if loadingSubnets}
					<ActivityIndicator label={t('loadBalancerCreate.form.subnet.loading')} />
				{:else if subnets.length === 0}
					<div class="text-ink-2 text-sm">{t('loadBalancerCreate.form.subnet.empty')}</div>
				{:else}
					<select
						id="lb-subnet"
						bind:value={form.vip_subnet_id}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
					>
						<option value="">{t('loadBalancerCreate.form.subnet.placeholder')}</option>
						{#each subnets as subnet}
							<option value={subnet.id}>{t('loadBalancerCreate.form.subnet.option', { name: subnet.name || subnet.id.slice(0, 8), cidr: subnet.cidr })}</option>
						{/each}
					</select>
				{/if}
			</div>
		{/if}

		<div>
			<label for="lb-desc" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('loadBalancerCreate.form.description.label')}</label>
			<input
				id="lb-desc"
				bind:value={form.description}
				type="text"
				placeholder={t('loadBalancerCreate.form.description.placeholder')}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			/>
		</div>

		{#if creating}<ProgressTrack value={null} active label={`${t('loadBalancerCreate.title')} · ${t('loadBalancerCreate.actions.creating')}`} />{/if}
		<div class="flex justify-end gap-3 pt-2">
			<button
				onclick={() => goto('/dashboard/network/loadbalancers')}
				class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors"
			>
				{t('loadBalancerCreate.actions.cancel')}
			</button>
			<Button onclick={createLb} disabled={creating} ariaBusy={creating}>
				{#if creating}<ActivityIndicator size="xs" tone="ink" />{t('loadBalancerCreate.actions.creating')}{:else}{t('loadBalancerCreate.actions.create')}{/if}
			</Button>
		</div>
	</div>
</div>
