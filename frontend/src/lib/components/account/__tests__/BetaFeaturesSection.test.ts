import { get } from 'svelte/store';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));

import BetaFeaturesSection from '../BetaFeaturesSection.svelte';
import { DEFAULT_BETA_FEATURES, betaFeatures } from '$lib/stores/betaFeatures';

describe('BetaFeaturesSection', () => {
	beforeEach(() => {
		localStorage.clear();
		betaFeatures.set(DEFAULT_BETA_FEATURES);
	});

	it('renders per-browser advanced VM option guidance', () => {
		render(BetaFeaturesSection);

		expect(screen.getByText('고급 VM 생성 옵션')).toBeTruthy();
		expect(
			screen.getByText('이 설정은 현재 브라우저에만 저장됩니다. 프로젝트 전체 서버 설정이나 다른 사용자에게는 적용되지 않습니다.'),
		).toBeTruthy();
	});

	it('toggles and persists beta feature flags', async () => {
		render(BetaFeaturesSection);

		const checkboxLabels = [
			'squashfs 라이브러리 소비 VM 생성 단계 표시',
			'HA 배포 옵션 표시',
			'Key Manager 표시',
			'볼륨 백업 표시',
			'볼륨 스냅샷 표시',
			'파일 스토리지 스냅샷 표시',
			'Share 네트워크 표시',
			'Security Service 표시',
			'DB 백업 표시',
		];

		for (const label of checkboxLabels) {
			expect(screen.getByRole('checkbox', { name: label })).toBeTruthy();
		}

		const squashfsToggle = screen.getByRole('checkbox', { name: checkboxLabels[0] }) as HTMLInputElement;
		const haToggle = screen.getByRole('checkbox', { name: checkboxLabels[1] }) as HTMLInputElement;
		const keyManagerToggle = screen.getByRole('checkbox', { name: 'Key Manager 표시' }) as HTMLInputElement;
		const volumeBackupsToggle = screen.getByRole('checkbox', { name: '볼륨 백업 표시' }) as HTMLInputElement;
		const fileStorageSnapshotsToggle = screen.getByRole('checkbox', { name: '파일 스토리지 스냅샷 표시' }) as HTMLInputElement;
		const databaseBackupsToggle = screen.getByRole('checkbox', { name: 'DB 백업 표시' }) as HTMLInputElement;

		expect(squashfsToggle.checked).toBe(false);
		expect(haToggle.checked).toBe(false);
		expect(keyManagerToggle.checked).toBe(false);
		expect(volumeBackupsToggle.checked).toBe(true);

		await fireEvent.click(squashfsToggle);
		await fireEvent.click(haToggle);
		await fireEvent.click(keyManagerToggle);
		await fireEvent.click(fileStorageSnapshotsToggle);
		await fireEvent.click(databaseBackupsToggle);

		expect(get(betaFeatures)).toEqual({
			...DEFAULT_BETA_FEATURES,
			libraryConsume: true,
			haDeploy: true,
			keyManager: true,
			volumeBackups: true,
			fileStorageSnapshots: true,
			databaseBackups: true,
		});
		expect(squashfsToggle.checked).toBe(true);
		expect(haToggle.checked).toBe(true);
		expect(keyManagerToggle.checked).toBe(true);
		expect(localStorage.getItem('afterglow.beta.libraryConsume')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.haDeploy')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.keyManager')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.volumeBackups')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.fileStorageSnapshots')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.databaseBackups')).toBe('true');
	});
});
