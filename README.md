# Resume Service

Generic resume tailoring and job application tracker. FastAPI + MongoDB, with
an LLM step (vLLM or local Ollama) that tailors a candidate's resume/cover
letter to a target job description, then renders a PDF.

Endpoints:
- `/users/*` — user resume data CRUD
- `/jobs/*` — LinkedIn job fetch + resume build
- `/applications/*` — application tracking CRUD + stats
- `/health` — liveness check

## Requirements

- Python 3.10+ (for running outside Docker)
- MongoDB (local or Docker)
- An LLM backend: either a vLLM-compatible endpoint, or [Ollama](https://ollama.com)
  running locally
- Docker + Docker Compose (for the containerized path)

## Configuration

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

Key settings:

| Var | Purpose |
|---|---|
| `MONGO_URI`, `MONGO_DB` | MongoDB connection |
| `LLM_PROVIDER` | `vllm` (default) or `ollama` — picks which backend `build_llm()` uses |
| `VLLM_BASE_URL`, `VLLM_API_KEY`, `VLLM_MODEL`, `VLLM_TEMPERATURE` | Used when `LLM_PROVIDER=vllm` |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TEMPERATURE` | Used when `LLM_PROVIDER=ollama` |
| `LINKEDIN_*` | LinkedIn credentials (password or cookie auth) for job fetching |

### Using Ollama

Either install Ollama on the host and pull a model:

```bash
ollama pull qwen2.5:7b
```

...and set in `.env` (for the venv path, `OLLAMA_BASE_URL` stays `localhost`;
for the Docker path this is what `docker-compose.yml` overrides to
`http://ollama:11434` — see below):

```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

...or run Ollama containerized (see **Running with Docker** — no host
install needed, just `docker compose exec ollama ollama pull <model>`).

Note: local CPU-bound models are noticeably slower than a remote vLLM
endpoint for the ~4096-token tailoring generation — expect it to take
significantly longer per resume build.

## Running locally (venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env is not auto-loaded — export it into the shell first
set -a && source .env && set +a

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then check:

```bash
curl http://localhost:8000/health
```

## Running with Docker

The image is built from the **parent directory** (`resumes/`) as build
context, since `resume_builder.py` imports `resume.py` which lives one level
above `resume_service/`.

```bash
docker compose build
docker compose up -d
```

This starts three services:
- `mongo` — MongoDB 7.0, persisted to the `mongo_data` volume, host port `27018`
- `ollama` — Ollama, persisted to the `ollama_data` volume, host port `11435`
- `app` — the FastAPI service, host port `8000`, using `.env` for config

The `app` container reaches both over the compose network regardless of host
port mappings:
- Mongo at `mongodb://mongo:27017` (set in `docker-compose.yml`, overriding
  whatever is in `.env`)
- Ollama at `http://ollama:11434` (same — overrides `.env`)

Host ports are remapped (`27018`, `11435`) to avoid clashing with any other
mongo/ollama already running on your machine — adjust the `ports:` left side
in `docker-compose.yml` if those also collide, or if you'd rather use your
existing host-level Ollama instead of the containerized one (in that case,
remove the `ollama` service and point `OLLAMA_BASE_URL` at
`http://host.docker.internal:11434` with `extra_hosts: ["host.docker.internal:host-gateway"]`
on `app`).

The `ollama` container starts with no models — pull one after first `up`:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

Check it's up:

```bash
curl http://localhost:8000/health
```

Rebuild after code changes:

```bash
docker compose build app
docker compose up -d app
```

## Output

Generated PDFs and cover letters are written to `../output/{username}/`
(relative to `resume_service/`) — mounted as a volume in Docker so they
persist on the host at `resumes/output/`.
