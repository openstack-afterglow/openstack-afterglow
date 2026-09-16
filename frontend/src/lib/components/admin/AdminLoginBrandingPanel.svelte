<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError, getBaseUrl } from '$lib/api/client';
	import { initSiteConfig, qualifyBackendAssetPaths, siteConfig } from '$lib/config/site';
	import { Alert, Button, Card } from '$lib/components/ui';

	type BrandingSlot = 'logo_light' | 'logo_dark';
	type LogoField = 'logo_light_path' | 'logo_dark_path';

	interface BrandingAsset {
		slot: BrandingSlot;
		filename: string;
		content_type: string;
		size_bytes: number;
		sha256: string;
		url: string;
		updated_at: string;
		updated_by_user_id: string | null;
	}

	interface BrandingStatus {
		effective: Record<'logo_path' | LogoField, string>;
		assets: Record<BrandingSlot, BrandingAsset | null>;
	}

	interface Props {
		token?: string;
		projectId?: string;
	}

	let { token, projectId }: Props = $props();

	const slots: { key: BrandingSlot; field: LogoField; title: string; description: string; previewClass: string }[] = [
		{
			key: 'logo_light',
			field: 'logo_light_path',
			title: 'Dark login background',
			description: '밝은 로고. 기본 어두운 로그인 배경에서 사용됩니다.',
			previewClass: 'preview-dark',
		},
		{
			key: 'logo_dark',
			field: 'logo_dark_path',
			title: 'Light login background',
			description: '어두운 로고. light theme 로그인 배경에서 사용됩니다.',
			previewClass: 'preview-light',
		},
	];

	let status = $state<BrandingStatus | null>(null);
	let loading = $state(true);
	let error = $state('');
	let notice = $state('');
	let pendingSlot = $state<BrandingSlot | null>(null);

	function applyStatus(next: BrandingStatus) {
		const effective = qualifyBackendAssetPaths(next.effective, getBaseUrl()) as BrandingStatus['effective'];
		status = { ...next, effective };
		initSiteConfig(effective);
	}

	async function loadStatus() {
		loading = true;
		error = '';
		try {
			applyStatus(await api.get<BrandingStatus>('/api/v1/site-config/admin/branding', token, projectId));
		} catch (e) {
			error = e instanceof ApiError ? `브랜딩 설정 조회 실패: ${e.message}` : '브랜딩 설정 조회 실패';
		} finally {
			loading = false;
		}
	}

	function effectivePath(field: LogoField): string {
		return status?.effective[field] || $siteConfig[field] || $siteConfig.logo_path;
	}

	function formatSize(size: number): string {
		return `${Math.ceil(size / 1024)} KiB`;
	}

	async function uploadLogo(slot: BrandingSlot, event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		if (file.size > 1_048_576) {
			error = '로고 파일은 1 MiB 이하여야 합니다';
			input.value = '';
			return;
		}
		pendingSlot = slot;
		error = '';
		notice = '';
		try {
			const formData = new FormData();
			formData.append('file', file, file.name);
			applyStatus(await api.upload<BrandingStatus>(`/api/v1/site-config/admin/branding/${slot}`, formData, token, projectId));
			notice = '로그인 로고를 업데이트했습니다';
		} catch (e) {
			error = e instanceof ApiError ? `업로드 실패: ${e.message}` : '업로드 실패';
		} finally {
			pendingSlot = null;
			input.value = '';
		}
	}

	async function resetLogo(slot: BrandingSlot) {
		pendingSlot = slot;
		error = '';
		notice = '';
		try {
			applyStatus(await api.delete<BrandingStatus>(`/api/v1/site-config/admin/branding/${slot}`, token, projectId));
			notice = '로그인 로고를 기본 설정으로 되돌렸습니다';
		} catch (e) {
			error = e instanceof ApiError ? `초기화 실패: ${e.message}` : '초기화 실패';
		} finally {
			pendingSlot = null;
		}
	}

	onMount(() => {
		void loadStatus();
	});
</script>

