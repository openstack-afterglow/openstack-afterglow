<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	let {
		submitting,
		onSubmit,
		onCancel,
	}: {
		submitting: boolean;
		onSubmit: (form: {
			direction: string;
			protocol: string;
			port_range_min: string;
			port_range_max: string;
			remote_ip_prefix: string;
			ethertype: string;
		}) => Promise<string | true>;
		onCancel: () => void;
	} = $props();

	let ruleForm = $state({
		direction: 'ingress',
		protocol: '',
		port_range_min: '',
		port_range_max: '',
		remote_ip_prefix: '',
		ethertype: 'IPv4',
	});
	let error = $state('');

	async function handleSubmit() {
		error = '';
		const result = await onSubmit({ ...ruleForm });
		if (result === true) {
			ruleForm = {
				direction: 'ingress',
				protocol: '',
				port_range_min: '',
				port_range_max: '',
				remote_ip_prefix: '',
				ethertype: 'IPv4',
			};
		} else {
			error = result;
		}
	}

	function handleCancel() {
		error = '';
		onCancel();
	}
</script>

<div class="motion-enter px-4 pb-3 border-t border-line-2 pt-3 bg-surface-base/30">
	<p class="text-xs text-ink-2 mb-2">{t('securityGroup.ruleForm.title')}</p>
	<div class="grid grid-cols-2 gap-2 mb-2 md:grid-cols-4">
		<select
			bind:value={ruleForm.direction}
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 focus:border-action-warm"
		>
			<option value="ingress">{t('securityGroup.rules.inbound')}</option>
			<option value="egress">{t('securityGroup.rules.outbound')}</option>
		</select>
		<select
			bind:value={ruleForm.ethertype}
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 focus:border-action-warm"
		>
			<option value="IPv4">IPv4</option>
			<option value="IPv6">IPv6</option>
		</select>
		<select
			bind:value={ruleForm.protocol}
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 focus:border-action-warm"
		>
			<option value="">{t('securityGroup.ruleForm.anyProtocol')}</option>
			<option value="tcp">TCP</option>
			<option value="udp">UDP</option>
			<option value="icmp">ICMP</option>
		</select>
		<input
			bind:value={ruleForm.remote_ip_prefix}
			placeholder={t('securityGroup.ruleForm.remoteIp')}
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none"
		/>
	</div>
	{#if ruleForm.protocol === 'tcp' || ruleForm.protocol === 'udp'}
		<div class="grid grid-cols-2 gap-2 mb-2 max-w-xs">
			<input
				bind:value={ruleForm.port_range_min}
				placeholder={t('securityGroup.ruleForm.startPort')}
				class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none"
			/>
			<input
				bind:value={ruleForm.port_range_max}
				placeholder={t('securityGroup.ruleForm.endPort')}
				class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none"
			/>
		</div>
	{/if}
	{#if error}
		<p class="text-xs text-red-400 mb-2">{error}</p>
	{/if}
	<div class="flex gap-2">
		<button
			onclick={handleSubmit}
			disabled={submitting}
			aria-busy={submitting}
			class="inline-flex items-center gap-1.5 text-xs text-warm-text hover:text-warm-text-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3"
		>
			{#if submitting}<ActivityIndicator size="xs" tone="ink" />{/if}{submitting ? t('securityGroup.ruleForm.adding') : t('securityGroup.ruleForm.add')}
		</button>
		<button
			onclick={handleCancel}
			class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 rounded transition-colors"
		>{t('securityGroup.actions.cancel')}</button>
	</div>
</div>
