import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import ChatToolApproval from '../ChatToolApproval.svelte';

describe('ChatToolApproval', () => {
	it('shows only redacted argument keys and sends an explicit decision', async () => {
		const onDecision = vi.fn();
		render(ChatToolApproval, {
			approval: {
				callId: 'call-1',
				name: 'afterglow_vm_delete',
				effect: 'external_mutation',
				argumentKeys: ['server_id'],
				preview: [{ type: 'text', text: 'Delete: server-1 (current state: ACTIVE)' }],
				expiresAt: '2026-07-27T12:00:00Z'
			},
			onDecision
		});

		expect(screen.getByText('가상 머신 삭제')).toBeTruthy();
		expect(screen.getByText('afterglow_vm_delete')).toBeTruthy();
		expect(screen.getByText('Delete: server-1 (current state: ACTIVE)')).toBeTruthy();
		expect(screen.getByText('server_id')).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: '이번만 허용하기' }));
		expect(onDecision).toHaveBeenCalledWith('call-1', 'approve');
	});

	it('disables both decisions while a request is pending', () => {
		render(ChatToolApproval, {
			approval: {
				callId: 'call-1',
				name: 'afterglow_vm_delete',
				effect: 'external_mutation',
				argumentKeys: [],
				preview: [],
				expiresAt: '2026-07-27T12:00:00Z'
			},
			busy: true,
			onDecision: vi.fn()
		});

		expect(screen.getByRole('button', { name: '거부' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: '처리 중…' }).hasAttribute('disabled')).toBe(true);
	});
});
