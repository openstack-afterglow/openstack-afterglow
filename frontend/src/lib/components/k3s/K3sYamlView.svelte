<script lang="ts">
  import type { MaskedKey } from '$lib/utils/k8sYaml';

  interface Props {
    text: string;
    maskedKeys?: MaskedKey[];
  }

  let { text, maskedKeys = [] }: Props = $props();

  type ParsedLine =
    | { kind: 'plain'; text: string }
    | { kind: 'masked'; prefix: string; key: string; value: string };

  const maskedMap = $derived(new Map(maskedKeys.map((m) => [m.key, m.value])));

  const parsedLines = $derived<ParsedLine[]>(
    text.split('\n').map((line): ParsedLine => {
      for (const [key, value] of maskedMap) {
        if (line.startsWith(`  ${key}: `) || line.startsWith(`${key}: `)) {
          const prefix = line.startsWith(`  ${key}: `) ? `  ${key}: ` : `${key}: `;
          return { kind: 'masked', prefix, key, value };
        }
      }
      return { kind: 'plain', text: line };
    })
  );

  let revealed = $state(new Set<string>());

  function toggle(key: string) {
    const next = new Set(revealed);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    revealed = next;
  }

  async function handleCopy() {
    const full = parsedLines
      .map((p) => (p.kind === 'masked' ? p.prefix + p.value : p.text))
      .join('\n');
    await navigator.clipboard.writeText(full);
  }
</script>

<div class="relative group">
  <button
    onclick={handleCopy}
    class="absolute top-2 right-2 text-xs text-ink-3 hover:text-ink-2 opacity-0 group-hover:opacity-100 transition-opacity z-10 bg-surface-base px-1.5 py-0.5 rounded"
  >복사</button>
  <pre class="text-xs font-mono text-ink-2 bg-surface-canvas rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">{#each parsedLines as parsed, i}{i > 0 ? '\n' : ''}{#if parsed.kind === 'masked'}<span class="text-ink-3">{parsed.prefix}</span>{#if revealed.has(parsed.key)}<span class="text-yellow-400">{parsed.value}</span><button onclick={() => toggle(parsed.key)} class="text-action-warm hover:text-action-warm-hover ml-1">숨기기</button>{:else}<span class="text-ink-3">••••••••••</span><button onclick={() => toggle(parsed.key)} class="text-action-warm hover:text-action-warm-hover ml-1">Reveal</button>{/if}{:else}{parsed.text}{/if}{/each}</pre>
</div>
