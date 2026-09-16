import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { get } from 'svelte/store';
import type { PublicSiteConfig } from '$lib/types/siteConfig';
import { siteConfig } from '$lib/config/site';

const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	apiUpload: vi.fn(),
	apiDelete: vi.fn(),
}));

vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		status: number;

		constructor(status: number, message: string) {
			super(message);
			this.status = status;
		}
	}

	return {
		ApiError,
		api: {
			get: mocks.apiGet,
			upload: mocks.apiUpload,
			delete: mocks.apiDelete,
		},
	};
});

import AdminLoginBrandingPanel from '../AdminLoginBrandingPanel.svelte';

const baseSiteConfig: PublicSiteConfig = {
	site_name: 'Afterglow',
	site_description: 'OpenStack VM + OverlayFS 배포 플랫폼',
	logo_path: '/logo.png',
	logo_dark_path: '/logo-white.png',
	logo_light_path: '/logo-dark.png',
	favicon_path: '/favicon.ico',
	refresh_interval_ms: 5000,
	services: { magnum: false, manila: false, zun: false, k3s: false, trove: false, swift: false, barbican: false, waygate: false, chat: false, mcp: false },
	runtime: {
		api_base: 'https://api.example.com',
		s3_base: '',
		grafana_base: '',
		librechat_base: '',
		gitlab_base: '',
	},
};

type BrandingSlot = 'logo_light' | 'logo_dark';

type BrandingStatus = {
	effective: {
		logo_path: string;
		logo_light_path: string;
		logo_dark_path: string;
	};
	assets: Record<BrandingSlot, {
		slot: BrandingSlot;
		filename: string;
		content_type: string;
		size_bytes: number;
		sha256: string;
		url: string;
		updated_at: string;
		updated_by_user_id: string | null;
	} | null>;
};

function buildStatus(overrides: Partial<BrandingStatus> = {}): BrandingStatus {
	return {
		effective: {
			logo_path: '/logo.png',
			logo_light_path: 'https://api.example.com/api/v1/site-config/assets/logo_light',
			logo_dark_path: 'https://api.example.com/api/v1/site-config/assets/logo_dark',
			...(overrides.effective ?? {}),
		},
		assets: {
			logo_light: {
				slot: 'logo_light',
				filename: 'login-light.png',
				content_type: 'image/png',
				size_bytes: 2048,
				sha256: 'abc123',
				url: 'https://api.example.com/api/v1/site-config/assets/logo_light',
				updated_at: '2026-07-07T00:00:00Z',
				updated_by_user_id: 'user-1',
			},
			logo_dark: null,
			...(overrides.assets ?? {}),
		},
	};
}

function renderPanel() {
	return render(AdminLoginBrandingPanel, {
		props: {
			token: 'test-token',
			projectId: 'test-project',
		},
	});
}

describe('AdminLoginBrandingPanel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		siteConfig.set({
			...baseSiteConfig,
			services: { ...baseSiteConfig.services },
			runtime: { ...baseSiteConfig.runtime },
		});
		mocks.apiGet.mockResolvedValue(buildStatus());
	});

	it('uploads the dark-login logo slot through FormData to the admin branding endpoint', async () => {
		mocks.apiUpload.mockResolvedValueOnce(
			buildStatus({
				effective: {
					logo_path: '/logo.png',
					logo_light_path: 'https://api.example.com/api/v1/site-config/assets/logo_light?v=2',
					logo_dark_path: 'https://api.example.com/api/v1/site-config/assets/logo_dark',
				},
				assets: {
					logo_light: {
						slot: 'logo_light',
						filename: 'light-updated.png',
						content_type: 'image/png',
						size_bytes: 3072,
						sha256: 'def456',
						url: 'https://api.example.com/api/v1/site-config/assets/logo_light?v=2',
						updated_at: '2026-07-07T01:00:00Z',
						updated_by_user_id: 'user-2',
					},
					logo_dark: null,
				},
			}),
		);

		renderPanel();

		const lightSlot = (await screen.findByRole('heading', { name: 'Dark login background' })).closest('.slot-card');
		expect(lightSlot).toBeTruthy();
		const lightQueries = within(lightSlot as HTMLElement);
		const uploadInput = lightQueries.getByLabelText('업로드') as HTMLInputElement;
		const file = new File(['binary-logo'], 'light-logo.png', { type: 'image/png' });

		await fireEvent.change(uploadInput, { target: { files: [file] } });

		await waitFor(() => {
			expect(mocks.apiUpload).toHaveBeenCalledWith(
				'/api/v1/site-config/admin/branding/logo_light',
				expect.any(FormData),
				'test-token',
				'test-project',
			);
		});

		const formData = mocks.apiUpload.mock.calls[0][1] as FormData;
		const uploadedFile = formData.get('file');
		if (!(uploadedFile instanceof File)) {
			throw new Error('Expected upload FormData to contain a File');
		}
		expect(uploadedFile.name).toBe('light-logo.png');
		expect(uploadedFile.type).toBe('image/png');
		expect(uploadedFile.size).toBe(file.size);
	});

	it('resets the uploaded dark-login logo slot through the admin branding endpoint', async () => {
		mocks.apiDelete.mockResolvedValueOnce(
			buildStatus({
				effective: {
					logo_path: '/logo.png',
					logo_light_path: '/logo-dark.png',
					logo_dark_path: 'https://api.example.com/api/v1/site-config/assets/logo_dark',
				},
				assets: {
					logo_light: null,
					logo_dark: null,
				},
			}),
		);

		renderPanel();

		const lightSlot = (await screen.findByRole('heading', { name: 'Dark login background' })).closest('.slot-card');
		expect(lightSlot).toBeTruthy();
		const lightQueries = within(lightSlot as HTMLElement);

		await fireEvent.click(lightQueries.getByRole('button', { name: '초기화' }));

		await waitFor(() => {
			expect(mocks.apiDelete).toHaveBeenCalledWith(
				'/api/v1/site-config/admin/branding/logo_light',
				'test-token',
				'test-project',
			);
		});

		await waitFor(() => {
			expect(get(siteConfig).logo_light_path).toBe('/logo-dark.png');
		});
	});
});
