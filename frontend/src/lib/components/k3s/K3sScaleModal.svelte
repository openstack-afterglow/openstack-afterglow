<script lang="ts">
	interface Props {
		deploymentName: string;
		currentReplicas: number;
		onClose: () => void;
		onApply: (replicas: number) => Promise<void>;
	}

	let { deploymentName, currentReplicas, onClose, onApply }: Props = $props();

	let replicas = $state(0);
	let applying = $state(false);

	$effect(() => {
		replicas = currentReplicas;
	});

	async function handleApply() {
		applying = true;
		try {
			await onApply(replicas);
			onClose();
		} finally {
			applying = false;
		}
	}
</script>

<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/60"
	onclick={(event) => {
		if (event.target === event.currentTarget) onClose();
	}}
	onkeydown={(event) => event.key === 'Escape' && onClose()}
	tabindex="-1"
	role="dialog"
	aria-modal="true"
>
	<div class="bg-surface-base border border-line-2 rounded-lg p-6 w-80 shadow-[var(--shadow-restraint)]" role="none">
		<h3 class="text-sm font-semibold text-ink-0 mb-1">Deployment 스케일</h3>
		<p class="text-xs text-ink-2 mb-4 font-mono">{deploymentName}</p>

		<div class="flex items-center justify-center gap-4 mb-6">
			<button
				onclick={() => { replicas = Math.max(0, replicas - 1); }}
				class="w-9 h-9 rounded-lg bg-surface-sunken text-ink-0 text-lg hover:bg-surface-selected transition-colors disabled:opacity-40"
				disabled={replicas <= 0}
			>−</button>
			<span class="text-2xl font-bold text-ink-0 tabular-nums w-12 text-center">{replicas}</span>
			<button
				onclick={() => { replicas = Math.min(100, replicas + 1); }}
				class="w-9 h-9 rounded-lg bg-surface-sunken text-ink-0 text-lg hover:bg-surface-selected transition-colors disabled:opacity-40"
				disabled={replicas >= 100}
			>+</button>
		</div>

		<div class="flex gap-2">
			<button
				onclick={onClose}
				class="flex-1 py-2 rounded-lg text-xs text-ink-2 bg-surface-sunken hover:bg-surface-selected transition-colors"
			>취소</button>
			<button
				onclick={handleApply}
				disabled={applying || replicas === currentReplicas}
				class="flex-1 py-2 rounded-lg text-xs text-action-on-warm bg-action-warm hover:bg-action-warm-hover disabled:opacity-40 transition-colors"
			>{applying ? '적용 중...' : '적용'}</button>
		</div>
	</div>
</div>
