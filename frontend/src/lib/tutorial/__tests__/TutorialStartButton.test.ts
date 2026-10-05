import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const startTour = vi.hoisted(() => vi.fn());
vi.mock('../engine', () => ({ startTour }));

import TutorialStartButton from '../TutorialStartButton.svelte';
import { tutorialStatuses, tutorialStatusesLoaded } from '../status';

beforeEach(() => {
	startTour.mockReset();
	tutorialStatuses.set({});
	tutorialStatusesLoaded.set(false);
});

describe('TutorialStartButton', () => {
	it('waits for status loading before inviting a pending administrator tour', async () => {
		render(TutorialStartButton, { tour: 'admin-compute' });
		expect(screen.queryByRole('dialog')).toBeNull();

		tutorialStatusesLoaded.set(true);
		expect(await screen.findByRole('dialog')).toBeTruthy();
		expect(screen.getByText('튜토리얼을 시작하시겠습니까?')).toBeTruthy();
	});

	it('does not invite a completed tour but keeps the accessible restart button', () => {
		tutorialStatuses.set({ 'admin-storage': 'completed' });
		tutorialStatusesLoaded.set(true);
		render(TutorialStartButton, { tour: 'admin-storage' });

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.getByRole('button', { name: '튜토리얼 시작' })).toBeTruthy();
	});

	it('starts the requested tour from the launcher', async () => {
		tutorialStatuses.set({ 'admin-library': 'completed' });
		tutorialStatusesLoaded.set(true);
		render(TutorialStartButton, { tour: 'admin-library' });

		await fireEvent.click(screen.getByRole('button', { name: '튜토리얼 시작' }));
		expect(startTour).toHaveBeenCalledWith('admin-library');
	});

	it('uses compact mobile presentation without changing the accessible name', () => {
		tutorialStatuses.set({ 'admin-network': 'dismissed' });
		tutorialStatusesLoaded.set(true);
		const { container } = render(TutorialStartButton, { tour: 'admin-network', compactOnMobile: true });

		expect(container.querySelector('.tutorial-start--compact')).not.toBeNull();
		expect(screen.getByRole('button', { name: '튜토리얼 시작' })).toBeTruthy();
	});
});
