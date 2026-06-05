# Research: Runtime Foundation for Argus (Llama 4 in Docker)

Research artifact for SPEC-INFRA-001. Resolves the open decisions enumerated in
`CONCEPT.md` and `tech.md` that block the runtime foundation: model runtime,
Llama 4 variant, hardware floor, persistence strategy, and basic API contract.

This document is a verification surface. Read it, correct any misunderstandings,
then proceed to SPEC creation.

---

## 1. Llama 4 Variants — What's Actually Runnable

Meta released three Llama 4 variants (April 2025): Scout, Maverick, Behemoth.
All three are Mixture-of-Experts (MoE) — only a subset of experts activate per
token, but **all experts must be resident in memory** during inference.

| Variant | Total / Active | Q4 Footprint | Realistic Host |
|---|---|---|---|
| **Scout** | 109B / 17B | ~32–67 GB (depending on GGUF flavor) | M-series Mac with 64 GB+ unified memory; or 64 GB system RAM + 24 GB VRAM GPU with offload |
| **Maverick** | 400B / 17B | ~48 GB+ VRAM at Q4 | RTX 5090 (32 GB) at Q4, or multi-GPU; **out of reach for personal hardware** |
| **Behemoth** | ~288B / ~2T | N/A | Server-class only; **rejected** |

### Decision: Llama 4 Scout is the only Llama 4 variant that fits the audience

Maverick at Q4 needs an RTX 5090-class card (~$2K USD just for the GPU);
Behemoth is data-center territory. Scout is the only variant where a serious-
but-attainable personal workstation can host the runtime. The SPEC will
**target Scout** as the primary model and treat smaller Llama 3.x models as an
opt-in fallback for users with constrained hardware.

### Variant constraints to encode in the SPEC

- Memory floor is dominated by Q4 GGUF size (`~32–67 GB` for Scout).
- Unified-memory Macs are first-class targets — they avoid the GPU/system-RAM
  split that haunts x86 deployments.
- The MoE architecture means inference speed is closer to a dense 17B than to
  a 109B model. Real-world reports: ~20 tokens/s on a 24 GB VRAM card with
  Unsloth 1.78-bit quantization.

---

## 2. Model Runtime — Three Real Candidates, One Rejection

### Ollama
- **API**: Native HTTP REST API on `127.0.0.1:11434`, with an OpenAI-compatible
  surface (`/v1/chat/completions`, streaming via SSE).
- **Llama 4 support**: First-class. `ollama run llama4:scout` is one command.
  Tags include multiple quantization levels.
- **Quantization defaults**: Default `llama4:scout` is ~67 GB Q4. Smaller
  community builds (Unsloth dynamic GGUFs) reduce this to ~32 GB.
- **Docker**: Official `ollama/ollama` image.
- **Strength**: Lowest friction. The "single command and it just works"
  experience matches the privacy-individual audience.
- **Weakness**: Less control over quantization layer-by-layer. Ollama owns the
  model store, which adds a layer between the user and raw weights.

### llama.cpp server
- **API**: HTTP server (`llama-server` binary). OpenAI-compatible endpoints.
- **Llama 4 support**: Native via GGUF format.
- **Quantization**: Maximum flexibility — Unsloth dynamic quants, k-quants,
  every variant. Best memory efficiency for any given quality target.
- **Docker**: `ghcr.io/ggml-org/llama.cpp:server-*` images exist.
- **Strength**: Maximum control, smallest possible memory footprint, no
  intermediate model store.
- **Weakness**: More configuration per model. Users have to know which GGUF
  file to download.

### vLLM — REJECTED for Argus
- Production GPU-serving framework. Optimized for H100/A100 multi-GPU.
- Tensor parallelism, FP8 inference, expert parallelism are powerful but
  irrelevant on personal hardware.
- A single H100 costs more than a typical Argus user's entire computer.
- **Reject for the on-device audience.** Revisit only if Argus pivots to
  enterprise/air-gapped deployment.

### Decision: Default runtime is Ollama; SPEC includes an llama.cpp escape hatch

