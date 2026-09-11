<script lang="ts">
	import { betaFeatures, setBetaFeature } from '$lib/stores/betaFeatures';

	const validatingFeatures = [
		{ key: 'keyManager', label: 'Key Manager 표시', description: 'Barbican Key Manager 화면을 사이드바와 직접 경로에서 노출합니다.' },
		{ key: 'volumeBackups', label: '볼륨 백업 표시', description: '볼륨 백업 목록, 생성, 복원, 자동 백업 설정을 노출합니다.' },
		{ key: 'volumeSnapshots', label: '볼륨 스냅샷 표시', description: '볼륨 스냅샷 목록과 생성 액션을 노출합니다.' },
		{ key: 'fileStorageSnapshots', label: '파일 스토리지 스냅샷 표시', description: '파일 스토리지 스냅샷 목록과 생성 액션을 노출합니다.' },
		{ key: 'fileStorageShareNetworks', label: 'Share 네트워크 표시', description: '파일 스토리지 Share 네트워크 목록과 생성 플로우를 노출합니다.' },
		{ key: 'fileStorageSecurityServices', label: 'Security Service 표시', description: '파일 스토리지 Security Service 목록과 연결 플로우를 노출합니다.' },
		{ key: 'databaseBackups', label: 'DB 백업 표시', description: 'DB 백업 목록, 생성, 복원, 자동 백업 설정을 노출합니다.' },
	] as const;
</script>

<section class="bg-surface-base border border-line rounded-xl p-5">
	<div class="mb-5">
		<p class="text-sm font-semibold text-ink-0">고급 VM 생성 옵션</p>
		<p class="text-xs text-ink-2 mt-1">
			이 설정은 현재 브라우저에만 저장됩니다. 프로젝트 전체 서버 설정이나 다른 사용자에게는 적용되지 않습니다.
		</p>
	</div>

	<div class="space-y-6">
		<div class="space-y-4">
			<label class="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface-canvas/40 px-4 py-3">
				<span>
					<span class="block text-sm font-medium text-ink-1">squashfs 라이브러리 소비 VM 생성 단계 표시</span>
					<span class="block text-xs text-ink-3 mt-1">Ubuntu 이미지 선택 시 VM 생성 마법사에서 관리자 공개 squashfs 프로필/레이어를 선택합니다.</span>
				</span>
				<input
					type="checkbox"
					aria-label="squashfs 라이브러리 소비 VM 생성 단계 표시"
					class="mt-1 h-4 w-4 rounded border-line-2 bg-surface-sunken text-blue-600 focus:ring-line-2"
					checked={$betaFeatures.libraryConsume}
					onchange={(event) => setBetaFeature('libraryConsume', event.currentTarget.checked)}
				/>
			</label>

			<label class="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface-canvas/40 px-4 py-3">
				<span>
					<span class="block text-sm font-medium text-ink-1">HA 배포 옵션 표시</span>
					<span class="block text-xs text-ink-3 mt-1">VM 생성 전략 단계에서 HA 스케줄링 옵션을 노출합니다.</span>
				</span>
				<input
					type="checkbox"
					aria-label="HA 배포 옵션 표시"
					class="mt-1 h-4 w-4 rounded border-line-2 bg-surface-sunken text-blue-600 focus:ring-line-2"
					checked={$betaFeatures.haDeploy}
					onchange={(event) => setBetaFeature('haDeploy', event.currentTarget.checked)}
				/>
			</label>
		</div>

		<div class="space-y-4">
			<div>
				<p class="text-sm font-semibold text-ink-0">검증 중인 기능</p>
				<p class="beta-feature-description text-xs mt-1">아직 일반 공개 품질로 검증되지 않은 기능을 현재 브라우저에서만 노출합니다.</p>
			</div>

			{#each validatingFeatures as feature}
				<label class="beta-feature-card flex items-start justify-between gap-4 rounded-lg px-4 py-3">
					<span>
						<span class="beta-feature-title block text-sm font-medium">{feature.label}</span>
						<span class="beta-feature-description block text-xs mt-1">{feature.description}</span>
					</span>
					<input
						type="checkbox"
						aria-label={feature.label}
						class="beta-feature-checkbox mt-1 h-4 w-4 rounded"
						checked={$betaFeatures[feature.key]}
						onchange={(event) => setBetaFeature(feature.key, event.currentTarget.checked)}
					/>
				</label>
			{/each}
		</div>
	</div>
</section>

<style>
	.beta-feature-card {
		border: 1px solid color-mix(in oklab, var(--color-warm) 24%, var(--color-line));
		background: color-mix(in oklab, var(--color-warm) 7%, var(--color-surface-raised));
	}

	.beta-feature-title {
		color: var(--color-ink-0);
	}

	.beta-feature-description {
		color: var(--color-ink-2);
	}

	.beta-feature-checkbox {
		border-color: var(--color-line-strong);
		background: var(--color-surface-sunken);
		color: var(--color-warm);
		--tw-ring-color: color-mix(in oklab, var(--color-warm) 45%, transparent);
	}
</style>
