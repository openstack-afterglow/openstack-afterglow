import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import RoleMetadataModal from '../RoleMetadataModal.svelte';
import type { ManagedRole } from '../types';
const role = (name: string): ManagedRole => ({ id: 'existing', name, description: '', protected: false, system_only: false, domain_id: null, implied_role_ids: [], inherited_role_ids: [], parent_role_ids: [] });
afterEach(cleanup);
describe('role metadata area/grade form', () => {
	it('previews all whitespace as hyphens and sends the canonical name', async () => {
		const onSave = vi.fn();
		render(RoleMetadataModal, { role: null, busy: false, disabled: false, error: '', onClose: vi.fn(), onSave });
		await fireEvent.input(screen.getByRole('textbox', { name: /^영역/ }), { target: { value: ' Lumen Chat ' } });
		await fireEvent.input(screen.getByRole('textbox', { name: /^등급/ }), { target: { value: ' Custom Grade ' } });
		expect(screen.getByText('-lumen-chat-_-custom-grade-')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '만들기' }));
		expect(onSave).toHaveBeenCalledWith({ name: '-lumen-chat-_-custom-grade-', description: '', domain_id: null });
	});
	it('does not rename a legacy role on metadata-only save', async () => {
		const onSave = vi.fn();
		render(RoleMetadataModal, { role: role('legacy-name'), busy: false, disabled: false, error: '', onClose: vi.fn(), onSave });
		await fireEvent.input(screen.getByRole('textbox', { name: '설명' }), { target: { value: 'Description' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(onSave).toHaveBeenCalledWith({ description: 'Description' });
	});
	it('never exposes native rename inputs even if provider metadata omits protected flag', async () => {
		const onSave = vi.fn();
		render(RoleMetadataModal, { role: role('member'), busy: false, disabled: false, error: '', onClose: vi.fn(), onSave });
		expect(screen.queryByRole('textbox', { name: /^영역/ })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(onSave).toHaveBeenCalledWith({ description: '' });
	});
});
