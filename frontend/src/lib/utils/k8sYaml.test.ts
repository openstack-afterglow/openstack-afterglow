// @vitest-environment node
import { describe, it, expect } from 'vitest';
import {
  toConfigMapYaml,
  toSecretReadYaml,
  toSecretEditYaml,
  fromConfigMapEditYaml,
  fromSecretEditYaml,
} from './k8sYaml';

describe('toConfigMapYaml', () => {
  it('단순 키/값을 YAML로 직렬화한다', () => {
    const yaml = toConfigMapYaml('my-config', 'default', { KEY: 'value' });
    expect(yaml).toContain('kind: ConfigMap');
    expect(yaml).toContain('name: my-config');
    expect(yaml).toContain('namespace: default');
    expect(yaml).toContain('KEY: value');
  });

  it('multiline 값을 블록 스칼라(|)로 직렬화한다', () => {
    const yaml = toConfigMapYaml('cfg', 'ns', {
      'config.toml': '[redis]\nurl = "redis://localhost"\n',
    });
    expect(yaml).toContain('|');
    expect(yaml).toContain('[redis]');
  });

  it('빈 data는 null로 직렬화된다', () => {
    const yaml = toConfigMapYaml('empty', 'ns', {});
    expect(yaml).toContain('data: null');
  });
});

describe('toSecretReadYaml', () => {
  it('값을 마스킹(•)으로 교체하고 maskedKeys를 반환한다', () => {
    const { text, maskedKeys } = toSecretReadYaml('my-secret', 'ns', 'Opaque', {
      DATABASE_URL: 'cG9zdGdyZXM=',
    });
    expect(text).toContain('DATABASE_URL: ••••••••••');
    expect(text).not.toContain('cG9zdGdyZXM=');
    expect(maskedKeys).toHaveLength(1);
    expect(maskedKeys[0]).toEqual({ key: 'DATABASE_URL', value: 'cG9zdGdyZXM=' });
  });

  it('type 필드가 YAML에 포함된다', () => {
    const { text } = toSecretReadYaml('s', 'ns', 'kubernetes.io/tls', { 'tls.crt': 'abc=' });
    expect(text).toContain('type: kubernetes.io/tls');
  });

  it('data가 없으면 maskedKeys가 비어있다', () => {
    const { maskedKeys } = toSecretReadYaml('empty', 'ns', 'Opaque', {});
    expect(maskedKeys).toHaveLength(0);
  });
});

describe('fromConfigMapEditYaml', () => {
  it('data 섹션을 파싱해 Record를 반환한다', () => {
    const input = `apiVersion: v1
kind: ConfigMap
metadata:
  name: cfg
data:
  KEY: value
  OTHER: hello
`;
    const result = fromConfigMapEditYaml(input);
    expect(result).toEqual({ KEY: 'value', OTHER: 'hello' });
  });

  it('data가 없으면 빈 객체를 반환한다', () => {
    const input = `apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\ndata: null\n`;
    expect(fromConfigMapEditYaml(input)).toEqual({});
  });

  it('kind가 ConfigMap이 아니면 오류를 던진다', () => {
    expect(() =>
      fromConfigMapEditYaml('apiVersion: v1\nkind: Secret\ndata:\n  k: v\n')
    ).toThrow('ConfigMap');
  });

  it('인식 불가 입력은 빈 data를 반환한다', () => {
    expect(fromConfigMapEditYaml('{')).toEqual({});
  });

  it('multiline 블록 스칼라를 올바르게 파싱한다', () => {
    const yaml = toConfigMapYaml('cfg', 'ns', { 'config.toml': '[redis]\nurl = "r"\n' });
    const result = fromConfigMapEditYaml(yaml);
    expect(result['config.toml']).toContain('[redis]');
  });
});

describe('fromSecretEditYaml', () => {
  it('stringData 섹션을 파싱해 Record를 반환한다', () => {
    const input = `apiVersion: v1
kind: Secret
type: Opaque
stringData:
  DB_URL: postgres://user:pass@localhost/db
`;
    const result = fromSecretEditYaml(input);
    expect(result).toEqual({ DB_URL: 'postgres://user:pass@localhost/db' });
  });

  it('stringData가 없으면 빈 객체를 반환한다', () => {
    const yaml = toSecretEditYaml('s', 'Opaque');
    expect(fromSecretEditYaml(yaml)).toEqual({});
  });

  it('data 필드가 있으면 오류를 던진다', () => {
    expect(() =>
      fromSecretEditYaml('apiVersion: v1\nkind: Secret\ndata:\n  k: dmFsdWU=\n')
    ).toThrow('stringData');
  });

  it('kind가 Secret이 아니면 오류를 던진다', () => {
    expect(() =>
      fromSecretEditYaml('apiVersion: v1\nkind: ConfigMap\nstringData:\n  k: v\n')
    ).toThrow('Secret');
  });
});
