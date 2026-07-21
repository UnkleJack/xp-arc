# Evolutionary Asset Generation Engine — SPEC.md

**Project**: XP-Arc Asset Engine (codename: **WYRM**)  
**Owner**: DRAGON / [PERSON_NAME]  
**Status**: Specification Phase — awaiting approval to implement  
**Repo**: `~/xp-arc` (subdirectory `asset-engine/`)  
**Target**: GitHub Actions cron (2×/day + manual dispatch) → zo.computer / exe.dev for heavy lifting

---

## 1. Vision & North Star

Build an **evolutionary asset generation engine** that:

1. **Generates** printable assets (coloring pages, tarot cards, planners, activity books) via multi-engine prompts
2. **Curates** via human-in-the-loop review (local folder + Google Drive sync)
3. **Evolves** styles through iterative feedback → "hyper-tuned style engines" (Simpsons/American Dad-level consistency)
4. **Replicates** proven engines via git-branched configs + prompt genomes
5. **Graduates** to Unity asset prototypes (textures, sprites, UI kits) for game dev portfolio

**North Star**: "Simpsons-style consistency" — look at any output and instantly recognize the style lineage.

---

## 2. Asset Categories & Output Specs

| Category | Primary Format | Secondary | Specs |
|----------|---------------|-----------|-------|
| **Coloring Pages** | SVG (vector line art) | PNG 300 DPI | Clean closed paths, no fills, 8.5×11" or A4 |
| **Tarot/Oracle Cards** | PNG 300 DPI | PDF (deck assembly) | 2.75×4.75" + 0.125" bleed, CMYK-aware palette |
| **Planners/Journals** | PDF (print-ready) | InDesign/Canva template | 300 DPI, CMYK, 0.125" bleed, 0.5" margins |
| **Activity Books** | PDF (multi-page) | PNG per page | 300 DPI, mixed line art + graphics |
| **Unity Prototypes** | PNG/PSD layers | FBX/glTF | PBR textures, sprite sheets, UI atlases |

**Naming convention**: `{style_engine}/{category}/{theme}_{variant}_v{version}.{ext}`  
Example: `simpsons-horror/coloring/bart-nightmare_v3.svg`

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GITHUB ACTIONS (CRON)                        │
│  • 2×/day scheduled  • manual workflow_dispatch  • artifact upload  │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│  PROMPT ENGINE │        │  STYLE REGISTRY │       │  ASSET STORE  │
│  (sub-agent)   │◄──────►│  (git configs)  │        │  (local + GDrive)│
└───────┬───────┘        └───────┬───────┘        └───────┬───────┘
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│ BROWSER AGENT │        │  API AGENT    │        │  REVIEW UI    │
│ (Playwright)  │        │ (OpenRouter,  │        │  (Obsidian/   │
│ ChatGPT,      │        │  Fal, Replicate,│       │   Local Web)  │
│ [PERSON_NAME], etc.)   │  Local ComfyUI)│        │               │
└───────────────┘        └───────────────┘        └───────────────┘
```

### 3.1 Component Responsibilities

| Component | Responsibility | Tech |
|-----------|---------------|------|
| **Prompt Engine** | Multi-shot prompt generation, style genome encoding, variant expansion | Python + Jinja2 templates |
| **Style Registry** | Git-tracked style genomes (prompt DNA, negative prompts, params, examples) | YAML + git branches |
| **Browser Agent** | Drives free web UIs (ChatGPT, [PERSON_NAME], Copilot, Grok) via Playwright | Python + Playwright |
| **API Agent** | Calls paid APIs (OpenRouter, Fal, Replicate, local ComfyUI) | Python + httpx |
| **Asset Store** | Local folder + Google Drive sync, metadata SQLite, review queue | SQLite + rclone/gdrive |
| **Review UI** | Human approval/rejection/annotation, feeds back to style genome | Obsidian vault + custom plugin OR local FastAPI + HTMX |
| **Scheduler** | GitHub Actions cron + manual dispatch | YAML workflow |

---

## 4. Style Genome (The "Simpsons DNA")

Each **Style Engine** = a git branch + YAML genome:

```yaml
# style-genomes/simpsons-horror/genome.yaml
style_id: simpsons-horror
parent: simpsons-base
version: 3
description: "Simpsons style with horror twist — thick outlines, yellow skin, exaggerated expressions, gothic elements"

