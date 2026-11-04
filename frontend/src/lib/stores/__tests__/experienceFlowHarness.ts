import { get } from 'svelte/store';
import { vi } from 'vitest';
import { experienceHealth, installExperienceCollector, type ExperienceCollectorController, type ExperiencePayload } from '$lib/utils/experience';
import type { InteractionOwner } from '$lib/utils/interactionAudit';

export interface FlowExperienceEvent {
	event_type: string;
	action_id?: string;
	feature: string;
	payload: ExperiencePayload;
}
export interface CapturedFlowExperience {
	events: FlowExperienceEvent[];
	collector: ExperienceCollectorController;
	flush(): Promise<FlowExperienceEvent[]>;
}

/** Real collector and serialization; only its diagnostic HTTP receiver is synthetic. */
export function captureFlowExperience(route: string, getOwner: () => InteractionOwner, businessFetch?: typeof fetch): CapturedFlowExperience {
	const events: FlowExperienceEvent[] = [];
	vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
		if (String(input).endsWith('/experience-contract')) return new Response(JSON.stringify({
			schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768,
		}), { headers: { 'Content-Type': 'application/json' } });
		if (!String(input).endsWith('/experience-events')) {
			if (businessFetch) return businessFetch(input, init);
			throw new Error('Unexpected non-diagnostic request');
		}
		const batch = JSON.parse(String(init?.body));
		events.push(...batch.events);
		return new Response(JSON.stringify({ accepted: batch.events.length, duplicates: 0, schema_version: 2 }), { status: 201 });
	});
	const collector = installExperienceCollector({
		getOwner, getRoute: () => route, getBaseUrl: () => '', isSuppressed: () => false,
		isEnabled: () => true, subscribeOwner: () => () => {},
	});
	return {
		events,
		collector,
		async flush() {
			for (let attempt = 0; attempt < 10 && get(experienceHealth).queued > 0; attempt += 1) await collector.flush();
			if (get(experienceHealth).queued > 0) throw new Error('Diagnostic receiver did not drain within ten batches');
			return events;
		},
	};
}
