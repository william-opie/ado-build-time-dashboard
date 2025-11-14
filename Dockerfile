FROM python:3.12-slim

# Install system deps (optional, but good for SSL/timezone stuff)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# Azure DevOps config passed at runtime:
#   AZDO_ORG
#   AZDO_PROJECT
#   AZDO_PAT

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
