import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const startTour = vi.hoisted(() => vi.fn());
vi.mock('../engine', () => ({ startTour, isTourActive: () => false, onTourActivityChange: () => () => {} }));

import TutorialStartButton from '../TutorialStartButton.svelte';
import { authReady, exitMockAuth, enterMockAuth, setLoginAuth, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { buildMockAuth } from '$lib/mockup/auth';
import { tutorialStatuses, tutorialStatusesLoaded } from '../status';

beforeEach(() => {
	startTour.mockReset();
	exitMockAuth();
	enterMockAuth(buildMockAuth('admin', '/admin'), 'admin');
	authReady.set(true);
	tutorialStatuses.set({});
	tutorialStatusesLoaded.set(false);
});

afterEach(() => {
	exitMockAuth();
	authReady.set(false);
	logoutInProgress.set(false);
	projectSwitching.set(false);
});

describe('TutorialStartButton', () => {
	it('waits for status loading before inviting a pending administrator tour', async () => {
		render(TutorialStartButton, { tour: 'admin-compute' });
		expect(screen.queryByRole('group')).toBeNull();

		tutorialStatusesLoaded.set(true);
		expect(await screen.findByRole('group', { name: '튜토리얼을 시작하시겠습니까?' })).toBeTruthy();
		expect(screen.getByText('튜토리얼을 시작하시겠습니까?')).toBeTruthy();
	});

	it('hides launcher and invite when a real non-admin session replaces tutorial auth', async () => {
		tutorialStatusesLoaded.set(true);
		render(TutorialStartButton, { tour: 'vm-create' });

		expect(await screen.findAllByRole('button', { name: '튜토리얼 시작' })).toHaveLength(2);
		expect(await screen.findByRole('dialog')).toBeTruthy();

		exitMockAuth();
		setLoginAuth({ token: 'real-token', userId: 'u1', username: 'real', isSystemAdmin: false });
		authReady.set(true);

		await waitFor(() => {
			expect(screen.queryByRole('button', { name: '튜토리얼 시작' })).toBeNull();
			expect(screen.queryByRole('dialog')).toBeNull();
		});
	});

	it('shows real-admin tours only after verification and hides them during project switching', async () => {
		exitMockAuth();
		setLoginAuth({ token: 'real-admin-token', userId: 'operator', username: 'admin', isSystemAdmin: true });
		authReady.set(false);
		render(TutorialStartButton, { tour: 'admin-settings' });

		expect(screen.queryByRole('button', { name: '튜토리얼 시작' })).toBeNull();
		authReady.set(true);
		expect(await screen.findByRole('button', { name: '튜토리얼 시작' })).toBeTruthy();

		projectSwitching.set(true);
		await waitFor(() => expect(screen.queryByRole('button', { name: '튜토리얼 시작' })).toBeNull());
		projectSwitching.set(false);
		expect(await screen.findByRole('button', { name: '튜토리얼 시작' })).toBeTruthy();
	});

	it('does not invite a completed tour but keeps the accessible restart button', () => {
		tutorialStatuses.set({ 'admin-storage': 'completed' });
		tutorialStatusesLoaded.set(true);
		render(TutorialStartButton, { tour: 'admin-storage' });

		expect(screen.queryByRole('group')).toBeNull();
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

	it('keeps a second pending tour on the same page from opening another invite', async () => {
		tutorialStatusesLoaded.set(true);
		render(TutorialStartButton, { tour: 'admin-identity', invite: false });
		render(TutorialStartButton, { tour: 'admin-users', label: '사용자 만들고 삭제하기' });

		expect(await screen.findAllByRole('group')).toHaveLength(1);
		expect(document.getElementById('ts-invite-title-admin-users')).not.toBeNull();
		expect(document.getElementById('ts-invite-title-admin-identity')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '사용자 만들고 삭제하기' }));
		expect(startTour).toHaveBeenCalledWith('admin-users');
	});

	it('keeps the invitation in normal flow and never presents it as a dialog', async () => {
		tutorialStatusesLoaded.set(true);
		const { container } = render(TutorialStartButton, { tour: 'vm-create' });
		const invitation = await screen.findByRole('group', { name: '튜토리얼을 시작하시겠습니까?' });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(invitation.parentElement?.classList.contains('tutorial-start')).toBe(true);
		expect(container.querySelector('.ts-invite__arrow')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '튜토리얼 시작' }));
		expect(startTour).toHaveBeenCalledWith('vm-create');
	});
});
