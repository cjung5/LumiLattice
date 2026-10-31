# LumiLattice

**A collaborative AI scientist for optoelectronic materials discovery.**

LumiLattice helps researchers find candidate materials for AR waveguides (high refractive index, transparent in the visible range). A Meta **Muse Spark** research agent plans the search and proposes changes. Deterministic scientific tools (pymatgen and public materials databases) compute every number. The researcher steers each step.

Built for the Meta Global AI Developer Hackathon (Oct 27 – Nov 4, 2026), track **Push the Frontier**.

> Status: early development. This README is updated as features land.

## Who it is for

LumiLattice is for researchers and for people new to the field. The app opens in **Guided** mode; **Expert** mode shows every tool at once. The choice is remembered in the browser.

Guided mode has these parts:

- **Why this exists.** A short statement of the problem (AR glasses need a material that bends light strongly and stays clear), what you do here, what you get, and what the tool cannot do.
- **Plain step names and starting points.** "Your goal, starting crystal, swap atoms, read the result". Four suggested starting crystals mean that nobody has to know a formula first.
- **Scales instead of bare numbers.** n is shown against glass, sapphire, and diamond. The band gap is shown on the visible spectrum, with the absorbed part darkened and the uncertain part striped.
- **A plain result.** Each candidate opens with what it means for your goal, how sure the evidence is, and buttons to have Muse Spark explain it or suggest a better swap. The verdicts are the same deterministic goal score that Expert mode shows.
- **A glossary.** Select an underlined term or an evidence tag to read a short definition.
- **Muse Spark in plain language.** In Guided mode, the agent and the critique explain technical terms and stay short. The rules on numbers do not change.

Nothing is removed: export, relaxation, publishing, lab results, and the checks move behind a click. Two evidence views (dispersion and site metrics) and the 3D structure analysis are in Expert mode.

## How it works

1. The researcher sets optical targets and constraints, and selects a host crystal structure.
2. Muse Spark (Meta Model API, Responses endpoint) plans the work and calls tools. It also reviews each candidate from its evidence and rendered views of its structure (multimodal critique).
3. Tools return values with provenance. The model never writes a number on its own.
4. Each value carries one evidence tag: `Experimental`, `DFT-computed`, `Heuristic`, or `Unknown`.
5. The researcher accepts, modifies, or rejects a candidate, and the agent revises it.

A step bar at the top of the app shows the four steps (goal, host, candidate, evidence and decision), marks the steps that are done, and tells the researcher what to do next. Each step scrolls to its section; the steps can be done in any order.

**Try the AR example** runs the steps once with real data: the AR waveguide goal (n ≥ 2.2, band gap ≥ 3.0 eV), SrTiO3 (mp-5229) as the host, and a candidate with La on 25% of the Sr sites and Al on 25% of the Ti sites. SrTiO3 has a high n; LaAlO3 has a wider gap. The example asks whether the co-substituted candidate keeps both, and points to the evidence views that answer it. It uses the same API calls as a researcher would, so it stays within the free-tier caps.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI app: Muse Spark agent loop, tool registry, scientific tools (pymatgen, Materials Project, OpenAlex) |
| `frontend/` | Next.js app in 6 languages: host search (Materials Project or COD), CIF upload, 3D viewer (3Dmol.js), candidates, optical evidence, literature, research agent |

## Agent tools

| Tool | Source | Returns |
|---|---|---|
| `composition_info` | pymatgen | Reduced formula, molar mass, charge-balanced oxidation states |
| `search_materials` | Materials Project | Known structures with DFT band gap, energy above hull, and refractive index, each tagged |
| `search_literature` | OpenAlex, Crossref, arXiv, Semantic Scholar | Paper metadata merged by DOI or title, with the sources that found each paper |
| `create_candidate` | LumiLattice | Substitutes elements on a host or on an earlier candidate (new atoms spread apart, or at the lowest Ewald energy), then runs the structural checks below |
| `get_candidate` | LumiLattice | A candidate's substitutions, checks, n range, measurements, and the researcher's decisions |
| `get_optical_reference` | refractiveindex.info, JARVIS-DFT | Measured n at 450/550/650 nm with sources; DFT band gaps and n (OptB88vdW, TBmBJ) |
| `score_against_goal` | LumiLattice | A candidate's verdicts against the researcher's goal, with evidence |

