import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export interface BetaFeatures {
	libraryConsume: boolean;
	haDeploy: boolean;
	keyManager: boolean;
	volumeBackups: boolean;
	volumeSnapshots: boolean;
	fileStorageSnapshots: boolean;
	fileStorageShareNetworks: boolean;
	fileStorageSecurityServices: boolean;
	databaseBackups: boolean;
}

export const DEFAULT_BETA_FEATURES: BetaFeatures = {
	libraryConsume: false,
	haDeploy: false,
	keyManager: false,
	volumeBackups: false,
	volumeSnapshots: false,
	fileStorageSnapshots: false,
	fileStorageShareNetworks: false,
	fileStorageSecurityServices: false,
	databaseBackups: false,
};

const STORAGE_KEYS: Record<keyof BetaFeatures, string> = {
	libraryConsume: 'afterglow.beta.libraryConsume',
	haDeploy: 'afterglow.beta.haDeploy',
	keyManager: 'afterglow.beta.keyManager',
	volumeBackups: 'afterglow.beta.volumeBackups',
	volumeSnapshots: 'afterglow.beta.volumeSnapshots',
	fileStorageSnapshots: 'afterglow.beta.fileStorageSnapshots',
	fileStorageShareNetworks: 'afterglow.beta.fileStorageShareNetworks',
	fileStorageSecurityServices: 'afterglow.beta.fileStorageSecurityServices',
	databaseBackups: 'afterglow.beta.databaseBackups',
};

function readFlag(key: keyof BetaFeatures): boolean {
	return browser ? localStorage.getItem(STORAGE_KEYS[key]) === 'true' : false;
}

function createBetaFeaturesStore() {
	const initial: BetaFeatures = { ...DEFAULT_BETA_FEATURES };
	for (const key of Object.keys(initial) as (keyof BetaFeatures)[]) {
		initial[key] = readFlag(key);
	}
	const { subscribe, set, update } = writable<BetaFeatures>(initial);

	function persist(value: BetaFeatures) {
		if (!browser) return;
		for (const key of Object.keys(STORAGE_KEYS) as (keyof BetaFeatures)[]) {
			localStorage.setItem(STORAGE_KEYS[key], value[key] ? 'true' : 'false');
		}
	}

	return {
		subscribe,
		set(value: BetaFeatures) {
			persist(value);
			set(value);
		},
		update(fn: (value: BetaFeatures) => BetaFeatures) {
			update(current => {
				const next = fn(current);
				persist(next);
				return next;
			});
		},
	};
}

export const betaFeatures = createBetaFeaturesStore();

export function setBetaFeature(key: keyof BetaFeatures, value: boolean): void {
	betaFeatures.update(current => ({ ...current, [key]: value }));
}
