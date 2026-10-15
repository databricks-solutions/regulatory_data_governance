#!/usr/bin/env bash
# Deploy do app RC18 no AKS com o docker/.env + docker/.env.bundle. Idempotente.
# Rode antes ./docker/setup.sh -t <target> --no-up.
#
# Uso: ./docker/deploy_aks.sh -g <rg> -r <acr> [-l <região>] [opções]
#
#   -g, --resource-group  resource group (obrigatório)
#   -r, --registry        nome do ACR, único no Azure (obrigatório)
#   -c, --cluster         cluster AKS (default: rc18)
#   -l, --location        região de um resource group novo — use a do workspace
#   -n, --namespace       namespace (default: rc18)
#       --node-size       VM de um cluster novo (default: Standard_D2s_v5)
#       --node-count      nós de um cluster novo (default: 1)
#       --api-server-ip-ranges
#                         CIDRs IPv4 que alcançam o API server (default: seu IP público)
#       --tag             tag da imagem (default: commit do git)
#       --image           deploya esta imagem em vez de buildar uma
#       --local-build     builda com o Docker local em vez do ACR Tasks
#       --dry-run         mostra as mudanças sem aplicar
#   -y, --yes             sem a confirmação
#   -h, --help            esta ajuda

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER_DIR="$REPO/docker"
ENV_FILE="$DOCKER_DIR/.env"
BUNDLE_ENV="$DOCKER_DIR/.env.bundle"
RESOURCE_GROUP=""
REGISTRY=""
CLUSTER="rc18"
LOCATION=""
NAMESPACE="rc18"
NODE_SIZE="Standard_D2s_v5"
NODE_COUNT=1
API_SERVER_RANGES=""
TAG=""
IMAGE=""
LOCAL_BUILD=0
DRY_RUN=0
ASSUME_YES=0
APP_NAME="rc18-app"
SECRET_NAME="rc18-app-env"
IMAGE_REPOSITORY="rc18-app"
# Próprios: o ACR e o cluster podem ser os da DQX Studio.
PULL_TOKEN="rc18-app-pull"
PULL_SECRET="rc18-app-acr-pull"
# Só do host: fora do Secret.
LOCAL_ONLY_KEYS="PIP_INDEX_URL NPM_CONFIG_REGISTRY RC18_PORT"
BUILD_ONLY_KEYS="PIP_INDEX_URL NPM_CONFIG_REGISTRY"
BUILD_PATHS=(app/frontend app/backend docker/Dockerfile docker/Dockerfile.dockerignore)

