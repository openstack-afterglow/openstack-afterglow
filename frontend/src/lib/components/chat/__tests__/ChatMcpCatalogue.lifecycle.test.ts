import { setVerifiedLumenActor } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { api } from '$lib/api/client';
import ChatMcpCatalogue from '../ChatMcpCatalogue.svelte';

const actor = {
	token: 'synthetic-owner-a', refreshToken: null, accessExpiresAt: 4102444800,
	userId: 'owner-a', username: 'Owner A', projectId: 'project-a', projectName: 'Project A',
	availableProjects: [], roles: ['member'], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false
};
const cloud = {
	available: true, enabled: false, access_level: 'read', project_id: 'project-a',
	project_name: 'Project A', source: 'lumen', allowed_projects: [], selection_name: null, tool_count: 0
};
const server = {
	id: 7, name: 'Reviewed source', url: 'https://mcp.example/mcp',
	auth_mode: 'oauth' as const, server_is_active: true, is_active: false, config_version: 4
};
const fetchMock = vi.fn();
const requests: Promise<unknown>[] = [];

beforeEach(() => {
	setVerifiedLumenActor(actor);
	fetchMock.mockReset();
	requests.length = 0;
	const post = api.post, patch = api.patch, remove = api.delete;
	vi.spyOn(api, 'post').mockImplementation(<T>(...args: Parameters<typeof api.post>) => {
		const request = post<T>(...args);
		requests.push(request);
		return request;
	});
	vi.spyOn(api, 'patch').mockImplementation(<T>(...args: Parameters<typeof api.patch>) => {
		const request = patch<T>(...args);
		requests.push(request);
		return request;
	});
	vi.spyOn(api, 'delete').mockImplementation(<T>(...args: Parameters<typeof api.delete>) => {
		const request = remove<T>(...args);
		requests.push(request);
		return request;
	});
	vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

async function settle() {
	await tick();
	await Promise.allSettled(requests);
	await tick();
}

describe('catalogue request ownership through the real HTTP client', () => {
	it.each(['cloud approval', 'remote activation', 'cloud deactivation', 'remote deactivation'])(
		'does not replay %s for a new account after a delayed 401', async (operation) => {
			const pending = Promise.withResolvers<Response>();
			const acceptedBy: string[] = [];
			let attempted = false;
			const deactivating = operation.endsWith('deactivation');
			const remote = operation.startsWith('remote');
			fetchMock.mockImplementation(async (url: string, options: RequestInit) => {
				if (options.method === 'GET') return Response.json({ ...cloud, enabled: !remote && deactivating });
				attempted = true;
				const bearer = new Headers(options.headers).get('Authorization')!;
				if (bearer === `Bearer ${actor.token}`) return pending.promise;
				acceptedBy.push(bearer);
				return Response.json({});
			});
			const onChanged = vi.fn(async () => {});
			render(ChatMcpCatalogue, {
				servers: remote ? [{ ...server, auth_mode: 'none', activation_is_active: deactivating, is_active: deactivating }] : [],
				loading: false, oauthStatus: {}, onChanged
			});
			if (deactivating) {
				await fireEvent.click(await screen.findByRole('button', { name: '비활성화' }));
			} else {
				const trigger = await screen.findByRole('button', { name: remote ? 'Reviewed source 활성화' : 'Afterglow MCP 활성화' });
				await waitFor(() => expect((trigger as HTMLButtonElement).disabled).toBe(false));
				await fireEvent.click(trigger);
				await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
			}
			await waitFor(() => expect(attempted).toBe(true));
			// B has completed verification: A's delayed 401 must not replay as B.
			setVerifiedLumenActor({ ...actor, token: 'synthetic-owner-b', userId: 'owner-b', username: 'Owner B' });
			await tick();
			pending.resolve(Response.json({ detail: 'expired owner A' }, { status: 401 }));
			await settle();
			expect(acceptedBy).toEqual([]);
			expect(onChanged).not.toHaveBeenCalled();
			expect(screen.queryByRole('dialog')).toBeNull();
		}
	);

	it('does not start OAuth after leaving settings while remote activation is pending', async () => {
		const activation = Promise.withResolvers<Response>();
		const oauthStarts: string[] = [];
		let activating = false;
		fetchMock.mockImplementation(async (url: string, options: RequestInit) => {
			if (options.method === 'GET') return Response.json(cloud);
			if (options.method === 'PATCH') { activating = true; return activation.promise; }
			oauthStarts.push(url);
			return Response.json({ authorization_url: 'https://oauth.example/authorize' });
		});
		const onChanged = vi.fn(async () => {});
		const view = render(ChatMcpCatalogue, { servers: [server], loading: false, oauthStatus: {}, onChanged });
		await fireEvent.click(await screen.findByRole('button', { name: 'Reviewed source 활성화' }));
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		await waitFor(() => expect(activating).toBe(true));
		view.unmount();
		activation.resolve(Response.json({ is_active: true }));
		await settle();
		expect(oauthStarts).toEqual([]);
		expect(onChanged).not.toHaveBeenCalled();
	});
});
