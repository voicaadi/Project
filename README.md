# ADRI AI

**An AI-powered DevOps assistant for managing development environments, containers, and infrastructure workflows.**

ADRI AI combines a web application, an API, a PostgreSQL database, and a local agent to provide a central interface for DevOps tasks.

- **Live application:** https://devopsadi.com
- **Source code:** https://github.com/voicaadi/Project

## Overview

ADRI AI is designed to bring common DevOps workflows into one place. The web interface communicates with a FastAPI backend. The backend manages application data, authentication, AI requests, and communication with paired local agents.

A local agent connects to the backend over a secure WebSocket connection. This allows the application to interact with the user's own environment rather than requiring every operation to run on the hosted server.

## Features

- AI assistance powered by Google Gemini
- User authentication using JWT
- Device pairing and authenticated local-agent communication
- Docker container information and operations
- Ubuntu-based Docker workspaces
- Workspace terminal and command execution
- PostgreSQL-backed application data
- React web interface
- Kubernetes deployment manifests
- Container image publishing through GitHub Container Registry
- GitHub Actions CI/CD workflow

> Available operations depend on the user's permissions, the connected agent, and the local Docker environment.

## Architecture

```text
                    User
                     |
                     v
              React + Vite UI
                     |
                     v
              FastAPI Backend
                /    |     \
               /     |      \
              v      v       v
         PostgreSQL Gemini  WebSocket
                              |
                              v
                         Local Agent
                              |
                              v
                         Docker Engine
                              |
                              v
                       Ubuntu Workspaces

Deployment and delivery:
GitHub Actions -> GHCR -> Kubernetes
                         |
                         v
                   Cloudflare Tunnel
```

## Technology Stack

| Area | Technology |
|---|---|
| Frontend | React, Vite, JavaScript |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| AI | Google Gemini |
| Authentication | JWT |
| Agent communication | WebSockets / WSS |
| Containers | Docker |
| Orchestration | Kubernetes |
| Web server | Nginx |
| Container registry | GitHub Container Registry |
| CI/CD | GitHub Actions |
| External access | Cloudflare Tunnel |

## Repository Structure

```text
.
├── agent/                  # Production local agent
├── agent-staging/          # Staging local agent
├── backend/                # FastAPI application and tests
├── frontend/               # React application and Nginx configuration
├── docker/
│   └── workspace/          # Ubuntu workspace image
├── k8s/                    # Kubernetes manifests
│   └── staging/
├── backups/                # Local backups; not for Git
├── docker-compose.yml      # Local development services
├── .env.example            # Environment-variable template
└── README.md
```

Local-only folders and credentials may not appear in the Git repository because they are excluded by `.gitignore`.

## Getting Started

### Prerequisites

- Git
- Python 3.12 or later
- Node.js and npm
- Docker Desktop or Docker Engine
- A Google Gemini API key

### 1. Clone the repository

```bash
git clone https://github.com/voicaadi/Project.git
cd Project
```

### 2. Configure environment variables

Create a local environment file:

```bash
cp .env.example .env
```

Edit `.env` and provide the required values. The example below shows variable names; use your own credentials.

```dotenv
JWT_SECRET_KEY=replace_with_a_long_random_secret
GOOGLE_API_KEY=your_google_api_key
POSTGRES_USER=devops_user
POSTGRES_PASSWORD=your_database_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=devops_ai
```

Other integrations may require additional variables documented in `.env.example`.

**Never commit `.env`, API keys, passwords, device tokens, or private certificates.**

### 3. Start PostgreSQL

From the repository root:

```bash
docker compose up -d postgres
docker compose ps
```

The Compose configuration uses a persistent Docker volume for PostgreSQL data. Do not remove that volume when troubleshooting unless you intentionally want to delete the database.

### 4. Start the backend

Open a terminal:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment.

Linux, macOS, or WSL:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health endpoint: `http://localhost:8000/health`

### 5. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`.

## Local Agent

The local agent runs on a machine where Docker operations or workspace execution are required. It connects to the backend using an authenticated secure WebSocket connection.

Production agent files are in `agent/`. Staging agent files and configuration are kept separately in `agent-staging/`.

### Agent configuration

Use the corresponding example environment file as a reference. Typical settings include:

```dotenv
DEVOPS_BACKEND_WS=wss://your-domain.example/api/devices/agent/connect
DEVOPS_AGENT_TOKEN=your_paired_device_token
DEVOPS_HEARTBEAT_SECONDS=25
```

Pair the device through the ADRI AI application and configure the token locally. Do not commit or share the token.

### Start on Linux, macOS, or WSL

From the repository root:

```bash
cd agent
chmod +x start-unix.sh
./start-unix.sh
```

### Start on Windows PowerShell

From the repository root:

```powershell
cd agent
Set-ExecutionPolicy -Scope Process Bypass -Force
.\start-windows.ps1
```

Use the staging agent and its separate credentials when testing staging. Do not mix production and staging tokens or configuration.

**Security note:** The local agent can perform operations on the machine where it runs. Only pair trusted devices, protect the device token, and review commands before execution.

## Docker Workspaces

The Ubuntu workspace image is defined in `docker/workspace/Dockerfile`.

The backend manages workspace operations through Docker. Workspace files live in the workspace container or its configured storage, while workspace metadata is stored by the application.

Docker must be available to the local agent for local Docker operations. The agent's operating-system user must have the required Docker permissions.

## Kubernetes

Kubernetes manifests are maintained in `k8s/`. Staging manifests are stored under `k8s/staging/`.

The Cloudflare Tunnel manifest is `k8s/cloudflared.yaml`.

**Deployment caution:** Inspect the namespace, image tags, referenced Kubernetes Secrets, and current cluster context before applying any manifest. The Cloudflare Tunnel manifest targets the production namespace. Do not apply staging resources to production or production resources to staging.

Example inspection commands:

```bash
kubectl config current-context
kubectl get namespaces
kubectl get deployments -A
kubectl get pods -A
```

## Tests and Build

Run the backend tests:

```bash
cd backend
python -m pytest tests/ -q
```

Run the production agent tests:

```bash
cd agent
python -m pytest -q
```

Run the staging agent tests:

```bash
cd agent-staging
python -m pytest -q
```

Build the frontend:

```bash
cd frontend
npm install
npm run build
```

Run each command from its corresponding project directory.

## CI/CD

The repository uses GitHub Actions for automated checks and delivery.

The workflow includes backend tests, agent tests, and a frontend build. The deployment workflow publishes container images to GitHub Container Registry and uses a self-hosted runner for Kubernetes deployment. Production deployment is protected by a GitHub environment approval step.

Review the workflow files under `.github/workflows/` for the current triggers, jobs, and deployment configuration.

## Security

- Keep `.env` and all credentials out of version control.
- Use separate credentials for production and staging.
- Protect local-agent device tokens.
- Use authenticated secure WebSocket connections.
- Restrict access to the Docker socket and local agent.
- Protect PostgreSQL data and backups.
- Review Kubernetes contexts and namespaces before deployment.
- Do not expose internal services or database ports publicly unless required and secured.

## Project Goals

ADRI AI aims to make common DevOps tasks easier to access through a single interface while keeping execution close to the user's own environment through a paired local agent.

The project brings together AI assistance, container management, workspaces, terminal access, and automated delivery workflows.

## Links

- **Live application:** https://devopsadi.com
- **GitHub repository:** https://github.com/voicaadi/Project
