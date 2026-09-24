// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { createChatRunAttachment } from '../chatRunAttachment';

describe('createChatRunAttachment', () => {
	it('detaches the local SSE reader without a cancel request', () => {
		const attachment = createChatRunAttachment();
		const reader = new AbortController();
		const runGeneration = attachment.generation;

		expect(attachment.attach(reader, runGeneration)).toBe(true);
		attachment.detach();

		expect(reader.signal.aborted).toBe(true);
		expect(attachment.isCurrent(runGeneration)).toBe(false);
	});

	it('allows a newly selected conversation to attach after navigation', () => {
		const attachment = createChatRunAttachment();
		const priorReader = new AbortController();
		attachment.attach(priorReader, attachment.generation);
		attachment.detach();
		const resumedReader = new AbortController();

		expect(attachment.attach(resumedReader, attachment.generation)).toBe(true);
		expect(priorReader.signal.aborted).toBe(true);
		expect(resumedReader.signal.aborted).toBe(false);
	});
});
