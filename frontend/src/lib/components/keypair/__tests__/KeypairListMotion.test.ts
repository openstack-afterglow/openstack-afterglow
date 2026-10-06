import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import KeypairListTable from '../KeypairListTable.svelte';
import KeypairCreateModal from '../KeypairCreateModal.svelte';

const keypairs = [
	{ name: 'key-a', type: 'ssh', fingerprint: 'aa' },
	{ name: 'key-b', type: 'ssh', fingerprint: 'bb' },
];

describe('keypair list operation feedback', () => {
	it('keeps keyed rows mounted on refresh and indicates only the deleting key', async () => {
		const props = { keypairs, deleting: null as string | null, copiedFingerprint: null, onCopy: vi.fn(), onDelete: vi.fn(async () => {}) };
		const view = render(KeypairListTable, props);
		const name = screen.getByText('key-a');
		await view.rerender({ ...props, keypairs: keypairs.map((keypair) => ({ ...keypair })), deleting: 'key-b' });
		expect(screen.getByText('key-a')).toBe(name);
		expect(screen.getByRole('button', { name: '삭제 중...' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: '삭제' }).hasAttribute('disabled')).toBe(false);
		expect(screen.getByRole('status').textContent?.trim()).toBe('삭제 중...');
		await view.rerender(props);
		expect(screen.queryByRole('status')).toBeNull();
	});

	it('keeps key generation feedback until the create callback settles', async () => {
		let resolve!: (value: { private_key?: string } | string) => void;
		const onCreate = vi.fn(() => new Promise<{ private_key?: string } | string>((done) => { resolve = done; }));
		render(KeypairCreateModal, { open: true, onCreate });
		await fireEvent.input(screen.getByLabelText(/이름/), { target: { value: 'my-key' } });
		await fireEvent.click(screen.getByRole('button', { name: '생성' }));
		expect(screen.getByRole('button', { name: '생성 중...' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('status').textContent?.trim()).toBe('생성 중...');
		resolve('생성 실패');
		await screen.findByText('생성 실패');
		expect(screen.getByRole('button', { name: '생성' }).hasAttribute('disabled')).toBe(false);
		expect(screen.queryByText('생성 중...')).toBeNull();
	});
});
