FROM python:3.12-slim

LABEL maintainer="CloudMedVault Security Team - MinTIC 2021 Compliance"
LABEL description="Contenedor de Cómputo y Balanceador Dinámico CloudMedVault"

# Endurecimiento de seguridad del contenedor (usuario no-root según MinTIC 2021)
RUN groupadd -r cloudmed && useradd -r -g cloudmed -m -s /sbin/nologin cloudmed

WORKDIR /srv/cloudmedvault

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
RUN mkdir -p /srv/cloudmedvault/data && chown -R cloudmed:cloudmed /srv/cloudmedvault

USER cloudmed

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.node_service:app", "--host", "0.0.0.0", "--port", "8000"]
