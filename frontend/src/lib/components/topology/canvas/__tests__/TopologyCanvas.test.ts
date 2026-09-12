// TopologyCanvas 렌더·선택·intent·검색·HUD·수동 배치 계약.
// jsdom 에는 ResizeObserver / PointerEvent / SVG 경로 API 가 없으므로 컴포넌트는 이를 가드하고, 여기서는 그 상태 그대로 검증한다.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import TopologyCanvas from '../TopologyCanvas.svelte';
import { buildGraph } from '../topologyGraph';
import { layoutStorageKey } from '../layoutStorage';
import { P, makeFixture, makeTraffic } from './fixtures';

function renderCanvas(props: Partial<Record<string, unknown>> = {}) {
	const callbacks = {
		onSelectInstance: vi.fn(),
		onSelectRouter: vi.fn(),
		onSelectLoadBalancer: vi.fn(),
		onSelectNetwork: vi.fn(),
		onIntentInstance: vi.fn(),
		onIntentRouter: vi.fn(),
		onCancelIntent: vi.fn(),
	};
	const utils = render(TopologyCanvas, {
		props: { data: makeFixture(), traffic: makeTraffic(), projectId: P, showAll: false, ...callbacks, ...props },
	});
	return { ...utils, ...callbacks };
}

// jsdom 에는 PointerEvent 생성자가 없으므로 MouseEvent 에 pointerId·pointerType 을 주입해 포인터 시퀀스를 재현한다.
// (setPointerCapture 는 컴포넌트가 옵셔널 호출 + try/catch 로 감싸므로 스텁이 필요 없다)
function firePointer(
	type: 'pointerdown' | 'pointerup' | 'pointercancel',
	target: Element,
	init: { pointerId: number; clientX?: number; clientY?: number; pointerType?: string },
) {
	const ev = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: init.clientX ?? 0, clientY: init.clientY ?? 0 });
	Object.defineProperty(ev, 'pointerId', { value: init.pointerId });
	Object.defineProperty(ev, 'pointerType', { value: init.pointerType ?? 'mouse' });
	return fireEvent(target, ev);
}

function pointerMove(init: { pointerId: number; clientX: number; clientY: number }) {
	const ev = new MouseEvent('pointermove', { bubbles: true, cancelable: true, clientX: init.clientX, clientY: init.clientY });
	Object.defineProperty(ev, 'pointerId', { value: init.pointerId });
	Object.defineProperty(ev, 'pointerType', { value: 'mouse' });
	return ev;
}

function fireWheel(target: Element, init: { deltaX?: number; deltaY?: number; deltaMode?: number; ctrlKey?: boolean; metaKey?: boolean; wheelDeltaY?: number }) {
	const ev = new WheelEvent('wheel', {
		bubbles: true, cancelable: true,
		deltaX: init.deltaX ?? 0, deltaY: init.deltaY ?? 0, deltaMode: init.deltaMode ?? 0,
		ctrlKey: init.ctrlKey ?? false, metaKey: init.metaKey ?? false,
		clientX: 200, clientY: 200,
	});
	// jsdom 은 비표준 wheelDeltaY 를 만들지 않는다. 마우스 휠(120 배수)을 재현할 때만 주입한다.
	if (init.wheelDeltaY !== undefined) Object.defineProperty(ev, 'wheelDeltaY', { value: init.wheelDeltaY });
	return fireEvent(target, ev);
}

/** 예약된 rAF 프레임을 흘려보낸다(휠은 pendingView 로 모아 프레임마다 한 번 적용된다). */
const flushFrame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));

const worldEl = () => document.querySelector<HTMLDivElement>('.topology-world')!;
function viewOf() {
	const t = worldEl().style.transform;
	const m = /translate\(([-\d.]+)px, ([-\d.]+)px\) scale\(([\d.]+)\)/.exec(t);
	if (!m) throw new Error(`unexpected world transform: ${t}`);
	return { panX: Number(m[1]), panY: Number(m[2]), k: Number(m[3]) };
}

const nodeCards = () => Array.from(document.querySelectorAll<HTMLButtonElement>('button[data-node-id]'));
const cardOf = (id: string) => document.querySelector<HTMLButtonElement>(`button[data-node-id="${id}"]`);