visual_dna:
  line_weight: "thick_constant"
  color_palette: ["#FFD700", "#FF6B00", "#8B0000", "#000000", "#FFFFFF"]
  proportions: "exaggerated_head_1.5x_body"
  shading: "cel_shaded_minimal"
  background: "simple_silhouette"

prompt_genome:
  positive_core: |
    {style_id} style, {subject}, thick black outlines, flat cel shading,
    yellow skin tone #FFD700, exaggerated facial features, large expressive eyes,
    {theme} elements, gothic horror atmosphere, dramatic lighting, clean vector lines
  negative_core: |
    realistic, photorealistic, gradient shading, soft edges, thin lines,
    pastel colors, watercolor, sketch, messy lines, watermark, text, signature
  parameters:
    sampler: euler_a
    steps: 30
    cfg_scale: 7
    width: 1024
    height: 1024
    aspect_ratio: "1:1"

variants:
  - id: coloring_page
    prompt_suffix: "coloring book page, line art only, no fill, clean closed paths, high contrast"
    negative_suffix: "color, fill, shading, gradient, background"
    output_format: svg
    postprocess: "potrace_svg_cleanup"

  - id: tarot_card
    prompt_suffix: "tarot card composition, ornate border, major arcana symbolism, vertical 2:3.5"
    output_format: png
    postprocess: "upscale_2x_add_bleed"

  - id: unity_sprite
    prompt_suffix: "game sprite sheet, multiple poses, transparent background, consistent lighting"
    output_format: png
    postprocess: "sprite_sheet_slice"

evolution_log:
  - version: 1
    note: "Base simpsons style from reference images"
    parent: null
    human_rating: 7/10
  - version: 2
    note: "Added horror theme, thicker lines"
    parent: 1
    human_rating: 8/10
  - version: 3
    note: "Fixed eye consistency, better closed paths for SVG"
    parent: 2
    human_rating: 9/10
