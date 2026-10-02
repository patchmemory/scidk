#!/usr/bin/env python3
"""
dump_notebook.py: write a notebook's results as plain text for review.

  python3 dump_notebook.py                         # dump the saved outputs
  python3 dump_notebook.py --execute               # run it first (uses neo4j.env if present)
  python3 dump_notebook.py --code                  # also include each cell's code

Writes review/notebook_results.txt (section headings, cell numbers, text outputs, errors) and
review/fig_NN.png for every figure. Attach the .txt and the figures, or paste the .txt.
Needs only the standard library; --execute also needs nbclient.
"""
import argparse
import base64
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("notebook", nargs="?", default="lwm_plan_next_study.ipynb")
ap.add_argument("--execute", action="store_true", help="run the notebook first and save it")
ap.add_argument("--code", action="store_true", help="include each code cell's source")
ap.add_argument("--max-lines", type=int, default=60, help="truncate long outputs (0 = never)")
ap.add_argument("--out", default="review")
a = ap.parse_args()

nb_path = Path(a.notebook)
if a.execute:
    import nbformat
    from nbclient import NotebookClient
    nb = nbformat.read(nb_path, 4)
    NotebookClient(nb, timeout=600, kernel_name="python3", allow_errors=True,
                   resources={"metadata": {"path": str(nb_path.parent.resolve())}}).execute()
    nbformat.write(nb, nb_path)
    print(f"executed and saved {nb_path}")

nb = json.loads(nb_path.read_text())
out = Path(a.out); out.mkdir(exist_ok=True)
for old in out.glob("fig_*.png"):
    old.unlink()


def text(x):
    return "".join(x) if isinstance(x, list) else (x or "")


def clip(s):
    lines = s.rstrip("\n").splitlines()
    if a.max_lines and len(lines) > a.max_lines:
        keep = a.max_lines // 2
        lines = lines[:keep] + [f"... ({len(lines) - 2 * keep} lines cut) ..."] + lines[-keep:]
    return "\n".join(lines)


lines, figs, errors, n = [], 0, 0, 0
for cell in nb["cells"]:
    src = text(cell["source"])
    if cell["cell_type"] == "markdown":
        heads = [l for l in src.splitlines() if l.startswith("#")]
        lines += [f"\n{h}" for h in heads]
        continue
    if cell["cell_type"] != "code":
        continue
    n += 1
    first = next((l for l in src.splitlines() if l.strip()), "")
    lines.append(f"\n--- [cell {n}] {first[:90]}")
    if a.code:
        lines.append(src)
        lines.append("  >>>")
    for o in cell.get("outputs", []):
        t = o["output_type"]
        if t == "stream":
            lines.append(clip(text(o["text"])))
        elif t == "error":
            errors += 1
            tb = re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(o.get("traceback", [])))
            lines.append(f"ERROR {o['ename']}: {o['evalue']}\n{clip(tb)}")
        elif t in ("execute_result", "display_data"):
            d = o.get("data", {})
            if "image/png" in d:
                figs += 1
                name = f"fig_{figs:02d}.png"
                (out / name).write_bytes(base64.b64decode(text(d["image/png"])))
                lines.append(f"[figure -> {out / name}]")
            elif "text/plain" in d:
                lines.append(clip(text(d["text/plain"])))

head = (f"{nb_path.name}: {n} code cells, {figs} figures, {errors} errors\n"
        f"(outputs as saved; figures in {out}/)\n")
dest = out / "notebook_results.txt"
dest.write_text(head + "\n".join(lines) + "\n")
print(head + f"wrote {dest}")
