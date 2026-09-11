<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';

	let {
		onClose,
		onGranted,
	}: {
		onClose: () => void;
		onGranted: () => void;
	} = $props();

	interface User {
		id: string;
		name: string;
		email: string;
		enabled: boolean;
	}

	let allUsers = $state<User[]>([]);
	let query = $state('');
	let loadingUsers = $state(true);
	let granting = $state(false);
	let grantError = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	const filtered = $derived(
		query.trim()
			? allUsers.filter(
					(u) =>
						u.name.toLowerCase().includes(query.toLowerCase()) ||
						(u.email ?? '').toLowerCase().includes(query.toLowerCase()),
			  )
			: allUsers,
	);

	async function loadUsers() {
		loadingUsers = true;
		const collected: User[] = [];
		let marker: string | null = null;
		try {
			for (let i = 0; i < 5; i++) {
				let url = '/api/v1/admin/users?limit=100';
				if (marker) url += `&marker=${marker}`;
				const res = await api.get<{ items: User[]; next_marker: string | null }>(url, token, projectId);
				collected.push(...res.items);
				marker = res.next_marker;
				if (!marker) break;
			}
			allUsers = collected;
		} catch {
			allUsers = [];
		} finally {
			loadingUsers = false;
		}
	}

	async function grant(user: User) {
		granting = true;
		grantError = '';
		try {
			await api.post('/api/v1/admin/identity/system-roles/grant', { user_id: user.id }, token, projectId);
			onGranted();
			onClose();
		} catch (e) {
			grantError = e instanceof ApiError ? e.message : '부여 실패';
		} finally {
			granting = false;
		}
	}

	$effect(() => {
		loadUsers();
	});
</script>

<div
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
	onkeydown={(e) => e.key === 'Escape' && onClose()}
	role="dialog"
	tabindex="-1"
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-4">System Admin 추가</h2>

		{#if grantError}
			<div class="mb-3 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{grantError}</div>
		{/if}

		<input
			bind:value={query}
			type="text"
			placeholder="이름 또는 이메일로 검색"
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mb-3"
		/>

		<div class="overflow-y-auto max-h-72 rounded-lg border border-line-2">
			{#if loadingUsers}
				<div class="text-ink-3 text-sm px-4 py-6 text-center">불러오는 중...</div>
			{:else if filtered.length === 0}
				<div class="text-ink-3 text-sm px-4 py-6 text-center">사용자 없음</div>
			{:else}
				<table class="w-full text-sm">
					<tbody>
						{#each filtered as u (u.id)}
							<tr
								class="border-b border-line/50 hover:bg-surface-sunken/50 cursor-pointer transition-colors"
								onclick={() => grant(u)}
							>
								<td class="px-4 py-2 text-ink-0 text-xs">{u.name}</td>
								<td class="px-4 py-2 text-ink-2 text-xs">{u.email || '-'}</td>
								<td class="px-4 py-2 text-ink-3 font-mono text-xs">{u.id.slice(0, 8)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</div>

		<div class="flex justify-end mt-4">
			<button
				onclick={onClose}
				disabled={granting}
				class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg"
			>
				취소
			</button>
		</div>
	</div>
</div>
