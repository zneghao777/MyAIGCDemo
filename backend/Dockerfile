FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY . .
RUN useradd --create-home cineai && chown -R cineai:cineai /app
USER cineai
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
