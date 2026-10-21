// jsdom has no layout/ResizeObserver. Keep zero-size layout here; actual chart
// dimensions and interactions are qualified in Chromium, never by this shim.
if (typeof window !== 'undefined' && !globalThis.ResizeObserver) {
	globalThis.ResizeObserver = class implements ResizeObserver {
		observe(_target: Element, _options?: ResizeObserverOptions): void {}
		unobserve(_target: Element): void {}
		disconnect(): void {}
	};
}

// Layout-less component tests start at desktop width. Responsive behavior is
// exercised with real matchMedia in Chromium and explicit change events in tests.
if (typeof window !== 'undefined' && !window.matchMedia) {
	window.matchMedia = (query: string): MediaQueryList => {
		const events = new EventTarget();
		const minimum = /min-width:\s*(\d+)px/.exec(query);
		const maximum = /max-width:\s*(\d+)px/.exec(query);
		return {
			media: query,
			matches: minimum ? window.innerWidth >= Number(minimum[1]) : maximum ? window.innerWidth <= Number(maximum[1]) : false,
			onchange: null,
			addEventListener: events.addEventListener.bind(events),
			removeEventListener: events.removeEventListener.bind(events),
			dispatchEvent: events.dispatchEvent.bind(events),
			addListener: () => undefined,
			removeListener: () => undefined,
		};
	};
}
