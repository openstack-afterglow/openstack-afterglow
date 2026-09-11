<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { projectNames } from '$lib/stores/projectNames';

	let {
		open = $bindable(false),
		onCreated,
	}: {
		open: boolean;
		onCreated: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let form = $state({ name: '', description: '', enabled: true });
	let creating = $state(false);
	let createError = $state('');

	$effect(() => {
		if (open) {
			form = { name: '', description: '', enabled: true };
			createError = '';
		}
	});

	async function createProject() {
		creating = true;
		createError = '';
		const namesScope = projectNames.scope(token, projectId);
		projectNames.invalidate(namesScope);
		try {
			await api.post(
				'/api/v1/admin/projects',
				{ name: form.name, description: form.description || null, enabled: form.enabled },
				token,
				projectId,
			);
			projectNames.invalidate(namesScope);
			open = false;
			onCreated();
		} catch (e) {
			createError = e instanceof ApiError ? e.message : '생성 실패';
		} finally {
			creating = false;
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; createError = ''; }}
		role="dialog" aria-modal="true" tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">프로젝트 생성</h2>
			{#if createError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{createError}</div>
			{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminprojectcreatemodal-72">이름</label>
					<input id="field-adminprojectcreatemodal-72" bind:value={form.name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminprojectcreatemodal-76">설명</label>
					<input id="field-adminprojectcreatemodal-76" bind:value={form.description} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div class="flex items-center gap-3">
					<button
						type="button"
						role="switch"
						aria-label="프로젝트 활성 상태"
						aria-checked={form.enabled}
						onclick={() => (form.enabled = !form.enabled)}
						class="relative w-11 h-6 rounded-full transition-colors {form.enabled ? 'bg-action-warm' : 'bg-surface-selected'}"
					><span class="absolute top-0.5 left-0.5 w-5 h-5 bg-surface-base rounded-full transition-transform {form.enabled ? 'translate-x-5' : ''}"></span></button>
					<span class="text-sm text-ink-2">{form.enabled ? '활성' : '비활성'}</span>
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; createError = ''; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={createProject} disabled={creating || !form.name} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{creating ? '생성 중...' : '생성'}</button>
			</div>
		</div>
	</div>
{/if}
