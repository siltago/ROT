FROM python:3.11-slim

WORKDIR /app

# Install the project itself plus its declared runtime dependencies
# (pyproject.toml) -- no extra system packages needed, piper-tts ships
# what it needs via wheels.
COPY pyproject.toml ./
COPY app ./app
COPY brain ./brain
COPY personality ./personality
COPY emotions ./emotions
COPY memory ./memory
COPY perception ./perception
COPY actions ./actions
COPY hardware ./hardware
COPY integrations ./integrations
COPY api ./api
COPY data ./data

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
