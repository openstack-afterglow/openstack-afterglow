<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';

	let {
		open = $bindable(false),
		onCreated,
	}: {
		open: boolean;
		onCreated: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let form = $state({ name: '', vcpus: 1, ram: 512, disk: 0, is_public: true });
	let creating = $state(false);
	let createError = $state('');

	async function createFlavor() {
		creating = true;
		createError = '';
		try {
			await api.post('/api/v1/admin/flavors', {
				name: form.name,
				vcpus: form.vcpus,
				ram: form.ram,
				disk: form.disk,
				is_public: form.is_public,
			}, token, projectId);
			open = false;
			form = { name: '', vcpus: 1, ram: 512, disk: 0, is_public: true };
			onCreated();
		} catch (e: unknown) {
			createError = e instanceof ApiError ? e.message : 'Flavor 생성 실패';
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
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">Flavor 생성</h2>
			{#if createError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{createError}</div>
			{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-flavorcreatemodal-68">이름</label>
					<input id="field-flavorcreatemodal-68" bind:value={form.name} type="text" placeholder="flavor 이름" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div class="grid grid-cols-3 gap-3">
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-flavorcreatemodal-73">VCPU</label>
						<input id="field-flavorcreatemodal-73" bind:value={form.vcpus} type="number" min="1" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
					</div>
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-flavorcreatemodal-77">RAM (MB)</label>
						<input id="field-flavorcreatemodal-77" bind:value={form.ram} type="number" min="0" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
					</div>
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-flavorcreatemodal-81">Disk (GB)</label>
						<input id="field-flavorcreatemodal-81" bind:value={form.disk} type="number" min="0" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
					</div>
				</div>
				<div class="flex items-center gap-3">
					<label class="text-sm text-ink-2" for="field-flavorcreatemodal-86">공개 여부</label>
					<button id="field-flavorcreatemodal-86"
						type="button"
						role="switch"
						aria-label="플레이버 공개 여부"
						aria-checked={form.is_public}
						onclick={() => (form.is_public = !form.is_public)}
						class="relative w-11 h-6 rounded-full transition-colors {form.is_public ? 'bg-action-warm' : 'bg-surface-selected'}"
					>
						<span class="absolute top-0.5 left-0.5 w-5 h-5 bg-surface-base rounded-full transition-transform {form.is_public ? 'translate-x-5' : ''}"></span>
					</button>
					<span class="text-xs text-ink-2">{form.is_public ? 'Public' : 'Private'}</span>
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={close} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={createFlavor} disabled={creating || !form.name} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">
					{creating ? '생성 중...' : '생성'}
				</button>
			</div>
		</div>
	</div>
{/if}
