<script lang="ts">
	import type { SecurityGroup, SecurityGroupRuleDraft } from '$lib/types/securityGroup';
	import { t } from '$lib/i18n/ns/network-pages';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	let {
		ruleForm = $bindable(),
		targetType = $bindable(),
		groups,
		originalRuleId,
		adding,
		canAdd,
		error,
		onAdd,
		onCancel,
		onRemoveOriginal,
	}: {
		ruleForm: SecurityGroupRuleDraft;
		targetType: 'cidr' | 'group';
		groups: SecurityGroup[];
		originalRuleId: string | null;
		adding: boolean;
		canAdd: boolean;
		error: string;
		onAdd: () => Promise<void>;
		onCancel: () => void;
		onRemoveOriginal: () => Promise<void>;
	} = $props();

	const control = 'w-full bg-surface-sunken border border-line-2 rounded-md px-2 py-1.5 text-sm text-ink-1 focus:border-action-warm focus:outline-none';
</script>

<div class="motion-enter border-t border-line bg-surface-base p-3 md:p-4" data-testid="inline-rule-form">
	<p class="text-sm font-medium text-ink-0 mb-3">{originalRuleId ? t('addRule.copyTitle') : t('addRule.newTitle')}</p>
	{#if originalRuleId}
		<p class="text-xs text-ink-2 mb-3">{t('addRule.copyHelp')}</p>
	{/if}
	<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
		<label class="text-xs text-ink-2">{t('addRule.direction')}
			<select bind:value={ruleForm.direction} class="{control} mt-1">
				<option value="ingress">{t('addRule.inbound')}</option>
				<option value="egress">{t('addRule.outbound')}</option>
			</select>
		</label>
		<label class="text-xs text-ink-2">{t('addRule.ipVersion')}
			<select bind:value={ruleForm.ethertype} class="{control} mt-1">
				<option value="IPv4">IPv4</option>
				<option value="IPv6">IPv6</option>
			</select>
		</label>
		<label class="text-xs text-ink-2">{t('addRule.protocol')}
			<select bind:value={ruleForm.protocol} class="{control} mt-1">
				<option value="">{t('addRule.anyProtocol')}</option>
				<option value="tcp">TCP</option>
				<option value="udp">UDP</option>
				<option value="icmp">ICMP</option>
			</select>
		</label>
		<label class="text-xs text-ink-2">{t('addRule.targetType')}
			<select bind:value={targetType} onchange={() => { ruleForm.remote_ip_prefix = ''; ruleForm.remote_group_id = ''; }} class="{control} mt-1">
				<option value="cidr">{t('addRule.cidr')}</option>
				<option value="group">{t('addRule.securityGroup')}</option>
			</select>
		</label>
		{#if targetType === 'cidr'}
			<label class="text-xs text-ink-2 md:col-span-2">{t('addRule.remoteIpRange')}
				<input bind:value={ruleForm.remote_ip_prefix} placeholder={t('addRule.remoteIpPlaceholder', { cidr: ruleForm.ethertype === 'IPv6' ? '::/0' : '0.0.0.0/0' })} class="{control} mt-1 placeholder-ink-3" />
			</label>
		{:else}
			<label class="text-xs text-ink-2 md:col-span-2">{t('addRule.remoteSecurityGroup')}
				<select bind:value={ruleForm.remote_group_id} class="{control} mt-1">
					<option value="">{t('addRule.selectSecurityGroup')}</option>
					{#each groups as group (group.id)}
						<option value={group.id}>{group.name} ({group.id.slice(0, 8)})</option>
					{/each}
				</select>
			</label>
		{/if}
		{#if ruleForm.protocol === 'tcp' || ruleForm.protocol === 'udp'}
			<label class="text-xs text-ink-2">{t('addRule.startPort')}
				<input bind:value={ruleForm.port_range_min} type="text" inputmode="numeric" placeholder="1–65535" class="{control} mt-1 placeholder-ink-3" />
			</label>
			<label class="text-xs text-ink-2">{t('addRule.endPort')}
				<input bind:value={ruleForm.port_range_max} type="text" inputmode="numeric" placeholder={t('addRule.endPort')} aria-describedby="rule-end-port-help" class="{control} mt-1 placeholder-ink-3" />
				<span id="rule-end-port-help" class="block text-xs text-ink-2 mt-1">{t('addRule.endPortHelp')}</span>
			</label>
		{/if}
	</div>
	{#if error}<p role="alert" class="text-xs text-state-danger-text mt-3">{error}</p>{/if}
	<div class="flex flex-wrap gap-2 mt-3">
		{#if originalRuleId}
			<button type="button" onclick={onRemoveOriginal} disabled={adding} class="text-xs text-state-danger-text border border-state-danger rounded-md px-3 py-1.5 disabled:opacity-50">{t('addRule.removeOriginal')}</button>
		{/if}
		<button type="button" onclick={onAdd} disabled={adding || !canAdd} aria-busy={adding} class="inline-flex items-center gap-1.5 text-xs bg-action-warm text-action-on-warm rounded-md px-3 py-1.5 disabled:opacity-50">{#if adding}<ActivityIndicator size="xs" tone="ink" />{/if}{adding ? t('addRule.adding') : t('addRule.add')}</button>
		<button type="button" onclick={onCancel} class="text-xs text-ink-2 border border-line-2 rounded-md px-3 py-1.5">{t('addRule.cancel')}</button>
	</div>
	{#if !canAdd}<p class="text-xs text-ink-2 mt-2">{t('addRule.quotaHelp')}</p>{/if}
</div>
