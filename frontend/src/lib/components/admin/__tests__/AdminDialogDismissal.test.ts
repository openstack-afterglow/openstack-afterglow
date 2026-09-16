import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AdminProjectDeleteModal from '../projects/AdminProjectDeleteModal.svelte';
import EvacuateModal from '../instances/EvacuateModal.svelte';

const project = {
	id: 'p1',
	name: 'demo',
	description: '',
	enabled: true,
	domain_id: null,
	created_at: null,
};

describe('admin dialog dismissal', () => {
	// These dialogs used to declare onkeydown={(e) => e.key === 'Escape' && ...} on the overlay
	// div while nothing ever moved focus inside it, so the handler could not fire and
	// aria-modal="true" sealed a screen reader out of a surface it could not leave. Raising the
	// key on `document` rather than on the dialog is what proves the old shape was dead.
	it('moves focus into the dialog and closes on Escape raised outside it', async () => {
		const onClose = vi.fn();
		render(AdminProjectDeleteModal, { props: { project, onClose, onSuccess: () => {} } });

		const dialog = screen.getByRole('dialog');
		await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

		await fireEvent.keyDown(document, { key: 'Escape' });

		expect(onClose).toHaveBeenCalled();
		expect(within(dialog).getByRole('button', { name: '취소' })).toBeTruthy();
	});

	it('isolates the page behind an open admin dialog', async () => {
		render(AdminProjectDeleteModal, { props: { project, onClose: () => {}, onSuccess: () => {} } });

		const dialog = screen.getByRole('dialog');
		await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

		for (const sibling of [...(dialog.parentElement?.children ?? [])]) {
			if (sibling === dialog) continue;
			expect((sibling as HTMLElement).inert).toBe(true);
		}
	});

	it('gives the evacuate dialog a named close control and an Escape route', async () => {
		const onClose = vi.fn();
		render(EvacuateModal, {
			props: { serverId: 'i-1234567890', serverName: 'web-01', currentHost: 'compute-01', onClose, onEvacuated: () => {} },
		});

		const dialog = screen.getByRole('dialog', { name: '인스턴스 강제 이주' });
		await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
		expect(within(dialog).getByRole('button', { name: '대화상자 닫기' })).toBeTruthy();

		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(onClose).toHaveBeenCalled();
	});
});
