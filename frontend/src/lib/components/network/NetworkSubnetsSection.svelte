<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { useNetworkDetailController } from '$lib/stores/networkDetailController.svelte';

	const s = useNetworkDetailController();
	let form = $state({ name: '', cidr: '', gateway: '', dhcp: true, routerId: '' });
	let submitted = $state(false);
	const cidrError = $derived.by(() => {
		if (!form.cidr) return t('network.subnets.cidrRequired');
		const [address, prefix] = form.cidr.split('/');
		const octets = address?.split('.').map(Number);
		if (
			!octets ||
			octets.length !== 4 ||
			octets.some((value) => !Number.isInteger(value) || value < 0 || value > 255) ||
			!/^[0-9]+$/.test(prefix ?? '') ||
			Number(prefix) > 32
		) {
			return t('network.subnets.cidrInvalid');
		}
		return '';
	});

	async function submit() {
		submitted = true;
		if (cidrError) return;
		if (await s.addSubnet(form)) {
			form = { name: '', cidr: '', gateway: '', dhcp: true, routerId: '' };
			submitted = false;
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between gap-3 mb-3">
		<h3 class="text-xs text-ink-2 uppercase tracking-wide">{t('network.subnets.titleCount', { count: s.network!.subnet_details.length })}</h3>
		{#if s.canManageNetwork}
			<Button variant="subtle" size="xs" onclick={() => { void s.toggleSubnetForm(); }}>
				{s.showSubnetForm ? t('network.actions.close') : t('network.subnets.addToggle')}
			</Button>
		{/if}
	</div>

	{#if s.showSubnetForm && s.canManageNetwork}
		<form class="mb-4 grid gap-3 border border-line-2 rounded-lg p-3" onsubmit={(event) => { event.preventDefault(); void submit(); }}>
			<Field label={t('network.subnets.name')} for="network-subnet-name" help={t('network.subnets.nameHelp')}>
				<TextInput id="network-subnet-name" bind:value={form.name} maxlength={255} placeholder={`${s.network!.name}-subnet`} />
			</Field>
			<Field label="CIDR" for="network-subnet-cidr" error={submitted ? cidrError : ''} required>
				<TextInput id="network-subnet-cidr" bind:value={form.cidr} required inputmode="text" placeholder="10.0.0.0/24" ariaInvalid={submitted && Boolean(cidrError)} />
			</Field>
			<Field label={t('network.labels.gateway')} for="network-subnet-gateway" help={t('network.subnets.gatewayHelp')}>
				<TextInput id="network-subnet-gateway" bind:value={form.gateway} inputmode="decimal" placeholder="10.0.0.1" />
			</Field>
			<Field label={t('network.subnets.router')} for="network-subnet-router" help={t('network.subnets.routerHelp')}>
				<SelectInput id="network-subnet-router" bind:value={form.routerId}>
					<option value="">{t('network.subnets.noRouter')}</option>
					{#each s.managedRouters as router}
						<option value={router.id}>{router.name || router.id.slice(0, 12)}</option>
					{/each}
				</SelectInput>
			</Field>
			<label class="flex items-center gap-2 text-xs text-ink-1"><input type="checkbox" bind:checked={form.dhcp} /> {t('network.subnets.enableDhcp')}</label>
			{#if s.subnetError}<Alert tone="danger" title={t('network.errors.createSubnet')}>{s.subnetError}</Alert>{/if}
			<div class="flex justify-end"><Button type="submit" variant="primary" size="sm" disabled={s.addingSubnet}>{s.addingSubnet ? t('network.subnets.creating') : t('network.subnets.create')}</Button></div>
		</form>
	{/if}

	{#if s.network!.subnet_details.length > 0}
		<div class="space-y-3">
			{#each s.network!.subnet_details as subnet}
				<div class="border-b border-line/50 pb-2 last:border-0 last:pb-0">
					<div class="text-xs text-ink-0 font-medium">{subnet.name || subnet.id.slice(0, 8)}</div>
					<dl class="mt-1 space-y-1 text-xs">
						<div class="flex justify-between gap-3"><dt class="text-ink-2">CIDR</dt><dd class="text-ink-2 font-mono">{subnet.cidr}</dd></div>
						<div class="flex justify-between gap-3"><dt class="text-ink-2">{t('network.labels.gateway')}</dt><dd class="text-ink-2 font-mono">{subnet.gateway_ip || '-'}</dd></div>
						<div class="flex justify-between gap-3"><dt class="text-ink-2">DHCP</dt><dd class="text-ink-1">{subnet.dhcp_enabled ? t('network.state.enabled') : t('network.state.disabled')}</dd></div>
					</dl>
				</div>
			{/each}
		</div>
	{:else}
		<p class="text-xs text-ink-2">{t('network.subnets.empty')}</p>
	{/if}
</div>
