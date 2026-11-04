import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import OnboardingAccountForm from '../OnboardingAccountForm.svelte';
import type * as ExperienceModule from '$lib/utils/experience';
import type { ExperienceContext } from '$lib/utils/experience';
const experience = vi.hoisted(() => ({ begin: vi.fn(), state: vi.fn(), applied: vi.fn(), discarded: vi.fn() }));
vi.mock('$lib/utils/experience', async importOriginal => {
	const actual = await importOriginal<typeof ExperienceModule>();
	return {
		...actual, beginExperienceAction: experience.begin, experienceState: experience.state,
		experienceApplied: experience.applied, experienceDiscarded: experience.discarded,
	};
});

beforeEach(() => { vi.resetAllMocks(); initLocale('en'); });
afterEach(cleanup);

describe('new human account credentials', () => {
	it('submits username and password without requiring workspace naming', async () => {
		const onSubmit = vi.fn().mockResolvedValue(undefined);
		render(OnboardingAccountForm, { idPrefix: 'test', submitLabel: 'Create account', onSubmit });
		await fireEvent.input(screen.getByRole('textbox', { name: 'Username' }), { target: { value: ' alice ' } });
		await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'long-enough-password' } });
		await fireEvent.input(screen.getByLabelText(/^Confirm password/), { target: { value: 'long-enough-password' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		expect(onSubmit).toHaveBeenCalledOnce();
		expect(onSubmit).toHaveBeenCalledWith({ name: 'alice', password: 'long-enough-password' });
		await waitFor(() => expect((screen.getByLabelText(/^Password/) as HTMLInputElement).value).toBe(''));
		expect((screen.getByLabelText(/^Confirm password/) as HTMLInputElement).value).toBe('');
	});

	it('does not submit twice while account provisioning is pending', async () => {
		const pending = Promise.withResolvers<void>();
		const onSubmit = vi.fn().mockReturnValue(pending.promise);
		render(OnboardingAccountForm, { idPrefix: 'test', submitLabel: 'Create account', onSubmit });
		for (const [label, value] of [['Username', 'alice'], ['Password', 'long-enough-password'], ['Confirm password', 'long-enough-password']]) {
			await fireEvent.input(screen.getByLabelText(new RegExp(`^${label}`)), { target: { value } });
		}
		const form = (screen.getByRole('textbox', { name: 'Username' }) as HTMLInputElement).form!;
		await fireEvent.submit(form);
		await fireEvent.submit(form);
		expect(onSubmit).toHaveBeenCalledOnce();
		expect((screen.getByLabelText(/^Password/) as HTMLInputElement).value).toBe('');
		expect((screen.getByLabelText(/^Confirm password/) as HTMLInputElement).value).toBe('');
		pending.resolve();
		await waitFor(() => expect((screen.getByLabelText(/^Password/) as HTMLInputElement).value).toBe(''));
	});
});

it.each(['error', 'discarded'] as const)('does not overwrite the parent account %s outcome when local submitting cleanup completes', async outcome => {
	const context = Object.freeze({ segmentId: 'account-segment' }) as unknown as ExperienceContext;
	experience.begin.mockReturnValue(context);
	const onSubmit = vi.fn(async (_account: { name: string; password: string }, received?: ExperienceContext) => {
		expect(received).toBe(context);
		if (outcome === 'error') experience.state(received, 'error');
		else experience.discarded(received, 'stale');
	});
	render(OnboardingAccountForm, { idPrefix: 'registration', submitLabel: 'Create account', onSubmit });
	for (const [label, value] of [['Username', 'alice'], ['Password', 'long-enough-password'], ['Confirm password', 'long-enough-password']]) {
		await fireEvent.input(screen.getByLabelText(new RegExp(`^${label}`)), { target: { value } });
	}
	await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
	await waitFor(() => expect((screen.getByRole('button', { name: 'Create account' }) as HTMLButtonElement).disabled).toBe(false));
	expect(onSubmit).toHaveBeenCalledOnce();
	expect(experience.state.mock.calls.some(([, state]) => state === 'ready')).toBe(false);
	expect(experience.applied).not.toHaveBeenCalled();
});
