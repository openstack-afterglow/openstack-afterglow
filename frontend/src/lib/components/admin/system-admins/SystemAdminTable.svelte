<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';

	interface SystemAdmin {
		user_id: string;
		name: string;
		email: string;
		enabled: boolean;
	}

	let {
		admins,
		onRevoked,
	}: {
		admins: SystemAdmin[];
		onRevoked: () => void;
	} = $props();

	let revoking = $state<string | null>(null);
	let revokeError = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const currentUserId = $derived($auth.userId ?? '');

	async function revoke(admin: SystemAdmin) {
		const isSelf = admin.user_id === currentUserId;
		if (isSelf) {
			if (!(await confirmDialog(t('systemTable.revokeSelfConfirm')))) return;
		}
		revoking = admin.user_id;
		revokeError = '';
		try {
			await api.post('/api/v1/admin/identity/system-roles/revoke', { user_id: admin.user_id }, token, projectId);
			onRevoked();
		} catch (e) {
			revokeError = e instanceof ApiError ? e.message : t('systemTable.revokeFailed');
		} finally {
			revoking = null;
		}
	}
</script>

{#if revokeError}
	<div class="mb-3 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{revokeError}</div>
{/if}

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">{t('systemTable.name')}</th>
				<th class="text-left py-2 pr-4">{t('systemTable.email')}</th>
				<th class="text-left py-2 pr-4">{t('systemTable.status')}</th>
				<th class="text-left py-2 pr-4">{t('systemTable.userId')}</th>
				<th class="text-left py-2"></th>
			</tr>
		</thead>
		<tbody>
			{#each admins as admin (admin.user_id)}
				<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors">
					<td class="py-2 pr-4 text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={admin.name || ''}>{admin.name || '-'}</span></td>
					<td class="py-2 pr-4 text-ink-2">{admin.email || '-'}</td>
					<td class="py-2 pr-4">
						<span class="px-1.5 py-0.5 rounded text-xs font-medium {admin.enabled ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">
							{admin.enabled ? t('systemTable.enabled') : t('systemTable.disabled')}
						</span>
					</td>
					<td class="py-2 pr-4 text-ink-2 font-mono text-xs">{admin.user_id.slice(0, 8)}</td>
					<td class="py-2">
						{#if admins.length <= 1}
							<span title={t('systemTable.lastAdminHelp')} class="px-3 py-1 text-xs rounded bg-surface-sunken text-ink-2 cursor-not-allowed">{t('systemTable.revoke')}</span>
						{:else}
							<button aria-busy={revoking === admin.user_id}
								onclick={() => revoke(admin)}
								disabled={revoking === admin.user_id}
								class="px-3 py-1 text-xs rounded bg-[var(--color-state-danger)]/10 hover:bg-[var(--color-state-danger)]/20 text-[var(--color-state-danger-text)] disabled:opacity-30"
							>
								{#if revoking === admin.user_id}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('systemTable.revoking')}</span>{:else}{t('systemTable.revoke')}{/if}
							</button>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
