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

	it('renders per-browser beta feature guidance', () => {
		render(BetaFeaturesSection);

		expect(screen.getByText('베타 기능')).toBeTruthy();
		expect(
			screen.getByText('이 설정은 현재 브라우저에만 저장됩니다. 프로젝트 전체 서버 설정이나 다른 사용자에게는 적용되지 않습니다.'),
		).toBeTruthy();
	});

	it('toggles and persists beta feature flags', async () => {
		render(BetaFeaturesSection);

		const checkboxLabels = [
			'Key Manager 표시',
			'볼륨 스냅샷 표시',
			'파일 스토리지 스냅샷 표시',
			'Share 네트워크 표시',
			'Security Service 표시',
		];

		for (const label of checkboxLabels) {
			expect(screen.getByRole('checkbox', { name: label })).toBeTruthy();
		}
		expect(screen.getAllByRole('checkbox')).toHaveLength(checkboxLabels.length);
		expect(screen.queryByRole('checkbox', { name: 'squashfs 라이브러리 소비 VM 생성 단계 표시' })).toBeNull();
		expect(screen.queryByRole('checkbox', { name: 'HA 배포 옵션 표시' })).toBeNull();

		const keyManagerToggle = screen.getByRole('checkbox', { name: 'Key Manager 표시' }) as HTMLInputElement;
		const fileStorageSnapshotsToggle = screen.getByRole('checkbox', { name: '파일 스토리지 스냅샷 표시' }) as HTMLInputElement;

		expect(keyManagerToggle.checked).toBe(false);

		await fireEvent.click(keyManagerToggle);
		await fireEvent.click(fileStorageSnapshotsToggle);

		expect(get(betaFeatures)).toEqual({
			...DEFAULT_BETA_FEATURES,
			keyManager: true,
			fileStorageSnapshots: true,
		});
		expect(keyManagerToggle.checked).toBe(true);
		expect(localStorage.getItem('afterglow.beta.keyManager')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.fileStorageSnapshots')).toBe('true');
	});
});
