"""
lwm_study.py: the analysis behind the LwM 2026 workshop notebook.

The notebook stays short and readable; the code it calls lives here:

    from lwm_study import Study
    study = Study(g)              # g = lwm_graph.connect()
    study.summary()               # every method returns a table or draws a figure

Everything is computed from what the graph returns (or the bundled CSV files offline).
"""
import json
import math
import os
import re
import urllib.error
import urllib.request
import warnings
from functools import cached_property
from getpass import getpass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch, Rectangle
from scipy import stats

ORDER = ["microCT", "MRI", "IVIS"]
COLOR = {"microCT": "#2a78d6", "MRI": "#eb6834", "IVIS": "#1baf7a"}
INK, MUTED = "#52514e", "#8a8984"
WEEKS = list(range(6, 15))
MAIN_KIND = {"microCT": "aerated_lung_pct", "MRI": "tumor_pixel_count", "IVIS": "total_flux"}
SCALE = {"microCT": "points of lung", "MRI": "log mm³", "IVIS": "log flux"}
MIN_MICE = 5          # below this, a modality's numbers are indicative only
EXPORT = Path("export")

warnings.filterwarnings("ignore", category=RuntimeWarning)   # empty slices for unanalyzed mice
pd.set_option("display.max_colwidth", 90)
plt.rcParams.update({
    "figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.8,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "font.size": 10,
})


def _plural(n, word, plural=None):
    return f"{n} {word if n == 1 else (plural or word + 's')}"