When a source is not available, the tool returns an error and the agent reports the value as unknown instead of guessing.

## Research goal and evidence charts

The researcher sets a **goal** first: minimum n near 550 nm, minimum band gap, and forbidden elements. Every host and candidate is scored against it (`meets`, `uncertain`, `fails`, `unknown`). Each verdict cites its evidence and tag; a Heuristic range that spans the target is `uncertain`, never `meets`.

The **Evidence** section shows the data behind each decision, in five views. Every chart has a legend, notes on what the data is, hover tooltips, and a table view:

| View | What it shows |
|---|---|
| n vs band gap | All materials with a measured n (refractiveindex.info, with JARVIS TBmBJ gaps), a sample of JARVIS DFT entries, the empirical Moss relation (n⁴·Eg ≈ 95 eV), the goal region, the host, the end members, and the candidate's n × gap range box |
| Dispersion n(λ) | Measured bulk n(λ) from 380 to 780 nm for the host and end members (no extrapolation), with the candidate's Heuristic band between them |
| Site metrics | For each checked cation site: ionic size mismatch and bond-valence misfit against the warn/fail thresholds, unrelaxed or CHGNet-relaxed |
| 3D structure | Spatial analysis of the host, the candidate, and its relaxed geometry (see below) |
| Goal score | The scored criteria for the host and the candidate |

Chart colors encode the evidence type (aqua = measured, blue = DFT, orange = Heuristic), from a palette validated for color-vision deficiency in light and dark modes.

### 3D structure analysis

The structural checks (see "Candidates and structural checks") look at one site at a time. The 3D structure view looks at the arrangement in space, before substitution, after it, and after CHGNet relaxation (if run):

| Analysis | Method | Why it matters for a waveguide |
|---|---|---|
| Symmetry and optical class | Space group (spglib via pymatgen) → crystal system → isotropic (cubic), uniaxial (tetragonal, trigonal, hexagonal), or biaxial | A non-cubic crystal is birefringent: n depends on polarization and direction |
| Polyhedra | Shape match (octahedron, tetrahedron, square planar), bond-length distortion index Δ (Baur 1974), quadratic elongation ⟨λ⟩, bond-angle variance σ², volume | Distorted polyhedra change local polarizability and can lower symmetry |
| Connectivity | Corner, edge, and face sharing between cation polyhedra, with periodic images; B–X–B angles through corner-shared anions; mean octahedral tilt (180° − angle)/2 for corner-only frameworks such as perovskites | Tilts and bent links are how many oxides accommodate a size mismatch |
| Dopant arrangement | Nearest same-element distance against the shortest possible spacing; flags clustered dopants | Clustering is a sign of a poor model of a random alloy |
| Ordering rank | All arrangements of the same dopants in a repeated cell (at least two dopants each, at most 80 atoms; a seeded random sample of 300 if there are more), ranked by Ewald energy with formal charges | Shows whether the chosen arrangement is electrostatically favorable among the alternatives |

Limits, also shown in the app: an ordered supercell is one model of a disordered solid solution, so its symmetry and arrangement are properties of that model. Small cells cannot show every tilt pattern. Ewald energies are unscreened point-charge energies, for ranking only; when all dopants have the same charge as the ions they replace, every arrangement has the same energy and only relaxation can rank them. The relaxed geometry is compared with the unrelaxed candidate, because relaxation does not move ions between sites.

## Refractive index evidence

Every n value carries one tag, shown with its own color, icon, and text:

| Tag | Where it comes from |
|---|---|
| `Experimental` | refractiveindex.info, measured n at 550 nm (bulk or crystal pages; thin films are listed but not used for the best value). For band gaps: literature values from Zhuo et al. (2018) |
| `DFT-computed` | JARVIS-DFT n = √ε from DFT linear optics (TBmBJ preferred, then OptB88vdW), or Materials Project n. This is a long-wavelength value, not n(550 nm) |
| `Heuristic` | A candidate's **range** spanned by its end members, e.g. SrTiO3 → LaAlO3 for Sr→La + Ti→Al. Never a single number, and not a prediction |
| `Unknown` | No data |

