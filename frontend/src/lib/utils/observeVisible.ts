// 뷰포트에 처음 들어올 때 한 번만 콜백을 실행하는 Svelte action.
// 관찰자를 컴포넌트마다 만들지 않고 모듈 단위로 공유한다.
type VisibleCallback = () => void;

const callbacks = new WeakMap<Element, VisibleCallback>();
let observer: IntersectionObserver | null = null;

function shared(): IntersectionObserver | null {
	if (typeof IntersectionObserver === 'undefined') return null;
	observer ??= new IntersectionObserver(
		(entries) => {
			for (const entry of entries) {
				if (!entry.isIntersecting) continue;
				const run = callbacks.get(entry.target);
				callbacks.delete(entry.target);
				observer?.unobserve(entry.target);
				run?.();
			}
		},
		{ rootMargin: '200px' }
	);
	return observer;
}

export function observeVisible(node: Element, callback: VisibleCallback) {
	const io = shared();
	if (!io) {
		// jsdom 등 IntersectionObserver 가 없는 환경에서는 즉시 로드한다.
		callback();
		return {};
	}
	callbacks.set(node, callback);
	io.observe(node);
	return {
		update(next: VisibleCallback) {
			if (callbacks.has(node)) callbacks.set(node, next);
		},
		destroy() {
			callbacks.delete(node);
			io.unobserve(node);
		}
	};
}
