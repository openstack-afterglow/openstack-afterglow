<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';

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
			if (!(await confirmDialog('본인 권한을 회수하면 즉시 로그아웃됩니다. 계속하시겠습니까?'))) return;
		}
		revoking = admin.user_id;
		revokeError = '';
		try {
			await api.post('/api/v1/admin/identity/system-roles/revoke', { user_id: admin.user_id }, token, projectId);
			onRevoked();
		} catch (e) {
			revokeError = e instanceof ApiError ? e.message : '회수 실패';
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
				<th class="text-left py-2 pr-4">이름</th>
				<th class="text-left py-2 pr-4">이메일</th>
				<th class="text-left py-2 pr-4">상태</th>
				<th class="text-left py-2 pr-4">User ID</th>
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
							{admin.enabled ? '활성' : '비활성'}
						</span>
					</td>
					<td class="py-2 pr-4 text-ink-3 font-mono text-xs">{admin.user_id.slice(0, 8)}</td>
					<td class="py-2">
						{#if admins.length <= 1}
							<span title="마지막 system admin은 회수할 수 없습니다" class="px-3 py-1 text-xs rounded bg-surface-sunken text-ink-3 cursor-not-allowed">회수</span>
						{:else}
							<button
								onclick={() => revoke(admin)}
								disabled={revoking === admin.user_id}
								class="px-3 py-1 text-xs rounded bg-red-900/30 hover:bg-red-900/60 text-red-400 disabled:opacity-30"
							>
								{revoking === admin.user_id ? '처리 중...' : '회수'}
							</button>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
