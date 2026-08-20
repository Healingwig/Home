#!/usr/bin/env bash
# Despliega la app en Cloud Run. Pensado para ejecutarse desde Google Cloud
# Shell, así que no hace falta tener nada instalado.
#
#   bash scripts/desplegar.sh
#
# La primera vez crea el cubo y pide las claves; después reutiliza lo que ya
# hay y solo actualiza el código.

set -euo pipefail

REGION="${REGION:-us-central1}"
SERVICIO="${SERVICIO:-recetas}"

info()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
error() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null || error "No encuentro gcloud. Ejecuta esto desde Google Cloud Shell."

PROYECTO="$(gcloud config get-value project 2>/dev/null)"
[ -n "$PROYECTO" ] && [ "$PROYECTO" != "(unset)" ] \
  || error "No hay proyecto seleccionado. Ejecuta: gcloud config set project TU-PROYECTO"

CUBO="${GCS_BUCKET:-${SERVICIO}-${PROYECTO}}"

info "Proyecto: $PROYECTO · región: $REGION · cubo: gs://$CUBO"

info "1/4 Activando los servicios necesarios (tarda un par de minutos la primera vez)…"
gcloud services enable run.googleapis.com storage.googleapis.com \
    artifactregistry.googleapis.com cloudbuild.googleapis.com --quiet

info "2/4 Preparando el cubo donde se guardan las recetas…"
if gcloud storage buckets describe "gs://$CUBO" >/dev/null 2>&1; then
  echo "Ya existía."
else
  gcloud storage buckets create "gs://$CUBO" --location="$REGION" --uniform-bucket-level-access
fi

info "3/4 Claves"
EXISTENTES="$(gcloud run services describe "$SERVICIO" --region "$REGION" \
    --format='value(spec.template.spec.containers[0].env)' 2>/dev/null || true)"

if [ -n "$EXISTENTES" ]; then
  echo "El servicio ya está desplegado: se conservan las claves que ya tiene."
  VARIABLES="STORAGE_BACKEND=gcs,GCS_BUCKET=$CUBO,LLM_PROVIDER=gemini,DATA_DIR=/tmp/recetas"
else
  read -rsp "Clave de Gemini (https://aistudio.google.com/apikey): " GEMINI_KEY; echo
  [ -n "$GEMINI_KEY" ] || error "Sin clave de Gemini no se puede generar ninguna receta."

  read -rp "Contraseña para entrar a la web desde la tablet: " PASSWORD
  [ -n "$PASSWORD" ] || error "Hace falta una contraseña."

  API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  VARIABLES="STORAGE_BACKEND=gcs,GCS_BUCKET=$CUBO,LLM_PROVIDER=gemini,DATA_DIR=/tmp/recetas"
  VARIABLES="$VARIABLES,GEMINI_API_KEY=$GEMINI_KEY,API_KEY=$API_KEY,APP_PASSWORD=$PASSWORD"
fi

# --update-env-vars, no --set-env-vars: el segundo reemplaza TODAS las
# variables del servicio, así que un redespliegue borraría las claves.
info "4/4 Desplegando (la primera vez tarda unos minutos: construye la imagen)…"
gcloud run deploy "$SERVICIO" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 2 \
  --update-env-vars "$VARIABLES" \
  --quiet

URL="$(gcloud run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)')"

info "Listo."
echo "  Dirección de la app : $URL"
if [ -n "${API_KEY:-}" ]; then
  echo "  Clave para el Atajo : $API_KEY"
  echo
  echo "  Apunta esa clave: no se vuelve a mostrar. Si la pierdes, sácala con:"
  echo "    gcloud run services describe $SERVICIO --region $REGION --format=json | grep -A1 '\"API_KEY\"'"
fi
echo
echo "Comprobación rápida:"
echo "  curl -s $URL/healthz"
