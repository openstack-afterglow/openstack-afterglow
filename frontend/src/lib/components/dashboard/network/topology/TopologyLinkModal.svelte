<script lang="ts">
	import { t } from '$lib/i18n/ns/network-pages';
	import RichText from '$lib/i18n/RichText.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import type { LinkRequest } from '$lib/components/topology/canvas/topologyLink';
	import type { SubnetDetail, TopologyNetwork } from '$lib/types/topology';

	export type LinkConfirmPayload =
		| { kind: 'vm-net' }
		| { kind: 'router-gateway' }
		| { kind: 'router-net'; subnetId: string }
		| { kind: 'router-net'; create: { name: string; cidr: string; dhcp: boolean } };

	interface Props {
		open: boolean;
		request: LinkRequest;
		network: TopologyNetwork;
		subnets?: SubnetDetail[];
		createdSubnet?: SubnetDetail | null;
		submitting?: boolean;
		error?: string;
		onConfirm: (payload: LinkConfirmPayload) => Promise<boolean> | void;
		onClose: () => void;
	}

	let {
		open = $bindable(false),
		request,
		network,
		subnets = [],
		createdSubnet = null,
		submitting = false,
		error = '',
		onConfirm,
		onClose,
	}: Props = $props();

	// 서브넷 생성 필드 (router-net 중 서브넷이 없는 경우)
	let newSubnetName = $state('');
	let newSubnetCidr = $state('10.0.0.0/24');
	let newSubnetDhcp = $state(true);

	// 서브넷 선택 필드 (router-net 중 서브넷이 1개 이상인 경우)
	let selectedSubnetId = $state('');

	$effect(() => {
		if (subnets.length > 0 && (!selectedSubnetId || !subnets.some((s) => s.id === selectedSubnetId))) {
			selectedSubnetId = subnets[0].id;
		}
	});

	const cidrRegex = /^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/;
	const isCreateSubnetMode = $derived(request.kind === 'router-net' && !createdSubnet && subnets.length === 0);
	const cidrError = $derived(
		isCreateSubnetMode && newSubnetCidr && !cidrRegex.test(newSubnetCidr)
			? t('topologyLink.invalidCidr')
			: ''
	);

	const isSubmitDisabled = $derived.by(() => {
		if (submitting) return true;
		if (createdSubnet) return false;
		if (isCreateSubnetMode) {
			return !newSubnetCidr || Boolean(cidrError);
		}
		if (request.kind === 'router-net') {
			return !selectedSubnetId;
		}
		return false;
	});

	const sourceKindLabel = $derived.by(() => {
		if (request.kind === 'vm-net') return t('topologyLink.instance');
		return t('topologyLink.router');
	});

	const sourceName = $derived.by(() => {
		if (request.kind === 'vm-net') return request.instanceName;
		return request.routerName;
	});

	async function handleSubmit() {
		if (isSubmitDisabled) return;

		let payload: LinkConfirmPayload;
		if (request.kind === 'vm-net') {
			payload = { kind: 'vm-net' };
		} else if (request.kind === 'router-gateway') {
			payload = { kind: 'router-gateway' };
		} else {
			if (createdSubnet) {
				payload = {
					kind: 'router-net',
					subnetId: createdSubnet.id,
				};
			} else if (isCreateSubnetMode) {
				payload = {
					kind: 'router-net',
					create: {
						name: newSubnetName.trim() || `${network.name}-subnet`,
						cidr: newSubnetCidr.trim(),
						dhcp: newSubnetDhcp,
					},
				};
			} else {
				payload = {
					kind: 'router-net',
					subnetId: selectedSubnetId,
				};
			}
		}

		await onConfirm(payload);
	}
</script>

<FormModal
	bind:open
	title={t('topologyLink.title')}
	{submitting}
	onSubmit={handleSubmit}
	submitLabel={createdSubnet ? t('topologyLink.retryRouter') : t('topologyLink.connect')}
	cancelLabel={t('topologyLink.cancel')}
	{onClose}
