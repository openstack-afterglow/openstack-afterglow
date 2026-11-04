import { afterEach, describe, expect, it } from 'vitest';
import { buildExperienceCatalog } from '../../../../scripts/experience-catalog.mjs';
import { defineMessages, initLocale, resolveExperienceMessage, restoreKeyDebugMode, KEY_DEBUG_STORAGE_KEY } from '../runtime.svelte';
import { unavailableExperienceMessage } from '../experienceMessages';
import { EXPERIENCE_CATALOG_REVISION } from '../experienceCatalogRevision';

const source = { 'actions.confirm': '확인', 'actions.cancel': '취소', 'state.loadingNamed': '{name} 불러오는 중…' };
const translate = defineMessages<typeof source>('common', {
	'../messages/ko/common.json': source,
	'../messages/en/common.json': { 'actions.confirm': 'Confirm', 'state.loadingNamed': 'Loading {name}…' },
	'../messages/ja/common.json': { 'state.loadingNamed': '{count, plural, one {壊れた}}' },
});

afterEach(() => {
	initLocale('ko');
	localStorage.removeItem(KEY_DEBUG_STORAGE_KEY);
	restoreKeyDebugMode();
});

describe('experience source metadata', () => {
	it('captures actual fallback locale and immutable revision without formatted parameters', () => {
		initLocale('ja');
		expect(translate('state.loadingNamed', { name: 'private-resource-name' })).toBe('Loading private-resource-name…');
		const metadata = resolveExperienceMessage('common', 'state.loadingNamed');
		expect(metadata).toEqual({ key: 'common:state.loadingNamed', locale: 'en', catalog_revision: EXPERIENCE_CATALOG_REVISION, tone: 'neutral', restoration: 'restored' });
		initLocale('bn');
		expect(metadata.locale).toBe('en');
		expect(Object.isFrozen(metadata)).toBe(true);
		expect(JSON.stringify(metadata)).not.toContain('private-resource-name');
		expect(resolveExperienceMessage('common', 'actions.cancel').locale).toBe('ko');
		expect(resolveExperienceMessage('common', 'actions.confirm', 'ko').locale).toBe('ko');
	});

	it('keeps unknown namespaces, arbitrary text, missing keys and debug display unavailable', () => {
		for (const [namespace, key] of [['unknown', 'actions.confirm'], ['common', 'private raw error'], ['common', 'missing']]) {
			expect(resolveExperienceMessage(namespace, key)).toEqual(unavailableExperienceMessage());
		}
		localStorage.setItem(KEY_DEBUG_STORAGE_KEY, 'keys');
		restoreKeyDebugMode();
		expect(translate('actions.confirm')).toBe('common:actions.confirm');
		expect(resolveExperienceMessage('common', 'actions.confirm').restoration).toBe('unavailable');
	});
});

describe('experience static generator', () => {
	const catalogs = {
		namespaces: ['sample'], modules: ['sample'], loadErrors: [],
		messages: {
			ko: { sample: { greeting: '안녕 {name}', onlySource: '원문' } },
			en: { sample: { greeting: 'Hello {name}', translationOnly: 'Do not register' } },
			ja: { sample: { greeting: '{count, plural, one {invalid}}' } },
		},
	};
	it('retains static templates, excludes translation-only keys and skips invalid fallback candidates', () => {
		const result = buildExperienceCatalog(catalogs);
		expect(result.messages['sample:greeting']).toEqual({ ko: '안녕 {name}', en: 'Hello {name}' });
		expect(result.messages['sample:translationOnly']).toBeUndefined();
		expect(result.revision).toMatch(/^[a-f0-9]{64}$/);
		expect(buildExperienceCatalog({ ...catalogs, namespaces: [...catalogs.namespaces].reverse() })).toEqual(result);
		expect(buildExperienceCatalog({ ...catalogs, messages: { ...catalogs.messages, en: { sample: { greeting: 'Changed {name}' } } } }).revision).not.toBe(result.revision);
	});
});
