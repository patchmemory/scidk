# LwM 2026 demo: planning quantitative research with a knowledge graph

Materials for the *Learning with Machines* workshop session on **October 5, 2026**
([lwm.mit.edu](https://lwm.mit.edu)).

The study is a protocol-development experiment from the Koch Institute's preclinical
imaging core: **13 mice in 5 cages**, imaged weekly from **week 6 to week 14** after tumor
induction (Jan 22 – Mar 19, 2024) on **IVIS**, **Bruker SkyScan microCT** and **Bruker MRI**
to compare how well each tracks lung tumor burden.

> **What's real.** The study structure (mice, weeks, acquisition dates, missing weeks,
> dropouts) comes from the study folders and the facility's file index. The measurements are
> the image analyst's results, kept as delivered in `source_results/`.
> **Still placeholders:** acquisition parameters (marked `values_source` on each session),
> which mouse sits in which cage, and sex and age (left blank). Every node the loader writes
> carries `demo_dataset: 'LWM-DEMO-2026'`, so it can be queried and removed on its own.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/patchmemory/scidk/blob/production-mvp/demo_data/lwm2026/lwm_plan_next_study.ipynb)

## The data

| | microCT | MRI | IVIS |
|---|---|---|---|
| Measures | aerated lung, % of total lung volume (falls as tumor grows) | tumor ROI size, pixels | total flux, p/s (supine, plus prone/left/right views) |
| Mice analyzed | 13 | 8 (10–15, 17, 19) | 4 (10, 13, 14, 15) |
| Missing week | 12 (specialist on vacation) | 10 (specialist on vacation; mouse 13 scanned early, not segmented) | none |
| Other | mouse 75 leaves after week 11 | mouse 15 only week 6; 17 and 19 start week 8 | mouse 13 has no supine week 14 |

What the analysis shows: little tumor signal before week 11; from week 11, microCT and MRI
agree closely (within-week Spearman 0.86–0.96) on mice 13, 17, 10 and 12 as the high-burden
animals. IVIS separates high (10, 13) from low (14, 15) but ranks mouse 10 above 13.

## What's here

| File | What it does |
|---|---|
| `lwm_plan_next_study.ipynb` | The workshop notebook: setup and the study at a glance (summary and coverage grid), then four parts. **A.** What each modality sees: resolution, when tumors become visible, agreement, time, cost and storage per scan. **B.** Designing a tumor-reduction study: enrollment by imaging, endpoints, mice per arm by effect size, scans, cost. **C.** What the data says about the USGI tumor model: take rate and tumor onset, and mice to inject. **D.** Curating the data, hands-on: coverage by week and by mouse, the files and machines behind each session, and a curation plan from an AI assistant through MIT's Parley API. An appendix shows the graph queries underneath. |
| `CURATION_PROMPT.md` | The curation prompt from part D, with a template for writing a coverage report for your own dataset. |
| `lwm_study.py` | The analysis and figures behind the notebook, as one `Study` class: each notebook cell is one call, such as `study.mice_per_arm()`. Also the curation prompt and the Parley API helpers. |
| `lwm_colab.py` | Starts a private Neo4j inside a Google Colab session and loads the study graph into it. |
| `lwm_graph.py` | Helper used by the notebook. Every question has a named Cypher query (`g.show(name)`) and an offline pandas version, so the notebook runs with or without a database. |
| `source_results/` | The analysis results exactly as delivered (microCT, MRI, IVIS spreadsheets exported to CSV), the file inventory, the parsed instrument tables, and the raw listings they came from (`listings/`). |
| `parse_instrument_files.py` | Turns the instrument-file dumps in `source_results/listings/` into `acq_microct.csv`, `acq_mri.csv` and `acq_ivis.csv`: every scan's parameters and timestamps from the SkyScan reconstruction logs, ParaVision `method`/`acqp` files and Living Image `ClickInfo` files. |
| `build_file_inventory.py` | Turns the raw file listings in `source_results/listings/` (Dropbox study folder, atwai folders, MRI scanner logs) into `source_results/file_inventory.csv`: one row per folder or file, mapped to modality, week and mouse, and classified as raw, copy, derived, result or document. |
| `generate_demo_data.py` | Builds `data/` from the study structure (constants at the top: `MICE`, `DATES`, ...) and `source_results/`. Stops with an error if any result has no matching imaging session. |
| `data/` | What gets loaded: `study.json`, `subjects.csv`, `sessions.csv` (acquisition metadata in `params_json`), `measurements.csv`, `observations.json`, and the extra nodes and links: `nodes.csv` (File, Folder, Acquisition, Instrument) and `links.csv`. |
| `build_plan_nb.py` | Rebuilds the notebook from source. |
| `dump_notebook.py` | Writes the notebook's results as plain text (`review/notebook_results.txt`) and its figures as PNGs, for review. `--execute` runs it first. |
| `load_demo_graph.py` | Loads `data/` into Neo4j. Safe to re-run; `--wipe` removes only the demo nodes. |
| `serve_colab_tunnel.sh` | Opens an ngrok TCP tunnel to the Neo4j Bolt port so Colab can reach the graph. |

