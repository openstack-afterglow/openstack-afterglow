<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { useNetworkDetailController } from '$lib/stores/networkDetailController.svelte';

	const s = useNetworkDetailController();
	let form = $state({ name: '', cidr: '', gateway: '', dhcp: true });
	let submitted = $state(false);
	const cidrError = $derived.by(() => {
		if (!form.cidr) return 'CIDR을 입력하세요.';
		const [address, prefix] = form.cidr.split('/');
		const octets = address?.split('.').map(Number);
		if (
			!octets ||
			octets.length !== 4 ||
			octets.some((value) => !Number.isInteger(value) || value < 0 || value > 255) ||
			!/^[0-9]+$/.test(prefix ?? '') ||
			Number(prefix) > 32
		) {
			return 'IPv4 CIDR 형식(예: 10.0.0.0/24)으로 입력하세요.';
		}
		return '';
	});

	async function submit() {
		submitted = true;
		if (cidrError) return;
		if (await s.addSubnet(form)) {
			form = { name: '', cidr: '', gateway: '', dhcp: true };
			submitted = false;
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between gap-3 mb-3">
		<h3 class="text-xs text-ink-2 uppercase tracking-wide">서브넷 ({s.network!.subnet_details.length})</h3>
		{#if s.isUserPanel}
			<Button variant="subtle" size="xs" onclick={() => (s.showSubnetForm = !s.showSubnetForm)}>
				{s.showSubnetForm ? '닫기' : '+ 서브넷 추가'}
			</Button>
		{/if}
	</div>

	{#if s.showSubnetForm && s.isUserPanel}
		<form class="mb-4 grid gap-3 border border-line-2 rounded-lg p-3" onsubmit={(event) => { event.preventDefault(); void submit(); }}>
			<Field label="서브넷 이름" for="network-subnet-name" help="비우면 네트워크 이름을 사용합니다.">
				<TextInput id="network-subnet-name" bind:value={form.name} maxlength={255} placeholder={`${s.network!.name}-subnet`} />
			</Field>
			<Field label="CIDR" for="network-subnet-cidr" error={submitted ? cidrError : ''} required>
				<TextInput id="network-subnet-cidr" bind:value={form.cidr} required inputmode="text" placeholder="10.0.0.0/24" ariaInvalid={submitted && Boolean(cidrError)} />
			</Field>
			<Field label="게이트웨이" for="network-subnet-gateway" help="비우면 Neutron이 게이트웨이를 선택합니다.">
				<TextInput id="network-subnet-gateway" bind:value={form.gateway} inputmode="decimal" placeholder="10.0.0.1" />
			</Field>
			<label class="flex items-center gap-2 text-xs text-ink-1"><input type="checkbox" bind:checked={form.dhcp} /> DHCP 활성화</label>
			{#if s.subnetError}<Alert tone="danger" title="서브넷 생성 실패">{s.subnetError}</Alert>{/if}
			<div class="flex justify-end"><Button type="submit" variant="primary" size="sm" disabled={s.addingSubnet}>{s.addingSubnet ? '생성 중...' : '서브넷 생성'}</Button></div>
		</form>
	{/if}

	{#if s.network!.subnet_details.length > 0}
		<div class="space-y-3">
			{#each s.network!.subnet_details as subnet}
				<div class="border-b border-line/50 pb-2 last:border-0 last:pb-0">
					<div class="text-xs text-ink-0 font-medium">{subnet.name || subnet.id.slice(0, 8)}</div>
					<dl class="mt-1 space-y-1 text-xs">
						<div class="flex justify-between gap-3"><dt class="text-ink-2">CIDR</dt><dd class="text-ink-2 font-mono">{subnet.cidr}</dd></div>
						<div class="flex justify-between gap-3"><dt class="text-ink-2">게이트웨이</dt><dd class="text-ink-2 font-mono">{subnet.gateway_ip || '-'}</dd></div>
						<div class="flex justify-between gap-3"><dt class="text-ink-2">DHCP</dt><dd class="text-ink-1">{subnet.dhcp_enabled ? '활성' : '비활성'}</dd></div>
					</dl>
				</div>
			{/each}
		</div>
	{:else}
		<p class="text-xs text-ink-2">서브넷이 없습니다</p>
	{/if}
</div>