>
	<div class="confirm-content">
		{#if error}
			<Alert tone="danger">{error}</Alert>
		{/if}

		<!-- 연결 컴포넌트 프리뷰 (Source ↔ Target) -->
		<div class="connection-preview" role="region" aria-label={t('topologyLink.componentsLabel')}>
			<div class="component-card">
				<div class="card-badge">
					<Pill tone="accent" size="xs">{sourceKindLabel}</Pill>
				</div>
				<div class="card-name" title={sourceName}>{sourceName}</div>
			</div>

			<div class="connection-cable" aria-hidden="true">
				<span class="cable-line"></span>
				<span class="cable-badge">{t('topologyLink.cable')}</span>
			</div>

			<div class="component-card">
				<div class="card-badge">
					<Pill tone={network.is_external ? 'warm' : 'neutral'} size="xs">
						{network.is_external ? t('topologyLink.externalNetwork') : t('topologyLink.internalNetwork')}
					</Pill>
				</div>
				<div class="card-name" title={network.name}>{network.name}</div>
			</div>
		</div>

		<!-- 연결 방식 및 세부 정보 -->
		<div class="connection-details">
			<div class="details-heading">{t('topologyLink.method')}</div>

			{#if request.kind === 'vm-net'}
				<div class="details-desc">
					<p class="desc-main">
						<RichText segments={t.rich('topologyLink.instanceDescription', { instance: request.instanceName, network: network.name })} />
					</p>
					<p class="desc-sub">{t('topologyLink.instanceHelp')}</p>
				</div>
			{:else if request.kind === 'router-gateway'}
				<div class="details-desc">
					<p class="desc-main">
						<RichText segments={t.rich('topologyLink.gatewayDescription', { router: request.routerName, network: network.name })} />
					</p>
					<p class="desc-sub">{t('topologyLink.gatewayHelp')}</p>
				</div>
			{:else if request.kind === 'router-net'}
				<div class="details-desc">
					<p class="desc-main">
						<RichText segments={t.rich('topologyLink.routerDescription', { router: request.routerName, network: network.name })} />
					</p>
				</div>

				{#if createdSubnet}
					<div class="single-subnet-box">
						<div class="box-label">{t('topologyLink.createdSubnet')}</div>
						<div class="subnet-info">
							<span class="subnet-name">{createdSubnet.name || t('topologyLink.newSubnet')}</span>
							<span class="subnet-cidr font-mono">{createdSubnet.cidr}</span>
							{#if createdSubnet.gateway_ip}
								<span class="subnet-gw">{t('topologyLink.gatewayAddress', { address: createdSubnet.gateway_ip })}</span>
							{:else}
								<span class="subnet-gw">{t('topologyLink.autoGateway')}</span>
							{/if}
						</div>
						<div class="create-notice">
							{t('topologyLink.createdNotice')}
						</div>
					</div>
				{:else if subnets.length === 0}
					<div class="subnet-create-box">
						<div class="create-notice">
							{t('topologyLink.createNotice')}
						</div>

						<Field label={t('topologyLink.subnetName')}>
							<TextInput
								bind:value={newSubnetName}
								placeholder="{network.name}-subnet"
								disabled={submitting}
							/>
						</Field>

						<Field label="CIDR" required help={t('topologyLink.cidrHelp')} error={cidrError}>
							<TextInput
								bind:value={newSubnetCidr}
								placeholder="10.0.0.0/24"
								class="font-mono"
								disabled={submitting}
							/>
						</Field>

						<label class="dhcp-check">
							<input type="checkbox" bind:checked={newSubnetDhcp} disabled={submitting} />
							<span>{t('topologyLink.enableDhcp')}</span>
						</label>
					</div>
				{:else if subnets.length === 1}
					<div class="single-subnet-box">
						<div class="box-label">{t('topologyLink.subnetToConnect')}</div>
						<div class="subnet-info">
							<span class="subnet-name">{subnets[0].name || t('topologyLink.defaultSubnet')}</span>
							<span class="subnet-cidr font-mono">{subnets[0].cidr}</span>
							{#if subnets[0].gateway_ip}
								<span class="subnet-gw">{t('topologyLink.gatewayAddress', { address: subnets[0].gateway_ip })}</span>
							{:else}
								<span class="subnet-gw">{t('topologyLink.autoGateway')}</span>
							{/if}
						</div>
					</div>
				{:else}
					<div class="multi-subnet-box">
						<Field label={t('topologyLink.subnetToConnect')} required help={t('topologyLink.subnetHelp')}>
							<SelectInput bind:value={selectedSubnetId} disabled={submitting}>
								{#each subnets as s (s.id)}
									<option value={s.id}>
										{s.gateway_ip ? t('topologyLink.subnetOptionWithGateway', { name: s.name || s.id.slice(0, 8), cidr: s.cidr, gateway: s.gateway_ip }) : t('topologyLink.subnetOption', { name: s.name || s.id.slice(0, 8), cidr: s.cidr })}
									</option>
								{/each}
							</SelectInput>
						</Field>
					</div>
				{/if}
			{/if}
		</div>
	</div>
</FormModal>

<style>
	.confirm-content {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		margin-top: 0.5rem;
	}

	.connection-preview {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 1rem;
		border-radius: 0.5rem;
		background: var(--color-surface-sunken);
		border: 1px solid var(--color-line);
	}

	.component-card {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.card-badge {
		display: flex;
	}

	.card-name {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-ink-0);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.connection-cable {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		flex-shrink: 0;
	}

	.cable-line {
		width: 2.5rem;
		height: 2px;
		background: var(--color-accent);
		border-radius: 1px;
	}

	.cable-badge {
		font-size: 0.6875rem;
		color: var(--color-ink-2);
		white-space: nowrap;
	}

	.connection-details {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 0.875rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
	}

	.details-heading {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-ink-2);
	}

	.details-desc {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.desc-main {
		font-size: 0.875rem;
		color: var(--color-ink-0);
		line-height: 1.4;
		margin: 0;
	}

	.desc-sub {
		font-size: 0.8125rem;
		color: var(--color-ink-2);
		line-height: 1.4;
		margin: 0;
	}

	.subnet-create-box,
	.single-subnet-box,
	.multi-subnet-box {
		margin-top: 0.5rem;
		padding-top: 0.75rem;
		border-top: 1px dashed var(--color-line);
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.create-notice {
		font-size: 0.8125rem;
		color: var(--color-ink-1);
		line-height: 1.4;
	}

	.box-label {
		font-size: 0.75rem;
		color: var(--color-ink-2);
		font-weight: 500;
	}

	.subnet-info {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8125rem;
	}

	.subnet-name {
		font-weight: 600;
		color: var(--color-ink-0);
	}

	.subnet-cidr {
		color: var(--color-accent);
	}

	.subnet-gw {
		color: var(--color-ink-2);
	}

	.dhcp-check {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8125rem;
		color: var(--color-ink-1);
		cursor: pointer;
		user-select: none;
	}

	.dhcp-check input {
		accent-color: var(--color-accent);
		width: 1rem;
		height: 1rem;
		margin: 0;
	}
</style>