usage() {
  sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

die() { echo "ERRO: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }
note() { echo "    $*"; }
changed() { [[ $DRY_RUN -eq 1 ]] || echo "    OK      $*"; }

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '    [dry-run]'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

# .env e depois .env.bundle: o último vence, como no compose.
env_pairs() {
  awk -v skip=" $LOCAL_ONLY_KEYS " '
    /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/ {
      line = $0
      sub(/^[[:space:]]+/, "", line)
      key = substr(line, 1, index(line, "=") - 1)
      value = substr(line, index(line, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value ~ /^".*"$/ || value ~ /^\047.*\047$/) value = substr(value, 2, length(value) - 2)
      if (index(skip, " " key " ")) next
      if (!(key in values)) order[++count] = key
      values[key] = value
    }
    END {
      for (i = 1; i <= count; i++) if (values[order[i]] != "") print order[i] "=" values[order[i]]
    }
  ' "$ENV_FILE" "$BUNDLE_ENV"
}

env_value() { env_pairs | grep -E "^$1=" | tail -n1 | cut -d= -f2- || true; }
env_file_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }

ipv4_int() {
  local a b c d
  IFS=. read -r a b c d <<<"$1"
  printf '%s' $(((a << 24) | (b << 16) | (c << 8) | d))
}

cidr_contains() {
  local outer=$1 inner=$2 outer_bits inner_bits mask
  [[ $outer == */* ]] || outer="$outer/32"
  [[ $inner == */* ]] || inner="$inner/32"
  outer_bits=${outer#*/}
  inner_bits=${inner#*/}
  [[ $outer_bits -le $inner_bits ]] || return 1
  mask=$(((0xFFFFFFFF << (32 - outer_bits)) & 0xFFFFFFFF))
  [[ $(($(ipv4_int "${outer%/*}") & mask)) -eq $(($(ipv4_int "${inner%/*}") & mask)) ]]
}

ipv4_cidr_re='^(25[0-5]|2[0-4][0-9]|1?[0-9]?[0-9])(\.(25[0-5]|2[0-4][0-9]|1?[0-9]?[0-9])){3}(/(3[0-2]|[12]?[0-9]))?$'

acr_pull_granted() {
  local kubelet
  [[ -n $ACR_ID ]] || return 1
  kubelet=$(az aks show -g "$RESOURCE_GROUP" -n "$CLUSTER" --query identityProfile.kubeletidentity.objectId -o tsv)
  [[ -n $kubelet ]] || return 1
  [[ $(az role assignment list --assignee "$kubelet" --scope "$ACR_ID" --include-inherited \
    --query "length([?roleDefinitionName=='AcrPull'])" -o tsv) -gt 0 ]]
}

checksum() {
  if command -v sha256sum >/dev/null; then sha256sum | cut -d' ' -f1; else shasum -a 256 | cut -d' ' -f1; fi
}

# ── Argumentos ──────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case $1 in
    -g | --resource-group | -r | --registry | -c | --cluster | -l | --location | -n | --namespace | \
      --node-size | --node-count | --api-server-ip-ranges | --tag | --image)
      [[ $# -ge 2 ]] || die "$1 exige um valor."
      case $1 in
        -g | --resource-group) RESOURCE_GROUP=$2 ;;
        -r | --registry) REGISTRY=$2 ;;
        -c | --cluster) CLUSTER=$2 ;;
        -l | --location) LOCATION=$2 ;;
        -n | --namespace) NAMESPACE=$2 ;;
        --node-size) NODE_SIZE=$2 ;;
        --node-count) NODE_COUNT=$2 ;;
        --api-server-ip-ranges) API_SERVER_RANGES=$2 ;;
        --tag) TAG=$2 ;;
        --image) IMAGE=$2 ;;
      esac
      shift 2
      ;;
    --local-build) LOCAL_BUILD=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -y | --yes) ASSUME_YES=1; shift ;;
    -h | --help) usage 0 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage 1 ;;
  esac
done

