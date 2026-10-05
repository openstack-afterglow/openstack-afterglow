import { t } from '$lib/i18n/ns/drover-pages';
import source from '$lib/i18n/messages/ko/drover-pages.json';

/**
 * Minimal K8s YAML serializer/parser — no external deps.
 * Handles the fixed ConfigMap/Secret object shape only.
 */

export interface MaskedKey {
  key: string;
  value: string;
}

// ---------------------------------------------------------------------------
// Serializer helpers
// ---------------------------------------------------------------------------

function needsQuoting(s: string): boolean {
  if (s === '') return true;
  const lower = s.toLowerCase();
  if (['null', 'true', 'false', 'yes', 'no', 'on', 'off'].includes(lower)) return true;
  if (/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(s)) return true;
  if (/^[:{}\[\],#&*!|>'"%@`~?]/.test(s)) return true;
  if (s.includes(': ') || s.includes(' #') || s.startsWith(' ') || s.endsWith(' ')) return true;
  return false;
}

function serializeScalar(value: string, childIndent: string): string {
  if (!value.includes('\n')) {
    return needsQuoting(value) ? JSON.stringify(value) : value;
  }
  // Block literal (|-)
  const keepNewline = value.endsWith('\n');
  const chomp = keepNewline ? '' : '-';
  const lines = (keepNewline ? value.slice(0, -1) : value).split('\n');
  return `|${chomp}\n${lines.map((l) => `${childIndent}${l}`).join('\n')}`;
}

function serializeData(data: Record<string, string>, key: string): string {
  const keys = Object.keys(data);
  if (keys.length === 0) return `${key}: null\n`;
  const lines: string[] = [`${key}:`];
  for (const k of keys) {
    const v = data[k];
    const serialized = serializeScalar(v, '    ');
    if (serialized.includes('\n')) {
      lines.push(`  ${k}: ${serialized}`);
    } else {
      lines.push(`  ${k}: ${serialized}`);
    }
  }
  return lines.join('\n') + '\n';
}

// ---------------------------------------------------------------------------
// Public serializers
// ---------------------------------------------------------------------------

export function toConfigMapYaml(
  name: string,
  namespace: string,
  data: Record<string, string>
): string {
  return [
    `apiVersion: v1\n`,
    `kind: ConfigMap\n`,
    `metadata:\n`,
    `  name: ${name || source['yaml.newConfigMap']}\n`,
    namespace ? `  namespace: ${namespace}\n` : '',
    serializeData(data, 'data'),
  ].join('');
}

export function toSecretReadYaml(
  name: string,
  namespace: string,
  type: string,
  data: Record<string, string>
): { text: string; maskedKeys: MaskedKey[] } {
  const maskedKeys: MaskedKey[] = Object.entries(data).map(([key, value]) => ({ key, value }));

  // Build YAML with placeholder so positions are stable
  const placeholderData: Record<string, string> = {};
  for (const k of Object.keys(data)) placeholderData[k] = `MASK_${k}_END`;

  const raw = [
    `apiVersion: v1\n`,
    `kind: Secret\n`,
    `type: ${serializeScalar(type, '  ')}\n`,
    `metadata:\n`,
    `  name: ${name}\n`,
    namespace ? `  namespace: ${namespace}\n` : '',
    serializeData(placeholderData, 'data'),
  ].join('');

  const text = raw.replace(/MASK_(.+?)_END/g, '••••••••••');
  return { text, maskedKeys };
}

export function toSecretEditYaml(name: string, type: string, namespace?: string): string {
  return [
    `apiVersion: v1\n`,
    `kind: Secret\n`,
    `type: ${serializeScalar(type, '  ')}\n`,
    `metadata:\n`,
    `  name: ${name || source['yaml.newSecret']}\n`,
    namespace ? `  namespace: ${namespace}\n` : '',
    `stringData: {}\n`,
  ].join('');
}

// ---------------------------------------------------------------------------
// Parser helpers
// ---------------------------------------------------------------------------

interface RawParsed {
  kind?: string;
  data?: Record<string, string>;
  stringData?: Record<string, string>;
}

function parseYamlSubset(text: string): RawParsed {
  const result: RawParsed = {};
  const lines = text.split('\n');
  let i = 0;
  type Section = 'root' | 'data' | 'stringData' | 'metadata' | 'other';
  let section: Section = 'root';

  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trimEnd();
    if (!trimmed.trim() || trimmed.trim().startsWith('#')) { i++; continue; }

    const indent = trimmed.match(/^( *)/)?.[1].length ?? 0;

    if (indent === 0) {
      const m = trimmed.match(/^([\w./-]+):\s*(.*)/);
      if (!m) { i++; continue; }
      const [, key, val] = m;
      if (key === 'kind') { result.kind = val.trim(); section = 'root'; }
      else if (key === 'data') { result.data = {}; section = 'data'; }
      else if (key === 'stringData') { result.stringData = {}; section = 'stringData'; }
      else if (key === 'metadata') { section = 'metadata'; }
      else { section = 'other'; }
      i++; continue;
    }

    if (indent === 2 && (section === 'data' || section === 'stringData')) {
      const dict = section === 'data' ? result.data! : result.stringData!;
      const m = trimmed.match(/^ {2}([^:]+):\s*(.*)/);
      if (!m) { i++; continue; }
      const [, rawKey, rawVal] = m;
      const k = rawKey.trim();
      const v = rawVal.trim();

      if (v === '|' || v === '|-' || v === '|+') {
        const keepNewline = v !== '|-';
        const contentLines: string[] = [];
        i++;
        while (i < lines.length) {
          const cl = lines[i];
          if (!cl.trim()) {
            if (contentLines.length > 0) contentLines.push('');
            i++; continue;
          }
          const ci = cl.match(/^( *)/)?.[1].length ?? 0;
          if (ci < 4) break;
          contentLines.push(cl.slice(4));
          i++;
        }
        // Strip trailing blank lines
        while (contentLines.length > 0 && !contentLines[contentLines.length - 1].trim()) {
          contentLines.pop();
        }
        dict[k] = contentLines.join('\n') + (keepNewline ? '\n' : '');
        continue;
      }

      if (v === "''") { dict[k] = ''; i++; continue; }
      if (v === '""') { dict[k] = ''; i++; continue; }
      if (v.startsWith('"')) {
        try { dict[k] = JSON.parse(v); } catch { dict[k] = v; }
        i++; continue;
      }
      if (v.startsWith("'")) {
        dict[k] = v.slice(1, -1).replace(/''/g, "'");
        i++; continue;
      }
      dict[k] = v;
      i++; continue;
    }

    i++;
  }
  return result;
}

// ---------------------------------------------------------------------------
// Public parsers
// ---------------------------------------------------------------------------

export function fromConfigMapEditYaml(text: string): Record<string, string> {
  let parsed: RawParsed;
  try {
    parsed = parseYamlSubset(text);
  } catch (e) {
    throw new Error(t('yaml.parseError', { error: e instanceof Error ? e.message : String(e) }));
  }
  if (parsed.kind && parsed.kind !== 'ConfigMap') throw new Error(t('yaml.configMapKind'));
  return parsed.data ?? {};
}

export function fromSecretEditYaml(text: string): Record<string, string> {
  let parsed: RawParsed;
  try {
    parsed = parseYamlSubset(text);
  } catch (e) {
    throw new Error(t('yaml.parseError', { error: e instanceof Error ? e.message : String(e) }));
  }
  if (parsed.kind && parsed.kind !== 'Secret') throw new Error(t('yaml.secretKind'));
  if (parsed.data && Object.keys(parsed.data).length > 0)
    throw new Error(t('yaml.stringDataRequired'));
  return parsed.stringData ?? {};
}
