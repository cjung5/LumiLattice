# LumiLattice

**A collaborative AI scientist for optoelectronic materials discovery.**

LumiLattice helps researchers find candidate materials for AR waveguides (high refractive index, transparent in the visible range). A Meta **Muse Spark** research agent plans the search and proposes changes. Deterministic scientific tools (pymatgen and public materials databases) compute every number. The researcher steers each step.

Built for the Meta Global AI Developer Hackathon (Oct 27 – Nov 4, 2026), track **Push the Frontier**.

> Status: early development. This README is updated as features land.

## How it works

1. The researcher sets optical targets and constraints, and selects a host crystal structure.
2. Muse Spark (Meta Model API, Responses endpoint) plans the work and calls tools.
3. Tools return values with provenance. The model never writes a number on its own.
4. Each value carries one evidence tag: `Experimental`, `DFT-computed`, `Heuristic`, or `Unknown`.
5. The researcher accepts, modifies, or rejects a candidate, and the agent revises it.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI app: Muse Spark agent loop, tool registry, scientific tools (pymatgen, Materials Project, OpenAlex) |
| `frontend/` | Next.js app with English and Korean UI (more languages planned): host search, CIF upload, 3D viewer (3Dmol.js), literature panel, agent console |

## Agent tools

| Tool | Source | Returns |
|---|---|---|
| `composition_info` | pymatgen | Reduced formula, molar mass, charge-balanced oxidation states |
| `search_materials` | Materials Project | Known structures with DFT band gap, energy above hull, and refractive index, each tagged |
| `search_literature` | OpenAlex | Paper metadata (title, authors, year, venue, DOI, open-access link) |
| `create_candidate` | LumiLattice | Substitutes elements on a host or on an earlier candidate, then runs the structural checks below |

When a source is not available, the tool returns an error and the agent reports the value as unknown instead of guessing.

## Candidates and structural checks

A candidate replaces a fraction of one element's sites in a known host (or in an earlier candidate, which records the parent and builds a version history). Partial fractions use the smallest supercell (1, 2, 3, 4, 6, or 8 cells). The replaced sites are spread as far apart as possible. Atoms are **not relaxed**, so the checks show how well the new elements fit the host geometry.

| Check | Method | Thresholds (heuristic) |
|---|---|---|
| Oxidation states and charge neutrality | pymatgen `oxi_state_guesses` | Fail: no balanced assignment. Warn: needs mixed valence |
| Interatomic distances | Pairwise distances | Fail: < 1.2 Å, or cation–anion < 0.8 × radius sum |
| Ionic size fit | Shannon (1976) ionic radii vs. site bond length | Warn > 10 %, fail > 20 % |
| Coordination environment | First anion shell; Shannon table | Warn: ion not tabulated at that coordination number |
| Bond valence sum | O'Keeffe & Brese (1991) universal parameters, b = 0.37 Å | Graded by the implied bond-length change: warn > 4 %, fail > 10 % |
| Goldschmidt tolerance factor | Perovskite-like ABX3 only | Pass 0.85–1.06, warn 0.80–1.10 |
| Reference analogs | Materials Project search for each 100 % end member | Information only |

Each failed or warned check lists its atom indices. The 3D viewer highlights those atoms, because the CIF is written in P1 and the viewer's atom order matches the backend's site order. The overall result is one of `Structurally Plausible`, `Structural Concerns`, or `Insufficient Evidence` (no anion, so the ionic checks do not apply). These checks do **not** predict whether a material can be synthesized.

## Researcher in the loop

The research agent sees the selected host and the current candidate, and it keeps the conversation (Responses API `previous_response_id`). For each candidate the researcher records a decision with a reason:

| Decision | Effect |
|---|---|
| Accept / Reject | Recorded on the candidate |
| Modify | Recorded, then the agent revises that candidate from the reason and compares the checks |
| Explore alternatives | Recorded, then the agent tests up to 2 alternatives from the reason |

Candidates from the form and from the agent share one version history (parent → child).

## API usage limits

- Materials Project and OpenAlex responses are cached for 24 hours. OpenAlex stops at 500 searches per day (half of its free daily budget) and stops early if the free budget left for the day falls below $0.05. Materials Project has a cap of 1,000 requests per day.
- The public demo protects Meta Model API credits: at most 10 agent requests per client per 10 minutes and 200 per day, with at most 8 tool steps per request.

## Run locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+.

Backend:

```bash
cd backend
cp .env.example .env   # then add your MODEL_API_KEY
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Frontend (in a second terminal):

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000.

Tests and live check:

```bash
cd backend
uv run pytest
uv run python -m scripts.smoke_muse   # needs MODEL_API_KEY; Muse Spark calls a real tool
```

## Deploy

The backend runs on Render (Docker, free plan) and the frontend on Vercel.

1. **Backend (Render):** New → Blueprint → select this repository. Render reads [`render.yaml`](render.yaml) and asks for `MODEL_API_KEY`, `MP_API_KEY`, and `OPENALEX_API_KEY`. When the deploy finishes, open `https://<service>.onrender.com/api/health`.
2. **Frontend (Vercel):** New Project → import this repository → Root Directory `frontend`. Add the environment variable `NEXT_PUBLIC_API_BASE_URL` = the Render URL (no trailing slash), then deploy.
3. **CORS:** `CORS_ORIGIN_REGEX` in `render.yaml` allows `https://lumilattice*.vercel.app`. If the Vercel project has another name, change it in the Render dashboard.

Limits of the free plan: the backend sleeps after 15 minutes without requests (the next request takes about a minute), and candidates are kept in memory, so they are lost when it sleeps. Open the health URL a minute before a demo.

## Built during the hackathon

All code in this repository was written during the hackathon period (Oct 27 – Nov 4, 2026). See the commit history for the timeline.

## Data sources and attribution

In use:

- **Materials Project** — crystal structures and DFT properties, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). A. Jain et al., "The Materials Project: A materials genome approach to accelerating materials innovation", *APL Materials* 1, 011002 (2013). Each record links to its Materials Project page.
- **OpenAlex** — scholarly metadata, [CC0](https://creativecommons.org/publicdomain/zero/1.0/). J. Priem, H. Piwowar, R. Orr, "OpenAlex: A fully-open index of scholarly works, authors, venues, institutions, and concepts", arXiv:2205.01833 (2022).
- **pymatgen** — structure parsing and analysis, MIT license. S. P. Ong et al., *Comput. Mater. Sci.* 68, 314 (2013).
- **Shannon ionic radii** — R. D. Shannon, *Acta Cryst.* A32, 751 (1976), as tabulated in pymatgen.
- **Bond valence parameters** — M. O'Keeffe and N. E. Brese, *J. Am. Chem. Soc.* 113, 3226 (1991), as tabulated in pymatgen.
- **3Dmol.js** — 3D viewer, BSD-3-Clause license.

Planned: JARVIS-DFT (CC BY 4.0), refractiveindex.info (CC0), Crystallography Open Database, Crossref, and arXiv.

## License

[Apache-2.0](LICENSE)
