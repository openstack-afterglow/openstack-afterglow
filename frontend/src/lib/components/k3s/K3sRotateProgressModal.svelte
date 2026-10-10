<script lang="ts">
	import { t } from '$lib/i18n/ns/drover';
	import { fetchWithAuth } from '$lib/api/client';
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import ProgressTrack from '$lib/components/ui/ProgressTrack.svelte';
	import StepProgress from '$lib/components/ui/StepProgress.svelte';

	interface ProgressMsg {
		step: string;
		progress: number;
		message: string;
		cluster_id?: string;
		error?: string;
		elapsed_seconds?: number;
	}

	interface Props {
		clusterId: string;
		clusterName: string;
		token?: string;
		projectId?: string;
		onclose: () => void;
	}

	const { clusterId, clusterName, token, projectId, onclose }: Props = $props();

	let messages = $state<ProgressMsg[]>([]);
	let done = $state(false);
	let failed = $state(false);
	/** The stream closed cleanly without a completed/failed event: the outcome is unknown, not a failure. */
	let unreported = $state(false);
	let progress = $state(0);
	const rotationSteps = $derived([
		{ id: 'rotate_discover', label: t('rotateProgress.steps.discover') },
		{ id: 'rotate_server', label: t('rotateProgress.steps.server') },
		{ id: 'rotate_verify', label: t('rotateProgress.steps.verify') },
	]);
	const currentStep = $derived.by(() => {
		for (let i = messages.length - 1; i >= 0; i--) {
			if (rotationSteps.some((step) => step.id === messages[i].step)) return messages[i].step;
		}
		return null;
	});
	const rotationStatus = $derived(failed ? 'failed' : done ? 'done' : 'running');

	// Destructive POST: start once on mount. Token/prop refreshes must never re-run it.
	onMount(() => { void startRotation(); });

	async function startRotation() {
		if (!get(k3sPermissions).administerClusters) { onclose(); return; }
		messages = [];
		done = false;
		failed = false;
		unreported = false;
		progress = 0;

		try {
			const resp = await fetchWithAuth(`/api/v1/k3s/clusters/${clusterId}/rotate-certs`, {
				method: 'POST',
			}, token, projectId);

			if (!resp.ok) {
				const body = await resp.json().catch(() => ({}));
				messages = [
					{
						step: 'failed',
						progress: 0,
						message: body.detail ?? t('rotateProgress.httpError', { status: resp.status }),
						error: String(resp.status),
					},
				];
				failed = true;
				done = true;
				return;
			}

			const reader = resp.body?.getReader();
			if (!reader) {
				failed = true;
				done = true;
				return;
			}

			const decoder = new TextDecoder();
			let buf = '';
			while (true) {
				const { value, done: streamDone } = await reader.read();
				if (streamDone) break;
				buf += decoder.decode(value, { stream: true });
				const lines = buf.split('\n');
				buf = lines.pop() ?? '';
				for (const line of lines) {
					if (!line.startsWith('data:')) continue;
					try {
						const msg: ProgressMsg = JSON.parse(line.slice(5).trim());
						messages = [...messages, msg];
						progress = msg.progress;
						if (msg.step === 'completed') {
							done = true;
						} else if (msg.step === 'failed') {
							failed = true;
							done = true;
						}
					} catch {
						// non-JSON SSE line (keepalive)
					}
				}
			}
			if (!done) {
				unreported = true;
				done = true;
			}
		} catch (e) {
			// 스트림 도중 끊겨도 앞선 단계 이력을 남겨 실패가 마지막 보고 단계에 표시되게 한다.
			messages = [
				...messages,
				{
					step: 'failed',
					progress,
					message: e instanceof Error ? e.message : t('rotateProgress.connectionError'),
					error: 'network',
				},
			];
			failed = true;
			done = true;
		}
	}

	function stepLabel(step: string): string {
		const map: Record<string, string> = {
			rotate_discover: t('rotateProgress.steps.discover'),
			rotate_server: t('rotateProgress.steps.server'),
			rotate_agent: t('rotateProgress.steps.agent'),
			rotate_verify: t('rotateProgress.steps.verify'),
			completed: t('rotateProgress.steps.completed'),
			failed: t('rotateProgress.steps.failed'),
		};
		return map[step] ?? step;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && done) onclose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="fixed inset-0 z-[60] flex items-center justify-center">
	<button class="absolute inset-0 bg-surface-scrim/70" onclick={() => done && onclose()} aria-label={t('rotateProgress.close')} tabindex="-1"></button>

	<div class="motion-enter relative bg-surface-canvas border border-line rounded-lg w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)] max-h-[85vh] flex flex-col">
		<div class="flex items-center justify-between px-5 py-4 border-b border-line shrink-0">
			<h2 class="text-sm font-semibold text-ink-0">{t('rotateProgress.title', { name: clusterName })}</h2>
			{#if done}
				<button onclick={onclose} class="text-ink-2 hover:text-ink-0 transition-colors text-lg leading-none">&times;</button>
			{/if}
		</div>

		<!-- 진행률 바 -->
		<div class="px-5 pt-4 shrink-0">
			{#if unreported}
				<p class="mb-4 text-xs text-ink-1" role="status">{t('rotateProgress.unreported')}</p>
			{:else}
				<StepProgress steps={rotationSteps} current={currentStep} status={rotationStatus} label={t('rotateProgress.title', { name: clusterName })} class="mb-4" />
			{/if}
			<ProgressTrack value={messages.length ? progress : null} label={t('rotateProgress.title', { name: clusterName })} tone={failed ? 'danger' : unreported ? 'neutral' : done ? 'success' : 'accent'} active={!done} />
			<p class="text-xs text-ink-2 mt-1 text-right">{progress}%</p>
		</div>

		<!-- 로그 -->
		<div class="flex-1 overflow-y-auto px-5 py-3 space-y-1.5 min-h-0">
			{#each messages as msg, i (i)}
				<div class="motion-fade flex items-start gap-2 text-xs">
					<span class="shrink-0 px-1.5 py-0.5 rounded text-xs font-mono
						{msg.step === 'completed' ? 'bg-state-success/15 text-state-success-text' :
						 msg.step === 'failed' ? 'bg-state-danger/15 text-state-danger-text' :
						 msg.step === 'rotate_server' ? 'bg-surface-selected/40 text-accent' :
						 'bg-surface-sunken text-ink-2'}">
						{stepLabel(msg.step)}
					</span>
					<span class="text-ink-2 leading-relaxed">{msg.message}</span>
					{#if msg.elapsed_seconds != null}
						<span class="ml-auto shrink-0 text-ink-2">{msg.elapsed_seconds}s</span>
					{/if}
				</div>
				{#if msg.error && msg.step === 'failed'}
					<p class="text-xs text-red-400 pl-2 font-mono">{msg.error}</p>
				{/if}
			{/each}
			{#if !done}
				<ActivityIndicator size="xs" label={t('rotateProgress.running')} class="text-xs" />
			{/if}
		</div>

		<div class="px-5 pb-4 pt-2 flex justify-end shrink-0 border-t border-line">
			<button
				onclick={onclose}
				disabled={!done}
				class="text-xs px-3 py-1.5 rounded-lg transition-colors
					{done ? 'bg-surface-selected hover:bg-surface-selected text-ink-0' : 'bg-surface-sunken text-ink-2 cursor-not-allowed'}"
			>
				{done ? t('rotateProgress.close') : t('rotateProgress.running')}
			</button>
		</div>
	</div>
</div>
