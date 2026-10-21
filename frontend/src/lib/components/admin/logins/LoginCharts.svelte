<script lang="ts">
  import Card from '$lib/components/ui/Card.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import { t } from '$lib/i18n/ns/login-monitoring';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import type { LoginBucket, LoginHour } from '$lib/types/loginMonitoring';
  import BklitChart from '$lib/components/charts/BklitChart.svelte';
  import type { ChartSpec } from '$lib/components/charts/types';
  let { timeline, hours }: { timeline: LoginBucket[]; hours: LoginHour[] } = $props();
  const peak = $derived(Math.max(0, ...timeline.map(bucket => bucket.successes)));
  const hourPeak = $derived(Math.max(0, ...hours.map(bucket => bucket.successes)));
  const number = (value: number) => new Intl.NumberFormat(intlLocale()).format(value);
  const date = (at: string) => new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'short', timeStyle: 'short', timeZone: 'UTC' }).format(new Date(at));
  const timelineSpan = $derived(timeline.length > 1 ? Date.parse(timeline[timeline.length - 1].at) - Date.parse(timeline[0].at) : 0);
  const axisDate = $derived(new Intl.DateTimeFormat(intlLocale(), timelineSpan >= 86_400_000
    ? { month: 'numeric', day: 'numeric', timeZone: 'UTC' }
    : { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }));
  const timelineSpec = $derived<ChartSpec>({
    kind: 'bar',
    data: timeline.map(bucket => ({ at: bucket.at, successes: bucket.successes })),
    xKey: 'at', series: [{ key: 'successes', label: t('count'), color: 'var(--color-chart-1)' }],
    domain: [0, peak || 1], formatValue: number,
    formatCategory: (at, context) => context === 'axis' ? axisDate.format(new Date(at)) : date(at),
  });
  const hoursSpec = $derived<ChartSpec>({
    kind: 'bar',
    data: hours.map(bucket => ({ hour: String(bucket.hour).padStart(2, '0'), successes: bucket.successes })),
    xKey: 'hour', series: [{ key: 'successes', label: t('count'), color: 'var(--color-chart-1)' }],
    domain: [0, hourPeak || 1], formatValue: number,
  });
</script>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
  <Card surface="base">
    <h2 class="text-sm font-semibold mb-2">{t('timeline')}</h2>
    <p class="text-xs text-ink-2 tabular-nums mb-2">{t('count')}: {number(0)} – {number(peak)}</p>
    <BklitChart spec={timelineSpec} height={160} label={t('timeline')} showData={false} />
    {#if timeline.length}<p class="flex justify-between gap-3 text-xs text-ink-2 mt-2"><span>{date(timeline[0].at)}</span><span>{date(timeline[timeline.length - 1].at)}</span></p>{/if}
    <details class="mt-3 text-sm"><summary class="min-h-11 cursor-pointer text-ink-1">{t('timelineDetails')}</summary>
      <div class="max-h-64 overflow-y-auto">
      <ResponsiveTable>
        {#snippet cards()}
          {#each timeline as bucket (bucket.at)}
            <CompactResourceCard><time datetime={bucket.at}>{date(bucket.at)}</time><p class="tabular-nums">{t('count')}: {number(bucket.successes)}</p></CompactResourceCard>
          {/each}
        {/snippet}
      <TableShell><table><thead><tr><th>{t('timestamp')}</th><th>{t('count')}</th></tr></thead><tbody>
        {#each timeline as bucket (bucket.at)}<tr><td>{date(bucket.at)}</td><td class="tabular-nums">{number(bucket.successes)}</td></tr>{/each}
      </tbody></table></TableShell>
      </ResponsiveTable>
      </div>
    </details>
  </Card>
  <Card surface="base">
    <h2 class="text-sm font-semibold mb-2">{t('hours')}</h2>
    <p class="text-xs text-ink-2 tabular-nums mb-3">{t('count')}: {number(0)} – {number(hourPeak)}</p>
    <BklitChart spec={hoursSpec} height={160} label={t('hours')} />
  </Card>
</div>
