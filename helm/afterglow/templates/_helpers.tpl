{{/*
Release 네임스페이스 (helm install -n <ns> 으로 주입)
*/}}
{{- define "afterglow.namespace" -}}
{{ .Release.Namespace }}
{{- end }}

{{/*
공통 레이블
*/}}
{{- define "afterglow.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
One Job mutates the schema; every SQL writer independently verifies it read-only.
Use the schema-capable API image with the writer's configuration and Secret.
*/}}
{{- define "afterglow.schemaContainer" -}}
- name: schema-bootstrap
  image: {{ .image.repository }}:{{ .image.tag }}
  imagePullPolicy: {{ .image.pullPolicy }}
  command: ["python", "-m", "scripts.bootstrap_schema", "--if-configured"{{ if .verifyOnly }}, "--verify-only"{{ end }}]
  env:
    - name: AFTERGLOW_ENV
      value: "production"
    - name: REDIS_URL
      valueFrom:
        configMapKeyRef:
          name: afterglow-config
          key: APP_REDIS_URL
  envFrom:
    - secretRef:
        name: afterglow-secrets
  volumeMounts:
    - name: afterglow-config-volume
      mountPath: /app/afterglow.conf
      subPath: afterglow.conf
      readOnly: true
    - name: afterglow-config-volume
      mountPath: /app/config.gpu.toml
      subPath: config.gpu.toml
      readOnly: true
  resources:
    {{- toYaml .resources | nindent 4 }}
{{- end }}

{{/*
Render the complete immutable Job pod template once, for its name and its body.
Only public configuration and Secret references participate in the identity.
*/}}
{{- define "afterglow.schemaJobTemplate" -}}
metadata:
  labels:
    app: schema-bootstrap
spec:
  restartPolicy: Never
  securityContext:
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    {{- include "afterglow.schemaContainer" (dict "image" .Values.image.backend "resources" .Values.resources.backend "verifyOnly" false) | nindent 4 }}
  volumes:
    - name: afterglow-config-volume
      configMap:
        name: afterglow-config
        items:
          - key: afterglow.conf
            path: afterglow.conf
          - key: config.gpu.toml
            path: config.gpu.toml
{{- end }}
