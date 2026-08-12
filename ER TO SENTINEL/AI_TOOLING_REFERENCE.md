# Applied AI Engineering — Tooling Reference

A lookup table for "I have this problem, what do people use?"

> **Read this first.** Written August 2026 against knowledge current to roughly May 2026.
> This ecosystem turns over faster than any other part of software. Treat every entry as a
> *starting point for a search*, not a settled fact. Verify version, maintenance status and
> pricing before you depend on anything. **No prices are listed here on purpose** — they change
> monthly and a stale price table is worse than none. Go to the vendor's pricing page.

Organised by problem, not alphabetically, because you'll arrive here with a problem.

---

## 1. "I need a model to call"

### Frontier APIs (closed weights, best quality)

| Provider | Models | Notes |
|---|---|---|
| **Anthropic** | Claude Opus 5 (`claude-opus-5`), Sonnet 5 (`claude-sonnet-5`), Fable 5 (`claude-fable-5`), Haiku 4.5 (`claude-haiku-4-5-20251001`) | Strong on long-context reasoning, tool use, code. Prompt caching and Batch API both meaningful cost levers |
| **OpenAI** | GPT-series, o-series reasoning models | Largest ecosystem, most third-party integrations assume its API shape |
| **Google** | Gemini Pro / Flash | Flash tier is the cheapest credible frontier-adjacent model; very long context; generous free tier via AI Studio |

**The API shape matters more than the vendor.** OpenAI's request/response format is the de facto
standard — Groq, Together, OpenRouter, vLLM, LM Studio and many others expose it. That means you
can usually swap providers by changing `base_url` and the key. Anthropic and Google use their own
shapes but both publish OpenAI-compatible endpoints or shims.

**Always write a thin provider interface of your own.** Two methods (`complete`, `stream`) over an
enum of providers. It costs an hour and it is the difference between swapping models in a config
change versus a refactor.

### Aggregators / routers

- **OpenRouter** — one key, hundreds of models, automatic fallback. Excellent for experimentation
  and for "route cheap, escalate expensive" without integrating three SDKs.
- **Together AI / Fireworks / Groq** — hosted open-weight models. **Groq** is the notable one:
  custom silicon, extremely low latency, which changes what interactions feel possible.

### Open-weight model families

Llama (Meta), Qwen (Alibaba), Mistral / Mixtral, DeepSeek, Gemma (Google), Phi (Microsoft),
Command (Cohere). Relevant when you need on-prem, data residency, no per-token cost, or
fine-tuning. **Check the licence** — "open weights" is not "open source" and several forbid
commercial use above a user threshold.

### Running models locally

- **Ollama** — simplest path. `ollama run qwen3` and you have an HTTP server on `:11434`.
  Best default for local dev.
- **LM Studio** — GUI equivalent, good for poking at models interactively.
- **llama.cpp** — the engine most of the above sit on. Drop to it for quantisation control.
- **vLLM** — production serving. Continuous batching, high throughput. This is what you'd deploy,
  not Ollama.

On Apple Silicon, an M-series Mac with 16GB+ runs 7–8B models comfortably and 30B+ slowly. Good
enough for development; not for serving users.

---

## 2. "I need the model to use tools / call functions"

**Native tool calling** is built into every frontier API. You describe tools as JSON Schema, the
model returns a structured call, you execute it and pass the result back. Learn this directly from
the provider docs *before* reaching for a framework — the frameworks are wrappers over it and you
will debug them badly if you don't know what's underneath.

**Model Context Protocol (MCP)** — Anthropic-originated open standard, now broadly adopted, for
exposing tools/resources to any MCP-speaking client. One server, many clients (Claude Code, Claude
Desktop, IDEs, your own app). Worth building one; it's a weekend, and it makes your own dev loop
better.

- SDKs: `@modelcontextprotocol/sdk` (TS), `mcp` (Python)
- Claude Code registers servers via `claude mcp add` → `.mcp.json` (project) or `~/.claude.json`
  (user). *Claude Desktop uses a different file, `claude_desktop_config.json` — these get confused
  constantly.*

**Structured output** — when you want typed data, not prose:
- Anthropic/OpenAI/Gemini all support schema-enforced JSON responses. Use them.
- **Instructor** (Python/TS) — Pydantic models in, validated objects out, with automatic retry on
  validation failure. Excellent, small, worth using.
- **Outlines**, **Guidance** — constrained decoding, guarantees grammar conformance at the token
  level. Heavier; relevant for local models that lack native schema support.

**Design rule:** authorization belongs in your tool implementation, not in the prompt. If the model
must not see a row, don't put the row in the context. Instructions are advisory; database
permissions are not.

---

## 3. "I need multi-step / agentic behaviour"

