"""analyze.py - builds summary tables and plots from results.csv.
Run:  python3 analyze.py        -> summary.csv + plots/*.png"""
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, os

df = pd.read_csv("results.csv")
df["extra"] = df["extra"].fillna("")
os.makedirs("plots", exist_ok=True)
rows = []

def summarize(g):
    """g: one series (all seeds). Returns zero-load latency, saturation rate, throughput numbers."""
    m = g.groupby("rate").agg(lat=("lat", lambda s: s.dropna().mean()),
                              acc=("acc", lambda s: s.dropna().mean()),
                              bad=("unstable", "max")).reset_index().sort_values("rate")
    ok = m[~m.bad.astype(bool) & m.lat.notna()]
    if ok.empty: return None
    L0 = ok.iloc[0].lat
    sat = m[(m.bad.astype(bool)) | (m.lat > 3 * L0)]
    if len(sat):
        sat_rate = sat.iloc[0].rate
        before = ok[ok.rate < sat_rate]
        acc_pre = before.iloc[-1].acc if len(before) else float("nan")
    else:
        sat_rate, acc_pre = float("nan"), ok.iloc[-1].acc
    return dict(zero_load_latency=round(L0, 2), sat_inj_rate=sat_rate,
                accepted_at_last_stable_point=round(acc_pre, 4),
                peak_accepted_throughput=round(m.acc.max(), 4))

keys = ["group", "traffic"]
for (grp, tr), sub in df.groupby(keys):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for (label, extra), s in sub.groupby(["label", "extra"]):
        res = summarize(s)
        if res: rows.append(dict(group=grp, traffic=tr, label=label, extra=extra, **res))
        m = s[~s.unstable].groupby("rate")[["lat", "acc"]].mean().reset_index()
        name = label + (f" ({extra.strip(';')})" if extra else "")
        ax[0].plot(m.rate, m.lat, marker="o", ms=3, label=name)
        ma = s.groupby("rate")[["acc"]].mean().reset_index()
        ax[1].plot(ma.rate, ma.acc, marker="o", ms=3, label=name)
    ax[0].set_ylim(0, 300); ax[0].set_xlabel("Injection rate (flits/node/cycle)")
    ax[0].set_ylabel("Avg packet latency (cycles)"); ax[0].set_title(f"{grp} - {tr}: latency")
    ax[1].set_xlabel("Injection rate (flits/node/cycle)"); ax[1].set_ylabel("Accepted throughput (flits/node/cycle)")
    ax[1].set_title(f"{grp} - {tr}: throughput")
    ax[0].legend(fontsize=7); ax[0].grid(alpha=.3); ax[1].grid(alpha=.3)
    plt.tight_layout(); plt.savefig(f"plots/{grp}_{tr.split('(')[0]}.png", dpi=180); plt.close()

pd.DataFrame(rows).to_csv("summary.csv", index=False)
print(pd.DataFrame(rows).to_string(index=False))