[[ -n $RESOURCE_GROUP && -n $REGISTRY ]] || { echo "Informe -g e -r." >&2; usage 1; }
[[ $RESOURCE_GROUP =~ ^[A-Za-z0-9._()-]{1,90}$ ]] || die "nome de resource group inválido: $RESOURCE_GROUP"
[[ $REGISTRY =~ ^[A-Za-z0-9]{5,50}$ ]] || die "--registry: 5 a 50 letras ou dígitos: $REGISTRY"
[[ $CLUSTER =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$ ]] || die "nome de cluster inválido: $CLUSTER"
[[ -z $LOCATION || $LOCATION =~ ^[a-z0-9]+$ ]] || die "--location: nome de região do Azure, ex.: eastus: $LOCATION"
[[ $NAMESPACE =~ ^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$ ]] || die "--namespace precisa ser um rótulo DNS: $NAMESPACE"
[[ $NODE_SIZE =~ ^[A-Za-z0-9_]+$ ]] || die "--node-size inválido: $NODE_SIZE"
[[ $NODE_COUNT =~ ^[1-9][0-9]*$ ]] || die "--node-count precisa ser inteiro positivo."
[[ -z $TAG || $TAG =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || die "--tag inválida: $TAG"
[[ -z $IMAGE || $IMAGE =~ ^[A-Za-z0-9._/:@-]+$ ]] || die "--image inválida: $IMAGE"
[[ -z $IMAGE || -z $TAG ]] || die "--tag nomeia a imagem que o script builda; não combina com --image."
[[ -z $IMAGE || $LOCAL_BUILD -eq 0 ]] || die "--local-build builda uma imagem; não combina com --image."

command -v az >/dev/null || die "Azure CLI não encontrada (brew install azure-cli)."
[[ $DRY_RUN -eq 1 ]] || command -v kubectl >/dev/null || die "kubectl não encontrado (brew install kubectl, ou az aks install-cli)."
[[ $LOCAL_BUILD -eq 0 ]] || command -v docker >/dev/null || die "--local-build exige Docker com buildx."
[[ -n $IMAGE ]] || command -v git >/dev/null || die "git é necessário para montar o contexto de build."

# ── Configuração: docker/.env + docker/.env.bundle ──────────────────────────

[[ -f $ENV_FILE ]] || die "docker/.env não existe: cp docker/.env.example docker/.env e preencha o SP."
[[ -f $BUNDLE_ENV ]] || die "docker/.env.bundle não existe: rode antes ./docker/setup.sh -t <target> --no-up."
for key in DATABRICKS_HOST DATABRICKS_CATALOG DATABRICKS_WAREHOUSE_ID; do
  [[ -n $(env_value "$key") ]] || die "$key ausente no docker/.env.bundle: rode ./docker/setup.sh -t <target> --no-up."
done
CLIENT_ID=$(env_value DATABRICKS_CLIENT_ID)
if [[ -n $CLIENT_ID ]]; then
  [[ $CLIENT_ID =~ ^[0-9a-f-]{36}$ ]] || die "DATABRICKS_CLIENT_ID do docker/.env não é um application id (UUID)."
  SECRET=$(env_value DATABRICKS_CLIENT_SECRET)
  [[ -n $SECRET && $SECRET != "<"* ]] || die "DATABRICKS_CLIENT_SECRET do docker/.env não preenchido."
  unset SECRET
  [[ -z $(env_value DATABRICKS_TOKEN) ]] || die "docker/.env tem SP e DATABRICKS_TOKEN: o SDK recusa os dois juntos."
else
  [[ -n $(env_value DATABRICKS_TOKEN) ]] || die "docker/.env sem identidade: preencha DATABRICKS_CLIENT_ID e DATABRICKS_CLIENT_SECRET."
  echo "    AVISO  DATABRICKS_TOKEN (PAT) no lugar do SP — só para teste."
fi
HOST=$(env_value DATABRICKS_HOST)
CATALOG=$(env_value DATABRICKS_CATALOG)
CONFIG_KEYS=$(env_pairs | cut -d= -f1 | paste -sd' ' -)
# No template do pod: config nova reinicia o pod.
CONFIG_CHECKSUM=$(env_pairs | checksum)

if [[ -z $API_SERVER_RANGES ]]; then
  API_SERVER_RANGES=$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)
  [[ -n $API_SERVER_RANGES ]] || die "não foi possível descobrir seu IP público; use --api-server-ip-ranges."
fi
API_SERVER_RANGES=$(printf '%s' "$API_SERVER_RANGES" | tr -d '[:space:]')
IFS=, read -r -a REQUESTED_RANGES <<<"$API_SERVER_RANGES"
[[ ${#REQUESTED_RANGES[@]} -gt 0 ]] || die "--api-server-ip-ranges vazio."
for range in "${REQUESTED_RANGES[@]}"; do
  [[ $range =~ $ipv4_cidr_re ]] || die "--api-server-ip-ranges: '$range' não é endereço ou CIDR IPv4."
  [[ $range != */0 ]] || die "--api-server-ip-ranges: '$range' abriria o API server para todos."
done

# ── Pré-voo: conta Azure e recursos existentes ──────────────────────────────

az account show -o none 2>/dev/null || die "sem login no Azure: az login."
SUBSCRIPTION=$(az account show --query '[name, id]' -o tsv | paste -sd' ' -)

GROUP_LOCATION=$(az group show -n "$RESOURCE_GROUP" --query location -o tsv 2>/dev/null || true)
if [[ -z $GROUP_LOCATION ]]; then
  [[ -n $LOCATION ]] || die "o resource group $RESOURCE_GROUP não existe; use --location para criá-lo (a região do workspace)."
  GROUP_PLAN="criar em $LOCATION"
else
  [[ -z $LOCATION || $LOCATION == "$GROUP_LOCATION" ]] ||
    note "AVISO  $RESOURCE_GROUP está em $GROUP_LOCATION; os recursos novos vão para lá, não para $LOCATION."
  LOCATION=$GROUP_LOCATION
  GROUP_PLAN="existe ($LOCATION)"
fi

ACR_ID=$(az acr show -n "$REGISTRY" --query id -o tsv 2>/dev/null || true)
if [[ -z $ACR_ID ]]; then
  REGISTRY_PLAN="criar (SKU Basic)"
  LOGIN_SERVER="$(printf '%s' "$REGISTRY" | tr '[:upper:]' '[:lower:]').azurecr.io"
else
  [[ $ACR_ID == */resourceGroups/*/providers/* ]] || die "id de registry inesperado: $ACR_ID"
  REGISTRY_PLAN="existe"
  LOGIN_SERVER=$(az acr show -n "$REGISTRY" --query loginServer -o tsv)
fi

CLUSTER_EXISTS=0
MISSING_RANGES=()
if az aks show -g "$RESOURCE_GROUP" -n "$CLUSTER" -o none 2>/dev/null; then
  CLUSTER_EXISTS=1
  CLUSTER_PLAN="existe"
  IS_PRIVATE=$(az aks show -g "$RESOURCE_GROUP" -n "$CLUSTER" --query apiServerAccessProfile.enablePrivateCluster -o tsv)
  CURRENT_RANGES=$(az aks show -g "$RESOURCE_GROUP" -n "$CLUSTER" \
    --query "join(',', apiServerAccessProfile.authorizedIpRanges || \`[]\`)" -o tsv)
  if [[ $IS_PRIVATE == true ]]; then
    RANGES_PLAN="cluster privado: o kubectl precisa de rede até a VNet dele"
  elif [[ -z $CURRENT_RANGES ]]; then
    RANGES_PLAN="sem restrição; mantido"
  else
    IFS=, read -r -a EXISTING_RANGES <<<"$CURRENT_RANGES"
    for range in "${REQUESTED_RANGES[@]}"; do
      covered=0
      for existing in "${EXISTING_RANGES[@]}"; do
        if [[ $existing =~ $ipv4_cidr_re ]] && cidr_contains "$existing" "$range"; then covered=1; break; fi
      done
      [[ $covered -eq 1 ]] || MISSING_RANGES+=("$range")
    done
    if [[ ${#MISSING_RANGES[@]} -eq 0 ]]; then
      RANGES_PLAN="$CURRENT_RANGES; cobre $API_SERVER_RANGES"
    else
      RANGES_PLAN="$CURRENT_RANGES; adicionar $(IFS=,; printf '%s' "${MISSING_RANGES[*]}")"
    fi
  fi
else
  CLUSTER_PLAN="criar ($NODE_COUNT × $NODE_SIZE)"
  RANGES_PLAN="$API_SERVER_RANGES"
fi

# Conceder AcrPull exige Owner; sem ele, token de pull.
USE_PULL_TOKEN=1
PULL_PLAN="token só-leitura $PULL_TOKEN (o cluster não tem AcrPull)"
if [[ $CLUSTER_EXISTS -eq 1 ]] && acr_pull_granted; then
  USE_PULL_TOKEN=0
  PULL_PLAN="AcrPull da identidade do cluster"
fi

if [[ -n $IMAGE ]]; then
  IMAGE_PLAN="$IMAGE  (pronta)"
else
  if [[ -z $TAG ]]; then
    TAG=$(git -C "$REPO" rev-parse --short=12 HEAD)
    [[ -z $(git -C "$REPO" status --porcelain -- "${BUILD_PATHS[@]}") ]] || TAG="$TAG-dirty-$(date -u +%Y%m%d%H%M%S)"
  fi
  IMAGE="$LOGIN_SERVER/$IMAGE_REPOSITORY:$TAG"
  if [[ $LOCAL_BUILD -eq 1 ]]; then
    IMAGE_PLAN="$IMAGE  (build local, linux/amd64)"
  else
    IMAGE_PLAN="$IMAGE  (build no ACR Tasks, linux/amd64)"
  fi
fi

# ── Plano + confirmação ─────────────────────────────────────────────────────

cat <<EOF

RC18 — deploy no AKS
  Subscription    $SUBSCRIPTION
  Resource group  $RESOURCE_GROUP  → $GROUP_PLAN
  Registry        $REGISTRY  → $REGISTRY_PLAN
  Cluster         $CLUSTER  → $CLUSTER_PLAN
  Pull da imagem  $PULL_PLAN
  API server      faixas autorizadas: $RANGES_PLAN
  Imagem          $IMAGE_PLAN
  Namespace       $NAMESPACE
  Secret          $SECRET_NAME  ← docker/.env + docker/.env.bundle ($CONFIG_KEYS)
  Workload        Deployment $APP_NAME (1 réplica) + Service ClusterIP na porta 8000
  Workspace       $HOST  (catálogo $CATALOG)
EOF

if [[ $DRY_RUN -eq 0 && $ASSUME_YES -eq 0 ]]; then
  (: </dev/tty) 2>/dev/null || die "sem terminal para confirmar; rode de novo com --yes."
  printf '\nAplicar? [s/N] '
  read -r reply </dev/tty
  [[ $reply =~ ^[SsYy]([Ii][Mm]|[Ee][Ss])?$ ]] || { echo "Cancelado; nada foi alterado."; exit 1; }
fi

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
chmod 700 "$WORK_DIR"

# ── Recursos Azure ──────────────────────────────────────────────────────────

step "[1/5] Resource group"
if [[ -z $GROUP_LOCATION ]]; then
  run az group create -n "$RESOURCE_GROUP" -l "$LOCATION" -o none
  changed "criado $RESOURCE_GROUP em $LOCATION"
else
  note "$RESOURCE_GROUP existe"
fi

step "[2/5] Container registry + cluster AKS"
if [[ -z $ACR_ID ]]; then
  run az acr create -g "$RESOURCE_GROUP" -n "$REGISTRY" -l "$LOCATION" --sku Basic -o none
  [[ $DRY_RUN -eq 1 ]] || ACR_ID=$(az acr show -n "$REGISTRY" --query id -o tsv)
  changed "criado $LOGIN_SERVER"
else
  note "$LOGIN_SERVER existe"
fi
if [[ $CLUSTER_EXISTS -eq 0 ]]; then
  [[ $DRY_RUN -eq 1 ]] || note "criando $CLUSTER; leva alguns minutos"
  run az aks create -g "$RESOURCE_GROUP" -n "$CLUSTER" -l "$LOCATION" \
    --node-count "$NODE_COUNT" --node-vm-size "$NODE_SIZE" --tier free \
    --enable-managed-identity --no-ssh-key \
    --api-server-authorized-ip-ranges "$API_SERVER_RANGES" -o none
  changed "criado $CLUSTER"
else
  if [[ ${#MISSING_RANGES[@]} -gt 0 ]]; then
    run az aks update -g "$RESOURCE_GROUP" -n "$CLUSTER" -o none \
      --api-server-authorized-ip-ranges "$CURRENT_RANGES,$(IFS=,; printf '%s' "${MISSING_RANGES[*]}")"
    changed "autorizado $(IFS=,; printf '%s' "${MISSING_RANGES[*]}") no API server"
  fi
  note "$CLUSTER existe"
fi
if [[ $USE_PULL_TOKEN -eq 0 ]]; then
  note "o cluster faz pull com AcrPull"
elif az acr token show -r "$REGISTRY" -n "$PULL_TOKEN" -o none 2>/dev/null; then
  note "token $PULL_TOKEN existe"
else
  run az acr token create -r "$REGISTRY" -n "$PULL_TOKEN" --repository "$IMAGE_REPOSITORY" content/read \
    --no-passwords -o none
  changed "criado token $PULL_TOKEN (só leitura em $IMAGE_REPOSITORY)"
fi

# ── Imagem ──────────────────────────────────────────────────────────────────

step "[3/5] Imagem"
if [[ $IMAGE_PLAN == *"(pronta)" ]]; then
  note "PULADO  --image"
elif [[ $LOCAL_BUILD -eq 1 ]]; then
  BUILD_ARGS=()
  for key in $BUILD_ONLY_KEYS; do
    value=$(env_file_value "$key")
    [[ -z $value ]] || BUILD_ARGS+=(--build-arg "$key=$value")
  done
  run az acr login -n "$REGISTRY"
  run docker buildx build --platform linux/amd64 -f "$DOCKER_DIR/Dockerfile" -t "$IMAGE" \
    ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} --push "$REPO/app"
  changed "publicada $IMAGE"
else
  # Só arquivos versionados: nenhum .env sai da máquina.
  CONTEXT="$WORK_DIR/context"
  mkdir -p "$CONTEXT"
  (
    cd "$REPO/app"
    git ls-files -z --cached --others --exclude-standard -- frontend backend |
      while IFS= read -r -d '' file; do [[ -f $file ]] && printf '%s\0' "$file"; done |
      tar -cf - --null -T - | tar -xf - -C "$CONTEXT"
  )
  cp "$DOCKER_DIR/Dockerfile" "$CONTEXT/Dockerfile"
  cp "$DOCKER_DIR/Dockerfile.dockerignore" "$CONTEXT/.dockerignore"
  note "contexto de build: $(du -sh "$CONTEXT" | cut -f1 | tr -d '[:space:]')"
  (
    cd "$CONTEXT"
    run az acr build -r "$REGISTRY" -t "$IMAGE_REPOSITORY:$TAG" --platform linux/amd64 \
      -f Dockerfile --timeout 3600 .
  )
  changed "publicada $IMAGE"
fi

# ── Kubernetes ──────────────────────────────────────────────────────────────

pull_secrets_yaml() {
  [[ $USE_PULL_TOKEN -eq 1 ]] || return 0
  printf '      imagePullSecrets:\n        - name: %s\n' "$PULL_SECRET"
}

manifests() {
  cat <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $APP_NAME
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: $APP_NAME
spec:
  # Uma réplica: o branding fica no filesystem do pod.
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: $APP_NAME
  template:
    metadata:
      labels:
        app.kubernetes.io/name: $APP_NAME
      annotations:
        rc18/config-checksum: "$CONFIG_CHECKSUM"
    spec:
      automountServiceAccountToken: false
$(pull_secrets_yaml)
      nodeSelector:
        kubernetes.io/os: linux
        kubernetes.io/arch: amd64
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: $APP_NAME
          image: $IMAGE
          ports:
            - name: http
              containerPort: 8000
          envFrom:
            - secretRef:
                name: $SECRET_NAME
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              memory: 2Gi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          # Não /api/v1/health: ele consulta o warehouse.
          startupProbe:
            httpGet:
              path: /api/openapi.json
              port: http
            periodSeconds: 5
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /api/openapi.json
              port: http
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /api/openapi.json
              port: http
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 5
---
# ClusterIP: o app não autentica usuário.
apiVersion: v1
kind: Service
metadata:
  name: $APP_NAME
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: $APP_NAME
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: $APP_NAME
  ports:
    - name: http
      port: 8000
      targetPort: http
EOF
}

# Server-side: sem last-applied com os valores do Secret.
apply_manifests() {
  kubectl apply --server-side --field-manager=rc18-deploy-aks --force-conflicts -f -
}

step "[4/5] Kubernetes"
if [[ $DRY_RUN -eq 1 ]]; then
  note "criaria o namespace $NAMESPACE e o secret $SECRET_NAME ($CONFIG_KEYS)"
  [[ $USE_PULL_TOKEN -eq 0 ]] || note "geraria uma senha do $PULL_TOKEN no secret $PULL_SECRET"
  note "aplicaria:"
  manifests | sed 's/^/      /'
  printf '\nDry run concluído; nada foi alterado.\n'
  exit 0
fi

export KUBECONFIG="$WORK_DIR/kubeconfig"
az aks get-credentials -g "$RESOURCE_GROUP" -n "$CLUSTER" --file "$KUBECONFIG" -o none
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | apply_manifests >/dev/null
(
  umask 077
  env_pairs >"$WORK_DIR/config.env"
)
kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" --from-env-file="$WORK_DIR/config.env" \
  --dry-run=client -o yaml | apply_manifests >/dev/null
rm -f "$WORK_DIR/config.env"
note "OK      secret $SECRET_NAME"
if [[ $USE_PULL_TOKEN -eq 1 ]]; then
  # Senha nova a cada execução; expira em um ano.
  password=$(az acr token credential generate -r "$REGISTRY" -n "$PULL_TOKEN" --password1 \
    --expiration-in-days 365 --query "passwords[0].value" -o tsv)
  auth=$(printf '%s:%s' "$PULL_TOKEN" "$password" | base64 | tr -d '\n')
  (
    umask 077
    printf '{"auths":{"%s":{"username":"%s","password":"%s","auth":"%s"}}}' \
      "$LOGIN_SERVER" "$PULL_TOKEN" "$password" "$auth" >"$WORK_DIR/dockerconfig.json"
  )
  unset password auth
  kubectl -n "$NAMESPACE" create secret generic "$PULL_SECRET" --type=kubernetes.io/dockerconfigjson \
    --from-file=.dockerconfigjson="$WORK_DIR/dockerconfig.json" --dry-run=client -o yaml | apply_manifests >/dev/null
  rm -f "$WORK_DIR/dockerconfig.json"
  note "OK      secret $PULL_SECRET"
fi
manifests | apply_manifests
if ! kubectl -n "$NAMESPACE" rollout status "deployment/$APP_NAME" --timeout=5m; then
  kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/name=$APP_NAME" -o wide || true
  kubectl -n "$NAMESPACE" logs "deployment/$APP_NAME" --tail=40 || true
  die "o rollout não ficou pronto; veja o status e os logs do pod acima."
fi

# ── Diagnóstico ─────────────────────────────────────────────────────────────

step "[5/5] Diagnóstico (/api/v1/diagnostics/prereqs)"
kubectl -n "$NAMESPACE" exec "deployment/$APP_NAME" -- python -c '
import json, urllib.request
d = json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/v1/diagnostics/prereqs", timeout=120))
for c in d["checks"]:
    fix = "  → " + c["remediation"] if c.get("remediation") else ""
    print("    %-16s %s%s" % (c["state"], c["id"], fix))
print("    diagnóstico: " + d["state"])' || note "AVISO  diagnóstico indisponível (kubectl -n $NAMESPACE logs deployment/$APP_NAME)"

PORT=$(env_file_value RC18_PORT)
cat <<EOF

==> RC18 rodando em $CLUSTER, namespace $NAMESPACE, sem exposição fora do cluster.
    Para abrir em http://localhost:${PORT:-8000}:

      az aks get-credentials -g $RESOURCE_GROUP -n $CLUSTER
      kubectl -n $NAMESPACE port-forward svc/$APP_NAME ${PORT:-8000}:8000

    Logs: kubectl -n $NAMESPACE logs -f deployment/$APP_NAME
EOF
