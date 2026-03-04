# AI Employee Vault – Platinum Tier Backend API
# HuggingFace Spaces Docker runtime  |  port 7860
#
# Build locally:
#   docker build -t vault-api .
#   docker run -p 7860:7860 -e VAULT_ROOT=/app vault-api
#
# Deploy to HF Spaces:
#   1. Create a Space (Docker SDK) at huggingface.co/spaces
#   2. Push this Dockerfile + all repo files to the Space repo
#   3. Set Secrets: ALLOWED_ORIGINS, VAULT_ROOT (optional)

FROM python:3.11-slim

# HF Spaces runs as a non-root user (uid=1000)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy the entire repo into the image
COPY --chown=appuser:appuser . /app

# Install API dependencies
RUN pip install --no-cache-dir -r /app/backend_api/requirements.txt

# Expose HF Spaces default port
EXPOSE 7860

USER appuser

# VAULT_ROOT points to the repo root inside the container
ENV VAULT_ROOT=/app
ENV PORT=7860
ENV ALLOWED_ORIGINS=*

CMD ["python", "-m", "uvicorn", "backend_api.main:app", \
     "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
