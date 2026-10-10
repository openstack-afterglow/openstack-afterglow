import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import StepProgress, { stepVisualState } from '../StepProgress.svelte';
import ProvisionPipeline from '../ProvisionPipeline.svelte';

const steps = [
	{ id: 'volume', label: '부트 볼륨', description: 'OS 이미지 볼륨 생성', meta: '4s' },
	{ id: 'server', label: 'VM 생성', description: 'Nova 인스턴스 생성' },
	{ id: 'fip', label: 'Floating IP', description: 'Floating IP 할당' },
];

function states(container: HTMLElement): (string | null)[] {
	return Array.from(container.querySelectorAll('li')).map((item) => item.getAttribute('data-state'));
}

describe('stepVisualState', () => {
	it('derives done, active and pending around the current step', () => {
		expect([0, 1, 2].map((index) => stepVisualState(index, 1, 'running'))).toEqual(['done', 'active', 'pending']);
	});

	it('keeps every step pending before the first progress report', () => {
		expect([0, 1, 2].map((index) => stepVisualState(index, -1, 'running'))).toEqual(['pending', 'pending', 'pending']);
	});

	it('marks the step a failed operation stopped at, and finishes every step on completion', () => {
		expect([0, 1, 2].map((index) => stepVisualState(index, 1, 'failed'))).toEqual(['done', 'failed', 'pending']);
		expect([0, 1, 2].map((index) => stepVisualState(index, -1, 'done'))).toEqual(['done', 'done', 'done']);
	});
});

describe('StepProgress', () => {
	it('names the active step in text and as the current step, not by color alone', () => {
		const { container } = render(StepProgress, { steps, current: 'server', label: 'VM 배포 단계' });
		const list = screen.getByRole('list', { name: 'VM 배포 단계' });
		expect(states(container)).toEqual(['done', 'active', 'pending']);
		const active = within(list).getAllByRole('listitem')[1];
		expect(active.getAttribute('aria-current')).toBe('step');
		expect(active.textContent).toContain('진행 중');
	});

	it('reveals a description only once its step is reached', () => {
		render(StepProgress, { steps, current: 'server', label: 'VM 배포 단계' });
		expect(screen.queryByText('OS 이미지 볼륨 생성')).not.toBeNull();
		expect(screen.queryByText('Nova 인스턴스 생성')).not.toBeNull();
		expect(screen.queryByText('Floating IP 할당')).toBeNull();
	});

	it('reports failure on the failed step with visible text', () => {
		const { container } = render(StepProgress, { steps, current: 'server', status: 'failed', label: 'VM 배포 단계' });
		expect(states(container)).toEqual(['done', 'failed', 'pending']);
		expect(container.querySelector('[data-state="failed"]')?.textContent).toContain('실패');
	});

	it('treats an unknown current step as not started rather than guessing', () => {
		const { container } = render(StepProgress, { steps, current: 'manila_preparing', label: 'VM 배포 단계' });
		expect(states(container)).toEqual(['pending', 'pending', 'pending']);
		expect(container.querySelector('[aria-current]')).toBeNull();
	});
});

describe('ProvisionPipeline', () => {
	const stages = steps.map(({ id, label }) => ({ id, label, icon: 'M4 4h16v16H4z' }));

	it('fills conduits behind finished stations and flows only into the active one', () => {
		const { container } = render(ProvisionPipeline, { stages, current: 'server', label: 'VM 배포 그래픽' });
		const conduits = Array.from(container.querySelectorAll('.conduit'));
		expect(conduits.map((conduit) => conduit.getAttribute('data-filled'))).toEqual(['true', null]);
		expect(conduits[0].querySelector('.conduit-packet')).not.toBeNull();
		expect(conduits[1].querySelector('.conduit-packet')).toBeNull();
	});

	it('is announced once: hidden from assistive technology beside a step list', () => {
		render(ProvisionPipeline, { stages, current: 'server', label: 'VM 배포 그래픽', decorative: true });
		expect(screen.queryByRole('list', { name: 'VM 배포 그래픽' })).toBeNull();
	});

	it('names each station with its state when used on its own', () => {
		render(ProvisionPipeline, { stages, current: 'server', label: 'VM 배포 그래픽' });
		const items = within(screen.getByRole('list', { name: 'VM 배포 그래픽' })).getAllByRole('listitem');
		expect(items.map((item) => item.textContent?.trim())).toEqual(['부트 볼륨 · 완료', 'VM 생성 · 진행 중', 'Floating IP · 대기']);
	});
});
