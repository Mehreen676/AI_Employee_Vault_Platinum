# AI Employee Vault – Platinum Tier Backend API
# HuggingFace Spaces Docker runtime  |  port 7860
#
# This Dockerfile is used when backend_api/ contents are placed at the Space root:
#   Space root/
#     Dockerfile
#     main.py
#     requirements.txt
#
# Build locally:
#   docker build -t vault-api .
#   docker run -p 7860:7860 -e VAULT_ROOT=/app vault-api
#
# Deploy to HF Spaces:
#   Push Dockerfile + main.py + requirements.txt to the Space repo root.

FROM python:3.11-slim

# HF Spaces runs as a non-root user (uid=1000)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy all Space-root files into the image
COPY --chown=appuser:appuser . /app

# Install API dependencies (requirements.txt is now at /app/requirements.txt)
RUN pip install --no-cache-dir -r /app/requirements.txt

# Expose HF Spaces default port
EXPOSE 7860

USER appuser

# VAULT_ROOT = /app (vault/ subdirs don't exist in Space; API returns empty gracefully)
ENV VAULT_ROOT=/app
ENV PORT=7860
ENV ALLOWED_ORIGINS=*

# main:app — module is main.py at /app/main.py (Space root)
CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
