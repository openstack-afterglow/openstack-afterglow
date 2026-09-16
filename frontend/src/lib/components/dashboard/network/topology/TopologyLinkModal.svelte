<script lang="ts">
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
			? '유효한 IPv4 CIDR 형식이 아닙니다 (예: 10.0.0.0/24)'
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
		if (request.kind === 'vm-net') return '인스턴스';
		return '라우터';
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
	title="컴포넌트 연결 확인"
	{submitting}
	onSubmit={handleSubmit}
	submitLabel={createdSubnet ? '라우터 연결 재시도' : '연결하기'}
	cancelLabel="취소"
	{onClose}
>
	<div class="confirm-content">
		{#if error}
			<Alert tone="danger">{error}</Alert>
		{/if}

		<!-- 연결 컴포넌트 프리뷰 (Source ↔ Target) -->
		<div class="connection-preview" role="region" aria-label="연결 대상 컴포넌트">
			<div class="component-card">
				<div class="card-badge">
					<Pill tone="accent" size="xs">{sourceKindLabel}</Pill>
				</div>
				<div class="card-name" title={sourceName}>{sourceName}</div>
			</div>

			<div class="connection-cable" aria-hidden="true">
				<span class="cable-line"></span>
				<span class="cable-badge">케이블 연결</span>
			</div>

			<div class="component-card">
				<div class="card-badge">
					<Pill tone={network.is_external ? 'warm' : 'neutral'} size="xs">
						{network.is_external ? '외부 네트워크' : '내부 네트워크'}
					</Pill>
				</div>
				<div class="card-name" title={network.name}>{network.name}</div>
			</div>
		</div>

		<!-- 연결 방식 및 세부 정보 -->
		<div class="connection-details">
			<div class="details-heading">연결 방식</div>

			{#if request.kind === 'vm-net'}
				<div class="details-desc">
					<p class="desc-main">
						<strong>{request.instanceName}</strong> 인스턴스에 새 가상 네트워크 인터페이스(NIC)를 생성하여
						<strong>{network.name}</strong> 네트워크에 연결합니다.
					</p>
					<p class="desc-sub">IP 주소는 서브넷의 DHCP 정책에 따라 자동으로 할당됩니다.</p>
				</div>
			{:else if request.kind === 'router-gateway'}
				<div class="details-desc">
					<p class="desc-main">
						<strong>{request.routerName}</strong> 라우터의 외부 게이트웨이(Default Route)를
						<strong>{network.name}</strong> 외부 네트워크로 지정합니다.
					</p>
					<p class="desc-sub">인터넷 통신 및 아웃바운드 SNAT 라우팅이 이 게이트웨이를 통해 활성화됩니다.</p>
				</div>
			{:else if request.kind === 'router-net'}
				<div class="details-desc">
					<p class="desc-main">
						<strong>{request.routerName}</strong> 라우터를
						<strong>{network.name}</strong> 네트워크의 서브넷 게이트웨이 인터페이스로 연결합니다.
					</p>
				</div>

				{#if createdSubnet}
					<div class="single-subnet-box">
						<div class="box-label">생성 완료된 서브넷</div>
						<div class="subnet-info">
							<span class="subnet-name">{createdSubnet.name || '새 서브넷'}</span>
							<span class="subnet-cidr font-mono">{createdSubnet.cidr}</span>
							{#if createdSubnet.gateway_ip}
								<span class="subnet-gw">GW: {createdSubnet.gateway_ip}</span>
							{:else}
								<span class="subnet-gw">게이트웨이 자동 지정</span>
							{/if}
						</div>
						<div class="create-notice">
							서브넷 생성이 완료되었습니다. 라우터 게이트웨이 인터페이스 연결만 재시도합니다.
						</div>
					</div>
				{:else if subnets.length === 0}
					<div class="subnet-create-box">
						<div class="create-notice">
							이 네트워크에는 활성 서브넷이 없습니다. 새 서브넷을 생성한 후 라우터 인터페이스에 연결합니다.
						</div>

						<Field label="서브넷 이름 (선택)">
							<TextInput
								bind:value={newSubnetName}
								placeholder="{network.name}-subnet"
								disabled={submitting}
							/>
						</Field>

						<Field label="CIDR" required help="예: 10.0.0.0/24 · 게이트웨이는 첫 주소로 자동 지정됩니다" error={cidrError}>
							<TextInput
								bind:value={newSubnetCidr}
								placeholder="10.0.0.0/24"
								class="font-mono"
								disabled={submitting}
							/>
						</Field>

						<label class="dhcp-check">
							<input type="checkbox" bind:checked={newSubnetDhcp} disabled={submitting} />
							<span>DHCP 활성화</span>
						</label>
					</div>
				{:else if subnets.length === 1}
					<div class="single-subnet-box">
						<div class="box-label">연결할 서브넷</div>
						<div class="subnet-info">
							<span class="subnet-name">{subnets[0].name || '기본 서브넷'}</span>
							<span class="subnet-cidr font-mono">{subnets[0].cidr}</span>
							{#if subnets[0].gateway_ip}
								<span class="subnet-gw">GW: {subnets[0].gateway_ip}</span>
							{:else}
								<span class="subnet-gw">게이트웨이 자동 지정</span>
							{/if}
						</div>
					</div>
				{:else}
					<div class="multi-subnet-box">
						<Field label="연결할 서브넷" required help="라우터 인터페이스를 연결할 서브넷을 선택하세요">
							<SelectInput bind:value={selectedSubnetId} disabled={submitting}>
								{#each subnets as s (s.id)}
									<option value={s.id}>
										{s.name || s.id.slice(0, 8)} ({s.cidr}){s.gateway_ip ? ` · GW ${s.gateway_ip}` : ''}
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
