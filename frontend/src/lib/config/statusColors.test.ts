// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { getStatusStyle } from './statusColors';

describe('chat run status style', () => {
	it('renders running durable conversations as an active status', () => {
		expect(getStatusStyle('chat_running')).toMatchObject({ tone: 'info', pulse: true });
	});

	it('uses semantic tones for MCP access levels and terminal grants', () => {
		expect(getStatusStyle('read')).toMatchObject({ tone: 'info' });
		expect(getStatusStyle('manage')).toMatchObject({ tone: 'warning' });
		expect(getStatusStyle('revoked')).toMatchObject({ tone: 'neutral' });
		expect(getStatusStyle('expired')).toMatchObject({ tone: 'neutral' });
	});

	it('maps Cloud Shell phases to semantic tones', () => {
		expect(getStatusStyle('cloud_shell_preparing')).toMatchObject({ tone: 'warning', pulse: true });
		expect(getStatusStyle('cloud_shell_authorizing')).toMatchObject({ tone: 'info', pulse: true });
		expect(getStatusStyle('cloud_shell_ready')).toMatchObject({ tone: 'success' });
		expect(getStatusStyle('cloud_shell_ending')).toMatchObject({ tone: 'warning', pulse: true });
		expect(getStatusStyle('cloud_shell_closed')).toMatchObject({ tone: 'neutral' });
		expect(getStatusStyle('cloud_shell_error')).toMatchObject({ tone: 'danger' });
	});

	it('maps every Palimpsest export state to an explicit semantic style', () => {
		expect(getStatusStyle('queued')).toMatchObject({ tone: 'neutral' });
		expect(getStatusStyle('downloading')).toMatchObject({ tone: 'info', pulse: true });
		expect(getStatusStyle('converting')).toMatchObject({ tone: 'info', pulse: true });
		expect(getStatusStyle('finalizing')).toMatchObject({ tone: 'info', pulse: true });
		expect(getStatusStyle('complete')).toMatchObject({ tone: 'success' });
		expect(getStatusStyle('error')).toMatchObject({ tone: 'danger' });
	});

	it('maps topology canvas operating states (Octavia / router) and falls back to neutral', () => {
		expect(getStatusStyle('DEGRADED')).toEqual({ tone: 'danger' });
		expect(getStatusStyle('OFFLINE')).toEqual({ tone: 'neutral' });
		expect(getStatusStyle('NO_MONITOR')).toEqual({ tone: 'info' });
		expect(getStatusStyle('DOWN')).toEqual({ tone: 'neutral' });
		expect(getStatusStyle('UNKNOWN_STATUS')).toEqual({ tone: 'neutral' });
		expect(getStatusStyle(null)).toEqual({ tone: 'neutral' });
		expect(getStatusStyle(undefined)).toEqual({ tone: 'neutral' });
	});
});
