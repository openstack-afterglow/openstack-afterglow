// jsdom has no layout/ResizeObserver. Keep zero-size layout here; actual chart
// dimensions and interactions are qualified in Chromium, never by this shim.
if (typeof window !== 'undefined' && !globalThis.ResizeObserver) {
	globalThis.ResizeObserver = class implements ResizeObserver {
		observe(_target: Element, _options?: ResizeObserverOptions): void {}
		unobserve(_target: Element): void {}
		disconnect(): void {}
	};
}
