<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { apiMut } from '$lib/api/mutations';

	let {
		open = $bindable(false),
		onCreated,
	}: {
		open: boolean;
		onCreated: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let form = $state({ name: '', size_gb: 10 });
	let creating = $state(false);
	let createError = $state('');

	async function createVolume() {
		if (!form.name.trim() || form.size_gb < 1) return;
		creating = true;
		createError = '';
		try {
			await apiMut('볼륨 생성', () => api.post('/api/v1/volumes', form, token, projectId));
			open = false;
			form = { name: '', size_gb: 10 };
			onCreated();
		} catch (e) {
			createError = e instanceof ApiError ? e.message : '생성 실패';
		} finally {
			creating = false;
		}
	}

	function close() {
		open = false;
		createError = '';
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={close}
		role="dialog" aria-modal="true" tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && close()}
	>
		<div
			data-tour="volume-create-form"
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">볼륨 생성</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이름
						<input bind:value={form.name} type="text" placeholder="my-volume" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">크기 (GB)
						<input bind:value={form.size_gb} type="number" min="1" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
			</div>
			{#if createError}
				<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{createError}</div>
			{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={close} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
				<button
					data-tour="volume-create-submit"
					onclick={createVolume}
					disabled={creating || !form.name.trim() || form.size_gb < 1}
					class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
				>{creating ? '생성 중...' : '생성'}</button>
			</div>
		</div>
	</div>
{/if}
