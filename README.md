<div align="center">

# DubMaster
### A Training-Free Multi-Agent Framework for Collaborative Audio Generation

[![Live Demo](https://img.shields.io/badge/Live%20Demo-dubmaster.fly.dev-6366f1?style=for-the-badge&logo=fly&logoColor=white)](https://dubmaster.fly.dev)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Node](https://img.shields.io/badge/Node-20-339933?style=for-the-badge&logo=node.js&logoColor=white)](https://nodejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)

</div>

---

DubMaster takes a video, image, or text prompt and produces a fully layered audio track — speech, sound effects, music, and atmosphere — without any fine-tuning or task-specific training. Everything runs through a multi-agent pipeline where specialized agents plan, route, generate, critique, and mix independently.

---

## How it works

The pipeline has four stages. Each one is handled by a dedicated agent:

**Stage 1 — Planning.** A multimodal LLM reads the input (video frames, images, text) and decomposes it into a structured list of audio events, each with a type, timeline position, semantic description, and volume. The user's chosen output category acts as a hard filter.

**Stage 2 — Expert routing.** Each event is handed to a domain expert. The SFX expert can do a video-conditioned pass with MMAudio and lets the LLM decide whether the result is worth keeping. The Speech expert extracts utterance text and speaker style. The Music expert writes a concise style prompt. The Song expert synthesizes an LRC lyric file from scratch.

**Stage 3 — Tree-of-Thought synthesis with Memory-Tree correction.** For each event, the system runs one or more generation attempts, scores each on three dimensions (alignment, quality, aesthetics) using a multimodal critic LLM, and rewrites the prompt when scores fall short. A memory tree tracks every attempt across all candidate models — when the system moves to the next model, it preloads the failure history so the first attempt is already informed by everything that went wrong before.

**Stage 4 — Mix.** All generated audio is placed on a shared timeline, volume-adjusted per event, and mixed down. If a source video was provided, the result is muxed back in.

---

## Memory-Tree scoring

The critic evaluates each generation on three dimensions with fixed weights:

| Dimension | Weight | What it measures |
|---|---|---|
| Alignment | **50%** | Does the audio match the event's timing and description? |
| Quality | **35%** | Acoustic clarity and fidelity |
| Aesthetics | **15%** | Style fit with the scene |

Early stop fires when alignment ≥ 0.7, quality ≥ 0.6, and aesthetics ≥ 0.6. If a model's score stops improving between attempts, it is abandoned and the next candidate inherits the full suggestion history.

---

## Models

| Audio type | Model | Inference |
|---|---|---|
| Sound Effects | MMAudio (video-conditioned → text fallback) | HF ZeroGPU |
| Speech / TTS | CosyVoice3 → CosyVoice2 → FireRed | HF ZeroGPU |
| Music | InspireMusic-1.5B-Long | HF ZeroGPU |
| Song | DiffRhythm + LRC synthesis | HF ZeroGPU |
| Planning & refinement | Kimi K2.5 | OpenAI-compat API |
| Audio scoring | Qwen3-Omni-Flash | DashScope API |

No local GPU required. All model inference runs on HuggingFace Gradio Spaces.

---

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | Vite · React 18 · TypeScript · Tailwind CSS |
| Backend | FastAPI · SQLite · Uvicorn |
| Pipeline | Python 3.11 · pydub · moviepy · ffmpeg |
| LLM adapters | OpenAI-compat · Google Gemini · NVIDIA · HuggingFace · Gradio |
| Deployment | Fly.io · Docker multi-stage build · persistent volume |

---

## Project layout

```
.
├── agents.py               DubMasterSystem — top-level orchestrator
├── plan.py                 AudioEvent / Plan dataclasses
├── experts.py              SFX / Speech / Music / Song domain experts
├── critiquers.py           Planning / Domain / AudioEval critics
├── tot.py                  Tree-of-Thought executor
├── tree_memory.py          TreeMemory, NodeRecord, cross-model context
├── mixer.py                final mix + video mux
├── llm.py                  LLM adapters
├── router.py               load_llm() — config.yaml → adapter
├── tools_v2.py             ToolLibrary registry
├── tool/                   Gradio Space adapters (one file per model)
├── utils/                  media probing, HF uploader, logger
├── template/               config_template.yaml
├── backend/
│   └── app/
│       ├── main.py         FastAPI app, static file serving
│       ├── schemas.py      Pydantic models
│       ├── routes/
│       │   ├── generations.py
│       │   └── upload.py
│       └── services/
│           ├── generation_service.py
│           └── storage.py
├── src/                    React + TypeScript frontend
│   ├── components/         HomeView, Workspace, ProcessingView, HistoryView …
│   ├── services/api.ts     fetch wrappers for every backend endpoint
│   └── types.ts            shared TypeScript types
├── public/demos/           demo MP4 files
├── Dockerfile              multi-stage: Node → Python → runtime
└── fly.toml                Fly.io config
```

---

## Local setup

**Prerequisites:** Node 20+, Python 3.11+, a HuggingFace account (Pro recommended), a Kimi API key or any OpenAI-compatible endpoint.

```bash
git clone https://github.com/Simon-leong/DubMaster.git
cd DubMaster

npm install
pip install -r requirements.txt -r backend/requirements.txt
```

Copy the config template and fill in your keys:

```bash
cp template/config_template.yaml config.yaml
```

```yaml
# config.yaml — minimum required fields
basic:
  hf_token: "hf_..."

llms:
  kimi:
    api_key: "..."

  qwen-omni-critic:
    api_key: "..."        # leave blank to fall back to neutral scores
```

Create `.env.local` for the frontend:

```bash
echo 'VITE_API_BASE_URL="http://localhost:8000"' > .env.local
```

Start both processes:

```bash
npm run dev:backend    # FastAPI on :8000
npm run dev:frontend   # Vite on :3000
```

---

## Deployment

The repo ships a multi-stage `Dockerfile` and `fly.toml`. The compiled frontend is served as static files by the same FastAPI process — no separate CDN setup needed.

```bash
# first time
fly launch --name dubmaster --region sin

fly secrets set KIMI_API_KEY=...
fly secrets set HF_TOKEN=...
fly secrets set DASHSCOPE_API_KEY=...

fly deploy
```

After that, deploying an update is just:

```bash
git pull origin main && fly deploy
```

Rotating a key restarts the machine automatically — no redeploy needed:

```bash
fly secrets set KIMI_API_KEY=new_value
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload/video` | Upload source video → `ref` |
| `POST` | `/upload/image` | Upload source image → `ref` |
| `POST` | `/upload/reference-audio` | Upload reference audio for voice cloning |
| `POST` | `/generations` | Start a generation job |
| `GET` | `/generations/{id}/status` | Poll stage + stageDetail + status |
| `GET` | `/generations/{id}` | Full job detail + artifact |
| `GET` | `/generations` | All completed artifacts |
| `POST` | `/generations/{id}/export` | Get a download URL |
| `GET` | `/generations/{id}/export/download` | Download final file |
| `GET` | `/generations/{id}/preview` | Stream for in-browser playback |

Job status: `pending` → `processing` → `completed` / `failed`

Pipeline stage: `uploading` → `planning` → `assigning` → `synthesizing` → `mixing` → `done`

---

## Limitations

- **ZeroGPU quota** — free HF tokens have a daily GPU budget. One generation can burn through it fast. Use a Pro token for anything beyond quick tests.
- **Single worker** — the backend runs `--workers 1` to avoid SQLite write conflicts. Works fine for demos; would need a proper database before going multi-tenant.
- **Multimodal critic** — the audio scoring step requires Qwen3-Omni or another multimodal model. Text-only LLMs return null scores; the ToT loop still picks the best wav available, just without scored guidance.

