FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY . /app
RUN mkdir -p /app/data /app/credentials && groupadd --system radar && useradd --system --gid radar --home-dir /app radar && chown -R radar:radar /app/data /app/credentials /app/site
USER radar
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)); assert d['status']=='ok'"
CMD ["python", "worker.py", "serve"]