## Run it

**In Google Colab (no setup).** Open the notebook with the badge above and run every cell. The first
cell starts a private Neo4j inside your Colab session (`lwm_colab.py`: Java, Neo4j Community, then
the study graph; about 2 minutes) and the notebook runs against it. Nothing to share and no VPN; the
database disappears when the session ends. Set `LIVE_GRAPH = False` in that cell to use the bundled
CSV files instead.

**Run the notebook against a local Neo4j.** Give it the connection settings in a `neo4j.env` file
next to the notebook (git-ignored). The easiest way is to link the kit's target file:
```bash
ln -s ~/Downloads/lwm_neo4j/targets/laptop.env neo4j.env     # or copy neo4j.env.example
jupyter lab lwm_plan_next_study.ipynb
```
The setup cell prints which file it read and `Connected: Neo4j at ...`. If it says the neo4j driver
isn't installed (common on shared Jupyter servers such as MIT Engaging), run `%pip install neo4j` in a
cell, restart the kernel, and run setup again. If it can't connect, it says
why and falls back to the bundled files.

**Send the curation prompt to Parley (MIT).** Part D can send its curation prompt to MIT's
Parley API. Get a key from the Parley Admin Portal (*My Keys*), then paste it when the cell asks, or
put `PARLEY_API_KEY=sk-parley-v1-...` in a git-ignored `parley.env` next to the notebook. The answer
is saved to `export/curation_plan.md`.

**Load the graph.** With the standalone Neo4j kit (`lwm_neo4j/`):
```bash
python3 generate_demo_data.py                                  # rebuild data/ (optional)
.../lwm_neo4j/run_on.sh laptop  python3 load_demo_graph.py --wipe   # test locally
.../lwm_neo4j/run_on.sh demo-vm python3 load_demo_graph.py --wipe   # then the VM
```
Expected node counts: ImagingSession 318, Measurement 238, Subject 13, Observation 15,
Modality 3, Study 1, Folder 615, File 386, Acquisition 427, Instrument 3, Host 5. Expected timeline gaps:
```
MRI      week 9 -> 11  (12 mice)
microCT  week 11 -> 13  (12 mice)
```

**The files on disk.** Each imaging session links to the data that holds it, using the same
`File`/`Folder` labels SciDK uses:

```
(ImagingSession)-[:STORED_IN]->(Folder|File)       microCT reconstruction, MRI DICOM and scanner study folder, IVIS weekly folder
(ImagingSession|Subject)-[:HAS_DERIVED]->(...)     exports, Dragonfly ROIs, NIfTI conversions, analysis outputs
(Folder|File)-[:COPY_OF]->(Folder|File)            every duplicate points at the canonical copy
(Measurement)-[:REPORTED_IN]->(File)               the results table each value came from
(Study)-[:HAS_FOLDER]->(Folder)-[:CONTAINS]->(...) the top folders on Dropbox and atwai
(Folder|File)-[:ON_HOST]->(Host)                   the machine each top folder and results file sits on
(Host)-[:SYNCED_TO]->(Host)                        Dropbox is synced to ki-ed3g
(Instrument)-[:WRITES_TO]->(Host)                  microCT -> instrument PC, MRI -> bmc-lab6
(Acquisition)-[:WRITTEN_ON]->(Host)                microCT scans written on the instrument PC
```

