import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable, type Writable } from 'svelte/store';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/drover';
import type { TableViewState } from '$lib/utils/tableView.svelte';
import { toSecretReadYaml } from '$lib/utils/k8sYaml';
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
import Harness from './SecretsConsumerHarness.svelte';
import K3sYamlView from '../K3sYamlView.svelte';

const secrets = [
	{ name: 'alpha', type: 'Opaque', data: { password: 'alpha-private' } },
	{ name: 'beta', type: 'Opaque', data: { password: 'beta-private' } },
];
function card(name: string) {
	return screen.getAllByTestId('k3s-secret').find(row => row.getAttribute('data-secret-name') === name)!;
}
async function reveal(name: string) {
	await fireEvent.click(within(card(name)).getByRole('button', { name: t('yamlView.reveal') }));
}
function expectMasked(name: string, value: string) {
	expect(card(name).textContent).not.toContain(value);
	expect(within(card(name)).getByRole('button', { name: t('yamlView.reveal') })).toBeTruthy();
}

beforeEach(() => {
	initLocale('ko');
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(leaf => leaf === 'drover-workloads_editor');
});
afterEach(cleanup);

describe('secret disclosure follows the resource, not its list position', () => {
	it('does not transfer a revealed password through sort or search, including a filtered-out resource returning', async () => {
		let table!: { search: string; state: TableViewState };
		render(Harness, { secrets, onTable: value => { table = value; } });
		await tick();
		const alpha = card('alpha');
		await reveal('alpha');
		expect(alpha.textContent).toContain('alpha-private');
		expectMasked('beta', 'beta-private');
		table.state.sort = { key: 'name', direction: 'desc' };
		await tick();
		expect(screen.getAllByTestId('k3s-secret').map(row => row.getAttribute('data-secret-name'))).toEqual(['beta', 'alpha']);
		expectMasked('beta', 'beta-private');
		table.search = '^beta$';
		await tick();
		expect(screen.getAllByTestId('k3s-secret')).toHaveLength(1);
		expectMasked('beta', 'beta-private');
		table.search = '';
		await tick();
		expectMasked('alpha', 'alpha-private');
		expectMasked('beta', 'beta-private');
		await reveal('beta');
		expect(card('beta').textContent).toContain('beta-private');
		expectMasked('alpha', 'alpha-private');
	});

	it.each([
		{ namespace: 'other' }, { projectId: 'project-b' }, { clusterId: 'cluster-b' },
	])('remasks the same resource name at a changed resource scope %j', async scope => {
		const view = render(Harness, { secrets });
		await reveal('alpha');
		expect(card('alpha').textContent).toContain('alpha-private');
		await view.rerender(scope);
		expectMasked('alpha', 'alpha-private');
		expectMasked('beta', 'beta-private');
	});

	it('does not retain reveals when the parent privacy/readiness boundary unmounts and restores the card', async () => {
		const view = render(Harness, { secrets });
		await reveal('alpha');
		expect(card('alpha').textContent).toContain('alpha-private');
		await view.rerender({ visible: false });
		expect(screen.queryByTestId('k3s-secret')).toBeNull();
		await view.rerender({ visible: true });
		expectMasked('alpha', 'alpha-private');
	});
});

describe('YAML secret snapshot replacement', () => {
	it.each(['value', 'identity'])('requires a fresh reveal after changing only the %s of supplied props', async change => {
		const original = toSecretReadYaml('alpha', 'default', 'Opaque', { password: 'alpha-private' });
		const view = render(K3sYamlView, original);
		await fireEvent.click(screen.getByRole('button', { name: t('yamlView.reveal') }));
		expect(screen.getByText('alpha-private', { exact: true })).toBeTruthy();
		const replacement = change === 'value'
			? { ...original, maskedKeys: [{ key: 'password', value: 'replacement-private' }] }
			: { ...original, text: original.text.replace('name: alpha', 'name: beta') };
		await view.rerender(replacement);
		expect(screen.queryByText('alpha-private', { exact: true })).toBeNull();
		expect(screen.queryByText('replacement-private', { exact: true })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('yamlView.reveal') }));
		expect(screen.getByText(change === 'value' ? 'replacement-private' : 'alpha-private', { exact: true })).toBeTruthy();
	});
});
