<script lang="ts">
	import ProfileSection from '$lib/components/account/ProfileSection.svelte';
	import PasswordSection from '$lib/components/account/PasswordSection.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';

	let { open = $bindable(false), onclose }: { open?: boolean; onclose?: () => void } = $props();

	function close() {
		open = false;
		onclose?.();
	}
</script>


{#if open}
<Modal bind:open onClose={close} labelledBy="account-settings-title">
	<div class="w-[min(32rem,calc(100vw-2rem))] max-h-[85vh] overflow-y-auto rounded-lg border border-line bg-surface-canvas shadow-[var(--shadow-restraint)]">
		<!-- 헤더 -->
		<div class="flex items-center justify-between px-6 py-4 border-b border-line sticky top-0 bg-surface-canvas z-10">
			<h2 id="account-settings-title" class="text-lg font-bold text-ink-0">계정 설정</h2>
			<div class="flex items-center gap-3">
				<a href="/dashboard/account" onclick={close} class="text-xs text-action-warm hover:text-action-warm-hover transition-colors">전체 설정 →</a>
				<button type="button" onclick={close} aria-label="계정 설정 닫기" class="text-ink-2 hover:text-ink-0 transition-colors p-1 rounded-lg hover:bg-surface-sunken">
					<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
					</svg>
				</button>
			</div>
		</div>

		<div class="p-6 space-y-4">
			<ProfileSection />
			<PasswordSection />
		</div>
	</div>
</Modal>
{/if}
