import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));

import { DEFAULT_BETA_FEATURES, betaFeatures, setBetaFeature } from '../betaFeatures';

describe('betaFeatures store', () => {
	beforeEach(() => {
		localStorage.clear();
		betaFeatures.set(DEFAULT_BETA_FEATURES);
	});

	it('ignores retired persisted flags while preserving unrelated preferences', async () => {
		localStorage.setItem('afterglow.beta.libraryConsume', 'true');
		localStorage.setItem('afterglow.beta.haDeploy', 'true');
		localStorage.setItem('afterglow.beta.keyManager', 'true');
		localStorage.setItem('afterglow.beta.fileStorageSnapshots', 'true');
		localStorage.setItem('afterglow.beta.fileStorageSecurityServices', 'true');
		localStorage.setItem('afterglow_theme', 'light');

		vi.resetModules();
		// Re-import after seeding storage to exercise initialization; a static import runs before the fixture.
		const restored = await import('../betaFeatures');
		expect(get(restored.betaFeatures)).toEqual({
			...DEFAULT_BETA_FEATURES,
			keyManager: true,
			fileStorageSnapshots: true,
			fileStorageSecurityServices: true,
		});
		expect(restored.DEFAULT_BETA_FEATURES).not.toHaveProperty('libraryConsume');
		expect(restored.DEFAULT_BETA_FEATURES).not.toHaveProperty('haDeploy');

		restored.setBetaFeature('volumeSnapshots', true);
		expect(get(restored.betaFeatures)).toEqual({
			...DEFAULT_BETA_FEATURES,
			keyManager: true,
			volumeSnapshots: true,
			fileStorageSnapshots: true,
			fileStorageSecurityServices: true,
		});
		expect(localStorage.getItem('afterglow.beta.libraryConsume')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.haDeploy')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.keyManager')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.fileStorageSnapshots')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.fileStorageSecurityServices')).toBe('true');
		expect(localStorage.getItem('afterglow_theme')).toBe('light');
	});

	it('persists the Key Manager beta toggle without enabling other validating features', () => {
		setBetaFeature('keyManager', true);

		expect(get(betaFeatures)).toEqual({ ...DEFAULT_BETA_FEATURES, keyManager: true });
		expect(localStorage.getItem('afterglow.beta.keyManager')).toBe('true');
		expect(localStorage.getItem('afterglow.beta.libraryConsume')).toBeNull();
		expect(localStorage.getItem('afterglow.beta.haDeploy')).toBeNull();
	});

});