Every File and Folder also has a `host` property (`dropbox`, `bmc-lab6`, `github`), so the query
`session_hosts` can say which machines hold each session and its copies. In this study IVIS is on
Dropbox only, and microCT weeks 7, 13 and 14 are on bmc-lab6 only (their copies are on the same server).

Each session also links to its **instrument records**: `(ImagingSession)-[:HAS_ACQUISITION]->(Acquisition)-[:ON_INSTRUMENT]->(Instrument)`.
An Acquisition is one microCT scan, MRI series or IVIS image, with the parameters and timestamps the
instrument wrote; the Instrument holds the facility rate and the time model measured from those
timestamps. The key parameters and timing are also copied onto each ImagingSession.

To refresh from new listings: `python3 build_file_inventory.py && python3 parse_instrument_files.py && python3 generate_demo_data.py`.

The listings in `source_results/listings/` were made on ki-ed3g with:
```bash
# files on Dropbox (from MultiModal/LungTumor) and on atwai (scan index)
find . -type f -printf '%s\t%TY-%Tm-%Td\t%P\n'
sqlite3 -readonly -header -csv ~/.scidk/scans/atwai_scan.db "SELECT parent_path, count(*) AS files, sum(size) AS bytes FROM files WHERE parent_path LIKE '%MultiModal Lung tumor test%' OR parent_path LIKE '%longitudinal mouse lung tumors%' GROUP BY parent_path"
# MRI raw data sizes (ParaVision study folders) -> atwai_mri_sizes.csv.gz
sqlite3 -readonly -header -csv ~/.scidk/scans/atwai_scan.db "SELECT parent_path, count(*) files, sum(size) bytes FROM files WHERE parent_path LIKE '%huangw/2024/%ulti%ung%' GROUP BY parent_path" | gzip > atwai_mri_sizes.csv.gz
# instrument files
ssh bmc-lab6 'for f in ".../raw data/"*_Rec/*.log; do grep -H "=" "$f"; done'            # SkyScan logs
ssh bmc-lab6 'for d in .../huangw/2024/*AIPT_*ulti*ung*/*/; do ... method/acqp ...; done'  # ParaVision
find IVIS -iname 'ClickInfo*.txt' -exec grep -H ":" {} +                                    # Living Image
```

**Rebuild the notebook after changing the data:**
```bash
python3 build_plan_nb.py
jupyter nbconvert --to notebook --execute --inplace lwm_plan_next_study.ipynb
```

**Let Colab reach the graph (during the session):**
```bash
ngrok config add-authtoken <token>           # once
bash serve_colab_tunnel.sh                   # prints e.g. 4.tcp.ngrok.io:12345
```

## Before exposing Neo4j through ngrok

- **The tunnel is public.** Use a Neo4j instance that holds only this data, give it a
  throwaway password and close the tunnel after the session. Neo4j Community has no
  read-only roles, so every login can write.
- **Traffic is unencrypted.** Bolt over a plain TCP tunnel sends the password in clear text.
- **ngrok TCP needs a card on file,** even on the free plan. The card isn't charged.
- **Use `bolt://`, not `neo4j://`.** The routing scheme would send clients to the VM's
  internal address.

## Still to fill in

- **Subjects:** cage/ID pairing, sex and age from `LungTumorMouseID.xlsx`.
- **IVIS week 13:** the Dropbox week-13 folder is a copy of week 12, though the results have
  week-13 values; the date in the data (Mar 12) is a guess.

Sources: microCT reconstructions on atwai under `Milton_CornwallBrady/Protocol Development in
vivo/MultiModal Lung tumor test` (also in `Anderson_Scott/Multimodal/...` and the archive);
analysis outputs in `Anderson_Scott/Multimodal/MultiModal Lung tumor test/processed data`;
MRI, IVIS and summary spreadsheets in the Dropbox folder `MultiModal/LungTumor`.

## License and data use

- **Code** in this folder: the repository's license (see `LICENSE` at the top of the repository).
- **Data** in `data/` and `source_results/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  Credit: "Koch Institute Preclinical Imaging & Testing Facility, multimodal lung tumor
  protocol-development study (2024)."

These are unpublished pilot results from a protocol-development study, shared for teaching with the
approval of the image analyst and the facility director. If you would like to use them in a
publication or presentation, please contact [name, email] first. We are glad to help and to make
sure the data are used in context.
