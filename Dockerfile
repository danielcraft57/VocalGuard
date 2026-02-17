FROM python:3.13-slim

# Dépendances système pour l'audio et le modem
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    libasound2-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Créer les dossiers nécessaires
RUN mkdir -p logs audio_cache

# Exposer le port de l'API
EXPOSE 8000

# Commande par défaut
CMD ["python", "-m", "vocalguard.main"]

