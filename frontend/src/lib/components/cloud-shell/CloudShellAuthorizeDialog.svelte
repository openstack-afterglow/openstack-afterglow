<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import { cloudShell } from '$lib/stores/cloudShell.svelte';

	const projectName = $derived(cloudShell.identity?.projectName || '현재 프로젝트');
</script>

<Modal
	open={cloudShell.phase === 'consent'}
	onClose={() => cloudShell.cancelConsent()}
	ariaLabel="Cloud Shell 승인"
>
	<section class="w-[min(34rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface-raised shadow-[var(--shadow-restraint)]">
		<header class="border-b border-line px-5 py-4 sm:px-6">
			<p class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-3">Session authorization</p>
			<h2 class="mt-1 font-display text-lg font-semibold text-ink-0">Cloud Shell 승인</h2>
			<p class="mt-1 text-sm text-ink-2">
				<span class="font-medium text-ink-1">{projectName}</span> 프로젝트 권한으로 새 셸 세션을 시작합니다.
			</p>
		</header>

		<div class="space-y-4 px-5 py-5 sm:px-6">
			<Alert tone="info" title="이 세션에서 사용하는 권한">
				현재 로그인 사용자와 선택 프로젝트의 권한으로 OpenStack API를 실행합니다. 비밀번호는 요청하거나 저장하지 않습니다.
			</Alert>

			<ul class="space-y-3 text-sm leading-6 text-ink-2">
				<li class="flex gap-3">
					<span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true"></span>
					<span>Keystone 토큰은 이 셸의 임시 <code class="font-mono text-xs text-ink-1">/dev/shm/afterglow</code>에만 기록되고 컨테이너 종료 시 사라집니다.</span>
				</li>
				<li class="flex gap-3">
					<span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true"></span>
					<span>사용자 × 프로젝트별 <strong class="font-medium text-ink-1">{cloudShell.homeSizeGiB} GiB 영구 홈</strong>은 전용 Cloud Shell 프로젝트에 유지됩니다.</span>
				</li>
				<li class="flex gap-3">
					<span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true"></span>
					<span>닫기, 20분 입출력 유휴, 최대 세션 시간, 토큰 만료 중 가장 이른 시점에 종료됩니다. 다음 세션은 다시 승인이 필요합니다.</span>
				</li>
			</ul>
		</div>

		<footer class="flex flex-col-reverse gap-2 border-t border-line px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
			<Button variant="ghost" onclick={() => cloudShell.cancelConsent()}>취소</Button>
			<Button variant="primary" onclick={() => void cloudShell.approve()}>Cloud Shell 승인</Button>
		</footer>
	</section>
</Modal>
