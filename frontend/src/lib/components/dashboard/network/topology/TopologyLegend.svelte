<script lang="ts">
	import { t } from '$lib/i18n/ns/network-pages';
	import StatusDot from '$lib/components/topology/StatusDot.svelte';
	let isLight = $state(false);
	$effect(() => {
		isLight = document.documentElement.classList.contains('light');
		const observer = new MutationObserver(() => {
			isLight = document.documentElement.classList.contains('light');
		});
		observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
		return () => observer.disconnect();
	});
</script>

<div class="flex flex-wrap gap-x-5 gap-y-2 text-xs px-1"
     style="color: {isLight ? '#4b5563' : '#9ca3af'}">
	<!-- 상태 dot: 카드의 StatusDot 과 같은 색 토큰. 범례는 실제 상태가 아니므로 숨쉬지 않는다 -->
	<span class="flex items-center gap-1.5">
		<StatusDot status="ACTIVE" live={false} />{t('topologyLegend.active')}
	</span>
	<span class="flex items-center gap-1.5">
		<StatusDot status="ERROR" live={false} />{t('topologyLegend.errorShutoff')}
	</span>
	<span class="flex items-center gap-1.5">
		<StatusDot status="PENDING" live={false} />{t('topologyLegend.pendingOther')}
	</span>
	<!-- 자원 타입 아이콘 -->
	<span class="flex items-center gap-1.5">
		<svg class="w-3.5 h-3.5 flex-shrink-0 text-warm-text" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
			<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2" fill="currentColor" opacity="0.5"/>
			<path d="M8 2v2M8 12v2M2 8h2M12 8h2"/>
		</svg>
		{t('topologyLegend.router')}
	</span>
	<span class="flex items-center gap-1.5">
		<svg class="w-3.5 h-3.5 flex-shrink-0 text-cyan-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
			<line x1="8" y1="2" x2="8" y2="14"/><line x1="3" y1="5" x2="13" y2="5"/><line x1="4" y1="11" x2="12" y2="11" opacity="0.6"/>
		</svg>
		{t('topologyLegend.loadBalancer')}
	</span>
	<span class="flex items-center gap-1.5">
		<svg class="w-3.5 h-3.5 flex-shrink-0 text-ink-2" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3">
			<ellipse cx="8" cy="5" rx="5" ry="2"/><line x1="3" y1="5" x2="3" y2="11"/><line x1="13" y1="5" x2="13" y2="11"/>
			<path d="M3 11 a5 2 0 0 0 10 0"/>
		</svg>
		{t('topologyLegend.instance')}
	</span>
	<!-- 네트워크 종류 (세로 바) -->
	<span class="flex items-center gap-1.5">
		<span class="w-0.5 h-4 flex-shrink-0 rounded-full" style="background:#ea580c"></span>{t('topologyLegend.externalNetwork')}
	</span>
	<span class="flex items-center gap-1.5">
		<span class="w-0.5 h-4 flex-shrink-0 rounded-full" style="background:#0d9488"></span>{t('topologyLegend.sharedNetwork')}
	</span>
	<span class="flex items-center gap-1.5">
		<span class="w-0.5 h-4 flex-shrink-0 rounded-full" style="background:#3b82f6"></span>{t('topologyLegend.internalNetwork')}
	</span>
	<!-- 마커 -->
	<span class="flex items-center gap-1.5">
		<span class="text-xs text-orange-400 font-mono flex-shrink-0">✦</span>{t('topologyLegend.floatingIp')}
	</span>
	<span class="flex items-center gap-1.5">
		<span class="text-xs px-1 rounded bg-surface-selected/40 text-warm-text flex-shrink-0">2NIC</span>{t('topologyLegend.multiNic')}
	</span>
	<!-- 연결선 -->
	<span class="flex items-center gap-1.5">
		<span class="inline-block w-6 h-0.5 flex-shrink-0 rounded-full" style="background:#3b82f6"></span>{t('topologyLegend.connectionTraffic')}
	</span>
	<span class="flex items-center gap-1.5">
		<span class="inline-block w-6 h-0.5 flex-shrink-0" style="background-image:repeating-linear-gradient(90deg,#f59e0b 0,#f59e0b 4px,transparent 4px,transparent 7px)"></span>{t('topologyLegend.loadBalancerMembers')}
	</span>
</div>
