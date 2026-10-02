<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-identity';
	import RichText from '$lib/i18n/RichText.svelte';
	interface SecurityPolicy {
		legacy_compat: boolean;
		system_admin_count: number;
		admin_project_member_count: number;
	}

	let {
		policy,
		onMigrate,
	}: {
		policy: SecurityPolicy;
		onMigrate: () => void;
	} = $props();
</script>

{#snippet recoveryCommand(text: string)}<code class="bg-red-900/40 px-1 rounded">{text}</code>{/snippet}

{#if !policy.legacy_compat && policy.system_admin_count === 0}
	<div class="mb-4 flex items-start gap-3 rounded-lg border border-red-700 bg-red-900/20 px-4 py-3 text-sm">
		<span class="mt-0.5 text-red-400 shrink-0">⚠</span>
		<div class="flex-1">
			<span class="font-semibold text-red-300">{t('securityPolicy.lockoutTitle')}</span>
			<span class="text-red-400 ml-1">{t('securityPolicy.lockoutDescription')}</span>
			<span class="block mt-1 text-red-500 text-xs"><RichText segments={t.rich('securityPolicy.recovery', { command: 'python3 scripts/manage_system_admins.py --os-system-scope grant <user-id>' })} tags={{ command: recoveryCommand }} /></span>
		</div>
	</div>
{:else if !policy.legacy_compat}
	<div class="mb-4 flex items-center gap-3 rounded-lg border border-green-700 bg-green-900/20 px-4 py-3 text-sm">
		<span class="text-green-400 shrink-0">✓</span>
		<span class="text-green-300">
			<RichText segments={t.rich('securityPolicy.strict', { count: policy.system_admin_count })} />
		</span>
	</div>
{:else}
	<div class="mb-4 flex items-center justify-between gap-3 rounded-lg border border-action-warm bg-surface-selected/20 px-4 py-3 text-sm">
		<div class="flex items-center gap-2 flex-1 min-w-0">
			<span class="text-warm-text shrink-0">⚙</span>
			<span class="text-warm-text">
				{t('securityPolicy.legacy', { count: policy.admin_project_member_count })}
			</span>
		</div>
		<button
			onclick={onMigrate}
			class="shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-action-warm/50 hover:bg-action-warm-hover/80 text-warm-text whitespace-nowrap"
		>
			{t('securityPolicy.migrate')}
		</button>
	</div>
{/if}
