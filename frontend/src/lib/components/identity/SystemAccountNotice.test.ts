import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, expect, it } from 'vitest';
import { LOCALES } from '$lib/i18n/locales';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/common';
import { isSystemAccount } from '$lib/utils/systemAccount';
import type { SystemAccountIdentity } from '$lib/types/common';
import SystemAccountNotice from './SystemAccountNotice.svelte';

const catalogs = import.meta.glob<Record<string, string>>('../../i18n/messages/*/common.json', { eager: true, import: 'default' });
const marked = { system_account: { kind: 'auto_backup' as const } };
afterEach(() => { cleanup(); initLocale('ko'); });

it.each(LOCALES)('renders authoritative %s label and accessible native explanation without fallback', locale => {
	initLocale(locale);
	const catalog = catalogs['../../i18n/messages/' + locale + '/common.json'];
	expect(catalog['systemAccount.autoBackup']).toBeTruthy();
	expect(catalog['systemAccount.managedHelp']).toBeTruthy();
	render(SystemAccountNotice, { identity: marked });
	const label = screen.getByText(catalog['systemAccount.autoBackup']);
	const summary = label.closest('summary');
	expect(summary).not.toBeNull();
	expect(summary?.parentElement?.tagName).toBe('DETAILS');
	expect(screen.getByText(catalog['systemAccount.managedHelp']).closest('details')).toBe(summary?.parentElement);
	expect(t('systemAccount.autoBackup')).toBe(catalog['systemAccount.autoBackup']);
	expect(t('systemAccount.managedHelp')).toBe(catalog['systemAccount.managedHelp']);
});

it.each([undefined, null, {}, { system_account: null }])('does not label an unmarked principal: %j', identity => {
	render(SystemAccountNotice, { identity });
	expect(document.querySelector('[data-system-account]')).toBeNull();
});

it('uses only the backend marker, never username or domain-name heuristics', () => {
	const foreign = { name: 'afterglow-auto-backup', domain_id: 'foreign-home', system_account: null };
	expect(isSystemAccount(foreign)).toBe(false);
	expect(isSystemAccount({ ...foreign, ...marked })).toBe(true);
	expect(isSystemAccount({ system_account: { kind: 'other' } } as unknown as SystemAccountIdentity)).toBe(false);
});
