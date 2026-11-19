import type { IsoNodeKind, IsoStatus, IsoTone } from './types';

export const toneVars: Record<IsoTone, string> = {
	external: 'var(--color-topology-external)', shared: 'var(--color-topology-shared)',
	internal: 'var(--color-topology-internal)', 'internal-2': 'var(--color-topology-internal-2)',
	router: 'var(--color-topology-router)', gateway: 'var(--color-topology-gateway)',
	accent: 'var(--color-warm)', info: 'var(--color-state-info)', success: 'var(--color-state-success)',
	warning: 'var(--color-state-warning)', danger: 'var(--color-state-danger)', neutral: 'var(--color-ink-2)',
};

/** Stroke glyphs on a 24-unit coordinate system. */
export const glyphs: Record<IsoNodeKind, string> = {
	instance: 'M3 4h18v6H3zM3 14h18v6H3zM7 7h1m-1 10h1m4-10h5m-5 10h5',
	router: 'M3 7h17m-4-4 4 4-4 4m5 6H4m4-4-4 4 4 4',
	loadbalancer: 'M10 2h4v4h-4zM2 16h4v4H2zM10 16h4v4h-4zM18 16h4v4h-4zM12 6v10M4 16v-5h16v5',
	database: 'M4 6a8 3 0 1 0 16 0 8 3 0 1 0-16 0zm0 0v12a8 3 0 0 0 16 0V6M4 12a8 3 0 0 0 16 0',
	gateway: 'M3 21h18M6 21V6l12-3v18M9 13h6m-2-2 2 2-2 2',
	'vpn-server': 'M12 2l8 3v5c0 6-4 10-8 12-4-2-8-6-8-12V5zM9 11h6v5H9zm1-1V9a2 2 0 0 1 4 0v1',
	peer: 'M3 4h18v12H3zM8 21h8m-4-5v5',
	'peer-group': 'M2 4h13v10H2zM6 18h6m-3-4v4m9-10h4v12h-7',
	internet: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0ZM2 12h20m-10-10c-5 6-5 14 0 20 5-6 5-14 0-20Z',
	cidr: 'M8 4 3 12l5 8m8-16 5 8-5 8m-3-15-2 14',
	'floating-ip': 'M12 22s7-6 7-13A7 7 0 1 0 5 9c0 7 7 13 7 13Zm2-13a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
	port: 'M5 3h14v7l-3 3v5H8v-5l-3-3zm5 0v5m4-5v5m-2 10v4',
	'security-group': 'M12 2l8 3v5c0 6-4 10-8 12-4-2-8-6-8-12V5zm-3 10 2 2 4-5',
	volume: 'M3 14h18v6H3zM3 14l3-9h12l3 9M7 17h.01M11 17h5',
	'file-share': 'M3 6h6l2 2h10v11H3zM3 11h18',
	'k8s-service': 'M12 2l9 5v10l-9 5-9-5V7zM12 8v8m-4-6 4 2 4-2',
};

export const statusIcons: Record<IsoStatus, { path: string; tone: string }> = {
	ok: { path: 'M1 4l2 2 4-4', tone: 'success' },
	pending: { path: 'M4 0 8 4 4 8 0 4z', tone: 'info' },
	warning: { path: 'M4 .5 8 7.5H0z', tone: 'warning' },
	error: { path: 'M1 1l6 6M7 1 1 7', tone: 'danger' },
	off: { path: 'M1 1h6v6H1z', tone: 'neutral' },
	unknown: { path: 'M.5 4h7', tone: 'neutral' },
};