### The honest first step

Write the loop yourself. A `while` loop, a list of tools, a state dict persisted to a table. Most
"agent" behaviour is 100 lines. Do this once so you understand what the frameworks abstract, then
decide whether you want the abstraction.

### Frameworks

| Tool | What it's for | Honest take |
|---|---|---|
| **LangGraph** | Stateful graphs, checkpointing, human-in-the-loop interrupts, resumable runs | The most substantial of these. Checkpointing and interrupt/resume are genuinely hard to hand-roll well |
| **Claude Agent SDK** | Building agents on Anthropic's harness (the one Claude Code uses) | Close to the metal, good if you're Anthropic-centric |
| **Pydantic AI** | Type-safe agents, Pydantic-native | Clean, small, good taste. Nice if you already think in Pydantic |
| **LangChain** | The original catch-all: chains, loaders, integrations | Huge surface area, heavy abstraction, frequent breaking changes. Its *integrations* (document loaders) are often more useful than its core |
| **LlamaIndex** | Document ingestion and retrieval-first pipelines | Strongest where RAG is the whole product |
| **CrewAI / AutoGen** | Multi-agent role-play orchestration | Demo well; multi-agent is usually the wrong answer to a problem one agent plus better tools would solve |

### Durable execution (the underrated category)

When a run takes minutes and must survive a process restart, this is the actual answer:

- **Temporal** — durable workflow execution. Heavyweight, industry-grade, the real solution to
  "don't re-run completed steps."
- **Inngest**, **Trigger.dev** — lighter, developer-friendly, good on serverless hosts.
- **Celery** (Python) / **BullMQ** (Node) — plain job queues. Combined with a status column and
  idempotency keys, this covers most of what you need.

**A state table plus retries with exponential backoff plus idempotency keys solves 80% of agent
reliability**, and none of it is AI-specific. It's ordinary distributed systems work.

---

## 4. "I need the model to know about my documents" (retrieval / RAG)

### Storage

| Option | When |
|---|---|
| **pgvector** (Postgres extension) | Default answer. Relational filters + vector search in one query, one database, one backup story |
| **Qdrant** | Dedicated, open source, self-hostable, excellent filtering |
| **Pinecone** | Managed, zero-ops, scales far |
| **Weaviate**, **Milvus**, **Chroma** | Chroma is fine for prototypes; Milvus for very large scale |
| **SQLite + sqlite-vec** | Embedded, local-first apps |

Hosts with pgvector ready: Supabase, Neon, Render, RDS.

### Embedding models

- APIs: OpenAI `text-embedding-3-*`, Cohere Embed, Voyage AI (strong on code and finance), Gemini
  embeddings
- Local/free: `sentence-transformers` — `all-MiniLM-L6-v2` (fast, small), `bge-*`, `gte-*`,
  `nomic-embed`. Run on CPU in milliseconds, cost nothing
- **Check MTEB leaderboard** for current rankings, but domain fit beats leaderboard position

### The retrieval pipeline, in the order things break

1. **Parsing** — garbage in, garbage out. This is where most RAG projects actually fail.
2. **Chunking** — fixed-size, recursive, semantic, or structural. For documents with real structure
   (filings, contracts, textbooks) **chunk on the structure**, not on token count.
3. **Embedding + storage**
4. **Retrieval** — this is where naive implementations fail
5. **Reranking**
6. **Assembly into the prompt**

### Fixing bad retrieval

