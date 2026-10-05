<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import RichText from '$lib/i18n/RichText.svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	interface Props {
		serverId: string;
		serverName: string;
		currentHost?: string | null;
		onClose: () => void;
		onEvacuated?: () => void;
	}

	let { serverId, serverName, currentHost, onClose, onEvacuated }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	type Phase = 'idle' | 'executing' | 'done' | 'error';
	let phase = $state<Phase>('idle');
	let host = $state('');
	let onSharedStorage = $state(false);
	let errorMsg = $state('');
	let confirmed = $state(false);

	async function execute() {
		if (!confirmed) return;
		phase = 'executing';
		try {
			await api.post(
				`/api/v1/admin/instances/${serverId}/evacuate`,
				{ host: host.trim() || null, on_shared_storage: onSharedStorage },
				token,
				projectId,
			);
			phase = 'done';
			onEvacuated?.();
		} catch (e: unknown) {
			errorMsg = e instanceof Error ? e.message : t('instances.evacuate.failed');
			phase = 'error';
		}
	}
</script>

<div
	use:dialogFocus={{ enabled: true, onEscape: () => { if (phase !== 'executing') onClose(); } }}
	class="material-scrim fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/60 p-4"
	role="dialog"
	aria-modal="true"
	aria-label={t('instances.evacuate.label')}
	tabindex="-1"
>
	<div class="bg-surface-base border border-line-2 rounded-xl w-full max-w-lg shadow-[var(--shadow-restraint)]">
		<!-- 헤더 -->
		<div class="flex items-center justify-between px-6 py-4 border-b border-line">
			<div>
				<h2 class="text-ink-0 font-semibold text-base">{t('instances.evacuate.title')}</h2>
				<p class="text-ink-2 text-xs mt-0.5 font-mono">{serverName} · {serverId.slice(0, 8)}</p>
			</div>
			<button onclick={onClose} aria-label={t('instances.closeDialog')} class="text-ink-2 hover:text-ink-1 transition-colors text-lg leading-none">✕</button>
		</div>

		<div class="px-6 py-5 space-y-4">

			<!-- 설명 -->
			<div class="bg-surface-selected/20 border border-action-warm/40 text-warm-text rounded-lg px-4 py-3 text-xs leading-relaxed">
				{#snippet cautionLabel(text: string)}<span class="font-medium">{text}</span>{/snippet}
				<RichText segments={t.rich('instances.evacuate.warning')} tags={{ warning: cautionLabel }} />
			</div>

			{#if currentHost}
				<div class="text-xs text-ink-2">
					{#snippet hostName(text: string)}<span class="text-ink-1 font-mono">{text}</span>{/snippet}
					<RichText segments={t.rich('instances.evacuate.currentHost', { host: currentHost })} tags={{ host: hostName }} />
				</div>
			{/if}

			<!-- 에러 -->
			{#if phase === 'error'}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
					{errorMsg}
				</div>
			{/if}

			<!-- 완료 -->
			{#if phase === 'done'}
				<div class="bg-green-900/30 border border-green-700/50 text-green-300 rounded-lg px-4 py-3 text-sm">
					{t('instances.evacuate.requested')}
				</div>
			{:else if phase !== 'executing'}
				<!-- 폼 -->
				<div class="space-y-3">
					<div>
						<label for="evacuate-host" class="block text-xs text-ink-2 mb-1 font-medium">
							{#snippet automaticHint(text: string)}<span class="text-ink-2">{text}</span>{/snippet}
							<RichText segments={t.rich('instances.evacuate.targetHost')} tags={{ hint: automaticHint }} />
						</label>
						<input
							id="evacuate-host"
							type="text"
							bind:value={host}
							placeholder={t('instances.evacuate.hostPlaceholder')}
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
						/>
					</div>

					<label class="flex items-start gap-3 cursor-pointer select-none">
						<input
							type="checkbox"
							bind:checked={onSharedStorage}
							class="mt-0.5 rounded border-line-2 bg-surface-sunken text-warm-text focus:ring-line-2 focus:ring-1"
						/>
						<div>
							<div class="text-sm text-ink-2">{t('instances.evacuate.sharedStorage')}</div>
							<div class="text-xs text-ink-2 mt-0.5">
								{t('instances.evacuate.sharedStorageHelp')}
							</div>
						</div>
					</label>
				</div>
			{/if}

			<!-- 실행 중 -->
			{#if phase === 'executing'}
				<div class="flex items-center gap-3 text-ink-2 text-sm py-4 justify-center">
					<svg class="animate-spin w-5 h-5 text-warm-text" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
					</svg>
					{t('instances.evacuate.requesting')}
				</div>
			{/if}
		</div>

		<!-- 푸터 -->
		<div class="flex items-center justify-between px-6 py-4 border-t border-line gap-4">
			{#if phase === 'idle' || phase === 'error'}
				<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer select-none">
					<input
						type="checkbox"
						bind:checked={confirmed}
						class="rounded border-line-2 bg-surface-sunken text-warm-text focus:ring-line-2 focus:ring-1"
					/>
					<span>{t('instances.evacuate.confirm')}</span>
				</label>
				<button
					onclick={execute}
					disabled={!confirmed}
					class="shrink-0 px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:opacity-40 disabled:cursor-not-allowed text-action-on-warm text-sm font-medium rounded-lg transition-colors"
				>
					{t('instances.evacuate.execute')}
				</button>
			{:else}
				<div></div>
				<button
					onclick={onClose}
					class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg transition-colors"
				>
					{t('instances.close')}
				</button>
			{/if}
		</div>
	</div>
</div>