describe('TopologyCanvas', () => {
	beforeEach(() => {
		localStorage.clear();
	});
	afterEach(() => {
		cleanup();
		localStorage.clear();
	});

	it('노드마다 종류·이름이 담긴 aria-label 을 가진 button 을 하나씩 렌더링한다', () => {
		renderCanvas();
		const graph = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const cards = nodeCards();
		expect(cards).toHaveLength(graph.nodes.size);
		expect(new Set(cards.map((c) => c.dataset.nodeId))).toEqual(new Set(graph.nodes.keys()));
		expect(screen.getByRole('button', { name: /^인스턴스 web-01 · ACTIVE · 10\.10\.1\.11/ })).toBeTruthy();
		expect(screen.getByRole('button', { name: /^라우터 edge-router · ACTIVE/ })).toBeTruthy();
		expect(screen.getByRole('button', { name: /^네트워크 스위치 vSwitch-app-net · ACTIVE · 10\.10\.2\.0\/24/ })).toBeTruthy();
		expect(screen.getByRole('button', { name: /^로드밸런서 web-lb · ACTIVE · 10\.10\.1\.100/ })).toBeTruthy();
		// 다른 프로젝트 리소스는 그려지지 않는다
		expect(cardOf('vm-other-01')).toBeNull();
		// 뷰포트는 키보드 조작이 가능한 application 랜드마크
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		expect(viewport.getAttribute('tabindex')).toBe('0');
		// 첫 라우터 카드만 관리자 투어 셀렉터를 가진다
		const tourCards = document.querySelectorAll('[data-tour="admin-network-resource"]');
		expect(tourCards).toHaveLength(1);
		expect(tourCards[0].getAttribute('data-node-id')).toBe('rtr-edge');
	});

	it('VM 카드 클릭은 onSelectInstance, 스위치 카드 클릭은 onSelectNetwork 를 호출한다', async () => {
		const { onSelectInstance, onSelectNetwork, onSelectRouter } = renderCanvas();
		await fireEvent.click(cardOf('vm-web-01')!);
		expect(onSelectInstance).toHaveBeenCalledWith('vm-web-01');
		await fireEvent.click(cardOf('sw:net-app')!);
		expect(onSelectNetwork).toHaveBeenCalledWith('net-app');
		await fireEvent.click(cardOf('rtr-edge')!);
		expect(onSelectRouter).toHaveBeenCalledWith('rtr-edge');
	});

	it('LB 카드 클릭은 raw TopologyLoadBalancer 를 넘기고 비제어 모드에서 눌린 상태가 된다', async () => {
		const { onSelectLoadBalancer, onSelectInstance, onSelectNetwork } = renderCanvas({ selectedId: undefined });
		await fireEvent.click(cardOf('lb-web')!);
		expect(onSelectLoadBalancer).toHaveBeenCalledTimes(1);
		expect(onSelectLoadBalancer.mock.calls[0][0]).toMatchObject({ id: 'lb-web', vip_address: '10.10.1.100' });
		expect(cardOf('lb-web')!.getAttribute('aria-pressed')).toBe('true');
		expect(onSelectInstance).not.toHaveBeenCalled();
		expect(onSelectNetwork).not.toHaveBeenCalled();
	});

	it('라우터 카드 pointerenter/leave 와 focus/blur 가 intent 콜백을 호출한다', async () => {
		const { onIntentRouter, onIntentInstance, onCancelIntent } = renderCanvas();
		const router = cardOf('rtr-edge')!;
		await fireEvent.pointerEnter(router);
		expect(onIntentRouter).toHaveBeenCalledWith('rtr-edge');
		expect(onCancelIntent).not.toHaveBeenCalled();
		await fireEvent.pointerLeave(router);
		expect(onCancelIntent).toHaveBeenCalledTimes(1);

		const vm = cardOf('vm-app-01')!;
		await fireEvent.focus(vm);
		expect(onIntentInstance).toHaveBeenCalledWith('vm-app-01');
		await fireEvent.blur(vm);
		expect(onCancelIntent).toHaveBeenCalledTimes(2);
	});

	it('selectedId prop 에 네트워크 id 를 주면 해당 스위치가 눌린 상태가 되고 무관한 카드는 흐려진다', () => {
		renderCanvas({ selectedId: 'net-app' });
		expect(cardOf('sw:net-app')!.getAttribute('aria-pressed')).toBe('true');
		expect(cardOf('sw:net-app')!.classList.contains('is-faded')).toBe(false);
		expect(cardOf('vm-app-01')!.classList.contains('is-faded')).toBe(false);
		expect(cardOf('vm-lab-01')!.classList.contains('is-faded')).toBe(true);
	});

	it("검색 '10.10.2.' 는 비매칭 카드를 흐리게 하고 결과 수를 알린다", async () => {
		renderCanvas();
		const input = screen.getByRole('searchbox', { name: '토폴로지 검색' });
		await fireEvent.input(input, { target: { value: '10.10.2.' } });
		expect(cardOf('vm-web-01')!.classList.contains('is-dim')).toBe(true);
		expect(cardOf('vm-app-01')!.classList.contains('is-dim')).toBe(false);
		expect(cardOf('vm-db-01')!.classList.contains('is-dim')).toBe(false);
		expect(cardOf('sw:net-app')!.classList.contains('is-dim')).toBe(false);
		const zoneApp = document.querySelector('rect[data-zone-net="net-app"]')!;
		const zoneWeb = document.querySelector('rect[data-zone-net="net-web"]')!;
		expect(zoneApp.classList.contains('is-match')).toBe(true);
		expect(zoneWeb.classList.contains('is-dim')).toBe(true);
		const live = document.querySelector('[aria-live="polite"]')!;
		await waitFor(() => expect(live.textContent).toMatch(/^검색 결과 \d+개$/));
		expect(screen.getByText(/^\d+건$/)).toBeTruthy();

		await fireEvent.keyDown(input, { key: 'Escape' });
		await waitFor(() => expect(cardOf('vm-web-01')!.classList.contains('is-dim')).toBe(false));
	});

	it('존 라벨 버튼이 가시 네트워크마다 있고 클릭하면 onSelectNetwork 를 호출한다', async () => {
		const { onSelectNetwork } = renderCanvas();
		const labels = screen.getAllByRole('button', { name: /^네트워크 .+ 선택$/ });
		const graph = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(labels).toHaveLength(graph.nets.length);
		const app = labels.find((l) => l.getAttribute('data-zone-label') === 'net-app')!;
		expect(within(app).getByText('app-net')).toBeTruthy();
		expect(within(app).getByText('내부')).toBeTruthy();
		await fireEvent.click(app);
		expect(onSelectNetwork).toHaveBeenCalledWith('net-app');
		// 사용자 화면에서는 관리자 pill(VLAN/MTU)이 없다
		expect(within(app).queryByText(/^MTU /)).toBeNull();
	});

	it("트렁크 배지는 '네트워크 합산' 캡션과 합산 속도를 표시하고 라우터 트래픽을 주장하지 않는다", () => {
		renderCanvas();
		const badges = Array.from(document.querySelectorAll<HTMLButtonElement>('button[data-trunk-badge]'));
		// edge-router: pub+web+app, transit-router: transit+app → 5개 트렁크
		expect(badges).toHaveLength(5);
		for (const b of badges) {
			expect(b.textContent).toContain('네트워크 합산');
			expect(b.getAttribute('title')).toBe('네트워크 합산 트래픽 · 라우터 exporter 없음');
		}
		const appBadge = badges.find((b) => b.dataset.trunkBadge === 'trunk:rtr-edge>sw:net-app')!;
		expect(appBadge.textContent).toContain('▼ 14.0M');
		const hit = document.querySelector('path[data-edge-key="trunk:rtr-edge>sw:net-app"]')!;
		expect(hit.querySelector('title')!.textContent).toContain('네트워크 합산 트래픽');
	});

	it('관리자 보기에서는 존 라벨에 세그먼트·MTU pill 이 붙는다', () => {
		const data = makeFixture();
		const pub = data.networks.find((n) => n.id === 'net-pub')!;
		pub.provider_network_type = 'vlan';
		pub.provider_segmentation_id = 120;
		pub.provider_physical_network = 'physnet1';
		renderCanvas({ data, adminView: true, storageScope: 'admin' });
		const labels = screen.getAllByRole('button', { name: /^네트워크 .+ 선택$/ });
		const pubLabel = labels.find((l) => l.getAttribute('data-zone-label') === 'net-pub')!;
		expect(within(pubLabel).getByText('VLAN 태그 120')).toBeTruthy();
		expect(within(pubLabel).getByText('MTU 1500')).toBeTruthy();
	});

	it('Shift+화살표로 노드를 옮기면 수동 배치 칩이 나타나고 초기화하면 저장소까지 비운다', async () => {
		renderCanvas();
		const key = layoutStorageKey('user', P);
		expect(screen.queryByRole('button', { name: /^수동 배치 \d+개 · 초기화$/ })).toBeNull();
		const card = cardOf('vm-web-01')!;
		const before = card.style.transform;
		await fireEvent.keyDown(card, { key: 'ArrowRight', shiftKey: true });
		expect(card.style.transform).not.toBe(before);
		const chip = await screen.findByRole('button', { name: '수동 배치 1개 · 초기화' });
		expect(JSON.parse(localStorage.getItem(key) ?? '{}')).toHaveProperty('vm-web-01');

		await fireEvent.click(chip);
		await waitFor(() => expect(screen.queryByRole('button', { name: /^수동 배치/ })).toBeNull());
		expect(localStorage.getItem(key)).toBeNull();
		expect(card.style.transform).toBe(before);
	});

	it('저장된 수동 위치는 id 로 복원되고 사라진 id 는 정리된다', () => {
		const key = layoutStorageKey('user', P);
		localStorage.setItem(key, JSON.stringify({ 'vm-web-01': { x: 5, y: 7 }, 'vm-gone': { x: 1, y: 1 } }));
		renderCanvas();
		expect(cardOf('vm-web-01')!.style.transform).toBe('translate(5px, 7px)');
		expect(screen.getByRole('button', { name: '수동 배치 1개 · 초기화' })).toBeTruthy();
		expect(JSON.parse(localStorage.getItem(key) ?? '{}')).toEqual({ 'vm-web-01': { x: 5, y: 7 } });
	});

	it('트래픽 갱신은 위치를 바꾸지 않고 NIC 행·배지 문구만 바꾼다', async () => {
		const { rerender } = renderCanvas();
		const card = cardOf('vm-app-01')!;
		const before = card.style.transform;
		expect(within(card).getByText('↓14.0M ↑6.0M')).toBeTruthy();
		const t = makeTraffic();
		t.interfaces!['port-app-01-eth0'].rx_bps = 2.8e7;
		t.networks['net-app'].rx_bps += 1.4e7;
		await rerender({ data: makeFixture(), traffic: t, projectId: P, showAll: false });
		expect(within(cardOf('vm-app-01')!).getByText('↓28.0M ↑6.0M')).toBeTruthy();
		expect(cardOf('vm-app-01')!.style.transform).toBe(before);
	});

	it('구조 갱신으로 사라진 노드의 stale 호버는 캔버스를 흐리게 하지 않는다', async () => {
		const view = renderCanvas();
		await fireEvent.pointerEnter(cardOf('vm-lab-01')!);
		// 호버가 실제로 등록되어 무관한 카드가 흐려졌는지 먼저 확인한다(반대 단정이 공허해지지 않도록)
		expect(nodeCards().filter((c) => c.classList.contains('is-faded')).length).toBeGreaterThan(0);
		const trimmed = makeFixture();
		trimmed.instances = trimmed.instances.filter((i) => i.id !== 'vm-lab-01');
		await view.rerender({ data: trimmed, traffic: makeTraffic(), projectId: P, showAll: false });
		expect(cardOf('vm-lab-01')).toBeNull();
		expect(nodeCards().filter((c) => c.classList.contains('is-faded')).map((c) => c.dataset.nodeId)).toEqual([]);
	});

	it('핀치가 소비한 시퀀스의 세 번째 포인터는 선택을 발생시키지 않는다', async () => {
		const { onSelectInstance, onSelectNetwork } = renderCanvas();
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const card = cardOf('vm-web-01')!;
		await firePointer('pointerdown', viewport, { pointerId: 1, clientX: 100, clientY: 100 });
		await firePointer('pointerdown', viewport, { pointerId: 2, clientX: 240, clientY: 160 });
		await firePointer('pointerdown', card, { pointerId: 3, clientX: 170, clientY: 130 });
		await firePointer('pointerup', viewport, { pointerId: 1, clientX: 100, clientY: 100 });
		await firePointer('pointerup', viewport, { pointerId: 2, clientX: 240, clientY: 160 });
		await firePointer('pointerup', card, { pointerId: 3, clientX: 170, clientY: 130 });
		expect(onSelectInstance).not.toHaveBeenCalled();
		expect(onSelectNetwork).not.toHaveBeenCalled();
		// 대조군: 같은 배선으로 단일 포인터 시퀀스는 선택을 호출한다
		await firePointer('pointerdown', card, { pointerId: 4, clientX: 170, clientY: 130 });
		await firePointer('pointerup', card, { pointerId: 4, clientX: 170, clientY: 130 });
		expect(onSelectInstance).toHaveBeenCalledWith('vm-web-01');
		expect(onSelectInstance).toHaveBeenCalledTimes(1);
	});

	it('드래그가 핀치로 중단되면 대기 중인 위치 프레임을 버린다', async () => {
		renderCanvas();
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const card = cardOf('vm-web-01')!;
		const before = card.style.transform;
		// 마우스로 드래그를 시작해 임계값을 넘기면 다음 rAF 프레임에 반영될 위치가 예약된다
		await firePointer('pointerdown', card, { pointerId: 1, clientX: 100, clientY: 100 });
		await fireEvent(viewport, pointerMove({ pointerId: 1, clientX: 220, clientY: 180 }));
		// 두 번째 포인터가 내려와 핀치로 승격되면 그 예약 프레임은 폐기되어야 한다
		await firePointer('pointerdown', viewport, { pointerId: 2, clientX: 320, clientY: 260 });
		// 예약 프레임을 실제로 흘려보낸다(정리되지 않았다면 여기서 위치가 어긋난다)
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));
		expect(cardOf('vm-web-01')!.style.transform).toBe(before);
		// 핀도 만들어지지 않는다(중단된 드래그는 확정되지 않는다)
		expect(screen.queryByRole('button', { name: /^수동 배치/ })).toBeNull();
	});

	it('다른 블럭 위에 놓으면 겹치지 않는 가까운 자리로 밀려나고 그 좌표가 저장된다', async () => {
		renderCanvas();
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const rectOf = (id: string) => {
			const el = cardOf(id)!;
			const m = /translate\((-?[\d.]+)px, (-?[\d.]+)px\)/.exec(el.style.transform)!;
			return { x: Number(m[1]), y: Number(m[2]), w: parseFloat(el.style.width), h: parseFloat(el.style.height) };
		};
		const target = rectOf('vm-web-01');
		const start = rectOf('vm-web-02');
		// vm-web-02 를 vm-web-01 위로 정확히 끌어다 놓는다(월드 좌표 = 화면 좌표, k=1 · pan=0 가 아닐 수 있어 델타로 옮긴다)
		const dx = target.x - start.x, dy = target.y - start.y;
		const card = cardOf('vm-web-02')!;
		await firePointer('pointerdown', card, { pointerId: 1, clientX: 100, clientY: 100 });
		await fireEvent(viewport, pointerMove({ pointerId: 1, clientX: 100 + dx, clientY: 100 + dy }));
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));
		await firePointer('pointerup', viewport, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });

		const dropped = rectOf('vm-web-02');
		const fixed = rectOf('vm-web-01');
		// 겹치지 않는다
		expect(dropped.x < fixed.x + fixed.w && fixed.x < dropped.x + dropped.w
			&& dropped.y < fixed.y + fixed.h && fixed.y < dropped.y + dropped.h).toBe(false);
		// 밀려난 자리는 원래 자리도, 놓은 자리도 아니다(실제로 옮겨졌다)
		expect({ x: dropped.x, y: dropped.y }).not.toEqual({ x: target.x, y: target.y });
		// 저장되는 것은 밀려난 자리가 아니라 사용자가 놓은 자리(의도)다.
		// 해소 결과를 저장하면 구조가 바뀔 때마다 그 값을 다시 해소해 핀이 조금씩 걸어간다.
		const saved = JSON.parse(localStorage.getItem(layoutStorageKey('user', P)) ?? '{}');
		expect(saved['vm-web-02']).toBeTruthy();
		expect(saved['vm-web-02']).not.toEqual({ x: dropped.x, y: dropped.y });
		// 그 저장값은 실제로 겹치는 자리 — 즉 놓은 자리 그대로다
		const sv = saved['vm-web-02'];
		expect(sv.x < fixed.x + fixed.w && fixed.x < sv.x + dropped.w
			&& sv.y < fixed.y + fixed.h && fixed.y < sv.y + dropped.h).toBe(true);
	});

	it('연결선 굵기가 사용량을 연속으로 반영한다(4단계 계단이 아니다)', () => {
		renderCanvas();
		const widths = [...document.querySelectorAll<SVGPathElement>('path.edge[data-key]')]
			.filter((p) => /^(cable|trunk):/.test(p.getAttribute('data-key') ?? ''))
			.map((p) => Number(p.style.strokeWidth))
			.filter((w) => Number.isFinite(w) && w > 0);
		expect(widths.length).toBeGreaterThan(3);
		// 예전 계단값 집합. 트래픽이 붙은 선 중 적어도 하나는 이 집합 밖(보간값)이어야 한다.
		const steps = new Set([1.5, 2.0, 2.5, 3.0, 3.5]);
		expect(widths.some((w) => !steps.has(w))).toBe(true);
		// 모든 굵기는 바닥값과 상한 사이에 있다
		for (const w of widths) {
			expect(w).toBeGreaterThanOrEqual(1.5);
			expect(w).toBeLessThanOrEqual(3.5);
		}
	});

	it('트랙패드 두 손가락 스크롤은 확대·축소가 아니라 위치를 이동한다', async () => {
		renderCanvas();
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const before = viewOf();
		await fireWheel(viewport, { deltaX: 40, deltaY: 120 });
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));
		const after = viewOf();
		// 배율은 그대로, 위치만 스크롤 방향으로 이동한다
		expect(after.k).toBe(before.k);
		expect(after.panX).toBe(before.panX - 40);
		expect(after.panY).toBe(before.panY - 120);
	});

	it('한 프레임에 들어온 휠 델타는 마지막 값이 아니라 합산되어 적용된다', async () => {
		renderCanvas();
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const before = viewOf();
		// 트랙패드 관성 스크롤은 한 프레임에 여러 이벤트를 보낸다 → pendingView 에 누적되어야 한다
		await fireWheel(viewport, { deltaY: 120 });
		await fireWheel(viewport, { deltaY: 120 });
		await flushFrame();
		expect(viewOf().panY).toBe(before.panY - 240);
	});

	it('마우스 휠(120 배수 노치)은 커서 기준으로 확대·축소한다', async () => {
		renderCanvas();
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const before = viewOf();
		// Chrome·Safari 는 마우스 휠에서 wheelDeltaY 를 120 의 배수로 보고한다 → 트랙패드 스크롤과 구분된다
		await fireWheel(viewport, { deltaY: -100, wheelDeltaY: 120 });
		await flushFrame();
		const after = viewOf();
		expect(after.k).toBeGreaterThan(before.k);
		expect(after.panX).toBeCloseTo(200 * (1 - after.k), 4);
	});

	it('줄 단위(deltaMode=1) 휠은 마우스 휠로 보아 확대하며, 줄→픽셀 정규화가 배율에 반영된다', async () => {
		// Firefox 는 마우스 휠만 줄 단위로 보고한다(트랙패드는 픽셀 단위) → 줄 단위면 마우스 휠이다.
		const lines = (() => {
			renderCanvas();
			const vp = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
			return { vp, before: viewOf() };
		})();
		await fireWheel(lines.vp, { deltaY: -3, deltaMode: 1 });
		await flushFrame();
		const byLines = viewOf().k;
		expect(byLines).toBeGreaterThan(lines.before.k);
		cleanup();

		// 3줄 × 16px = 48px 과 같은 배율이어야 한다(정규화가 빠지면 3px 로 계산돼 거의 변하지 않는다)
		renderCanvas();
		const vp2 = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		await fireWheel(vp2, { deltaY: -48, wheelDeltaY: 120 });
		await flushFrame();
		expect(viewOf().k).toBeCloseTo(byLines, 6);
	});

	it('Ctrl(⌘)+휠은 커서 기준으로 확대·축소한다', async () => {
		renderCanvas();
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const before = viewOf();
		await fireWheel(viewport, { deltaY: -120, ctrlKey: true });
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));
		const zoomedIn = viewOf();
		expect(zoomedIn.k).toBeGreaterThan(before.k);
		// 커서(200,200) 아래 지점이 고정된다: panX = sx - (sx - panX) * (k2/k), jsdom rect 는 0 이므로 200*(1-k2)
		expect(zoomedIn.panX).toBeCloseTo(200 * (1 - zoomedIn.k), 4);
		expect(zoomedIn.panY).toBeCloseTo(200 * (1 - zoomedIn.k), 4);
		await fireWheel(viewport, { deltaY: 240, metaKey: true });
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));
		expect(viewOf().k).toBeLessThan(zoomedIn.k);
	});

	it('존을 300ms 안에 두 번 누르면 네트워크 선택은 한 번만 발생한다', async () => {
		const { onSelectNetwork } = renderCanvas();
		const zone = () => document.querySelector<SVGRectElement>('rect[data-zone-net="net-app"]')!;
		await firePointer('pointerdown', zone(), { pointerId: 1, clientX: 300, clientY: 300 });
		await firePointer('pointerup', zone(), { pointerId: 1, clientX: 300, clientY: 300 });
		expect(onSelectNetwork).toHaveBeenCalledTimes(1);
		expect(onSelectNetwork).toHaveBeenCalledWith('net-app');
		// 두 번째 pointerup 은 판정에서 제외되고 dblclick 의 fitZone 만 남는다
		await firePointer('pointerdown', zone(), { pointerId: 1, clientX: 300, clientY: 300 });
		await firePointer('pointerup', zone(), { pointerId: 1, clientX: 300, clientY: 300 });
		expect(onSelectNetwork).toHaveBeenCalledTimes(1);
	});

	it('존 라벨 aria-pressed 는 선택만 반영하고 호버 강조는 시각 클래스로만 남는다', async () => {
		const view = renderCanvas();
		const label = (netId: string) => document.querySelector<HTMLButtonElement>(`button[data-zone-label="${netId}"]`)!;
		await fireEvent.pointerEnter(cardOf('vm-app-01')!);
		// 호버 파생 강조(is-active)는 켜지지만 aria-pressed 는 여전히 false 다
		expect(label('net-app').classList.contains('is-active')).toBe(true);
		expect(label('net-app').getAttribute('aria-pressed')).toBe('false');
		expect(label('net-mgmt').getAttribute('aria-pressed')).toBe('false');
		await view.rerender({ data: makeFixture(), traffic: makeTraffic(), projectId: P, showAll: false, selectedId: 'net-app' });
		expect(label('net-app').getAttribute('aria-pressed')).toBe('true');
		expect(label('net-web').getAttribute('aria-pressed')).toBe('false');
	});

	it('FIP 을 가진 VM 을 호버하면 그 FIP 의 외부망 존·라벨도 함께 강조된다', async () => {
		renderCanvas();
		const label = (netId: string) => document.querySelector<HTMLButtonElement>(`button[data-zone-label="${netId}"]`)!;
		const zone = (netId: string) => document.querySelector<SVGRectElement>(`rect[data-zone-net="${netId}"]`)!;
		expect(label('net-pub').classList.contains('is-active')).toBe(false);
		// bastion-01 은 net-transit·net-web NIC + net-pub FIP 을 갖는다 → FIP 선이 향하는 net-pub 도 활성이어야 한다
		await fireEvent.pointerEnter(cardOf('vm-bastion-01')!);
		expect(label('net-pub').classList.contains('is-active')).toBe(true);
		expect(zone('net-pub').classList.contains('is-active')).toBe(true);
		// FIP 이 없는 VM 은 외부망을 강조하지 않는다
		await fireEvent.pointerLeave(cardOf('vm-bastion-01')!);
		await fireEvent.pointerEnter(cardOf('vm-app-01')!);
		expect(label('net-pub').classList.contains('is-active')).toBe(false);
	});

	it('비제어 모드에서 같은 카드를 다시 누르면 선택이 해제된다', async () => {
		const { onSelectInstance } = renderCanvas({ selectedId: undefined });
		await fireEvent.click(cardOf('vm-web-01')!);
		expect(cardOf('vm-web-01')!.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(cardOf('vm-web-01')!);
		expect(cardOf('vm-web-01')!.getAttribute('aria-pressed')).toBe('false');
		// 부모도 같은 콜백으로 패널을 닫도록 두 번 발화한다
		expect(onSelectInstance).toHaveBeenCalledTimes(2);
		expect(onSelectInstance.mock.calls.every((c) => c[0] === 'vm-web-01')).toBe(true);
	});

	it('패킷 흐름은 기본 on 이고 끌 수 있으며 경로 API 가 없는 환경에서는 점을 만들지 않는다', async () => {
		renderCanvas();
		const chk = screen.getByRole('checkbox', { name: /패킷 흐름/ });
		expect((chk as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(chk);
		expect((chk as HTMLInputElement).checked).toBe(false);
		expect(document.querySelectorAll('.flow-dot')).toHaveLength(0);
	});
});
