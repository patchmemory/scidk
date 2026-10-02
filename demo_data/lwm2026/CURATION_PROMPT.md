# Curating a dataset with an AI assistant

A prompt for turning a **coverage report** (what data exists, per subject and timepoint) into a
short curation plan: gaps and risks, standard data objects, a naming and folder convention, a draft
NIH Data Management and Sharing plan, and the top actions. The workshop notebook builds the report
from the knowledge graph and writes the finished prompt to `export/curation_prompt.md`. For your own
dataset, write the report yourself in the format below, even by hand.

## How to use it

1. Make a coverage report for your dataset (template below).
2. Paste the prompt, then the report, into an AI assistant (Claude, ChatGPT, a local model).
3. Treat the answer as a draft: check every claim against the files before acting on it.
4. Record the notes it proposes (section 7) wherever your study keeps its metadata. In the workshop
   graph they become `Observation` nodes.

Leave out anything you can't share (patient identifiers, unpublished values) and check your
institution's rules for which assistants may see research data.

## The prompt

```text
You are a research data manager helping a lab curate an imaging study so it can be reused,
shared and cited. Below is a coverage report generated from the study's knowledge graph.

Rules:
- Facts about THIS study come only from the report. If something is not in it, write "not in report".
- Recommendations should follow standard practice: the NIH Data Management and Sharing (DMS) Policy,
  FAIR principles, and common library guidance on file naming, folder structure and documentation.
- Be brief. Use tables and bullets, not paragraphs. No more than about 600 words in total.
- Keep mouse, modality, week and note IDs exactly as written in the report. In before -> after
  renames, leave a part as "?" when the name doesn't say it (e.g. a week or a mouse); don't guess.
- Don't invent policy requirements. Under the NIH DMS Policy, scientific data are shared no later
  than publication or the end of the award, whichever comes first; for retention periods and
  repository rules, say "check with your institution and funder".

Answer with exactly these sections:

1. Status (3 bullets): what is complete, what is partial, what is missing.
2. Gaps and risks (table, at most 8 rows): issue | evidence from the report | explained by (note ID) or "unexplained".
3. Standard data objects to keep (table): object | what it holds (key columns or contents) | open format.
   Cover at least: README, subjects table, sessions table, long-format measurements table,
   data dictionary, notes/observations log, file manifest with checksums.
4. Naming and folder convention:
   - one folder pattern and one file-name pattern, built from study, modality, subject, timepoint;
   - the rules in 5 bullets or fewer (e.g. ISO 8601 dates, zero-padded IDs, no spaces, versions as
     a suffix or column, not "final2" or names in parentheses);
   - a before -> after table renaming 5 of the names listed in the report.
5. NIH DMS plan, one line per element: data types; related tools, software and code; standards;
   preservation, access and timelines (suggest a suitable repository); access and reuse considerations;
   oversight.
6. Top 5 actions, most valuable first, each with effort (low/medium/high).
7. New notes to record, only for unexplained gaps or risks, as JSON objects, at most 5:
   {"id": "OBS-...", "kind": "...", "modality": "...", "subjects": [...], "weeks": [...], "text": "..."}

COVERAGE REPORT
---------------
```

For a study that isn't mice or weeks, replace those words with your own units (patients and visits,
samples and batches).

## Report template

```text
STUDY: <title>
Design: <N> subjects; modalities <A, B, C>; <schedule>, timepoints <first>-<last> (<dates>).

COVERAGE (one row per subject, one column per timepoint)
  M = measured   o = on disk, not analyzed   x = acquired, files not found   . = not acquired

<modality A> / week  1  2  3  4
S01                  M  M  .  M
S02                  M  o  .  M
  measured 5 of 6 sessions; 1 on disk not analyzed; 0 files not found

TIMELINE GAPS (a timepoint skipped for many subjects at once)
  <modality>: week <a> -> <b>, <n> subjects; explained by <note ID or NOTHING>: <reason>

NOTES ALREADY RECORDED (id, kind, modality: text)
  <ID> (<kind>, <modality>): <what happened and why>

FILE AND FOLDER NAMES AS FOUND (examples per modality)
  <modality> data (<n> distinct): <name> | <name> | <name>
  results and study sheets: <name> | <name>

STORAGE (machines holding each session's data, including copies)
  <modality> on <machine(s)>: <n> sessions, timepoints [...]
  total on disk <GB>, of which copies <GB>
```

What matters most is the grid and the notes: the assistant can only tell an explained gap from an
unexplained one if the explanations are written down.