Band gaps follow the same order: a measured value first, then a JARVIS-DFT value (TBmBJ, then OptB88vdW). Measured gaps are the median of the reports for a formula in the Zhuo et al. compilation (3,895 reports; the 2,458 entries with a gap of 0 are labels for metals and are not used). The compilation does not record the method for each report, so a value can be an optical, direct, or indirect gap, and reports for one formula can disagree (SrTiO3: 3.0 to 4.1 eV). The app shows the median and the spread. Many materials have no measured gap (LaAlO3 and Al2O3 among them) and keep a `DFT-computed` value, so a candidate's range can mix measured and computed gaps.

The reference data is matched by formula, so the polymorph can differ from the selected structure; the app says so next to each value.

The bundled `backend/data/reference.sqlite` (10 MB) holds a subset of JARVIS-DFT 3D (2025-09-24, 93,902 entries) the refractiveindex.info database (release 2026-05-24, 868 measured pages with n in the visible range; "Models and simulations" pages are excluded), and the measured band gaps. To rebuild it:

```bash
cd backend
uv run python -m scripts.download_data       # pinned versions, SHA-256 checked; about 62 MB into data/raw/
uv run python -m scripts.build_reference_db
```

## Candidates and structural checks

A candidate replaces a fraction of one element's sites in a known host (or in an earlier candidate, which records the parent and builds a version history). Partial fractions use the smallest supercell (1, 2, 3, 4, 6, or 8 cells). Atoms are **not relaxed**, so the checks show how well the new elements fit the host geometry.

The researcher (or the agent) chooses where the new atoms go:

- **Spread apart** (default): the replaced sites are as far apart as possible (farthest-point selection), in the smallest supercell.
- **Lowest Ewald energy:** every arrangement of the new atoms is compared by point-charge (Ewald) energy with formal charges, and the lowest is kept. The search uses the same cell as the ordering rank in the 3D structure view (the smallest repeat with at least 2 of each new atom), so the result ranks first there. Up to 50,000 arrangements are compared exhaustively; above that, a seeded random sample is improved by greedy swaps, and the candidate says the result is not guaranteed to be the lowest. Example: for 25% La and 25% Al in SrTiO3, the spread arrangement ranks 6 of 23 distinct energies (+51 meV/atom); the lowest-Ewald candidate (4×2×1 cell, 40 atoms) ranks 1. Point charges have no screening or relaxation, so CHGNet relaxation can change the order.

When every new atom's nearest same-element neighbor is its own periodic image (the cell is one host cell thick in that direction), the 3D view says so instead of calling it clustering: every arrangement in that cell has the same chains.

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

## Host structures

- **Materials Project** (DFT): search by formula, elements, or ID.
- **Crystallography Open Database** (experimental, CC0): search by formula; each entry shows its authors, journal, year, and DOI. Oxidation-state labels in CIFs (e.g. `Sr2+`) are removed on import.
- **Your own CIF**.

Materials Project stores many crystals as primitive cells: skewed boxes whose axes are not the crystal axes (anatase has angles of 110°). LumiLattice converts them to the conventional standard cell with spglib (`symprec` 0.01), the cell that textbooks draw, so the structure looks right and supercells follow the crystal axes. The conversion is rejected if the formula or the density would change, and the provenance records the method. Uploaded and COD CIFs keep the cell in the file. The viewer uses an orthographic camera, and it draws atoms on a cell face, edge, or corner again on the opposite side. These copies are for display only and do not count as sites.

## Researcher in the loop

The research agent sees the selected host and the current candidate, and it keeps the conversation (Responses API `previous_response_id`). For each candidate the researcher records a decision with a reason:

| Decision | Effect |
|---|---|
| Accept / Reject | Recorded on the candidate |
| Modify | Recorded, then the agent revises that candidate from the reason and compares the checks |
| Explore alternatives | Recorded, then the agent tests up to 2 alternatives from the reason |

Candidates from the form and from the agent share one version history (parent → child).

