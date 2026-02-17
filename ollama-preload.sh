#!/bin/bash
# Script de préchargement optimisé du modèle Ollama

MODEL="${OLLAMA_PRELOAD_MODEL:-gemma-2b-fast}"
OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
MAX_RETRIES=15
RETRY_DELAY=2

echo "Prechargement du modele $MODEL..."

# Attendre que Ollama soit prêt (avec timeout plus court)
for i in $(seq 1 $MAX_RETRIES); do
    if curl -s --max-time 2 "$OLLAMA_HOST/api/tags" > /dev/null 2>&1; then
        echo "Ollama est pret, chargement du modele..."
        break
    fi
    if [ $i -lt $MAX_RETRIES ]; then
        echo "Attente d'Ollama... ($i/$MAX_RETRIES)"
        sleep $RETRY_DELAY
    fi
done

# Précharger le modèle avec une requête très courte et optimisée
# Utiliser un prompt minimal pour charger le modèle rapidement
# Timeout de 120s pour le premier chargement
curl -s --max-time 120 -X POST "$OLLAMA_HOST/api/generate" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$MODEL\", \"prompt\": \"ok\", \"stream\": false, \"options\": {\"num_predict\": 5}}" \
    > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "Modele $MODEL precharge avec succes"
    exit 0
else
    echo "Erreur lors du prechargement du modele $MODEL"
    exit 1
fi
