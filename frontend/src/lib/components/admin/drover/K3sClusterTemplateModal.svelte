<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { K3sClusterTemplate } from '$lib/types/k3s';

	let {
		template = null,
		onClose,
		onSaved,
	}: {
		template?: K3sClusterTemplate | null;
		onClose: () => void;
		onSaved: () => void;
	} = $props();

	const isEdit = $derived(template !== null);

	let form = $state({
		name: '',
		description: '',
		k3s_version: '',
		default_node_count: 1,
		default_agent_flavor_id: '',
		default_image_id: '',
		os_type: 'ubuntu',
		public_visible: true,
	});

	$effect(() => {
		if (template) {
			form.name = template.name;
			form.description = template.description ?? '';
			form.k3s_version = template.k3s_version ?? '';
			form.default_node_count = template.default_node_count;
			form.default_agent_flavor_id = template.default_agent_flavor_id ?? '';
			form.default_image_id = template.default_image_id ?? '';
			form.os_type = template.os_type ?? 'ubuntu';
			form.public_visible = template.public_visible ?? true;
		}
	});

	let saving = $state(false);
	let error = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function save() {
		saving = true;
		error = '';
		try {
			const body = {
				...form,
				default_node_count: Number(form.default_node_count),
				k3s_version: form.k3s_version || null,
				default_agent_flavor_id: form.default_agent_flavor_id || null,
				default_image_id: form.default_image_id || null,
				description: form.description || null,
			};
			if (isEdit && template) {
				await api.patch(`/api/v1/k3s/cluster-templates/${template.id}`, body, token, projectId);
			} else {
				await api.post('/api/v1/k3s/cluster-templates', body, token, projectId);
			}
			onSaved();
		} catch (e) {
			error = e instanceof ApiError ? e.message : '저장 실패';
		} finally {
			saving = false;
		}
	}
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
		<h2 class="text-lg font-semibold text-ink-0 mb-5">{isEdit ? '템플릿 수정' : '템플릿 생성'}</h2>

		<div class="space-y-4">
			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				이름
				<input
					bind:value={form.name}
					disabled={isEdit}
					type="text"
					placeholder="my-template"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5 disabled:opacity-50"
				/>
			</label>

			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				설명 (선택)
				<input
					bind:value={form.description}
					type="text"
					placeholder="GPU dev 노드 3대 + Cinder CSI"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
				/>
			</label>

			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				k3s 버전 (선택, 미지정 시 설정값)
				<input
					bind:value={form.k3s_version}
					type="text"
					placeholder="v1.32.0+k3s1"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1.5"
				/>
			</label>

			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				기본 에이전트 수
				<input
					bind:value={form.default_node_count}
					type="number"
					min="0"
					max="20"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
				/>
			</label>

			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				기본 에이전트 Flavor ID (선택)
				<input
					bind:value={form.default_agent_flavor_id}
					type="text"
					placeholder="flavor-uuid"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1.5"
				/>
			</label>

			<div>
				<span class="block text-xs text-ink-2 uppercase tracking-wide mb-1.5">OS 타입</span>
				<div class="flex gap-2">
					<button
						type="button"
						onclick={() => (form.os_type = 'ubuntu')}
						class="flex-1 px-3 py-2 rounded-lg border text-sm transition-colors {form.os_type === 'ubuntu' ? 'border-action-warm bg-surface-selected/30 text-ink-0' : 'border-line-2 bg-surface-sunken text-ink-2 hover:border-line-2'}"
					>Ubuntu</button>
					<button
						type="button"
						onclick={() => (form.os_type = 'fcos')}
						class="flex-1 px-3 py-2 rounded-lg border text-sm transition-colors {form.os_type === 'fcos' ? 'border-orange-500 bg-orange-900/30 text-ink-0' : 'border-line-2 bg-surface-sunken text-ink-2 hover:border-line-2'}"
					>CoreOS</button>
				</div>
			</div>

			<label class="flex items-center gap-2 cursor-pointer text-sm text-ink-2">
				<input type="checkbox" bind:checked={form.public_visible} class="accent-blue-500" />
				사용자에게 공개
			</label>
		</div>

		{#if error}
			<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
		{/if}

		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} disabled={saving} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0">취소</button>
			<button
				onclick={save}
				disabled={saving || !form.name}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg"
			>
				{saving ? '저장 중...' : isEdit ? '수정' : '생성'}
			</button>
		</div>
	</div>
</div>
