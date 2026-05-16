# Project 4 — LLM Gateway

**Status:** In Progress

## Overview

A self-hosted LLM gateway built on FastAPI and LiteLLM, providing a unified OpenAI-compatible API endpoint that proxies requests to local and cloud-hosted models. Redis is used for caching and rate-limiting.

## Stack

| Component | Role |
|-----------|------|
| FastAPI | API server |
| LiteLLM | Model proxy / unified interface |
| Redis | Response caching, rate limiting |
| Ollama | Local LLM inference (Proxmox VM) |

## Endpoints

| Service | URL |
|---------|-----|
| Proxmox Ollama | http://&lt;homelab-ollama-host&gt;:11434 |

## Layout

```
04-llm-gateway/
├── Chart.yaml          # Helm chart metadata
├── values.yaml         # Default values
├── values-aks.yaml     # AKS overrides
├── templates/          # Helm templates (to be added)
└── app/
    ├── main.py         # FastAPI entrypoint
    ├── Dockerfile
    ├── routers/        # Route modules
    └── middleware/     # Middleware modules
```

## Local Development

```bash
cd app
pip install fastapi uvicorn litellm redis
uvicorn main:app --reload
```

## Helm

```bash
helm lint 04-llm-gateway/
helm install llm-gateway 04-llm-gateway/ -f 04-llm-gateway/values-aks.yaml
```
