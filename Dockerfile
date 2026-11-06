# ---------- STAGE 1: builder ----------
FROM python:3.12-slim AS builder

# Dipendenze di build (solo per compilar wheels se servisse)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libjpeg-dev zlib1g-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY kindle_dashboard/ ./kindle_dashboard/

# Installa in /install (isolato dal runtime)
RUN pip install --no-cache-dir --prefix=/install -e .


# ---------- STAGE 2: runtime ----------
FROM python:3.12-slim AS runtime

# Solo librerie runtime necessarie a Pillow + tzdata, più font veri: senza TTF Pillow usa il
# font incorporato, che non ha le accentate né "×" e le disegna come quadrati nel pannello.
# `fonts-liberation` è il font del pannello, non un ripiego: `fonts.py` lo mette come primo
# candidato **anche su Windows**, così l'anteprima sul PC misura gli stessi pixel del device (un
# font più stretto, come il Segoe UI Semibold, non regala spazio: nasconde il troncamento).
# `DejaVuSans-Bold` è largo ~1,3 volte e con quello il pannello troncava "REG 12519" e i nomi degli
# eventi; `fonts-dejavu-core` resta come riserva di copertura dei glifi.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g tzdata fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Utente non-root (sicurezza)
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser
WORKDIR /home/appuser

# Copia solo i file installati dal builder
COPY --from=builder /install /usr/local

# Copia sorgenti (sola lettura per l'utente appuser)
COPY --chown=appuser:appuser kindle_dashboard/ ./kindle_dashboard/
COPY --chown=appuser:appuser config.example.toml ./config.example.toml

# Cartelle dati (montate come volumi a runtime)
RUN mkdir -p cache && chown appuser:appuser cache

USER appuser
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/appuser/.local/bin:${PATH}"

# Healthcheck (usato da docker-compose / orchestratori). python:3.12-slim non include wget/curl:
# il controllo usa la stdlib, così non serve aggiungere pacchetti solo per una riga di shell.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/health').status == 200 else 1)"

EXPOSE 8787
ENTRYPOINT ["python", "-m", "kindle_dashboard"]
CMD ["serve"]