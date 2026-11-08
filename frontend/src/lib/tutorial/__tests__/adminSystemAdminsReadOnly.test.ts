const driverHarness = vi.hoisted(() => {
	const highlight = vi.fn();
	const driver = vi.fn(() => ({ highlight, refresh: vi.fn(), destroy: vi.fn() }));
	return { driver, highlight };
});

vi.mock('driver.js', () => ({ driver: driverHarness.driver }));
vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }));
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authReady, exitMockAuth, setLoginAuth } from '$lib/stores/auth';
import { startTour, stopTour } from '../engine';
import { getTour } from '../tours';
import { REAL_ADMIN_TOUR_IDS } from '../access';

const originalGetClientRects = HTMLElement.prototype.getClientRects;

beforeEach(() => {
	sessionStorage.clear();
	HTMLElement.prototype.getClientRects = function () {
		return { 0: this.getBoundingClientRect(), length: 1, item: () => this.getBoundingClientRect(), [Symbol.iterator]: function* () { yield this[0]; } } as DOMRectList;
	};
	exitMockAuth();
	setLoginAuth({ token: 'real-token', userId: 'operator', username: 'op', isSystemAdmin: true });
	authReady.set(true);
	driverHarness.highlight.mockClear();
});

afterEach(() => {
	stopTour();
	document.body.innerHTML = '';
	sessionStorage.clear();
	HTMLElement.prototype.getClientRects = originalGetClientRects;
	exitMockAuth();
	authReady.set(false);
});

describe('system administrator tour is read-only in use', () => {
	it('marks every step readOnly, with no click-driven advance', () => {
		const tour = getTour('admin-system-admins')!;
		expect(Object.hasOwn(REAL_ADMIN_TOUR_IDS, tour.id)).toBe(true);
		for (const step of tour.steps) {
			expect(step.readOnly).toBe(true);
			expect(step.advanceOn).toBeUndefined();
			expect(step.advanceElement).toBeUndefined();
		}
	});

	it('swallows real clicks and keyboard activation on a live Add or Revoke button inside the highlight, on every step', async () => {
		const add = vi.fn();
		const revoke = vi.fn();
		const outside = vi.fn();
		document.body.innerHTML = `
			<button data-tour="admin-system-admins-add" id="add">Add</button>
			<div data-tour="admin-system-admins-policy">policy</div>
			<div data-tour="admin-system-admins-list"><button id="revoke">Revoke other admin</button></div>
			<button id="outside">elsewhere</button>`;
		const byId = (id: string) => document.getElementById(id) as HTMLButtonElement;
		byId('add').addEventListener('click', add);
		byId('revoke').addEventListener('click', revoke);
		byId('outside').addEventListener('click', outside);

		for (const step of [0, 1, 2]) {
			await startTour('admin-system-admins', step);
			await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
			const target = getTour('admin-system-admins')!.steps[step].element;
			const button = target.includes('add') ? byId('add') : target.includes('list') ? byId('revoke') : null;
			if (button) {
				// Mouse click and keyboard Enter/Space both reach the page as a click event.
				button.click();
				button.focus();
				button.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
				button.click();
				button.dispatchEvent(new KeyboardEvent('keyup', { key: ' ', bubbles: true, cancelable: true }));
				button.click();
			}
			stopTour();
		}
		expect(add).not.toHaveBeenCalled();
		expect(revoke).not.toHaveBeenCalled();
		// The guard is scoped to the highlight: it is not a page-wide click blocker.
		await startTour('admin-system-admins', 2);
		byId('outside').click();
		expect(outside).toHaveBeenCalledOnce();
	});
});
