import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import type { TourStep } from '../tours';
import { selectOwnDomain } from './admin-resources';

// Administration application credential issue/delete tour. Step builders only; registration stays in tours.ts.
// The delete anchor exists only on the credential this page just issued.
export function adminApplicationCredentialSteps(): TourStep[] {
	return [
		{
			// Creation stays disabled until the domain directory proves the signed-in administrator.
			element: '[data-tour="admin-app-credentials-scope"]',
			route: '/admin/application-credentials',
			beforeReady: selectOwnDomain,
			prepare: () => sidebarOpen.close(),
			readyElement: '[data-tour="admin-app-credentials-create-open"]:not([disabled])',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminApplicationCredentials.step1.title'); },
			get description() { return t('tours.adminApplicationCredentials.step1.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-app-credentials-create-open"]',
		},
		{
			// Highlight the whole dialog so the name field and role checkboxes stay clickable.
			element: '[data-tour="admin-app-credentials-form"]',
			readyElement: '[data-tour="admin-app-credentials-roles"]',
			waitTimeoutMs: 20000,
			popoverSide: 'top',
			get title() { return t('tours.adminApplicationCredentials.step2.title'); },
			get description() { return t('tours.adminApplicationCredentials.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-app-credentials-submit"]',
		},
		{
			// Appears after the issue request settles; a rejected save rewinds to the form.
			element: '[data-tour="admin-app-credentials-issued"]',
			waitTimeoutMs: 10000,
			get title() { return t('tours.adminApplicationCredentials.step3.title'); },
			get description() { return t('tours.adminApplicationCredentials.step3.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-app-credentials-close"]',
		},
		{
			element: '[data-tour="admin-app-credentials-delete"]',
			waitTimeoutMs: 10000,
			get title() { return t('tours.adminApplicationCredentials.step4.title'); },
			get description() { return t('tours.adminApplicationCredentials.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-app-credentials-delete-confirm"]',
			get title() { return t('tours.adminApplicationCredentials.step5.title'); },
			get description() { return t('tours.adminApplicationCredentials.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="admin-app-credentials-list"]',
			get title() { return t('tours.adminApplicationCredentials.step6.title'); },
			get description() { return t('tours.adminApplicationCredentials.step6.description'); },
		},
	];
}

// The section marks its personal-token list settled only after the post-issue/post-revoke reload and the
// permission preview finish, so later highlights are measured on the final layout. The preview request
// may take up to its 40s client timeout, so steps waiting on it allow longer than that.
const MCP_TOKENS_SETTLED = '[data-tour="mcp-personal-tokens"][data-tour-settled="true"]';
const MCP_PREVIEW_WAIT_MS = 45000;

// Account personal MCP token issue/revoke tour. The revoke anchor exists only on the key this page just issued.
export function accountMcpSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="mcp-method-api"]',
			route: '/dashboard/account/mcp',
			prepare: () => sidebarOpen.close(),
			waitTimeoutMs: 20000,
			get title() { return t('tours.accountMcp.step1.title'); },
			get description() { return t('tours.accountMcp.step1.description'); },
			advanceOn: 'click',
		},
		{
			// The whole form is taller than the viewport, so only the name field is highlighted (and stays
			// typeable). Permission, expiry and project selection keep their defaults.
			element: '[data-tour="mcp-token-name"]',
			readyElement: '[data-tour="mcp-token-submit"]:not([disabled])',
			waitTimeoutMs: 20000,
			waitAllowsInput: true,
			get title() { return t('tours.accountMcp.step2.title'); },
			get description() { return t('tours.accountMcp.step2.description'); },
		},
		{
			element: '[data-tour="mcp-token-submit"]',
			// Enabled is not enough: a read token can be issued while the preview above the button still loads.
			readyElement: '[data-tour="mcp-token-submit-row"][data-tour-settled="true"]',
			waitTimeoutMs: MCP_PREVIEW_WAIT_MS,
			// Enter in the name field already submitted the form; continue with the issued token.
			skipIf: () => document.querySelector('[data-tour="mcp-issued-token"]') !== null,
			get title() { return t('tours.accountMcp.step3.title'); },
			get description() { return t('tours.accountMcp.step3.description'); },
			advanceOn: 'click',
			showPrevious: true,
		},
		{
			// Appears after the issue request settles; a rejected request rewinds to the submit step.
			element: '[data-tour="mcp-issued-token"]',
			waitTimeoutMs: 10000,
			get title() { return t('tours.accountMcp.step4.title'); },
			get description() { return t('tours.accountMcp.step4.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="mcp-issued-done"]',
		},
		{
			element: '[data-tour="mcp-token-revoke"]',
			readyElement: MCP_TOKENS_SETTLED,
			waitTimeoutMs: MCP_PREVIEW_WAIT_MS,
			get title() { return t('tours.accountMcp.step5.title'); },
			get description() { return t('tours.accountMcp.step5.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="confirm-accept"]',
			get title() { return t('tours.accountMcp.step6.title'); },
			get description() { return t('tours.accountMcp.step6.description'); },
			advanceOn: 'click',
		},
		{
			// The full list can be taller than a tablet viewport; highlight its heading and count only.
			element: '[data-tour="mcp-personal-tokens-head"]',
			readyElement: MCP_TOKENS_SETTLED,
			waitTimeoutMs: MCP_PREVIEW_WAIT_MS,
			get title() { return t('tours.accountMcp.step7.title'); },
			get description() { return t('tours.accountMcp.step7.description'); },
		},
	];
}
