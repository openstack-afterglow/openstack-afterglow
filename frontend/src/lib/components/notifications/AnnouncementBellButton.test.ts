import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import AnnouncementBellButton from './AnnouncementBellButton.svelte';

describe('AnnouncementBellButton', () => {
	it('announces the unread count and shows the reduced-motion-safe indicator', () => {
		const { container } = render(AnnouncementBellButton, { count: 3, open: false, onclick: vi.fn() });
		const button = screen.getByRole('button', { name: '알림, 읽지 않은 공지 3개' });
		const indicator = container.querySelector('[data-unread-indicator]');

		expect(button.getAttribute('aria-expanded')).toBe('false');
		expect(indicator).toBeTruthy();
		expect(indicator?.querySelector('.animate-ping')?.classList.contains('motion-reduce:animate-none')).toBe(true);
	});

	it('renders the ordinary notification label without an unread indicator', () => {
		const { container } = render(AnnouncementBellButton, { count: 0, open: true, onclick: vi.fn() });
		expect(screen.getByRole('button', { name: '알림' }).getAttribute('aria-expanded')).toBe('true');
		expect(container.querySelector('[data-unread-indicator]')).toBeNull();
	});
});
