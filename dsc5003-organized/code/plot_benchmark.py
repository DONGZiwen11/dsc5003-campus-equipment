"""Render Section 6 figures from the CSV produced by benchmark.py."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

out = Path(__file__).resolve().parent.parent / "evaluation"
with (out / "metrics.csv").open() as stream:
    rows = list(csv.DictReader(stream))
for name, panels in [
    ("query-scaling", [("Overdue loans", "median_ms"), ("Borrower history", "median_ms")]),
    ("checkout-scaling", [("Committed checkout", "median_ms"), ("Committed checkout", "p95_ms")]),
]:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    for ax, (workload, metric) in zip(axes, panels):
        samples = [r for r in rows if r["workload"] == workload]
        for color, config in zip(["#a83848", "#17685e"], dict.fromkeys(r["configuration"] for r in samples)):
            group = [r for r in samples if r["configuration"] == config]
            ax.plot([int(r["loans"]) for r in group], [float(r[metric]) for r in group],
                    marker="o", label=config, color=color)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xticks([1000,10000,50000,100000])
        ax.set_xticklabels(["1k","10k","50k","100k"])
        ax.set_xlabel("Loan records (log scale)")
        ax.set_ylabel(("Median" if metric=="median_ms" else "95th percentile")+" latency (ms, log scale)")
        ax.set_title(workload)
        ax.grid(alpha=.22)
        ax.legend(fontsize=9)
    fig.savefig(out / (name + ".png"), dpi=180)
    plt.close(fig)
