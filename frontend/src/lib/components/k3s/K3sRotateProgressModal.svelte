<script lang="ts">
	import { getBaseUrl } from '$lib/api/client';

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
	let progress = $state(0);

	$effect(() => {
		void startRotation();
	});

	async function startRotation() {
		messages = [];
		done = false;
		failed = false;
		progress = 0;

		const headers: Record<string, string> = {};
		if (token) headers['Authorization'] = `Bearer ${token}`;
		if (projectId) headers['X-Project-Id'] = projectId;

		try {
			const resp = await fetch(`${getBaseUrl()}/api/v1/k3s/clusters/${clusterId}/rotate-certs`, {
				method: 'POST',
				headers,
			});

			if (!resp.ok) {
				const body = await resp.json().catch(() => ({}));
				messages = [
					{
						step: 'failed',
						progress: 0,
						message: body.detail ?? `오류 ${resp.status}`,
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
		} catch (e) {
			messages = [
				{
					step: 'failed',
					progress: 0,
					message: e instanceof Error ? e.message : '연결 오류',
					error: 'network',
				},
			];
			failed = true;
			done = true;
		}
	}

	function stepLabel(step: string): string {
		const map: Record<string, string> = {
			rotate_discover: '노드 검색',
			rotate_server: '서버 재시작',
			rotate_agent: '에이전트 재시작',
			rotate_verify: '검증',
			completed: '완료',
			failed: '실패',
		};
		return map[step] ?? step;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && done) onclose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="fixed inset-0 z-[60] flex items-center justify-center">
	<button class="absolute inset-0 bg-surface-scrim/70" onclick={() => done && onclose()} aria-label="닫기" tabindex="-1"></button>

	<div class="relative bg-surface-canvas border border-line rounded-lg w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)] max-h-[85vh] flex flex-col">
		<div class="flex items-center justify-between px-5 py-4 border-b border-line shrink-0">
			<h2 class="text-sm font-semibold text-ink-0">인증서 회전 — {clusterName}</h2>
			{#if done}
				<button onclick={onclose} class="text-ink-3 hover:text-ink-0 transition-colors text-lg leading-none">&times;</button>
			{/if}
		</div>

		<!-- 진행률 바 -->
		<div class="px-5 pt-4 shrink-0">
			<div class="h-1.5 bg-surface-sunken rounded-full overflow-hidden">
				<div
					class="h-full transition-all duration-500 rounded-full {failed ? 'bg-red-500' : done ? 'bg-green-500' : 'bg-action-warm'}"
					style="width: {progress}%"
				></div>
			</div>
			<p class="text-xs text-ink-3 mt-1 text-right">{progress}%</p>
		</div>

		<!-- 로그 -->
		<div class="flex-1 overflow-y-auto px-5 py-3 space-y-1.5 min-h-0">
			{#each messages as msg}
				<div class="flex items-start gap-2 text-xs">
					<span class="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-mono
						{msg.step === 'completed' ? 'bg-green-900/40 text-green-400' :
						 msg.step === 'failed' ? 'bg-red-900/40 text-red-400' :
						 msg.step === 'rotate_server' ? 'bg-surface-selected/40 text-action-warm' :
						 'bg-surface-sunken text-ink-2'}">
						{stepLabel(msg.step)}
					</span>
					<span class="text-ink-2 leading-relaxed">{msg.message}</span>
					{#if msg.elapsed_seconds != null}
						<span class="ml-auto shrink-0 text-ink-3">{msg.elapsed_seconds}s</span>
					{/if}
				</div>
				{#if msg.error && msg.step === 'failed'}
					<p class="text-xs text-red-400 pl-2 font-mono">{msg.error}</p>
				{/if}
			{/each}
			{#if !done}
				<div class="flex items-center gap-2 text-xs text-ink-3">
					<span class="inline-block w-2 h-2 bg-action-warm rounded-full animate-pulse"></span>
					진행 중...
				</div>
			{/if}
		</div>

		<div class="px-5 pb-4 pt-2 flex justify-end shrink-0 border-t border-line">
			<button
				onclick={onclose}
				disabled={!done}
				class="text-xs px-3 py-1.5 rounded-lg transition-colors
					{done ? 'bg-surface-selected hover:bg-surface-selected text-ink-0' : 'bg-surface-sunken text-ink-3 cursor-not-allowed'}"
			>
				{done ? '닫기' : '진행 중...'}
			</button>
		</div>
	</div>
</div>