Each candidate also has:

- **CHGNet relaxation (local install only):** moves atoms and the cell with a machine-learned potential and runs the same checks on the relaxed geometry; the UI switches between unrelaxed and relaxed views. It needs PyTorch, which does not fit the free server, so the live demo says "local install". CHGNet energies are never compared with DFT energies.
- **Measurements:** the researcher can add a measured n (with wavelength) or band gap, with sample type, method, and reference. The app shows whether a measured n falls inside the candidate's end-member range. LumiLattice records these values as given.
- **Share link:** `?candidate=LL-0003` opens that candidate on the same backend.
- **Export:** a CIF of the candidate (and of its relaxed geometry, if relaxed) and a JSON research record (below).
- **Muse Spark critique:** a reviewer's reading of the candidate from its evidence and three views of its structure (below).
- **Registry:** all candidates in one table with filters, and a side-by-side comparison of up to 3 (checks, n range, ΔV after relaxation, measurements).

### Muse Spark critique

Muse Spark is multimodal, so the critique gives it two kinds of input:

1. **Evidence items** built by the deterministic tools, each with an ID: every structural check (`check.bond_valence`), the per-site numbers (`site.La0`), the n and band-gap ranges and end members (`optics.n`, `optics.SrTiO3`), the goal verdicts (`goal.band_gap`), the 3D structure analysis (`spatial.symmetry`, `spatial.poly.Al4`, `spatial.links`, `spatial.ordering`), the CHGNet relaxation and the relaxed checks, and the researcher's measurements.
2. **Three rendered views** of the cell, down the a, b, and c axes, captured from the 3D viewer. The substituted atoms are labeled with their site IDs (for example La0), and the element colors are sent as a legend, so the model can tie what it sees to the evidence.

It returns a strict JSON critique: a verdict (`promising`, `mixed`, `weak`, `insufficient_evidence`), a short summary, strengths and concerns, up to 3 suggested next steps, and up to 3 questions for the researcher. Guardrails:

- Every point cites evidence IDs, and unknown IDs are rejected. A point based only on the images says so ("seen in the image").
- Every decimal number in the text must appear in the evidence at the precision written. Muse Spark gets one retry to fix a problem; problems that remain are shown with the critique.
- The critique is labeled "AI review: an opinion, not evidence". It never changes an evidence tag, a check, or a score. The evidence it saw is stored with it, and it is included in the JSON export.
- "Ask the agent to test this" sends a suggestion to the research agent, which makes and checks the new candidate with the usual tools.

### Export

| File | Contents |
|---|---|
| `LL-0003.cif`, `LL-0003-relaxed.cif` | The P1 cell (every site, in the same order as the site indices in the app) with a comment header: candidate ID, original host and source, all substitutions from the root formula, the geometry (host positions or CHGNet settings), and the export time. ASCII only, as CIF 1.1 requires; tested with the pymatgen and ASE readers |
| `LL-0003-record.json` | Format `lumilattice.candidate-record/1`: the full candidate (structure, substitutions, checks with their methods, n and band-gap evidence with tags, decisions, measurements, relaxation), its ancestry back to the original host, the goal and goal score, the 3D structure analysis (unrelaxed and relaxed), the data sources with versions, licenses, and SHA-256 of the bundled datasets, the evidence-tag definitions, and the caveats |

The same files are available from the API:

```bash
curl -OJ "http://localhost:8000/api/candidates/LL-0003/export.cif"               # add ?relaxed=true
curl -OJ "http://localhost:8000/api/candidates/LL-0003/export.json?target_n=2.2&min_band_gap=3.0&forbidden=Pb,Cd"
```

Candidates are **private by default**. Publishing needs explicit consent and a credit choice (by name/ORCID or anonymous). In this version, publishing records the choice only; nothing is sent outside LumiLattice.

Candidates are kept in memory unless `DATABASE_URL` points to a Postgres database (for example the free plan of Neon or Supabase); then they survive restarts.

## API usage limits

