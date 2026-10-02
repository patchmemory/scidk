"""build_plan_nb.py: builds lwm_plan_next_study.ipynb, the LwM 2026 workshop notebook.

The notebook stays short: each code cell calls lwm_study.Study or lwm_graph. Edit text and
calls here, then run this script and execute the notebook."""
import nbformat as nbf

nb = nbf.v4.new_notebook()
C = []
md = lambda s: C.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: C.append(nbf.v4.new_code_cell(s.strip()))

md("""
# Planning the next study from the last one
**Learning with Machines workshop, October 5, 2026**

The Koch Institute's preclinical imaging core ran a **protocol-development study**: lung tumors from
a luciferase-reporter cell line delivered by ultrasound-guided intratracheal injection (USGI) in
**13 mice**, imaged weekly from **week 6 to week 14** on **microCT**, **MRI** and **IVIS**. The point
was to compare how well each modality measures lung tumors, so the image analyst focused on the
mice where there was tumor to measure.

Everything about the study sits in a knowledge graph: the mice, every scan, the analysis results,
the notes about what went wrong, and the files on disk. This notebook starts with what the study
holds, then mines it in four parts:

* **A. What each modality sees:** resolution, when tumors become visible, how well the modalities
  agree, and what a scan costs in time, money and storage.
* **B. Designing a tumor-reduction study** with those measurements: enrollment, endpoints, length,
  number of mice, total cost.
* **C. What the data says about the tumor model itself,** a question the study never set out to
  answer: how often USGI produced a measurable tumor, and when.
* **D. Curating the data, hands-on:** where the gaps and the files are, then a curation plan drafted
  by an AI assistant through MIT's Parley API.

> **What's real here:** the study structure, the analysis results, every scan's instrument
> parameters and timestamps, the files on disk and the facility's hourly rates. **Still
> placeholders:** which mouse sat in which cage, sex and age. With 4 to 13 mice per measurement,
> every estimate below is a starting point for discussion, not a final design.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/patchmemory/scidk/blob/production-mvp/demo_data/lwm2026/lwm_plan_next_study.ipynb)

**Two ways to run it:** offline from the bundled files (no setup), or against the live graph: put
the connection settings in a `neo4j.env` file next to this notebook, or in Colab enter the address
and password the presenter shares. The setup cell says which one it is using.

**About the code:** each cell asks one question with one short call. The analysis behind it lives in
`lwm_study.py` (and the graph queries in `lwm_graph.py`); add `??` after any call, as in
`study.mice_per_arm??`, to read how it works.
""")
md("""
## 0 · Setup and the study at a glance
""")
code("""
# Google Colab only: fetch the helper module and data from the SciDK repo
import os, sys
IN_COLAB = "google.colab" in sys.modules
if IN_COLAB:
    REPO = "https://github.com/patchmemory/scidk"
    BRANCH = "production-mvp"
    SUBDIR = "demo_data/lwm2026"
    !pip -q install "neo4j>=5.8"
    if not os.path.exists("/content/scidk"):
        !git clone -q --depth 1 --branch {BRANCH} {REPO} /content/scidk
    %cd /content/scidk/{SUBDIR}

    LIVE_GRAPH = True   # run a private Neo4j in this Colab session (~2 min); False = bundled files
    if LIVE_GRAPH:
        try:
            from lwm_colab import start_neo4j
            start_neo4j()
        except Exception as e:
            print(f"Couldn't start Neo4j here ({e}); the notebook will use the bundled files.")
""")
code("""
from lwm_graph import connect
from lwm_study import Study, curation_prompt, ask_parley, proposed_notes

g = connect()          # the live knowledge graph if settings are given, otherwise the bundled files
study = Study(g)       # loads the sessions, measurements and notes once
""")
md("""
### The last study in one call

One query over the graph summarizes every modality (the appendix shows the query):
""")
code("""
study.summary()
""")
md("""
Every modality imaged all 13 mice. The analyst measured microCT in all of them, MRI in the 8 with
visible tumor, and IVIS in 4 chosen to span high and low tumor burden: the right choices for comparing
measurement protocols, and worth keeping in mind for what each number below can support.
""")
md("""
### What exists, by mouse, modality and week

Every imaging session in the graph knows whether it was **measured** (an analysis result points to
it), whether its **files are on disk** (it is `STORED_IN` a folder or file), or only that it
**happened** (the session is in the study but no files were found):
""")
code("""
study.plot_coverage()
""")
md("""
Each modality tells a different coverage story. **microCT** is complete except the vacation week and
mouse 75, which left after week 11. **MRI** scanned every mouse but was analyzed only in the 8 with
tumor: the rest is on disk, unanalyzed. **IVIS** imaged every cage but was analyzed in 4 mice, and its
week-13 images were never found.
""")
md("""
---
# A · What each modality sees

## A1 · Resolution and units

Each modality turns a tumor into a different kind of number, at a different resolution. Every
imaging session in the graph carries the parameters its instrument recorded: the SkyScan
reconstruction log for microCT, the ParaVision `method` file for MRI, and Living Image's
`ClickInfo` for IVIS.
""")
code("""
study.resolution()
""")
md("""
### Did the protocol stay the same?

The same parameters, week by week, straight from each session's instrument record:
""")
code("""
study.protocol_by_week()
""")
code("""
study.protocol_changes()
""")
md("""
Four changes surfaced from the instrument files alone, none of them written down anywhere else:
microCT exposure went up at week 8 and week 14 used a fixed reconstruction range; MRI covered 20 mm
instead of 23 mm in week 12; IVIS switched to short exposures once tumors got bright. The MRI change
matters for analysis: a large tumor could extend past the covered region that week.
""")
md("""
The MRI results are reported as "pixel counts". Are they areas on one slice, or volumes summed over
slices? The data answers it: one 256 × 256 slice has 65,536 pixels.
""")
code("""
study.mri_units()
""")
md("""
microCT measures tumor *indirectly*: tumor displaces air, so what the analysis reports is the aerated
fraction of the lung. Its 37 µm voxels are fine enough to see small nodules, but the reported number
only moves once enough lung is filled. MRI measures the tumor *directly* at coarser resolution.
IVIS measures *living tumor cells* by their light, not tumor size.
""")
md("""
## A2 · Tumor growth, as each modality saw it

For comparison, microCT is shown as **lung lost to tumor**: each mouse's own baseline (mean of weeks
6–8) minus that week's aerated %.
""")
code("""
study.plot_growth()
""")
md("""
Until about week 10 little changes. From week 11 the mice with tumor pull away on every modality,
while several mice on microCT stay flat for the whole study. The MRI values before week 10 (about
2–20 mm³) are not tumor: they are the floor of the segmentation, what an ROI picks up when there is
nothing to find. The gaps are the vacation weeks (MRI week 10, microCT week 12).
""")
md("""
## A3 · When does each modality see a tumor?

**Noise:** how much a measure jumps from week to week in the same mouse before there is any tumor
(weeks 6–9). **Signal:** how far mice with tumor have moved from their own baseline. A modality sees
the tumor once the signal clears the noise. A mouse counts as having **visible tumor** if it lost
more than 10 points of aerated lung by its last scan.
""")
code("""
study.plot_visibility()
""")
md("""
microCT and MRI both see tumor from about **week 11**, with two caveats. MRI skipped week 10 (only
one mouse was scanned, and not analyzed), so MRI may have seen tumor a week earlier; microCT at week
10 sits just under the line. IVIS crosses at week 9, but from only 3 mice with tumor, so treat that as a
hint rather than a finding.
""")
md("""
## A4 · Do the modalities agree?

Within a single week, do the mice with the most lung lost on microCT also have the most tumor on MRI?
""")
code("""
study.agreement()
""")
md("""
Before week 11 there is not enough tumor for the two to agree. From week 11 they rank the mice almost
identically (ρ 0.86 to 0.96). They measure the same tumors in different ways, which is the
result a protocol-development study hopes for.
""")
md("""
## A5 · Time and cost per scan

The facility bills imaging by the hour. Time per session depends on how many mice go through the
instrument at once: microCT and MRI image one mouse at a time; IVIS images a cage (up to 5) per
acquisition. These times come from the instruments' own timestamps:
""")
code("""
study.cost_per_scan(n_mice=10)
""")
md("""
Checking the time model against how long each weekly session actually took, from the session times in the graph:
""")
code("""
study.session_times()
""")
md("""
The model tracks the real sessions well. The exceptions have explanations in the data: MRI week 8
ran over an hour long, week 10's MRI was a single mouse with extra series, and IVIS week 11 ran over
two days (week 13's images are the misfiled ones). For reference, what this study's imaging cost:
""")
code("""
study.imaging_cost_so_far()
""")
md("""
## A6 · Storage and software per scan

What this study occupies today, measured from the files on Dropbox and the facility share (atwai):
""")
code("""
study.storage()
""")
md("""
The same total by modality. `CFT` is cryofluorescence tomography, an endpoint imaging method that is not one of the three modalities compared here:
""")
code("""
study.storage_by_modality()
""")
md("""
Per mouse-scan, from the size of the data each session is stored in:
""")
code("""
study.storage_per_scan()
""")
code("""
study.software()
""")
md("""
microCT dominates storage at about half a gigabyte per mouse per scan. MRI is about 75 MB, mostly the
scanner's raw ParaVision data (the DICOM export is 6 MB); IVIS is a few megabytes. Across the study,
about 150 GB are copies: the microCT reconstructions sit in up to four places. The cryofluorescence
(CFT) endpoint volume on Dropbox is the single largest item, about 106 GB in one folder that no
imaging session in the graph points to.
""")
md("""
---
# B · Designing a tumor-reduction study

Suppose the next study tests a therapy meant to shrink or slow these tumors. Part A gives everything
needed to design it:

1. **Inject, then enroll by imaging.** Screen at weeks 10–11, when tumor first clears the noise on
   microCT and MRI. Enroll only mice with visible tumor, and randomize with stratification by tumor
   size so both arms start alike. (Part C estimates how many mice to inject to enroll enough.)
2. **Treat and image weekly** from enrollment. In this model the window is about **3–4 weeks**:
   tumors just visible at week 11 reached the largest burden in the study by week 14 (mouse 13 had
   about 11% of its lung still aerated). That also brings the study close to humane endpoints.
3. **Choose the endpoint before the first scan:**
   * change from each mouse's own enrollment scan (fold change or growth rate), with enrollment size
     as a covariate: the most efficient use of imaging
   * tumor size at a fixed week, treated vs. control (tumor growth inhibition)
   * regression: smaller than at enrollment
   * time to progression, or survival if the study continues past imaging

## B1 · How many mice?

An **arm** is one group of the study: here a treated arm and a control (vehicle) arm. "Mice per arm"
is the size of each group, so a two-arm study enrolls twice that many.

The number of mice depends on the effect you need to detect and on how much the measure varies
between mice with tumor. Two designs, from this study's variability:

For a measure on a log scale with between-mouse standard deviation SD, the mice per arm to detect a
fractional reduction *effect* (5% significance, 80% power) is

  **n = 2 × ((1.96 + 0.84) × SD / ln(1 − effect))²**
""")
code("""
study.mice_per_arm(effects=[0.2, 0.3, 0.4, 0.5, 0.7, 0.8])
""")
md("""
For comparison, most published mouse imaging efficacy studies use **about 5–10 mice per arm**. This
model gets there for the large effects that a successful therapy usually shows (70–80% less tumor):
about 2–5 per arm on microCT, 6–15 on MRI. Detecting a subtle 40% effect takes several times more,
which is a reason to improve the model before running that study, not to use hundreds of mice.
IVIS ("—") was measured in too few mice with tumor to estimate.

There is no microCT growth row on purpose. microCT's number is lung *lost*, not a tumor volume: at
enrollment it is close to zero (sometimes negative), so a fold change from it is unstable, and it
cannot grow past the size of the lung. Growth on microCT is handled as a rate in points per week (B2).

One more caution: a spread estimated from 7 mice is itself uncertain.
""")
code("""
study.sd_uncertainty(effect=0.7, k=7)
""")
md("""
## B2 · How many scans?

For a growth-rate endpoint, every extra weekly scan sharpens each mouse's estimate, up to a point.
Mice needed to detect **50% slower growth**, by number of weekly scans after enrollment:
""")
code("""
growth_multiplier = 0.5
study.scans_needed(slower=growth_multiplier)
""")
md("""
**The endpoint picks the modality.** For tumor size at a fixed week (B1), microCT needs the fewest
mice. For growth rate, MRI does: on a log scale its tumors grow at a similar rate in every mouse
(0.74 ± 0.32 per week), so four scans pin each mouse's rate down and about 12 mice per arm detect a
halving. microCT's rate in points of lung varies far more between mice (9 ± 6 points per week), and
that spread is real biology plus a measure that saturates, so extra scans don't help: it stays near 30
per arm.

Either way the gains stop at about **four weekly scans**, which is also the window this model allows
(weeks 11–14). IVIS is left out: too few mice.

## B3 · What would the study cost?

Two arms of the headline design (70% effect, size at week 14), a screening scan at week 10 for every
injected mouse, then weekly scans of the enrolled mice from week 11 (set the number of scans here;
4 covers weeks 11–14, the window this model allows):
""")
code("""
SCANS_AFTER_ENROLLMENT = 10
study.design_cost(effect=0.7, scans_after_enrollment=SCANS_AFTER_ENROLLMENT, copies=2)
""")
code("""
study.xray_dose(scans=1 + SCANS_AFTER_ENROLLMENT)     # screening scan + weekly scans
""")
md("""
Radiation at that level can slow tumor growth on its own, so a microCT-based design should image
both arms identically and keep the number of scans to what the endpoint needs.

Enrollment needs a screening scan of every injected mouse, and how many to inject depends on how
reliably the model produces tumors. That is part C.
""")
md("""
---
# C · What the data says about the tumor model

The study was designed to compare measurements, not to test the USGI injection. But microCT was
analyzed in every mouse, so the data can answer a question nobody asked: **how often did the
injection produce a measurable tumor, and when did it appear?**

Mice 67, 68, 69 and 75 were controls (not injected), so they are left out of the take rate. Edit the
list below and rerun to see how the answer changes.
""")
code("""
study.tumor_outcomes()
""")
code("""
NOT_INJECTED = ["M67", "M68", "M69", "M75"]     # controls: not injected
study.take_rate(not_injected=NOT_INJECTED)
""")
md("""
The tumors that took split into two clear groups: lung lost by week 14 is 13 to 70 points in seven
mice and essentially zero in the rest, so the take rate barely depends on the threshold. Onset is
consistent: one tumor was visible at week 10, five at week 11, and one (mouse 14) only at week 14. A
therapy study enrolling at week 11 would catch six of the seven and miss the slow one.

### Mice to inject

Put it together: to enroll the mice part B needs, inject enough to cover the take rate and early
losses, then add the screening scan:
""")
code("""
study.mice_to_inject(effect=0.7, not_injected=NOT_INJECTED, scans_after_enrollment=SCANS_AFTER_ENROLLMENT)
""")
md("""
The tumor model, not the imaging, sets how many animals the study uses: with 7 of 9 injected mice
growing a measurable tumor, about 1.3 mice must be injected for every mouse enrolled. Improving the injection (dose, technique, confirming delivery) is the cheapest
way to cut animal numbers.
""")
md("""
---
## The plan, side by side
""")
code("""
study.plan(effect=0.7, not_injected=NOT_INJECTED, scans_after_enrollment=SCANS_AFTER_ENROLLMENT)
""")
md("""
**Takeaways for the next study**

* **Enroll by imaging at weeks 10–11** and image weekly for about four weeks; earlier scans mostly
  record baseline in this model.
* **microCT** is the cheapest per scan, needs the fewest mice and generates the most data. Its
  measure is indirect (air displaced), so pair it with MRI on a subset if tumor volume matters.
* **MRI** measures the tumor directly but costs the most per scan and varies more between mice.
* **IVIS** needs to be analyzed in every animal, in one agreed view, before it can carry an endpoint.
* **The tumor model sets the animal count:** about 1.3 injections per enrolled mouse (78% take).
  Improving take is the most effective reduction.
* **Plan the data too:** one canonical copy, one long results table, a reason for every gap.
""")
md("""
---
# D · Curating the data, hands-on

The coverage grid at the top showed what exists. Two more angles show what it can support. First,
how many mice have analyzed data on more than one modality in the same week? That is what any
comparison between modalities can use:
""")
code("""
study.coverage_by_week()
""")
md("""
And per mouse: how long a series does each mouse have on each modality? Mice marked ★ had visible
tumor on microCT.
""")
code("""
study.coverage_by_mouse()
""")
md("""
Only four mice have all three modalities analyzed over time, and they were chosen to span high and low
tumor burden. The unanalyzed MRI and IVIS sessions are the cheapest new data this study can offer:
they are already on disk.

### What's on disk now

Putting this study into the graph surfaced the usual problems:

* **Copies that disagree:** microCT reconstructions in three identical places on the facility
  share, plus a Dropbox copy that stops at week 11.
* **A misfiled folder:** the Dropbox "week 13" IVIS folder is a copy of week 12, though the analysis
  sheet has real week-13 values.
* **Inconsistent names:** `12T2axial.dcm`, `15T2.dcm`, `17-T2W.dcm`, `1013_T2_axial.dcm` (mouse 13);
  microCT week 7 named by cage and ear punch on Dropbox; MRI sessions named `multimodelLung`,
  `multiModelLung` and `multimodalLung` on the scanner.
* **Results versioned by file name:** `... measurements 2 (Milton's changes 2024-05-28).xlsx`.
* **Results as presentation spreadsheets:** the IVIS sheet holds four views, a duplicate block and
  a %-change table in one grid, which had to be parsed by hand.
""")
md("""
### From the graph to the files

The graph records where every session's data lives: which folder or file holds it, what was derived
from it, and how many copies exist. For one mouse in one week:
""")
code("""
files = g.run("session_files")
files[(files.subject == "M13") & (files.week == 13)]
""")
md("""
Mouse 13's week 13 lives in several places: the MRI scanner's study folder and an exported DICOM
(with an XNAT copy), and a microCT reconstruction with two more copies and a NIfTI conversion beside
it. Section A6 sums the same idea over the whole study.
""")
md("""
### Which machines hold each session?

Every folder and file in the graph carries the machine it sits on, and each top folder links to a
`Host` node: the Dropbox folder (synced to ki-ed3g), the facility file server bmc-lab6 that serves
atwai, the microCT instrument PC that wrote the scans, and the GitHub repository with the results.
""")
code("""
g.show("hosts")
g.run("hosts")[["host", "role", "note", "synced_to"]]
""")
md("""
Following each session to the data it is stored in, and to every copy of that data, gives the set of
machines holding it. Each cell below shows where that modality's sessions for that week can be found:
""")
code("""
g.show("session_hosts")
study.where_sessions_live()
""")
code("""
study.single_host_sessions()
""")
md("""
What this shows:

* **IVIS exists only on Dropbox.** No copy on the facility server was found, so the Dropbox folder
  is the only place the optical data lives. The week-13 images were not found anywhere: the week-13
  folder is a copy of week 12, though the results have week-13 values.
* **MRI is on both machines**, but they are not the same data: the DICOM exports are on Dropbox and
  the ParaVision raw study folders are on bmc-lab6.
* **microCT weeks 7, 13 and 14 are on bmc-lab6 only** (plus mouse 18 in week 11). Those sessions have
  several copies, but all on the same server under different users' folders, so they are duplicates,
  not a backup. Week 7 does have copies on Dropbox, but named by cage rather than mouse, so they can't be
  matched to a session.

Counting copies says a session is safe; asking *which machines* hold them says whether it is.
""")
md("""
### Ask an assistant to curate it

Everything above can be condensed into a short **coverage report**: a text grid of what exists, the
notes and gaps, examples of how files are named today, and where they are stored. Paired with a
curation prompt, it can be given to any AI assistant (Claude, ChatGPT, a local model).

The prompt asks for a short, standard answer rather than an essay: the gaps and risks, the
**standard data objects** every study should keep (README, subjects, sessions, a long measurements
table, a data dictionary, a notes log, a file manifest), a **naming and folder convention** with
before → after examples from this study's own files, a one-line-per-element draft of an **NIH Data
Management and Sharing plan**, and the top five actions. Facts must come from the report; the
conventions follow NIH DMS policy, FAIR principles and library guidance on file naming.
""")
code("""
%%time
report = study.coverage_report()
print(report)
""")
code("""
%%time
prompt = curation_prompt(report)
""")
md("""
### Send it to MIT's Parley API

MIT's [Parley](https://parley.mit.edu/) gateway gives everyone at MIT access to models from OpenAI,
Anthropic (Claude, through AWS Bedrock) and Google through one OpenAI-compatible API, billed to their
own account. To run the prompt yourself:

1. **Sign in** to the Parley Admin Portal with your MIT credentials. The first sign-in creates a
   personal account with free credit; students get \\$10, faculty and staff \\$30. This prompt costs a
   few cents per run.
2. **Copy your key** from *My Keys*. It looks like `sk-parley-v1-...`.
3. **Run the next cell** and paste the key when asked. It is held in memory only and never saved in
   the notebook. To skip the prompt, put `PARLEY_API_KEY=sk-parley-v1-...` in a `parley.env` file
   next to the notebook (git-ignored) or set it as an environment variable.

Two rules: **treat the key like a password** (never paste it into a cell, a slide or a chat), and
send Parley only **low- or medium-risk data**, per MIT policy. This report is fine: mouse IDs, weeks
and file locations, no people's data.
""")
code("""
%%time
from IPython.display import Markdown
answer = ask_parley(prompt)            # or ask_parley(prompt, model="...") to pick a model
if answer:
    display(Markdown(answer))
""")
md("""
The proposed notes (section 7 of the answer) come back as JSON, so they can be checked as a table
before anything goes into the graph:
""")
code("""
if answer:
    notes = proposed_notes(answer)
    print(f"{len(notes)} new notes proposed; the graph already has {len(study.observations)}")
    display(notes)
else:
    print("No answer yet: run the Parley cell above with your key.")
""")
md("""
**Try it on your own data.** The prompt doesn't depend on this study. Make the same kind of report for
your dataset, even by hand (a row per subject, a column per timepoint, a letter for what exists),
add any notes you already have, and paste both. What comes back is a starting point: check every
claim against the files before acting on it. The notes in section 7 are written so they can go
straight back into the graph as new Observation nodes.
""")
md("""
---
# Appendix · Under the hood

## The whole dataset in one call

This is the query behind the summary at the top. It walks the graph once: every imaging session,
its mouse, its modality and any measurements, then the notes attached to each modality.
""")
code("""
g.show("dataset_summary")
g.run("dataset_summary")
""")
md("""
Because the reasons for gaps live in the graph as notes, the summary can say *why* data is missing:
""")
code("""
g.run("gaps")
""")
md("""
## A layout built from the key variables

The key variables are **study, modality, mouse, week**. Make them the folder path and the file name,
keep raw data read-only, and keep every result in one long table:

```
LungTumor_2024/
├── README.md                    # design, people, protocol, dates
├── study.json                   # machine-readable version of the README
├── subjects.csv                 # mouse, cage, ear punch, group, sex, age
├── observations.json            # gaps, dropouts, QC notes, with reasons
├── raw/                         # read-only, one canonical copy (+ one backup)
│   └── microCT/wk06/M010/ ...   # <modality>/wk<NN>/M<NNN>/ instrument files as written
├── derived/                     # reconstructions, ROIs, masks; each with the software version
│   └── MRI/dragonfly_rois/wk11/M013/ ...
├── results/
│   └── measurements.csv         # mouse, week, modality, kind, value, unit, method, version
└── manifest.csv                 # every file: path, size, checksum, session id
```

The graph can generate both the target path for every session and the long results table, so the
reorganization is a copy job rather than a manual one:
""")
code("""
study.export_layout()
""")
md("""
Principles behind it:

* **One source of truth.** One canonical copy plus a backup; everything else is a link or a query.
* **Raw is read-only.** Derived files record which raw files, software and version produced them.
* **IDs and dates are fixed-width and sortable:** `M013`, `wk06`, `2024-03-12`.
* **Results are long and tidy:** one row per measurement, with its unit and method, never a grid.
* **Versions are a column, not a file name.**
* **Every gap gets a reason, written where the data lives.** That is what made the vacation weeks
  explainable here.
""")
md("""
## Ask your own questions

Every table above comes from a named query. `g.show(name)` prints its Cypher and `g.run(name)`
returns the answer as a pandas DataFrame, live or offline. On the live graph, `g.cypher(...)` runs any
Cypher you write, for example every acquisition of mouse 13 in week 13:
""")
code("""
if g.live:
    display(g.cypher(\"\"\"
        MATCH (se:ImagingSession)-[:HAS_ACQUISITION]->(a)-[:ON_INSTRUMENT]->(i:Instrument)
        WHERE se.id IN ['LWM-MRI-M13-W13', 'LWM-MCT-M13-W13']
        RETURN se.modality AS modality, i.name AS instrument, count(a) AS acquisitions
    \"\"\"))
else:
    print("Custom Cypher needs the live graph. Named questions:", ", ".join(g.queries()))
""")


nb.cells = C
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, "lwm_plan_next_study.ipynb")
print("ok", len(C), "cells")
