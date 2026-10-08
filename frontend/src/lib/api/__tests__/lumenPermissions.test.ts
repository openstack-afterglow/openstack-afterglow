import { grantLumen } from '../../components/chat/__tests__/lumenPermissionFixture';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { defaultChatFeatureOptions } from '../chatContracts';
import { chatRequestPermission, outputPermission, textOnlyToolPolicy } from '../lumenPermissions';
import { requireLumenCapability } from '../lumenAccess';
import { createChatRun } from '../chatStream';
import { uploadChatAttachment } from '../chatAttachments';

const calls = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../client', () => ({ fetchWithAuth: calls.fetch }));
const only = (...leaves: string[]) => (leaf: string) => leaves.includes(leaf);
beforeEach(() => {
	calls.fetch.mockReset();
	auth.update((state) => ({ ...state, token: 'token', projectId: 'project', userId: 'owner' }));
});

describe('independent Lumen admission', () => {
	it('requires images and audio independently for paid output', () => {
		const chat = only('lumen-chat_user');
		expect(outputPermission([{ type: 'image' }], chat)).toBe('lumen-images_user');
		expect(outputPermission([{ type: 'audio' }], chat)).toBe('lumen-audio_user');
		expect(outputPermission([{ type: 'video' }], only('lumen-images_user'))).toBe('lumen-audio_user');
	});
	it('does not confuse an owned image input with paid image generation', () => {
		const features = defaultChatFeatureOptions();
		textOnlyToolPolicy(features);
		expect(chatRequestPermission({ parts: [{ type: 'image', asset_id: 'owned-image' }], features }, only('lumen-chat_user'))).toBeNull();
	});
	it('disables implicit all-tools defaults for legitimate chat-only use', () => {
		const features = defaultChatFeatureOptions();
		expect(chatRequestPermission({ features }, only('lumen-chat_user'))).toBe('lumen-tools_user');
		textOnlyToolPolicy(features);
		expect(chatRequestPermission({ features }, only('lumen-chat_user'))).toBeNull();
		expect(chatRequestPermission({ features, agent_id: 7 }, only('lumen-chat_user'))).toBe('lumen-tools_user');
		expect(chatRequestPermission({ features, skill_ids: [7] }, only('lumen-chat_user'))).toBe('lumen-tools_user');
	});
	it('checks saved image generation payloads after a downgrade, before dispatch', async () => {
		grantLumen('lumen-chat_user');
		const features = defaultChatFeatureOptions();
		textOnlyToolPolicy(features);
		features.output_modalities = ['image'];
		await expect(createChatRun('/api/v1/chat/temp-completions', { features }, { token: 'token', projectId: 'project' })).rejects.toMatchObject({ status: 403 });
		expect(calls.fetch).not.toHaveBeenCalled();
	});
	it('rejects persistent attachment uploads without asset editor authority', async () => {
		grantLumen('lumen-chat_user', 'lumen-images_user');
		await expect(uploadChatAttachment(new File(['bytes'], 'photo.png', { type: 'image/png' }), { token: 'token', projectId: 'project' })).rejects.toMatchObject({ status: 403 });
		expect(calls.fetch).not.toHaveBeenCalled();
	});
	it('does not reuse grants for a request captured in another project', () => {
		grantLumen('lumen-images_user');
		expect(() => requireLumenCapability('lumen-images_user', 'token', 'previous-project')).toThrow();
		expect(() => requireLumenCapability('lumen-images_user', 'token', 'project')).not.toThrow();
		grantLumen();
		expect(() => requireLumenCapability('lumen-images_user', 'token', 'project')).toThrow();
	});
});