```

**Evolution workflow**:
1. Human rates outputs → updates `human_rating` + notes
2. Prompt Engine proposes genome mutation (A/B prompt variants)
3. Human approves → new version committed to style branch
4. Branch can be forked for new style lines

---

## 5. Prompt Engine (Sub-Agent)

### 5.1 Multi-Shot Prompt Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PROMPT ENGINE PIPELINE                   │
├─────────────────────────────────────────────────────────────┤
│  1. THEME EXPANSION                                         │
│     Input: "halloween coloring pages for kids"              │
│     Output: 20 specific concepts (witch, pumpkin, ghost...) │
│                                                             │
│  2. STYLE GENOME INJECTION                                  │
│     For each concept × each active style engine:            │
│     Render prompt_template with {concept, theme, style_dna} │
│                                                             │
│  3. VARIANT GENERATION                                      │
│     Per (concept, style, variant): 3-5 prompt mutations     │
│     (seed variation, parameter jitter, emphasis shifts)     │
│                                                             │
│  4. ROUTING                                                 │
│     Browser targets → Playwright queue                      │
│     API targets → async HTTP queue                          │
│                                                             │
│  5. EXECUTION MONITORING                                    │
│     Track latency, success rate, cost per engine            │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Prompt Templates (Jinja2)

```jinja2
{# templates/coloring_page.j2 #}
{{ style.genome.positive_core }}

Subject: {{ concept.name }}
Theme: {{ theme.name }}
Style: {{ style.style_id }}

{{ style.genome.variants.coloring_page.prompt_suffix }}

Technical: {{ style.genome.parameters | tojson }}

---
NEGATIVE PROMPT:
{{ style.genome.negative_core }}
{{ style.genome.variants.coloring_page.negative_suffix }}
```

---

## 6. Browser Agent (Playwright)

### 6.1 Targets (Free Tier)

| Platform | URL | Auth | Notes |
|----------|-----|------|-------|
| ChatGPT (DALL-E 3) | chat.openai.com | Google/email login | 2-3 generations/day free |
| [PERSON_NAME] | [PERSON_NAME].ai | Google login | Free tier generous |
| Copilot Designer | designer.microsoft.com | Microsoft account | DALL-E 3, 15/day |
| Grok | x.com/i/grok | X account | Limited free |

### 6.2 Browser Agent Architecture

```python
# browser_agent/engine.py
class BrowserEngine:
    def __init__(self, platform: str, profile_dir: Path):
        self.platform = platform
        self.context = await browser.new_context(
            storage_state=profile_dir / "auth.json"
        )
    
    async def generate(self, prompt: PromptJob) -> list[Asset]:
        page = await self.context.new_page()
        await page.goto(self.platform.url)
        await self._navigate_to_generator(page)
        await self._input_prompt(page, prompt.rendered)
        await self._wait_for_generation(page)
        assets = await self._download_results(page, prompt.output_dir)
        await page.close()
        return assets
```

### 6.3 Session Persistence

- Each platform = persistent Playwright profile (`~/.asset-engine/browser-profiles/{platform}/`)
- Auth state saved after manual login (one-time setup)
- Headless on server, headed optional for debugging locally

---

## 7. API Agent (Paid/Unlimited)

### 7.1 Providers & Models

| Provider | Models | Use Case |
|----------|--------|----------|
| **OpenRouter** | gpt-oss-120b, nemotron-3-ultra, claude-3.5-sonnet | Prompt engineering, reasoning |
| **Fal.ai** | Flux-dev, Flux-schnell, SDXL, Recraft | High-quality generation, fast |
| **Replicate** | 100+ models (Flux, Midjourney v6, Ideogram) | Specialty models |
| **Local ComfyUI** (zo.computer) | Any SDXL/Flux/LoRA | Unlimited, full control, LoRA training |

### 7.2 Routing Logic

```python
# api_agent/router.py
def route_generation(prompt_job: PromptJob) -> GenerationTarget:
    style = prompt_job.style_genome
    variant = prompt_job.variant
    
    # Coloring pages → SVG-capable or clean line models
    if variant.output_format == "svg":
        return GenerationTarget(
            provider="comfyui",
            model="flux-dev-lora-lineart",
            endpoint="zo.computer:8188"
        )
    
    # Tarot cards → high detail, Flux/Midjourney
    if variant.id == "tarot_card":
        if budget.allows("midjourney"):
            return GenerationTarget(provider="replicate", model="midjourney-v6")
        return GenerationTarget(provider="fal", model="flux-dev")
    
    # Default → best free/cheap
    return GenerationTarget(provider="openrouter", model="nvidia/nemotron-3-ultra")
```

---

## 8. Asset Store & Review Workflow

### 8.1 File Structure

```
~/asset-engine/
├── style-genomes/           # Git-tracked style definitions
│   ├── simpsons-base/
│   ├── simpsons-horror/
│   └── disney-dark/
├── generation-runs/         # Timestamped run outputs
│   └── 2026-07-12_06-00/
│       ├── prompts.jsonl    # All prompts sent
│       ├── results.jsonl    # All results with metadata
│       └── assets/          # Downloaded files
├── review-queue/            # Human review staging
│   ├── pending/
│   ├── approved/
│   ├── rejected/
│   └── needs-revision/
├── metadata.db              # SQLite: assets, ratings, lineage
└── google-drive-sync/       # rclone config for GDrive
```

### 8.2 Metadata Schema (SQLite)

```sql
CREATE TABLE assets (
    id TEXT PRIMARY KEY,                    -- UUID
    run_id TEXT,                            -- generation run
    style_id TEXT,                          -- style genome
    variant_id TEXT,                        -- coloring_page, tarot_card, etc.
    concept TEXT,                           -- "halloween witch"
    theme TEXT,                             -- "halloween"
    prompt TEXT,                            -- full rendered prompt
    negative_prompt TEXT,
    engine TEXT,                            -- "chatgpt", "fal-flux", "comfyui"
    model TEXT,                             -- "dall-e-3", "flux-dev"
    parameters TEXT,                        -- JSON params
    output_path TEXT,                       -- local file path
    gdrive_path TEXT,                       -- Google Drive file ID
    width INTEGER,
    height INTEGER,
    format TEXT,                            -- svg, png, pdf
    human_rating INTEGER,                   -- -1=unrated, 0=reject, 1-5=approve
    human_notes TEXT,
    parent_asset_id TEXT,                   -- for evolution lineage
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP
);

CREATE INDEX idx_style_variant ON assets(style_id, variant_id);
CREATE INDEX idx_rating ON assets(human_rating);
CREATE INDEX idx_review_queue ON assets(human_rating) WHERE human_rating = -1;
```

### 8.3 Review UI Options

**Option A: Obsidian Vault (Recommended for you)**
- Each asset = markdown note with frontmatter + embedded image
- Tags: `#pending #approved #rejected #style:simpsons-horror`
- Dataview queries for review queues
- Mobile access via Obsidian Sync
- Your existing workflow

**Option B: Local Web UI (FastAPI + HTMX)**
- `/review` — grid of pending assets, keyboard shortcuts (A=approve, R=reject, N=next)
- `/styles/{style_id}` — evolution dashboard, rating charts
- `/queue` — generation run status
- Runs on zo.computer, accessible via Tailscale

**Decision**: Start with **Obsidian** (zero dev time), migrate to web UI if needed.

---

## 9. GitHub Actions Workflow

### 9.1 Cron Schedule

```yaml
# .github/workflows/generate.yml
on:
  schedule:
    - cron: '0 6 * * *'   # 6 AM UTC (11 PM PT previous day)
    - cron: '0 18 * * *'  # 6 PM UTC (11 AM PT)
  workflow_dispatch:
    inputs:
      style_id:
        description: 'Specific style engine to run (empty = all active)'
        required: false
        type: string
      count:
        description: 'Prompts per style'
        required: false
        default: '10'
        type: string
```

### 9.2 Job Matrix

```yaml
jobs:
  generate:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        style: ${{ fromJson(needs.discover-styles.outputs.active_styles) }}
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Run Prompt Engine
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          FAL_API_KEY: ${{ secrets.FAL_API_KEY }}
          REPLICATE_API_TOKEN: ${{ secrets.REPLICATE_API_TOKEN }}
        run: |
          python -m prompt_engine.main \
            --style ${{ matrix.style }} \
            --count ${{ github.event.inputs.count || 10 }} \
            --output-dir run-${{ github.run_id }}
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: assets-${{ matrix.style }}-${{ github.run_id }}
          path: run-${{ github.run_id }}/assets/
          retention-days: 30
```

### 9.3 Secrets Required

| Secret | Source |
|--------|--------|
| `OPENROUTER_API_KEY` | openrouter.ai |
| `FAL_API_KEY` | fal.ai |
| `REPLICATE_API_TOKEN` | replicate.com |
| `GDRIVE_CREDENTIALS` | Service account JSON (base64) |
| `BROWSER_PROFILES` | Base64 tar of Playwright profiles |

---

## 10. Evolution Loop (The "Simpsons Consistency" Engine)

```
┌────────────────────────────────────────────────────────────────┐
│                    EVOLUTION CYCLE                              │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. GENERATE                                                   │
│     Prompt Engine → Browser/API Agents → Assets                │
│                          │                                     │
│                          ▼                                     │
│  2. HUMAN REVIEW (Obsidian)                                    │
│     Rate 1-5, tag #approved/#rejected, notes                   │
│                          │                                     │
│                          ▼                                     │
│  3. GENOME UPDATE                                              │
│     Prompt Engine analyzes:                                    │
│       - High-rated prompts → extract patterns                  │
│       - Low-rated prompts → identify failure modes             │
│       - Proposes prompt mutations (A/B variants)               │
│                          │                                     │
│                          ▼                                     │
│  4. HUMAN APPROVES MUTATION                                    │
│     New genome version committed to style branch               │
│                          │                                     │
│                          ▼                                     │
│  5. FORK (when style diverges enough)                          │
│     git checkout -b new-style-lineage                          │
│     Modify genome.yaml → commit                                │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 10.1 Automated Pattern Extraction

```python
# evolution/analyzer.py
def analyze_approved_prompts(style_id: str, min_rating: int = 4) -> GenomeMutation:
    approved = db.query("""
        SELECT prompt, parameters FROM assets 
        WHERE style_id = ? AND human_rating >= ?
    """, (style_id, min_rating))
    
    # Extract common phrases, parameter ranges, negative patterns
    common_positive = extract_ngrams([a.prompt for a in approved], n=3, min_freq=0.3)
    param_ranges = compute_parameter_ranges([a.parameters for a in approved])
    failure_patterns = analyze_rejected(db.query("""
        SELECT prompt FROM assets WHERE style_id = ? AND human_rating = 0
    """, (style_id,)))
    
    return GenomeMutation(
        suggested_positive_additions=common_positive,
        suggested_parameter_ranges=param_ranges,
        suggested_negative_additions=failure_patterns,
        confidence=len(approved) / 10.0  # max 1.0 at 10+ samples
    )
```

---

## 11. Unity Asset Pipeline (Future Phase)

When style engines are stable (rating ≥ 4.5/5 over 50+ assets):

```yaml
# unity-pipeline/config.yaml
style_engine: simpsons-horror
outputs:
  - type: sprite_sheet
    prompts:
      - "character_idle_4frames"
      - "character_walk_8frames"
      - "character_attack_6frames"
    postprocess:
      - slice_sheet
      - generate_unity_meta
      - pack_atlas
  - type: texture
    prompts:
      - "seamless_tileable_background"
      - "ui_panel_nine_slice"
    postprocess:
      - make_seamless
      - generate_normal_map
  - type: ui_kit
    prompts:
      - "button_normal_hover_pressed"
      - "health_bar_segments"
      - "inventory_slot_states"
```

---

## 12. Implementation Phases

| Phase | Scope | Duration | Deliverable |
|-------|-------|----------|-------------|
| **0. Spec Review** | This document → approve/iterate | 1 session | Signed-off SPEC.md |
| **1. Foundation** | Repo structure, SQLite, style genome schema, GitHub Actions skeleton | 2-3 days | Runnable empty pipeline |
| **2. Prompt Engine** | Theme expansion, template rendering, variant generation | 2-3 days | Generates prompt JSONL |
| **3. API Agent** | OpenRouter + Fal integration, routing, async queue | 2-3 days | Generates via API |
| **4. Browser Agent** | Playwright profiles, ChatGPT/[PERSON_NAME]/Copilot automation | 3-4 days | Generates via free web UIs |
| **5. Asset Store + Sync** | Local fs + rclone GDrive, metadata DB, review queue | 2 days | Assets appear in Obsidian |
| **6. Review Workflow** | Obsidian vault setup, Dataview queries, rating flow | 1 day | Human review loop works |
| **7. Evolution Engine** | Pattern extraction, mutation proposals, genome versioning | 3-4 days | Styles improve over time |
| **8. Unity Pipeline** | Sprite sheet, texture, UI kit generation | Later | Game-ready assets |

**Total to MVP (phases 1-6)**: ~2-3 weeks part-time

---

## 13. Repository Structure

```
asset-engine/
├── .github/
│   └── workflows/
│       └── generate.yml
├── prompt_engine/
│   ├── main.py
│   ├── templates/
│   │   ├── coloring_page.j2
│   │   ├── tarot_card.j2
│   │   ├── planner_page.j2
│   │   └── activity_page.j2
│   ├── themes/
│   │   ├── halloween.yaml
│   │   ├── christmas.yaml
│   │   └── fantasy.yaml
│   └── concepts/
│       └── (auto-generated)
├── browser_agent/
│   ├── engine.py
│   ├── platforms/
│   │   ├── chatgpt.py
│   │   ├── [PERSON_NAME].py
│   │   ├── copilot.py
│   │   └── grok.py
│   └── profiles/           # gitignored, synced via secrets
├── api_agent/
│   ├── router.py
│   ├── providers/
│   │   ├── openrouter.py
│   │   ├── fal.py
│   │   ├── replicate.py
│   │   └── comfyui.py
│   └── queue.py
├── asset_store/
│   ├── db.py
│   ├── models.py
│   ├── sync_gdrive.py
│   └── review_queue.py
├── evolution/
│   ├── analyzer.py
│   ├── mutator.py
│   └── genome.py
├── style-genomes/          # Git-tracked, versioned
│   ├── simpsons-base/
│   │   └── genome.yaml
│   └── ...
├── review-vault/           # Obsidian vault (git-tracked)
│   ├── .obsidian/
│   ├── pending/
│   ├── approved/
│   ├── rejected/
│   └── templates/
├── unity-pipeline/         # Phase 8
│   └── ...
├── tests/
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 14. Configuration

```yaml
# config.yaml
scheduler:
  cron: "0 6,18 * * *"
  manual_trigger: true
  max_prompts_per_run: 20

style_engines:
  active:
    - simpsons-horror
    - disney-dark
  max_per_run: 10

generation:
  browser:
    enabled: true
    platforms: [chatgpt, [PERSON_NAME], copilot]
    headless: true
    timeout_seconds: 120
  api:
    enabled: true
    providers:
      - openrouter
      - fal
      - replicate
    budget_per_run_usd: 5.00

review:
  interface: obsidian
  vault_path: "~/asset-engine/review-vault"
  auto_open_on_run: false

sync:
  gdrive:
    enabled: true
    remote_name: "asset-engine"
    folder_id: "1ABC..."  # root folder ID
    sync_on_review: true

unity:
  enabled: false  # Phase 8
```

---

## 15. Open Decisions (Need Your Call)

| Decision | Options | Recommendation |
|----------|---------|----------------|
| **Review UI** | Obsidian vs Local Web UI | Start Obsidian, migrate if painful |
| **Browser Profiles Storage** | GitHub Secrets (base64 tar) vs zo.computer persistent | zo.computer persistent volume |
| **ComfyUI Hosting** | zo.computer (always-on) vs exe.dev vs GitHub Actions self-hosted | zo.computer (you control it) |
| **Style Genome Format** | YAML (shown) vs JSON vs TOML | YAML (human-readable, git-friendly) |
| **Theme/Concept Source** | Manual YAML lists vs LLM-generated vs scraped | Manual curated + LLM expansion |
| **Cost Monitoring** | Per-run budget alerts (GitHub Actions summary) | Yes, fail run if > $5 |

---

## 16. Next Steps

1. **You review this SPEC** — push back on anything wrong/missing
2. **Approve** → I initialize repo structure, GitHub Actions, SQLite schema
3. **You set up secrets** (OpenRouter, Fal, Replicate, GDrive service account)
4. **We implement Phase 1-2** (foundation + prompt engine)
5. **You do one-time browser auth** (record Playwright profiles)
6. **Phase 3-4** (agents) → first real generation run
7. **Phase 5-6** (review loop) → you start rating
8. **Phase 7** (evolution) → styles get sharper

---

**Ready to proceed?** Say the word and I'll scaffold the repo with Phase 1-2. [2026-07-12 14:30]