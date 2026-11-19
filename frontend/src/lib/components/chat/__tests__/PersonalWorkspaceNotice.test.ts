import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as ClientModule from '$lib/api/client';
import { api } from '$lib/api/client';
import { acceptAuthVerification, clearAuth, getAuthVerificationEpoch, setLoginAuth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/chat-settings';
import { t as ws } from '$lib/i18n/ns/workspace-selector';
import PersonalWorkspaceNotice from '../PersonalWorkspaceNotice.svelte';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/api/client', async (importOriginal) => {
	const methods = { get: vi.fn(), post: vi.fn() };
	return { ...(await importOriginal<typeof ClientModule>()), api: { ...methods, withExperience: () => methods } };
});

const personal = { id: 'personal', name: 'Personal', kind: 'personal' as const };
const organization = { id: 'dmslab', name: 'dmslab', kind: 'organization' as const };
const project = { id: 'project-1', name: 'My project' };

function signIn(domain: typeof personal | typeof organization, canCreateDomain: boolean) {
	setLoginAuth({ token: 'token', userId: 'alice', domainId: domain.id, domainName: domain.name, identityDomainId: personal.id, identityDomainName: personal.name, projectId: project.id, projectName: project.name, availableDomains: [personal, organization], canCreateDomain, federated: false });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
}

beforeEach(() => {
	vi.clearAllMocks(); localStorage.clear(); clearAuth();
	vi.mocked(api.get).mockImplementation(async (path) => path === '/api/v1/auth/domains' ? [personal, organization]
		: { domain: personal, projects: [project], default_project_id: project.id, is_domain_manager: false, can_create_project: false });
});
afterEach(() => { cleanup(); clearAuth(); });

describe('PersonalWorkspaceNotice', () => {
	it('opens the existing resource chooser without the create-domain form', async () => {
		signIn(personal, false);
		render(PersonalWorkspaceNotice);
		expect(screen.getByText(t('dashboardChat.personalUnavailable'))).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('dashboardChat.createOrganization') })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('dashboardChat.switchWorkspace') }));
		const chooser = await screen.findByRole('dialog', { name: ws('title') });
		expect(within(chooser).queryByLabelText(new RegExp(ws('domainName')))).toBeNull();
		await fireEvent.click(within(chooser).getByRole('button', { name: ws('close') }));
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});

	it('goes straight to the existing create-domain form when the policy allows it', async () => {
		signIn(personal, true);
		render(PersonalWorkspaceNotice);
		await fireEvent.click(screen.getByRole('button', { name: t('dashboardChat.createOrganization') }));
		const chooser = await screen.findByRole('dialog', { name: ws('title') });
		expect(within(chooser).getByLabelText(new RegExp(ws('domainName')))).toBeTruthy();
	});

	it('renders nothing in an organization project', () => {
		signIn(organization, true);
		render(PersonalWorkspaceNotice);
		expect(screen.queryByText(t('dashboardChat.personalUnavailable'))).toBeNull();
		expect(screen.queryByRole('button')).toBeNull();
	});
});