class Study:
    """One study, loaded from the graph once. Methods answer one question each."""

    def __init__(self, graph):
        self.g = graph
        self.sessions = graph.run("sessions")
        self.measurements = graph.run("measurements")
        self.observations = graph.run("observations")
        self.mice = sorted(self.sessions.subject.unique())
        main = self.measurements[self.measurements.kind == self.measurements.modality.map(MAIN_KIND)]
        self.raw = main.pivot_table(index=["subject", "week"], columns="modality",
                                    values="value").reindex(columns=ORDER)
        # instrument parameters per session, one column per parameter
        self.params = pd.concat([self.sessions[["session", "subject", "modality", "week"]],
                                 pd.json_normalize(self.sessions.props.tolist())], axis=1)
        self.p = {mod: self.params[self.params.modality == mod] for mod in ORDER}

    # ------------------------------------------------------------ measures
    @cached_property
    def aerated(self):
        """microCT aerated lung, % of lung volume: mouse x week."""
        return self.raw["microCT"].unstack("week")

    @cached_property
    def baseline(self):
        return self.aerated[[6, 7, 8]].mean(axis=1)

    @cached_property
    def lung_lost(self):
        """Points of aerated lung lost since each mouse's own baseline (weeks 6-8)."""
        return self.baseline.values[:, None] - self.aerated

    @cached_property
    def mri_mm3(self):
        """MRI tumor volume in mm³: voxel counts times each session's own voxel size."""
        voxel = self.p["MRI"].set_index(["subject", "week"]).voxel_mm3
        return (self.raw["MRI"] * voxel.reindex(self.raw.index)).unstack("week")

    @cached_property
    def ivis_flux(self):
        return self.raw["IVIS"].unstack("week")

    @cached_property
    def last_lost(self):
        last = self.aerated.apply(lambda r: r.dropna().iloc[-1], axis=1)
        return self.baseline - last

    @cached_property
    def with_tumor(self):
        """Mice that lost more than 10 points of aerated lung by their last scan."""
        return sorted(self.last_lost.loc[lambda x: x > 10].index)

    @cached_property
    def _scaled(self):
        return {"microCT": self.lung_lost, "MRI": np.log(self.mri_mm3), "IVIS": np.log(self.ivis_flux)}

    @cached_property
    def noise(self):
        """Week-to-week jitter in the same mouse before any tumor (weeks 6-9)."""
        out = {}
        for mod in ORDER:
            pre = self._scaled[mod][[w for w in self._scaled[mod].columns if w <= 9]]
            out[mod] = pre.sub(pre.mean(axis=1), axis=0).stack().std()
        return out

    # ------------------------------------------------------------ overview
    def summary(self):
        """The whole study in one graph query, one row per modality."""
        s = self.g.run("dataset_summary").set_index("modality").reindex(ORDER)
        s["kinds"] = s.kinds.map(sorted)
        return s

    @cached_property
    def coverage(self):
        """Per modality, a mouse x week grid: 3 measured, 2 on disk, 1 files not found, 0 not scanned."""
        cov = self.g.run("session_coverage")
        cov["state"] = np.select([cov.measurements > 0, cov.stored_items > 0], [3, 2], default=1)
        self._coverage_rows = cov
        return {mod: cov[cov.modality == mod].pivot(index="subject", columns="week", values="state")
                .reindex(index=self.mice, columns=WEEKS).fillna(0).astype(int) for mod in ORDER}

    STATES = {3: "measured", 2: "on disk, not analyzed", 1: "scanned, files not found", 0: "not scanned"}

    @staticmethod
    def _cell_style(state, color):
        return {3: dict(facecolor=color),
                2: dict(facecolor=color, alpha=0.28),
                1: dict(facecolor="white", edgecolor=color, hatch="////", lw=0),
                0: dict(facecolor="#efeee9")}[state]

    def plot_coverage(self):
        """Mouse x week grid per modality, colored by what exists."""
        gaps = self.g.run("gaps")
        fig, axes = plt.subplots(1, 3, figsize=(12, 4.8), sharey=True)
        for ax, mod in zip(axes, ORDER):
            gm = self.coverage[mod]
            for i, m in enumerate(gm.index):
                for j, w in enumerate(WEEKS):
                    ax.add_patch(Rectangle((j - 0.43, i - 0.43), 0.86, 0.86,
                                           **self._cell_style(gm.loc[m, w], COLOR[mod])))
            for _, gap in gaps[gaps.modality == mod].iterrows():
                for w in range(int(gap.last_before) + 1, int(gap.first_after)):
                    label = "vacation" if "vacation" in str(gap.reason) else "gap"
                    ax.text(WEEKS.index(w), -0.9, label, ha="center", va="bottom", fontsize=7, color=INK)
            n_meas, n_sess = int((gm == 3).values.sum()), int((gm > 0).values.sum())
            ax.set_title(f"{mod}: {n_meas} of {n_sess} sessions measured", loc="left", fontsize=11, pad=14)
            ax.set_xlim(-0.6, len(WEEKS) - 0.4); ax.set_ylim(len(gm) - 0.4, -1.1)
            ax.set_xticks(range(len(WEEKS)), WEEKS); ax.set_xlabel("Study week")
            ax.set_yticks(range(len(gm)), gm.index)
            ax.grid(False); ax.spines[["left", "bottom"]].set_visible(False); ax.tick_params(length=0)
        handles = [Patch(**self._cell_style(s, INK), label=self.STATES[s]) for s in (3, 2, 1, 0)]
        fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.03))
        fig.tight_layout(rect=(0, 0.05, 1, 1)); plt.show()

    def coverage_by_week(self):
        """How many mice have analyzed data on 3, 2 or 1 modalities each week."""
        n_mods = pd.concat({mod: (self.coverage[mod] == 3).astype(int) for mod in ORDER}).groupby(level=1).sum()
        per_week = pd.DataFrame({k: (n_mods == k).sum() for k in (3, 2, 1)})
        shades = {3: "#3d3b36", 2: MUTED, 1: "#cfcdc6"}
        fig, ax = plt.subplots(figsize=(8, 3.2))
        bottom = np.zeros(len(per_week))
        for k in (3, 2, 1):
            ax.bar(per_week.index, per_week[k], bottom=bottom, width=0.6, color=shades[k], edgecolor="white",
                   lw=2, label=f"{k} modalit{'y' if k == 1 else 'ies'}")
            bottom += per_week[k].values
        for w, total in zip(per_week.index, bottom):
            ax.text(w, total + 0.2, int(total), ha="center", va="bottom", fontsize=8, color=INK)
        ax.set_xticks(WEEKS); ax.set_xlabel("Study week"); ax.set_ylabel("Mice with analyzed data")
        ax.set_title("Mice analyzed each week, by number of modalities", loc="left", fontsize=11)
        ax.set_ylim(0, len(self.mice) + 1.5); ax.set_axisbelow(True); ax.grid(axis="x", visible=False)
        ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1, 1)); plt.show()
        return per_week.rename(columns=lambda k: f"{k} modalities").T

    def coverage_by_mouse(self):
        """Analyzed timepoints per mouse and modality (★ = visible tumor on microCT)."""
        series_len = pd.DataFrame({mod: (self.coverage[mod] == 3).sum(axis=1) for mod in ORDER})
        order = series_len.sum(axis=1).sort_values().index
        fig, ax = plt.subplots(figsize=(8, 4.2))
        for k, mod in enumerate(ORDER):
            ax.barh(np.arange(len(order)) + (k - 1) * 0.26, series_len.loc[order, mod], height=0.24,
                    color=COLOR[mod], label=mod)
        ax.set_yticks(range(len(order)), [f"{m} ★" if m in self.with_tumor else m for m in order])
        ax.set_xlabel("Weeks with an analysis result"); ax.set_xticks(range(0, len(WEEKS) + 1))
        ax.set_title("Analyzed timepoints per mouse", loc="left", fontsize=11)
        ax.set_axisbelow(True); ax.grid(axis="y", visible=False)
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles[::-1], labels[::-1], frameon=False, loc="upper left", bbox_to_anchor=(1, 1))
        plt.show()

    # ------------------------------------------------------------ A1 resolution and protocol
    def resolution(self):
        mct_um, mri_voxel = self.p["microCT"].voxel_um.median(), self.p["MRI"].voxel_mm3.median()
        print(f"one MRI voxel = {mri_voxel * 1e9 / mct_um ** 3:,.0f} microCT voxels")
        return pd.DataFrame({
            "measures": ["air left in the lung (% of lung volume)", "tumor region drawn on the images",
                         "light from luciferase-expressing cells"],
            "voxel / pixel": self._resolution_short().values,
            "voxel volume (µm³)": [f"{mct_um ** 3:,.0f}", f"{mri_voxel * 1e9:,.0f}", "—"],
            "result": ["aerated lung, %", "tumor voxels (→ mm³)", "total flux, photons/s"],
        }, index=ORDER)

    def protocol_by_week(self):
        """Key acquisition parameters, week by week, from each session's instrument record."""
        def distinct(x):
            return ", ".join(f"{v:g}" if isinstance(v, float) else str(v) for v in sorted(x.dropna().unique()))
        def span(x):
            return f"{x.min():.0f}" if x.min() == x.max() else f"{x.min():.0f}–{x.max():.0f}"
        p = self.p
        proto = pd.concat({
            "microCT exposure (ms)": p["microCT"].groupby("week").exposure_ms.agg(distinct),
            "microCT recon slices": p["microCT"].groupby("week").recon_slices.agg(span),
            "MRI TR (ms)": p["MRI"].groupby("week").tr_ms.agg(distinct),
            "MRI slices": p["MRI"].groupby("week").slices.agg(distinct),
            "IVIS exposures (s)": p["IVIS"].groupby("week").exposures_s.first(),
        }, axis=1).sort_index()
        proto.loc[13, "IVIS exposures (s)"] = "copy of week 12"     # the week-13 folder holds week 12's images
        return proto.fillna("not scanned")

    def protocol_changes(self):
        o = self.observations
        return o.loc[o.kind == "protocol_change", ["id", "modality", "text"]]

    def mri_units(self):
        pix = self.raw["MRI"].dropna()
        print(f"largest MRI count: {int(pix.max()):,} pixels ({pix.idxmax()[0]}, week {pix.idxmax()[1]}); "
              f"one slice holds {256*256:,}")
        print(f"so the counts are voxels summed over slices: {self.mri_mm3.min().min():.1f} to "
              f"{self.mri_mm3.max().max():.0f} mm³ of tumor")

    # ------------------------------------------------------------ A2-A4 growth, visibility, agreement
    def plot_growth(self):
        series = {"microCT": self.lung_lost, "MRI": self.mri_mm3, "IVIS": self.ivis_flux}
        ylabel = {"microCT": "Lung lost to tumor (points)", "MRI": "Tumor volume (mm³, log)",
                  "IVIS": "Total flux, supine (p/s, log)"}
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharex=True)
        for ax, mod in zip(axes, ORDER):
            x = series[mod].reindex(columns=WEEKS)
            x = x[x.notna().any(axis=1)]
            for _, row in x.iterrows():
                ax.plot(WEEKS, row.values, color=COLOR[mod], lw=1.2, alpha=0.5)
            ax.set_title(f"{mod} (n = {len(x)} mice)", loc="left", fontsize=11)
            ax.set_xlabel("Study week"); ax.set_ylabel(ylabel[mod])
            if mod != "microCT":
                ax.set_yscale("log")
        fig.tight_layout(); plt.show()

    @cached_property
    def signal_to_noise(self):
        rows = []
        for mod in ORDER:
            x = self._scaled[mod].loc[self._scaled[mod].index.isin(self.with_tumor)]
            base = x[[w for w in x.columns if w <= 8]].mean(axis=1)
            for w in x.columns:
                rows.append({"modality": mod, "week": w,
                             "signal/noise": (x[w] - base).abs().median() / self.noise[mod]})
        return pd.DataFrame(rows).pivot(index="week", columns="modality", values="signal/noise")[ORDER]

    @cached_property
    def n_tumor(self):
        return {mod: int(self._scaled[mod].loc[self._scaled[mod].index.isin(self.with_tumor)]
                         .notna().any(axis=1).sum()) for mod in ORDER}

    @cached_property
    def first_visible_week(self):
        return {mod: int(self.signal_to_noise[mod].loc[lambda s: s > 2].index.min()) for mod in ORDER}

    def plot_visibility(self):
        sn = self.signal_to_noise
        fig, ax = plt.subplots(figsize=(8, 3.4))
        for mod in ORDER:
            ls = "-" if self.n_tumor[mod] >= MIN_MICE else ":"
            ax.plot(sn.index, sn[mod], color=COLOR[mod], marker="o", ms=4, lw=2, ls=ls,
                    label=f"{mod} ({self.n_tumor[mod]} mice)")
        ax.axhline(2, color=INK, lw=1, ls="--")
        ax.annotate("visible (2× noise)", (6, 2), xytext=(0, 4), textcoords="offset points", fontsize=8, color=INK)
        ax.set_xlabel("Study week"); ax.set_ylabel("Median change ÷ noise")
        ax.set_title("When does each modality see tumor above its own week-to-week noise?", loc="left",
                     fontsize=11)
        ax.legend(frameon=False); plt.show()
        print(f"mice with visible tumor: {', '.join(m[1:] for m in self.with_tumor)}")
        print("week-to-week noise, weeks 6-9:", {m: f"{v:.2f} {SCALE[m]}" for m, v in self.noise.items()})
        print("first week above 2× noise:", self.first_visible_week,
              "(dotted = fewer than 5 mice: indicative only)")

    def agreement(self):
        """Within each week, Spearman rank correlation between microCT and MRI."""
        rows = []
        for w in WEEKS:
            x = pd.DataFrame({"microCT": self.lung_lost.get(w), "MRI": self.mri_mm3.get(w)}).dropna()
            rows.append({"week": w, "mice": len(x),
                         "Spearman ρ": round(stats.spearmanr(x.microCT, x.MRI)[0], 2) if len(x) >= 5 else None})
        return pd.DataFrame(rows).astype({"mice": "Int64"}).set_index("week").T

    # ------------------------------------------------------------ A5 time and cost
    @cached_property
    def instruments(self):
        """Facility rate and time model per modality, from the Instrument nodes."""
        return self.g.run("instruments").set_index("modality").props

    def session_hours(self, mod, n_mice):
        t = self.instruments[mod]
        return (t["setup_min"] + math.ceil(n_mice / t["mice_per_acq"]) * t["min_per_acq"]) / 60

    def session_cost(self, mod, n_mice):
        return self.session_hours(mod, n_mice) * self.instruments[mod]["rate_per_hour"]

    def cost_per_scan(self, n_mice=10):
        return pd.DataFrame({mod: {
            "rate ($/h)": self.instruments[mod]["rate_per_hour"],
            f"session, {n_mice} mice (h)": round(self.session_hours(mod, n_mice), 2),
            f"cost per mouse-scan, {n_mice} mice ($)": round(self.session_cost(mod, n_mice) / n_mice, 2),
            "time source": self.instruments[mod]["time_source"]} for mod in ORDER}).T

    def session_times(self):
        """Actual minutes per weekly session (instrument timestamps) next to the time model."""
        t = self.params.assign(start=pd.to_datetime(self.params.acq_start), end=pd.to_datetime(self.params.acq_end))
        actual = pd.concat({
            "microCT": t[t.modality == "microCT"].groupby("week").agg(s=("start", "min"), e=("end", "max"))
                       .pipe(lambda x: (x.e - x.s).dt.total_seconds() / 60),
            "MRI": t[t.modality == "MRI"].groupby("week").slot_min.sum(),
            "IVIS": t[t.modality == "IVIS"].groupby("week").session_min.first(),
        }, axis=1).round(0)
        per_week = self.params.groupby(["week", "modality"]).subject.nunique().unstack()[ORDER]
        model = per_week.apply(lambda col: col.map(
            lambda n: round(self.session_hours(col.name, int(n)) * 60) if pd.notna(n) else None))
        print("blank: not scanned that week; IVIS week 11 ran over two days (Feb 29 – Mar 1), "
              "and IVIS week 13's folder holds week 12's images")
        return pd.concat({"actual (min)": actual.astype("Int64"), "model (min)": model.astype("Int64")},
                         axis=1).sort_index()

    def imaging_cost_so_far(self):
        per_week = self.sessions.groupby(["modality", "week"]).subject.nunique()
        out = pd.DataFrame({mod: {"sessions": int(per_week[mod].size),
                                  "hours": round(sum(self.session_hours(mod, n) for n in per_week[mod]), 1)}
                            for mod in ORDER}).T
        rate = pd.Series({mod: self.instruments[mod]["rate_per_hour"] for mod in ORDER})
        out["cost ($)"] = (out.hours * rate).round(0).astype(int)
        return out.astype({"sessions": int})

    # ------------------------------------------------------------ A6 storage
    def storage(self):
        where = self.g.run("storage_by_location")
        print(f"This study on disk today: {where.GB.sum():.0f} GB, "
              f"of which copies: {where.loc[where.role == 'copy', 'GB'].sum():.0f} GB")
        return where

    def storage_by_modality(self):
        by_mod = self.g.run("storage_by_modality").replace({"modality": {"": "documents, results"}})
        return by_mod.pivot_table(index="modality", columns="location", values="GB", aggfunc="sum",
                                  margins=True, margins_name="total").fillna(0).round(1)

    @cached_property
    def mb_per_mouse_scan(self):
        files = self.g.run("session_files")
        raw = files[(files.link == "STORED_IN") & (files.role == "raw") & files.bytes.notna()].copy()
        # a folder holding several mice (IVIS weekly folder, MRI study folder) is split over its sessions
        raw["share_mb"] = raw.bytes / raw.groupby("path").path.transform("size") / 1e6
        per_session = raw.groupby(["modality", "subject", "week"]).share_mb.sum()
        return per_session.groupby(level=0).median().reindex(ORDER)

    def storage_per_scan(self):
        """Median raw data per mouse-scan, from the size of the data each session is stored in."""
        return self.mb_per_mouse_scan.round(1).rename("MB per mouse-scan").to_frame()

    @staticmethod
    def software():
        return pd.DataFrame([
            ("microCT", "acquisition", "SkyScan control software (Bruker)", "with instrument"),
            ("microCT", "reconstruction", "NRecon (Bruker)", "with instrument"),
            ("microCT", "analysis", "aerated-lung segmentation (tool to confirm with analyst)", "check"),
            ("MRI", "acquisition", "ParaVision (Bruker)", "with instrument"),
            ("MRI", "analysis", "Dragonfly (tumor ROIs)", "commercial; check license"),
            ("MRI", "analysis", "Fiji/ImageJ (MRILungTumor.ijm macro)", "open source"),
            ("IVIS", "acquisition + analysis", "Living Image", "with instrument"),
            ("all", "metadata + this notebook", "Neo4j, Python (pandas, scipy, matplotlib)", "open source"),
        ], columns=["modality", "step", "software", "license"])

    # ------------------------------------------------------------ B design
    @staticmethod
    def n_per_arm(sd_log, effect, alpha=0.05, power=0.80):
        """Mice per arm to detect `effect` (fractional reduction) for a log-scale measure with SD `sd_log`."""
        z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
        return math.ceil(2 * (z * sd_log / -np.log(1 - effect)) ** 2)

    def _endpoint_sds(self, enroll_week, end_week):
        size = {"microCT": self.lung_lost, "MRI": self.mri_mm3, "IVIS": self.ivis_flux}
        out = {}
        for mod in ORDER:
            x = size[mod].loc[size[mod].index.isin(self.with_tumor)]
            out[(mod, f"size at week {end_week}")] = np.log(x[end_week].where(x[end_week] > 0)).dropna()
            if mod != "microCT":   # lung lost is near zero at enrollment: a fold change from it is unstable
                out[(mod, f"growth week {enroll_week}→{end_week}")] = np.log(x[end_week] / x[enroll_week]).dropna()
        return out

    def mice_per_arm(self, effects=(0.4, 0.5, 0.7, 0.8), enroll_week=11, end_week=14, alpha=0.05, power=0.80):
        rows = []
        for (mod, design), v in self._endpoint_sds(enroll_week, end_week).items():
            ok = len(v) >= MIN_MICE
            rows.append({"modality": mod, "design": design, "mice": len(v),
                         "SD (log)": round(v.std(), 2) if ok else None,
                         **{f"{int(e*100)}%": (self.n_per_arm(v.std(), e, alpha, power) if ok else "—")
                            for e in effects}})
        return pd.DataFrame(rows).set_index(["modality", "design"])

    def headline_mice(self, mod, effect=0.7, end_week=14):
        sd = self._endpoint_sds(11, end_week)[(mod, f"size at week {end_week}")].std()
        return self.n_per_arm(sd, effect)

    def sd_uncertainty(self, effect=0.7, k=7):
        lo = (k - 1) / stats.chi2.ppf(0.975, k - 1)
        hi = (k - 1) / stats.chi2.ppf(0.025, k - 1)
        print(f"95% range on a variance from {k} mice: x{lo:.2f} to x{hi:.2f}; mouse numbers scale the same way")
        for mod in ["microCT", "MRI"]:
            base = self.headline_mice(mod, effect)
            print(f"  {mod}, {int(effect*100)}% effect: {base} per arm "
                  f"(plausibly {max(2, math.ceil(base*lo))} to {math.ceil(base*hi)})")

    def scans_needed(self, slower=0.5, enroll_week=11, max_scans=8, alpha=0.05, power=0.80):
        """Mice per arm to detect `slower` growth, by number of weekly scans after enrollment."""
        z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
        rates = {}
        for mod in ORDER:
            x = self._scaled[mod].loc[self._scaled[mod].index.isin(self.with_tumor),
                                      [w for w in self._scaled[mod].columns if w >= enroll_week]]
            slopes = [stats.linregress(r.dropna().index, r.dropna().values).slope
                      for _, r in x.iterrows() if r.notna().sum() >= 2]
            rates[mod] = (abs(np.mean(slopes)), np.std(slopes, ddof=1) if len(slopes) > 1 else np.nan, len(slopes))

        def sxx(T):
            t = np.arange(T); return ((t - t.mean()) ** 2).sum()

        rows = []
        for mod in ORDER:
            mean, sd_obs, n = rates[mod]
            if n < MIN_MICE:
                continue
            sd_between = math.sqrt(max(sd_obs**2 - self.noise[mod]**2 / sxx(4), 0))   # observed over ~4 weeks
            for T in range(2, max_scans + 1):
                var = sd_between**2 + self.noise[mod]**2 / sxx(T)
                rows.append({"modality": mod, "weekly scans": T,
                             "mice/arm": math.ceil(2 * z**2 * var / (slower * mean) ** 2)})
        scans = pd.DataFrame(rows).pivot(index="weekly scans", columns="modality", values="mice/arm")
        fig, ax = plt.subplots(figsize=(8, 3.2))
        for mod in scans.columns:
            ax.plot(scans.index, scans[mod], color=COLOR[mod], marker="o", ms=4, lw=2, label=mod)
        ax.set_xlabel("Weekly scans after enrollment"); ax.set_ylabel("Mice per arm")
        ax.set_title(f"Mice needed to detect {int(slower*100)}% slower growth", loc="left", fontsize=11)
        ax.legend(frameon=False); plt.show()
        print("growth per week (mean ± SD between mice, n):",
              {m: f"{r[0]:.2f} ± {r[1]:.2f} {SCALE[m]}, n={r[2]}" for m, r in rates.items()})
        return scans

    def design_cost(self, effect=0.7, scans_after_enrollment=4, copies=2):
        rows = {}
        for mod in ["microCT", "MRI"]:
            per_arm = self.headline_mice(mod, effect)
            enrolled = 2 * per_arm
            rows[mod] = {"mice per arm": per_arm, "mice enrolled": enrolled,
                         "imaging after enrollment ($)": round(scans_after_enrollment * self.session_cost(mod, enrolled)),
                         f"storage, {copies} copies (GB)": round(self.mb_per_mouse_scan[mod] * enrolled
                                                                 * scans_after_enrollment * copies / 1024, 1)}
        return pd.DataFrame(rows).T.astype({"mice per arm": int, "mice enrolled": int,
                                            "imaging after enrollment ($)": int})

    def xray_dose(self, scans=5):
        dose = self.p["microCT"].dose_mouse_mgy.median()
        print(f"microCT x-ray dose: about {dose:.0f} mGy per scan (scanner estimate), "
              f"{dose * scans / 1000:.1f} Gy over {scans} scans per mouse "
              f"(this study: {dose * 8 / 1000:.1f} Gy over 8)")

    # ------------------------------------------------------------ C tumor model
    def _onset(self, row, after=9):
        # first week (from `after` on) after which the mouse stays above 2x noise
        above = row.dropna() > 2 * self.noise["microCT"]
        above = above[above.index >= after]
        for w in above.index:
            if above.loc[w:].all():
                return int(w)
        return None

    def tumor_outcomes(self):
        out = pd.DataFrame({
            "lung lost by last scan (points)": self.last_lost.round(1),
            "last scan (week)": self.aerated.apply(lambda r: int(r.dropna().index.max()), axis=1),
            "tumor visible from week": self.lung_lost.apply(self._onset, axis=1),
        })
        out["tumor"] = out.index.isin(self.with_tumor)
        out["MRI analyzed"] = out.index.isin(self.mri_mm3.dropna(how="all").index)
        out["IVIS analyzed"] = out.index.isin(self.ivis_flux.dropna(how="all").index)
        return out.sort_values("lung lost by last scan (points)", ascending=False)

    def take_rate(self, not_injected=()):
        """How often the injection produced a measurable tumor, and when it appeared."""
        self._take_model(not_injected, report=True)

    def _take_model(self, not_injected=(), report=False):
        out = self.tumor_outcomes()
        injected = [m for m in self.mice if m not in not_injected]
        evaluable = [m for m in injected if out.loc[m, "last scan (week)"] == 14]
        took = [m for m in evaluable if out.loc[m, "tumor"]]
        left_early = [m for m in injected if out.loc[m, "last scan (week)"] < 14]
        rate = len(took) / len(evaluable)
        if report:
            onset = out.loc[took, "tumor visible from week"]
            print(f"injected mice: {len(injected)}; followed to week 14: {len(evaluable)}; "
                  f"left early: {', '.join(left_early) or 'none'}")
            print(f"measurable tumor by week 14: {len(took)} of {len(evaluable)} = {rate:.0%}")
            print(f"week each tumor became visible: {sorted(onset.astype(int).tolist())} "
                  f"(median week {onset.median():.0f})")
            if not not_injected:
                alt = [m for m in evaluable if m not in ("M67", "M68", "M69")]
                n_alt = len([m for m in took if m in alt])
                print(f"if 67-69 were not injected: {n_alt} of {len(alt)} = {n_alt / len(alt):.0%}")
        return {"take_rate": rate, "attrition": len(left_early) / len(injected)}

    def mice_to_inject(self, effect=0.7, not_injected=(), scans_after_enrollment=4, copies=2):
        model = self._take_model(not_injected)
        design = self.design_cost(effect, scans_after_enrollment, copies)
        rows = {}
        for mod, r in design.iterrows():
            enrolled = int(r["mice enrolled"])
            inject = math.ceil(enrolled / model["take_rate"] / (1 - model["attrition"]))
            screen = self.session_cost("microCT", inject)          # screen everyone on microCT at week 10
            rows[mod] = {"mice enrolled": enrolled, "mice to inject": inject,
                         "screening, microCT ($)": round(screen),
                         "imaging after enrollment ($)": int(r["imaging after enrollment ($)"]),
                         "total imaging ($)": round(screen + r["imaging after enrollment ($)"]),
                         "storage (GB)": r[f"storage, {copies} copies (GB)"]}
        return pd.DataFrame(rows).T.astype({c: int for c in [
            "mice enrolled", "mice to inject", "screening, microCT ($)",
            "imaging after enrollment ($)", "total imaging ($)"]})

    def plan(self, effect=0.7, not_injected=(), scans_after_enrollment=4, copies=2):
        """The next study, side by side for each modality."""
        fw = self.first_visible_week
        full = self.mice_to_inject(effect, not_injected, scans_after_enrollment, copies)
        per_scan = self.cost_per_scan()
        plan = pd.DataFrame({
            "resolution": self._resolution_short(),
            "first visible week": pd.Series({"microCT": f"{fw['microCT']}",
                                             "MRI": f"{fw['MRI']} (week 10 skipped)",
                                             "IVIS": f"{fw['IVIS']} (3 mice: indicative)"}),
            "cost per mouse-scan, 10 mice ($)": per_scan["cost per mouse-scan, 10 mice ($)"],
            "MB per mouse-scan": self.mb_per_mouse_scan.round(1),
            f"mice per arm, {int(effect*100)}% effect": full["mice enrolled"].floordiv(2).astype("Int64"),
            "mice to inject": full["mice to inject"].astype("Int64"),
            "total imaging ($)": full["total imaging ($)"].astype("Int64"),
        }).reindex(ORDER)
        return plan.astype(object).where(plan.notna(), "too few mice")

    def _resolution_short(self):
        p, mct_um = self.p, self.p["microCT"].voxel_um.median()
        fov = ", ".join(str(v) for v in sorted(p["IVIS"].fov_cm.dropna().unique()))
        return pd.Series({
            "microCT": f"{mct_um:.1f} µm, isotropic",
            "MRI": f"{p['MRI'].in_plane_mm.median()*1000:.0f} × {p['MRI'].in_plane_mm.median()*1000:.0f} µm"
                   f" × {p['MRI'].slice_mm.median()} mm slices",
            "IVIS": f"2D image, {fov} cm field of view; blurred by scattering"})

    # ------------------------------------------------------------ D curation
    def where_sessions_live(self):
        """Which machines hold each modality's sessions, week by week."""
        where = self.g.run("session_hosts")
        where["hosts"] = where.hosts.map(lambda h: " + ".join(sorted(h)) if len(h) else "(not found)")
        self._session_hosts = where

        def cell(x):
            counts = x.value_counts()
            if len(counts) == 1:
                return counts.index[0]
            return ", ".join(f"{k} ({_plural(v, 'mouse', 'mice')})" for k, v in counts.items())

        have = self.sessions.groupby(["week", "modality"]).size().unstack("modality").reindex(columns=ORDER)
        table = (where.groupby(["week", "modality"]).hosts.agg(cell)
                 .unstack("modality").reindex(index=have.index, columns=ORDER))
        return table.mask(table.isna() & have.notna(), "files not found").fillna("no session")

    def single_host_sessions(self):
        if not hasattr(self, "_session_hosts"):
            self.where_sessions_live()
        w = self._session_hosts
        single = w[~w.hosts.str.contains(r"\+")]
        print("Sessions held on one machine only:")
        return (single.groupby(["modality", "hosts"])
                .agg(sessions=("subject", "size"), weeks=("week", lambda x: sorted(set(x))),
                     copies_on_that_machine=("stored_items", "median"))
                .reset_index())

    def coverage_report(self):
        """The coverage, notes, gaps and storage as plain text, for a person or an AI assistant."""
        info = self.g.run("study").study[0]
        cov = self.g.run("session_coverage")
        lines = [f"STUDY: {info.get('title', info.get('id'))}",
                 f"Design: {len(self.mice)} mice; modalities {', '.join(ORDER)}; weekly, study weeks "
                 f"{WEEKS[0]}-{WEEKS[-1]} ({cov.acq_date.min()} to {cov.acq_date.max()}).",
                 "", "COVERAGE (one row per mouse, one column per study week)",
                 "  M = measured   o = on disk, not analyzed   x = scanned, files not found   . = not scanned"]
        letter = {3: "M", 2: "o", 1: "x", 0: "."}
        for mod in ORDER:
            gm = self.coverage[mod]
            lines += ["", f"{mod + ' / week':<15}" + " ".join(f"{w:>2}" for w in WEEKS)]
            lines += [f"{m:<15}" + " ".join(f"{letter[v]:>2}" for v in gm.loc[m]) for m in gm.index]
            lines.append(f"  measured {int((gm == 3).values.sum())} of {int((gm > 0).values.sum())} sessions; "
                         f"{int((gm == 2).values.sum())} on disk not analyzed; "
                         f"{int((gm == 1).values.sum())} files not found")
        lines += ["", "TIMELINE GAPS (a week skipped for many mice at once)"]
        for _, r in self.g.run("gaps").iterrows():
            lines.append(f"  {r.modality}: week {r.last_before} -> {r.first_after}, {r.mice_affected} mice; "
                         f"explained by {r.explained_by or 'NOTHING'}: {r.reason or ''}")
        lines += ["", "NOTES ALREADY RECORDED (id, kind, modality: text)"]
        for _, o in self.observations.iterrows():
            mod = o.modality if isinstance(o.modality, str) else "study"
            lines.append(f"  {o.id} ({o.kind}, {mod}): {o.text}")
        lines += ["", "FILE AND FOLDER NAMES AS FOUND (examples per modality)"]
        files = self.g.run("session_files")
        files["name"] = files.path.str.rstrip("/").str.split("/").str[-1]
        for (mod, link), x in files.groupby(["modality", "link"]):
            names = sorted(x.name.unique())
            pick = names[:: max(1, len(names) // 6)][:6]
            kind = "data" if link == "STORED_IN" else "derived"
            lines.append(f"  {mod} {kind} ({len(names)} distinct): " + " | ".join(pick))
        docs = self.g.run("result_files")
        lines.append("  results and study sheets: " + " | ".join(docs.name))
        lines += ["", "STORAGE (machines holding each session's data, including copies)"]
        held = self.g.run("session_hosts")
        held["hosts"] = held.hosts.map(lambda h: " + ".join(sorted(h)))
        for (mod, h), x in held.groupby(["modality", "hosts"]):
            lines.append(f"  {mod} on {h}: {len(x)} sessions, weeks {sorted(set(x.week))}")
        total = self.g.run("storage_by_location")
        lines.append(f"  total on disk {total.GB.sum():.0f} GB, "
                     f"of which copies {total.loc[total.role == 'copy', 'GB'].sum():.0f} GB")
        return "\n".join(lines)

    def export_layout(self):
        """Target folder for every session, and the results as one long table, written to export/."""
        s = self.sessions
        pad = lambda m: f"M{int(m[1:]):03d}"
        layout = s[["session", "subject", "modality", "week", "acq_date"]].copy()
        layout["target_path"] = [f"raw/{mod}/wk{w:02d}/{pad(sub)}/"
                                 for mod, w, sub in zip(layout.modality, layout.week, layout.subject)]
        results = self.measurements.merge(s[["session", "acq_date"]], on="session")[
            ["subject", "week", "acq_date", "modality", "kind", "value", "unit"]]
        EXPORT.mkdir(exist_ok=True)
        layout.to_csv(EXPORT / "session_layout.csv", index=False)
        results.to_csv(EXPORT / "measurements_long.csv", index=False)
        print(f"{len(layout)} sessions -> export/session_layout.csv; "
              f"{len(results)} measurements -> export/measurements_long.csv")
        return layout.head()


# ---------------------------------------------------------------- the curation prompt
CURATION_PROMPT = """You are a research data manager helping a lab curate an imaging study so it can be reused,
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
"""


def curation_prompt(report, save_to=EXPORT / "curation_prompt.md"):
    """The prompt followed by the report; also saved to a file for pasting into any assistant."""
    prompt = CURATION_PROMPT + report
    Path(save_to).parent.mkdir(exist_ok=True)
    Path(save_to).write_text(prompt)
    print(f"{len(prompt):,} characters -> {save_to}: paste it into an AI assistant")
    return prompt


# ---------------------------------------------------------------- MIT Parley API
PARLEY_URL = "https://parley.api.mit.edu/v1"


def parley_key(env_file="parley.env"):
    """Your Parley key, from PARLEY_API_KEY, a parley.env file, or a password prompt. Never printed."""
    if not os.environ.get("PARLEY_API_KEY") and Path(env_file).exists():
        for line in Path(env_file).read_text().splitlines():
            if line.strip().startswith("PARLEY_API_KEY="):
                os.environ["PARLEY_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not os.environ.get("PARLEY_API_KEY"):
        try:
            os.environ["PARLEY_API_KEY"] = getpass("Parley API key (sk-parley-v1-..., blank to skip): ").strip()
        except Exception:      # no one at the keyboard
            pass
    return os.environ.get("PARLEY_API_KEY") or None


def _parley(path, body=None, timeout=300, url=None):
    req = urllib.request.Request(
        f"{url or PARLEY_URL}/{path}", data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {os.environ['PARLEY_API_KEY']}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Parley returned {e.code}: {e.read().decode()[:300]}") from None


def parley_models(url=None):
    """The models your Parley account can use."""
    return sorted(m["id"] for m in _parley("models", url=url)["data"])


def ask_parley(prompt, model=None, max_tokens=16000, save_to=EXPORT / "curation_plan.md", url=None):
    """Send a prompt to MIT's Parley API and return the answer as text (also saved to a file)."""
    if not parley_key():
        print("No Parley key: skipped. The prompt is in export/curation_prompt.md for any assistant.")
        return None
    if model is None:
        models = parley_models(url)
        prefer = ["claude-sonnet", "claude-opus", "claude", "gpt-5"]
        model = next((m for p in prefer for m in models if p in m.lower()), models[0])
    print(f"Sending the prompt to {model} ...")
    reply = _parley("chat/completions", {"model": model, "max_tokens": max_tokens,
                                         "messages": [{"role": "user", "content": prompt}]}, url=url)
    choice = reply["choices"][0]
    text = choice["message"]["content"]
    use = reply.get("usage", {})
    cached = (use.get("prompt_tokens_details") or {}).get("cached_tokens")
    Path(save_to).parent.mkdir(exist_ok=True)
    Path(save_to).write_text(text)
    print(f"{use.get('prompt_tokens', '?')} tokens in"
          + (f" (+{cached} cached)" if cached else "")
          + f", {use.get('completion_tokens', '?')} out -> {save_to}")
    if choice.get("finish_reason") == "length":
        print(f"Warning: the answer stopped at the {max_tokens:,}-token limit and is cut off. "
              f"Run again with a higher limit, e.g. ask_parley(prompt, max_tokens={max_tokens * 2}).")
    return text


def proposed_notes(answer):
    """The new notes (JSON objects with an OBS- id) found in an assistant's answer, as a table."""
    found = []
    for block in re.findall(r'\{[^{}]*"id"\s*:\s*"OBS-[^{}]*\}', answer or ""):
        try:
            found.append(json.loads(block))
        except json.JSONDecodeError:
            pass
    return pd.DataFrame(found)
