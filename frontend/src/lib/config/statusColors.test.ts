import { describe, expect, it } from 'vitest';
import { getStatusStyle } from './statusColors';

describe('chat run status style', () => {
	it('renders running durable conversations as an active status', () => {
		expect(getStatusStyle('chat_running')).toEqual({
			tone: 'info',
			pulse: true,
			label: '실행 중'
		});
	});

	it('uses explicit authority labels for MCP access levels and terminal grants', () => {
		expect(getStatusStyle('read')).toEqual({ tone: 'info', label: '읽기' });
		expect(getStatusStyle('manage')).toEqual({ tone: 'warning', label: '관리' });
		expect(getStatusStyle('revoked')).toEqual({ tone: 'neutral', label: '폐기됨' });
		expect(getStatusStyle('expired')).toEqual({ tone: 'neutral', label: '만료됨' });
	});

	it('maps Cloud Shell phases to explicit text and semantic tones', () => {
		expect(getStatusStyle('cloud_shell_preparing')).toEqual({ tone: 'warning', pulse: true, label: '준비 중' });
		expect(getStatusStyle('cloud_shell_authorizing')).toEqual({ tone: 'info', pulse: true, label: '인증 중' });
		expect(getStatusStyle('cloud_shell_ready')).toEqual({ tone: 'success', label: '연결됨' });
		expect(getStatusStyle('cloud_shell_ending')).toEqual({ tone: 'warning', pulse: true, label: '종료 중' });
		expect(getStatusStyle('cloud_shell_closed')).toEqual({ tone: 'neutral', label: '종료됨' });
		expect(getStatusStyle('cloud_shell_error')).toEqual({ tone: 'danger', label: '오류' });
	});

	it('maps every Palimpsest export state to an explicit semantic style', () => {
		expect(getStatusStyle('queued')).toEqual({ tone: 'neutral', label: '대기 중' });
		expect(getStatusStyle('downloading')).toEqual({
			tone: 'info',
			pulse: true,
			label: '다운로드 중'
		});
		expect(getStatusStyle('converting')).toEqual({
			tone: 'info',
			pulse: true,
			label: '변환 중'
		});
		expect(getStatusStyle('finalizing')).toEqual({
			tone: 'info',
			pulse: true,
			label: '마무리 중'
		});
		expect(getStatusStyle('complete')).toEqual({ tone: 'success', label: '완료' });
		expect(getStatusStyle('error')).toEqual({ tone: 'danger', label: '오류' });
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