Ollama is the right default for the audience. But a "power user" subset will
want llama.cpp's flexibility. The SPEC will:

1. Ship Ollama as the default `model` service in `docker-compose.yml`.
2. Document an alternative `compose.llamacpp.yml` overlay or `--profile` for
   llama.cpp users.
3. Define the API contract at the **Argus API layer**, not at the model
   runtime layer, so swapping runtimes is a configuration change, not a code
   rewrite.

---

## 3. Hardware Floor — The Constraint That Shapes Everything

This is the most important number to publish. Underselling the requirement
will burn users; overselling will exclude viable hardware.

### Recommended minimum (Llama 4 Scout, Q4 baseline)

- **Apple Silicon**: M2/M3/M4 Pro or Max with **64 GB unified memory**.
  Mac Studio M2 Ultra (192 GB) is ideal.
- **Linux/Windows x86**: **64 GB system RAM** + a discrete GPU with **24 GB
  VRAM** (RTX 3090, 4090, 5090, A6000). CPU offload via llama.cpp/Ollama is
  required at this floor.

### Hard floor (below this, Argus will not run Scout acceptably)

- 32 GB unified memory or 32 GB system RAM with 12 GB VRAM. At this level,
  the user is restricted to heavy quantization (1.78-bit Unsloth GGUFs) with
  slow tokens/sec. The SPEC will surface a clear "your hardware is below the
  recommended floor" warning rather than silently degrade.

### Fallback hardware path (smaller models)

For users below the 64 GB floor, the runtime SHALL support pointing Ollama
or llama.cpp at smaller models (Llama 3.2 1B/3B/8B). This preserves the
on-device promise even when Llama 4 isn't viable. The default product
experience targets Scout; smaller models are a documented downgrade.

---

## 4. Persistence — Where Weights and Caches Live

Model weights are large (32–67 GB for Scout). Re-downloading on container
recreate is unacceptable.

### Plan

- One named Docker volume per model runtime:
  - `argus_ollama_models` mounted at `/root/.ollama` in the Ollama container
  - `argus_llamacpp_models` mounted at the llama.cpp `MODELS_PATH` (in the
    optional overlay)
- Volume survives `docker-compose down`. Only removed by explicit
  `docker volume rm` or by passing `down --volumes`.
- The `run_server.sh` first-run path SHALL pull Llama 4 Scout via the
  runtime's standard mechanism (`ollama pull llama4:scout`) and complete only
  after the model is resident. Subsequent runs skip the pull.

### Out of scope for this SPEC

- Chat history persistence. v1 has no chat persistence (`product.md`
  non-goal). Future SPECs can add a separate `argus_data` volume for chat
  history.
- Encrypted-at-rest model weights. Defer — for v1 the host disk encryption
  (FileVault, LUKS, BitLocker) is the user's responsibility.

---

## 5. API Contract — What the Backend Exposes

The Argus API sits in front of the model runtime. This indirection lets us
swap runtimes (Ollama ↔ llama.cpp) without breaking the React UI.

### Endpoints (v1 minimum)

- `GET /health` — `200 {"status": "ready"}` when the model is loaded;
  `503 {"status": "loading", "progress": ...}` during cold start.
- `POST /v1/chat/completions` — OpenAI-compatible streaming. SSE format
  (`data: {...}\n\n`) because:
  - The React UI is going to consume it via `EventSource` or `fetch` with
    a stream parser — both work cleanly with SSE.
  - Ollama and llama.cpp both already speak this format natively.
  - SSE is one-way (server → client), which matches chat streaming. WebSocket
    isn't necessary until we have agent tool callbacks.
- `GET /v1/models` — list models known to the configured runtime.

### Network surface — locked to localhost

- The FastAPI server SHALL bind to `127.0.0.1` only.
- The Docker host port mapping SHALL use `127.0.0.1:PORT:PORT`, not
  `0.0.0.0:PORT:PORT`. This is the single biggest defense against accidental
  LAN exposure.
- Any request received with a non-localhost `Origin` or `Host` header SHALL
  be rejected `403`. This protects against DNS rebinding and misconfigured
  reverse proxies even if the localhost bind is bypassed.

