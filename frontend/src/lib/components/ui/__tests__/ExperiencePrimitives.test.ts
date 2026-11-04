import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import Button from '../Button.svelte';
import Field from '../Field.svelte';
import Alert from '../Alert.svelte';
import Modal from '../Modal.svelte';
import FormModal from '../FormModal.svelte';
import WizardStepper from '../../wizard/WizardStepper.svelte';
import WizardHeader from '../../wizard/WizardHeader.svelte';
import type { ExperienceContext } from '$lib/utils/experience';
import type { ExperienceMessageMetadata } from '$lib/i18n/experienceMessages';

const presentation = vi.hoisted(() => vi.fn());
vi.mock('$lib/utils/experiencePresentation', () => ({
	experiencePresentation: (node: HTMLElement, options: unknown) => {
		presentation(node, options);
		return { update: (next: unknown) => presentation(node, next), destroy: vi.fn() };
	},
}));

const children = createRawSnippet(() => ({ render: () => '<span>Visible source text</span>' }));
const experience = { segmentId: 'explicit' } as ExperienceContext;
const experienceMessage: ExperienceMessageMetadata = { key: 'common:actions.confirm', locale: 'ko', catalog_revision: 'a'.repeat(64), tone: 'neutral', restoration: 'restored' };
const semanticProps = { experience, experienceMessage };
afterEach(() => vi.clearAllMocks());

describe('semantic primitive compatibility', () => {
	it('preserves native button clicks and disabled link prevention with optional source metadata', async () => {
		const onclick = vi.fn();
		const button = render(Button, { ...semanticProps, onclick, ariaLabel: 'Confirm', children });
		await fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
		expect(onclick).toHaveBeenCalledOnce();
		expect(presentation).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ context: experience, message: experienceMessage, state: 'ready' }));
		button.unmount();
		render(Button, { ...semanticProps, onclick, href: '/docs', disabled: true, ariaLabel: 'Docs', children });
		const link = screen.getByLabelText('Docs');
		expect(link.getAttribute('href')).toBeNull();
		expect(link.getAttribute('aria-disabled')).toBe('true');
		await fireEvent.click(link);
		expect(onclick).toHaveBeenCalledOnce();
	});

	it('preserves field association, error alert and Alert status roles', () => {
		const field = render(Field, { ...semanticProps, label: 'Input label', for: 'field-id', error: 'Error text', children });
		expect(screen.getByText('Input label').closest('label')?.htmlFor).toBe('field-id');
		expect(screen.getByRole('alert').id).toBe('field-id-message');
		expect(presentation).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ state: 'error' }));
		field.unmount();
		render(Alert, { ...semanticProps, tone: 'info', children });
		expect(screen.getByRole('status')).toBeTruthy();
		expect(presentation).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ message: { ...experienceMessage, tone: 'info' } }));
	});

	it('keeps closed modal unmounted and visible dialog accessibility intact', async () => {
		const modal = render(Modal, { ...semanticProps, open: false, ariaLabel: 'Dialog', children });
		expect(screen.queryByRole('dialog')).toBeNull();
		await modal.rerender({ ...semanticProps, open: true, ariaLabel: 'Dialog', children });
		expect(screen.getByRole('dialog', { name: 'Dialog' }).getAttribute('aria-modal')).toBe('true');
	});

	it('forwards FormModal source metadata without altering submit delivery', async () => {
		const onSubmit = vi.fn();
		render(FormModal, { ...semanticProps, open: true, title: 'Form title', submitLabel: 'Save', onSubmit, children });
		expect(screen.getByRole('dialog', { name: 'Form title' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		expect(onSubmit).toHaveBeenCalledOnce();
		expect(presentation).toHaveBeenCalledWith(expect.any(HTMLElement), { context: experience, message: experienceMessage });
	});

	it('reports the explicit wizard step and preserves completed-step navigation', async () => {
		const goTo = vi.fn();
		render(WizardStepper, { ...semanticProps, cur: 2, totalSteps: 3, stepLabels: ['One', 'Two', 'Three'], goTo });
		await fireEvent.click(screen.getByRole('button', { name: 'One' }));
		expect(goTo).toHaveBeenCalledExactlyOnceWith(1);
		expect(screen.getByRole('button', { name: /Two/ }).getAttribute('aria-current')).toBe('step');
		expect(presentation).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ state: 'ready', step: 2 }));
	});

	it('observes the mobile-visible wizard header without copying resource/project text', () => {
		render(WizardHeader, { ...semanticProps, step: 2, totalSteps: 3, stepName: 'private step draft', onReset: vi.fn(), onClose: vi.fn() });
		expect(presentation).toHaveBeenCalledWith(expect.any(HTMLElement), { context: experience, message: experienceMessage, state: 'ready', step: 2 });
		expect(JSON.stringify(presentation.mock.calls.map((call) => call[1]))).not.toContain('private step draft');
	});
});
