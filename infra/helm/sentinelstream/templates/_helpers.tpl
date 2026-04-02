{{- define "sentinelstream.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "sentinelstream.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- if contains (include "sentinelstream.name" .) .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "sentinelstream.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "sentinelstream.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "sentinelstream.labels" -}}
helm.sh/chart: {{ include "sentinelstream.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "sentinelstream.selectorLabels" -}}
app.kubernetes.io/name: {{ include "sentinelstream.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "sentinelstream.serviceName" -}}
{{- printf "%s-%s" (include "sentinelstream.fullname" .root) .name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "sentinelstream.configName" -}}
{{- printf "%s-config" (include "sentinelstream.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "sentinelstream.secretName" -}}
{{- default (printf "%s-secrets" (include "sentinelstream.fullname" .)) .Values.secrets.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "sentinelstream.serviceAccountName" -}}
{{- $serviceAccount := default .root.Values.serviceDefaults.serviceAccount .service.serviceAccount -}}
{{- if $serviceAccount.name -}}
{{- $serviceAccount.name -}}
{{- else -}}
{{- include "sentinelstream.serviceName" (dict "root" .root "name" .name) -}}
{{- end -}}
{{- end -}}

{{- define "sentinelstream.serviceImage" -}}
{{- $repository := default .name .service.repository -}}
{{- printf "%s/%s:%s" .root.Values.global.imageRegistry $repository .root.Values.global.imageTag -}}
{{- end -}}