<Card padding="lg" class="login-branding-panel">
	<div class="panel-header">
		<div>
			<p class="eyebrow">Login branding</p>
			<h2>로그인 로고</h2>
			<p class="summary">배경별 로그인 로고를 DB에 저장합니다. 업로드가 없으면 config/static 기본값이 유지됩니다.</p>
		</div>
		<Button variant="subtle" size="sm" onclick={loadStatus} disabled={loading || pendingSlot !== null}>새로고침</Button>
	</div>

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}
	{#if notice}
		<Alert tone="success">{notice}</Alert>
	{/if}

	{#if loading}
		<div class="loading-card">브랜딩 설정을 불러오는 중...</div>
	{:else}
		<div class="slot-grid">
			{#each slots as slot}
				{@const asset = status?.assets[slot.key] ?? null}
				{@const path = effectivePath(slot.field)}
				<div class="slot-card">
					<div class="slot-copy">
						<div>
							<h3>{slot.title}</h3>
							<p>{slot.description}</p>
						</div>
						<span class="asset-state" data-uploaded={asset !== null}>{asset ? 'Uploaded' : 'Config default'}</span>
					</div>

					<div class="logo-preview {slot.previewClass}">
						<img src={path} alt="{slot.title} preview" loading="lazy" />
					</div>

					<dl class="asset-meta">
						<div>
							<dt>Effective path</dt>
							<dd title={path}>{path}</dd>
						</div>
						{#if asset}
							<div>
								<dt>Stored file</dt>
								<dd>{asset.filename} · {asset.content_type} · {formatSize(asset.size_bytes)}</dd>
							</div>
						{/if}
					</dl>

					<div class="slot-actions">
						<label class="upload-label" aria-disabled={pendingSlot !== null}>
							<input
								type="file"
								accept="image/png,image/jpeg,image/webp,image/gif"
								disabled={pendingSlot !== null}
								onchange={(event) => uploadLogo(slot.key, event)}
							/>
							<span>{pendingSlot === slot.key ? '업로드 중...' : '업로드'}</span>
						</label>
						<Button variant="ghost" size="sm" onclick={() => resetLogo(slot.key)} disabled={pendingSlot !== null || asset === null}>초기화</Button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</Card>

<style>
	.login-branding-panel :global(.card) { overflow: visible; }
	.panel-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1rem;
	}
	.eyebrow {
		margin: 0 0 0.25rem;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--admin-tone, var(--color-brand));
	}
	h2 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 700;
		color: var(--color-ink-0);
	}
	.summary {
		margin: 0.35rem 0 0;
		font-size: 0.8rem;
		color: var(--color-ink-2);
	}
	.loading-card {
		border: 1px dashed var(--color-line);
		border-radius: 0.875rem;
		padding: 1rem;
		font-size: 0.85rem;
		color: var(--color-ink-2);
	}
	.slot-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
	}
	.slot-card {
		border: 1px solid var(--color-line);
		border-radius: 0.9rem;
		padding: 0.9rem;
		background: color-mix(in oklab, var(--color-surface-sunken) 76%, transparent);
	}
	.slot-copy {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}
	h3 {
		margin: 0;
		font-size: 0.9rem;
		font-weight: 650;
		color: var(--color-ink-1);
	}
	.slot-copy p {
		margin: 0.25rem 0 0;
		font-size: 0.76rem;
		line-height: 1.45;
		color: var(--color-ink-2);
	}
	.asset-state {
		align-self: flex-start;
		border: 1px solid var(--color-line);
		border-radius: 999px;
		padding: 0.16rem 0.45rem;
		font-size: 0.65rem;
		font-weight: 700;
		color: var(--color-ink-2);
		white-space: nowrap;
	}
	.asset-state[data-uploaded='true'] {
		border-color: color-mix(in oklab, var(--color-state-success) 36%, transparent);
		color: var(--color-state-success);
		background: color-mix(in oklab, var(--color-state-success) 10%, transparent);
	}
	.logo-preview {
		display: grid;
		place-items: center;
		min-height: 8rem;
		border-radius: 0.75rem;
		border: 1px solid color-mix(in oklab, var(--color-line) 80%, transparent);
		margin-bottom: 0.75rem;
		padding: 1rem;
	}
	.logo-preview img {
		max-width: min(16rem, 100%);
		max-height: 6rem;
		object-fit: contain;
	}
	.preview-dark {
		background: radial-gradient(circle at 30% 20%, color-mix(in oklab, var(--color-warm) 15%, transparent), transparent 35%), var(--color-surface-base);
	}
	.preview-light {
		background: linear-gradient(135deg, var(--color-ink-0), var(--color-ink-1));
	}
	.asset-meta {
		display: grid;
		gap: 0.5rem;
		margin: 0 0 0.85rem;
	}
	.asset-meta div { min-width: 0; }
	dt {
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-ink-2);
	}
	dd {
		margin: 0.15rem 0 0;
		font-size: 0.75rem;
		color: var(--color-ink-2);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.slot-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.upload-label {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 2rem;
		border: 1px solid color-mix(in oklab, var(--admin-tone, var(--color-brand)) 38%, transparent);
		border-radius: 0.65rem;
		padding: 0 0.75rem;
		font-size: 0.78rem;
		font-weight: 650;
		color: var(--admin-tone, var(--color-brand));
		background: color-mix(in oklab, var(--admin-tone, var(--color-brand)) 9%, transparent);
		cursor: pointer;
	}
	.upload-label:hover {
		background: color-mix(in oklab, var(--admin-tone, var(--color-brand)) 15%, transparent);
	}
	.upload-label[aria-disabled='true'] {
		opacity: 0.55;
		cursor: not-allowed;
	}
	.upload-label input {
		position: absolute;
		inline-size: 1px;
		block-size: 1px;
		opacity: 0;
		pointer-events: none;
	}
	@media (max-width: 900px) {
		.slot-grid { grid-template-columns: 1fr; }
		.panel-header { flex-direction: column; }
	}
</style>