- Materials Project and OpenAlex responses are cached for 24 hours. OpenAlex stops at 500 searches per day (half of its free daily budget) and stops early if the free budget left for the day falls below $0.05. Materials Project has a cap of 1,000 requests per day.
- Crossref (public pool, 1 request per second), arXiv (1 request per 3 seconds, as its API terms ask), Semantic Scholar (optional free key), and COD are free; they are cached and capped too. If a source rate-limits or times out, it is skipped for 10 minutes so the other sources still answer quickly. No personal email address is sent.
- The public demo protects Meta Model API credits: at most 10 agent requests per client per 10 minutes and 200 per day, with at most 8 tool steps per request. Critiques count as agent requests (one request, plus at most one retry).

## Run locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+.

Backend:

```bash
cd backend
cp .env.example .env   # then add your MODEL_API_KEY
uv sync --group relax  # --group relax adds CHGNet + PyTorch (optional, about 1 GB)
uv run --group relax uvicorn app.main:app --reload --port 8000
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

## Languages

English and Korean are written by hand. Chinese (Simplified), Japanese, Spanish, and German are machine-translated by Muse Spark with a strict JSON schema; the script rejects any output that drops a key or a `{placeholder}`, and the UI marks these languages as machine-translated. Only strings that a language does not have yet are sent, so earlier translations stay stable. Scientific messages from the backend (check results, findings) are in English.

```bash
cd backend
uv run python -m scripts.translate_ui          # new strings, all four; or e.g.: ja de
uv run python -m scripts.translate_ui --all    # translate every string again
```

## Deploy

The backend runs on Render (Docker, free plan) and the frontend on Vercel.

1. **Backend (Render):** New → Blueprint → select this repository. Render reads [`render.yaml`](render.yaml) and asks for `MODEL_API_KEY`, `MP_API_KEY`, `OPENALEX_API_KEY`, and `DATABASE_URL` (optional: a Neon or Supabase Postgres URL; leave it empty to keep candidates in memory). When the deploy finishes, open `https://<service>.onrender.com/api/health`.
2. **Frontend (Vercel):** New Project → import this repository → Root Directory `frontend`. Add the environment variable `NEXT_PUBLIC_API_BASE_URL` = the Render URL (no trailing slash), then deploy.
3. **CORS:** `CORS_ORIGIN_REGEX` in `render.yaml` allows `https://lumilattice*.vercel.app`. If the Vercel project has another name, change it in the Render dashboard.

Limits of the free plan: the backend sleeps after 15 minutes without requests (the next request takes about a minute). Without `DATABASE_URL`, candidates are lost when it sleeps. Open the health URL a minute before a demo.

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
- **JARVIS-DFT** — 3D dataset version 2025-09-24, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), [doi:10.6084/m9.figshare.6815699](https://doi.org/10.6084/m9.figshare.6815699). K. Choudhary et al., *npj Comput. Mater.* 6, 173 (2020); optics: K. Choudhary et al., *Sci. Data* 5, 180082 (2018).
- **refractiveindex.info database** — release 2026-05-24, [CC0](https://creativecommons.org/publicdomain/zero/1.0/). M. N. Polyanskiy, *Sci. Data* 11, 94 (2024). Each measured value links to its page and original reference.

- **Experimental band gaps** — [Expt Gap Data](https://doi.org/10.6084/m9.figshare.7289687.v1), MIT license on the Figshare record. Y. Zhuo, A. Mansouri Tehrani, J. Brgoch, "Predicting the Band Gaps of Inorganic Solids by Machine Learning", *J. Phys. Chem. Lett.* 9, 1668 (2018).

- **Crystallography Open Database** — experimental structures, [CC0](https://creativecommons.org/publicdomain/zero/1.0/). S. Gražulis et al., *J. Appl. Cryst.* 42, 726 (2009). Credit the original authors shown with each entry.
- **Crossref** — scholarly metadata (public REST API).
- **arXiv** — preprint metadata via the arXiv API. Thank you to arXiv for use of its open access interoperability.
- **Semantic Scholar** — paper metadata via the Semantic Scholar Academic Graph API.
- **CHGNet** (optional, local) — B. Deng et al., *Nat. Mach. Intell.* 5, 1031 (2023), BSD-3-Clause license.

## License

[Apache-2.0](LICENSE)