- **Hybrid search** — combine keyword (BM25 / Postgres `tsvector`) with vector similarity, fused
  via Reciprocal Rank Fusion. Fixes the classic failure where an exact term ("Q3 budget", a product
  code, a person's name) doesn't land in a semantically similar region.
- **Rerankers** — Cohere Rerank, Voyage Rerank, or a local cross-encoder (`bge-reranker`).
  Retrieve 50, rerank, keep 5. Usually the single highest-return upgrade.
- **Query rewriting / HyDE** — have a cheap model expand or rephrase the query first.
- **Metadata filtering** — often the real fix. If you know the year, filter by year; don't hope
  the embedding encodes it.
- **Contextual retrieval** — prepend a short document-level summary to each chunk before embedding,
  so chunks aren't stranded without context.
- **GraphRAG** — build an entity graph over the corpus. Powerful for multi-hop questions, expensive
  to build. Try everything above first.

**Consider not doing RAG.** If your corpus is small, or has clean structure, or fits in a long
context window, deterministic section selection beats vector search on both accuracy and
debuggability. RAG is a technique for when the corpus exceeds what you can select from directly.

### Document parsing

- **Unstructured.io**, **Docling** (IBM), **LlamaParse** — layout-aware document → structured text
- **PyMuPDF** / `pdfplumber` — fast, programmatic, good when PDFs are clean
- **Marker**, **Nougat** — PDF → markdown, good on academic/technical layout
- **Vision models** — for scans, handwriting, complex tables, screenshotting the page and asking a
  vision model is now often the most accurate option
- Tables are the hard part in every one of these. Test on your worst document first

---

## 5. "I can't tell what my system is doing" (observability)

| Tool | Notes |
|---|---|
| **Langfuse** | Open source, self-hostable, generous cloud tier. Good default |
| **LangSmith** | LangChain's. Excellent if you're in that ecosystem |
| **Arize Phoenix** | Open source, strong on evals + tracing together |
| **Braintrust** | Evals-first, good UI, commercial |
| **Helicone** | Proxy-based — one line to adopt, less granular |
| **OpenLLMetry / OpenTelemetry GenAI** | Vendor-neutral semantic conventions. The standards-based path |

**What to actually record**, whichever you pick: input, output, model, token counts in/out, cost,
latency, and a `trace_id` / `session_id` / `user_id` on every call. Nest spans so multi-step runs
render as a tree.

If you're solo and low-volume, structured JSON logs into a Postgres table plus three SQL queries
(cost per run, p95 latency per step, failure rate by step) teaches you more than a dashboard.
Adopt a real tool when you have volume — or when you want to say the word in an interview.

---

## 6. "How do I know if a change made it worse?" (evals)

The genuinely differentiating skill. Almost nobody does it properly.

### Frameworks

- **Deepeval** — pytest-style, familiar shape
- **Ragas** — RAG-specific: faithfulness, answer relevancy, context precision/recall
- **Promptfoo** — config-driven, very good for side-by-side model/prompt comparison, easy in CI
- **Inspect** (UK AISI) — rigorous, research-grade
- **OpenAI Evals**, **Braintrust**, **Langfuse Datasets** — platform-attached

### What actually matters

**The dataset is 90% of the value, the framework is 10%.** Thirty examples with known-correct
answers, drawn from real usage, beats any framework over synthetic data.

Three kinds of metric:
1. **Deterministic** — exact match, regex, JSON schema validity, numeric tolerance. Cheap, reliable.
   Use these wherever the answer is checkable.
2. **LLM-as-judge** — a model scores the output against a rubric. Use for open-ended text. Pin the
   judge model and version, or your scores drift under you.
3. **Human** — the ground truth the other two approximate. Sample regularly.

**Failure modes to avoid:** judging with the same model that generated the output; letting your
eval set leak into your prompt examples; measuring only averages when the tail is what hurts users;
and building an eval set once and never updating it.

**Run in CI.** A GitHub Action that runs evals on any PR touching prompts, failing below a
threshold, is the concrete artifact that proves you do this.

---

## 7. "Users are waiting" (latency and UX)

- **Streaming** is the answer to perceived latency, always. SSE from the backend, incremental
  render on the frontend. Time-to-first-token is the metric users feel, not total generation time.
  Shrinking the payload does not help — generation time dominates.
- **Vercel AI SDK** — the standard for React/Next.js streaming, including streaming structured
  objects so UI components fill in progressively
- **FastAPI** `StreamingResponse` / **Django** `StreamingHttpResponse` — server side
- **Prompt caching** — cache the stable prefix (system prompt, document, schema). Large cost and
  latency reduction on repeated calls over the same context. *Trap: concurrent requests can't read
  a cache still being written — fire one, wait for first token, then fan out*
- **Speculative / eager UI** — show skeletons, stream partial structure, never a bare spinner
- **Batch APIs** — Anthropic and OpenAI both offer heavily discounted asynchronous batch
  processing. Ideal for overnight jobs where latency is irrelevant

---

## 8. "This is getting expensive"

In rough order of return:
1. **Route by complexity** — cheap model triages, expensive model handles the minority that needs it
2. **Prompt caching** — often the largest single win when context is repeated
3. **Semantic caching** — return a stored answer for a near-identical query (GPTCache, or your own
   with an embedding similarity threshold). Careful: near-identical isn't identical
4. **Batch API** for anything non-interactive
5. **Trim context** — most prompts carry passengers. Measure before you assume
6. **Smaller/local models** for mechanical sub-tasks: classification, extraction, embeddings
7. **Cap spend per user** — a daily token budget per account, enforced server-side

Measure cost per *unit of user value* (per memo, per marked paper, per conversation), not per token.
That's the number that tells you whether the product works.

---

## 9. "Is this safe?" (guardrails and security)

**Prompt injection** is the defining security problem of LLM applications and there is no complete
defence. The mitigations that work are architectural:

- Don't put data in the context that the user must not see. Authorization at the query, not in the
  prompt
- Treat all model output as untrusted input to whatever consumes it next
- Never let model output become a shell command, SQL string or file path without validation
- Least privilege on tools: read-only DB roles, table allowlists, no filesystem or network access
  unless the task needs it
- Human approval gates on irreversible actions (send, pay, delete, publish)
- Assume any content the model reads — a web page, a PDF, a user upload — may contain instructions
  aimed at it

**Tooling:** Llama Guard, NeMo Guardrails, Guardrails AI, Rebuff, Lakera. Useful as defence in
depth. None replace the architectural points above.

**Also:** PII handling and redaction before sending to third-party APIs; data residency and
retention terms (check whether your provider trains on your data — most business tiers don't);
the EU AI Act if you serve EU users; and sector rules — in UK finance, anything that reads as a
personal recommendation engages FCA rules regardless of whether a model wrote it.

---

## 10. "I need to train something"

Usually you don't. Ordered by cost, try: better prompt → few-shot examples → better retrieval →
fine-tune. Most "we need to fine-tune" turns out to be a retrieval problem.

When you genuinely do:
- **Unsloth**, **Axolotl**, **LLaMA-Factory** — practical LoRA/QLoRA fine-tuning
- **Hugging Face TRL / PEFT** — the underlying libraries
- **Together / Fireworks / Predibase / OpenAI fine-tuning** — managed, no GPU wrangling
- **Modal**, **RunPod**, **Lambda Labs** — rent GPUs by the minute

Fine-tuning is good at *form* (tone, format, structured output conformance, domain vocabulary) and
bad at *facts* (which is retrieval's job).

---

## 11. "Where does it run"

- **Vercel** — Next.js, edge, excellent streaming support. Function timeouts matter for long AI jobs
- **Render / Railway / Fly.io** — long-running processes, background workers, managed Postgres.
  Better than Vercel for anything that runs for minutes
- **Modal / Beam** — serverless GPU and long-running Python. Purpose-built for AI workloads
- **Cloudflare Workers AI** — edge inference, small models
- **Docker** — non-negotiable for anything with Python ML dependencies
- **Supabase / Neon** — Postgres with pgvector, generous free tiers

Secrets: `.env` locally (gitignored), `.env.example` committed, platform environment variables in
production. Never a `.env` in the image or the repo. For anything with a team or real stakes:
Doppler, Infisical, or your cloud's secret manager. Rotate anything that has ever touched a
terminal you shared.

---

## 12. Development tooling

- **Claude Code** — CLI/IDE agent, multi-file edits, MCP support, hooks, subagents
- **Cursor**, **Windsurf** — AI-native editors
- **GitHub Copilot** — inline completion plus agent mode
- **Aider** — open source, git-native CLI pair programmer
- **Continue** — open source IDE extension, bring your own model

For prompt work: **Promptfoo** for comparison, **LangSmith/Langfuse** for versioning and playground,
or plain files in git — prompts are source code and belong under version control with everything else.

---

## 13. Staying current

- **Papers:** arXiv cs.CL and cs.AI; Hugging Face Daily Papers for the filtered version
- **Engineering blogs:** Anthropic, OpenAI, Google DeepMind, plus Langfuse / LangChain / LlamaIndex
  for practitioner material
- **Model rankings:** LMArena, MTEB (embeddings), SWE-bench (code), Artificial Analysis (cost/latency)
- **Community:** r/LocalLLaMA is the best single source on open models

Read for **patterns**, not tools. The tool names in this document will churn; hybrid retrieval,
checkpointed state, judge-based evaluation and least-privilege tool design will not.

---

## Appendix — problem → first thing to try

| Problem | Start here |
|---|---|
| Retrieval returns irrelevant chunks | Hybrid search, then a reranker |
| Retrieval misses exact terms/numbers | Keyword search or metadata filter, not embeddings |
| Model invents facts | Ground it: pass source text, require citations, forbid uncited claims |
| Model does arithmetic wrong | Don't let it. Compute in code, pass the result in |
| Agent loops forever | Hard step cap, and a state machine instead of a free loop |
| Agent fails mid-run and redoes everything | Persisted per-step state, idempotency keys, resume from checkpoint |
| Users complain it's slow | Stream. Measure time-to-first-token, not total time |
| Costs spiked | Route by complexity, cache the prefix, cap per user |
| "Did my prompt change help?" | You need an eval set. There is no shortcut |
| Can't reproduce a user's bad output | You need tracing with session IDs. Also no shortcut |
| Users extracting things they shouldn't | Remove it from the context. Don't instruct the model to withhold it |
| Output format keeps breaking | Schema-enforced structured output, plus a retry on validation failure |