### Out of scope for v1

- Auth tokens. Localhost bind + non-localhost rejection is the v1 threat
  model. Bearer tokens come in a follow-up SPEC if multi-user or remote
  desktop scenarios are added.
- Rate limiting. Single-user, single-device — no realistic abuse vector.

---

## 6. docker-compose Topology

### Services (minimum)

1. **`model`** — Ollama by default (or llama.cpp via overlay). Pulls and
   serves Llama 4 Scout. Bound to internal network only.
2. **`api`** — Argus FastAPI backend. Talks to `model` over the internal
   Docker network. Bound to `127.0.0.1` on the host.

The React UI is **NOT** part of this SPEC. It will be a third service
(`web`) added in the follow-up SPEC. For v1, the API can be hit directly via
`curl` or any HTTP client — that's the demo-able state at the end of this
SPEC.

### Why two services, not one

- Separation of concerns: API restart should not require model reload.
- Future-proof: agent tool services (file I/O sandbox, retrieval) become
  additional containers later.
- Clear failure boundary: a crash in the API doesn't take down the model.

### Entry scripts

- `run_server.sh`: `docker compose up -d`, then poll `/health` until ready.
- `run_debug.sh`: `docker compose up` (foreground, no `-d`), with
  `OLLAMA_DEBUG=1` or equivalent env vars exported. Streams logs to stdout.
- Both must be idempotent: re-running them on an already-running stack must
  be a no-op (or a graceful restart with `--force-recreate` flag).

---

## 7. Risks and Open Questions Captured

### Hard risks

1. **Hardware floor excludes users.** Privacy-individual audience may
   include hobbyists on 16 GB laptops. Mitigation: surface the floor
   prominently in product.md, support smaller-model fallback path.
2. **Model download UX on first run.** 32–67 GB pull is a long-running
   operation. Mitigation: `run_server.sh` MUST show progress and survive
   interruption (Ollama handles resume natively).
3. **Architecture lock-in if API contract is loose.** If the API just
   forwards to Ollama, swapping runtimes will break things. Mitigation:
   define the API contract explicitly in this SPEC (Section 5), implement
   a thin adapter in `api/inference.py`.

### Open questions resolved by this SPEC

- ✅ Model runtime: Ollama default, llama.cpp escape hatch
- ✅ Llama 4 variant: Scout
- ✅ Hardware floor: 64 GB unified memory or 64 GB RAM + 24 GB VRAM
- ✅ Persistence: named Docker volume for model weights
- ✅ Auth model (partial): localhost bind + non-localhost-rejection. Full
  bearer token deferred.

### Open questions deferred past this SPEC

- React framework wrapper (Vite vs Next.js) — belongs to the UI SPEC.
- Streaming transport on the UI side — backend uses SSE; UI SPEC decides how
  React consumes it.
- Smaller-model fallback UX (how users opt into Llama 3.2 instead of Llama 4
  Scout) — captured as a follow-up enhancement, not v1.

---

## Sources

- [Llama 4 Guide: Running Scout and Maverick Locally (InsiderLLM)](https://insiderllm.com/guides/llama-4-guide-scout-maverick/)
- [Run Llama 4 Scout Locally: 24GB VRAM, GGUF, Real Speeds (Botmonster)](https://botmonster.com/ai/how-to-run-llama-4-on-consumer-gpus-2026/)
- [Llama 4 GPU System Requirements (Scout, Maverick, Behemoth) — APXML](https://apxml.com/posts/llama-4-system-requirements)
- [Deploy Llama 4 with vLLM: Scout vs Maverick Setup Guide (PremAI)](https://blog.premai.io/eploy-llama-4-with-vllm-scout-vs-maverick-setup-guide-2026/)
- [Llama 4 Scout on MLX: The Apple Silicon Guide (SitePoint)](https://www.sitepoint.com/llama-4-scout-on-mlx-the-complete-apple-silicon-guide-2026/)
- [llama.cpp VRAM Requirements: Complete 2026 Guide (LocalLLM.in)](https://localllm.in/blog/llamacpp-vram-requirements-for-local-llms)
