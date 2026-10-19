"""
run_experiments.py - runs all BookSim sweeps for Task 1, 2, 3 and writes results.csv
Run from booksim2/src (where ./booksim and cluster16.txt live).

  python3 run_experiments.py --list              # show experiment groups
  python3 run_experiments.py --only E4 T3        # run selected groups
  python3 run_experiments.py                     # run everything
  python3 run_experiments.py --quick --only E1   # coarse + 1 seed, to test the pipeline
Resumable: series already in results.csv are skipped.
"""
import subprocess, re, csv, os, sys, tempfile, argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

BOOKSIM = "./booksim"
OUT = "results.csv"
COLS = ["group","label","topo","k","routing","vcs","traffic","extra","rate","seed",
        "lat","net_lat","acc","hops","unstable"]

def frange(a, b, s):
    out, x = [], a
    while x <= b + 1e-9: out.append(round(x, 4)); x += s
    return out

RATES      = frange(0.02, 1.00, 0.02)     # flits/node/cycle, stops automatically after saturation
RATES_HOT  = frange(0.002, 0.06, 0.002)   # hotspot saturates at ~1/(N-1) per node
HOT = {64: 27, 36: 14, 16: 5}             # fixed hotspot node per network size (central-ish)

def net_cfg(topo, k):
    if topo in ("mesh", "torus"): return f"topology = {topo}; k = {k}; n = 2;"
    if topo == "fattree":         return "topology = fattree; k = 4; n = 3;"
    if topo == "fly":             return "topology = fly; k = 8; n = 2;"
    if topo == "cluster":         return "topology = anynet; network_file = cluster16.txt;"
    raise ValueError(topo)

def nodes_of(topo, k):
    return {"mesh": k*k, "torus": k*k, "fattree": 64, "fly": 64, "cluster": 16}[topo]

def traffic_str(tr, topo, k):
    return f"hotspot({{{HOT[nodes_of(topo,k)]}}},{{1}})" if tr == "hotspot" else tr

def S(group, label, topo, k, routing, vcs, traffic, extra=""):
    return dict(group=group, label=label, topo=topo, k=k, routing=routing,
                vcs=vcs, traffic=traffic, extra=extra)

def experiments():
    E = []
    for k in (4, 6, 8):                                   # E1 mesh sizes
        E.append(S("E1", f"mesh {k}x{k}", "mesh", k, "dim_order", 4, "uniform"))
    for k in (4, 6, 8):                                   # E2 torus sizes
        E.append(S("E2", f"torus {k}x{k}", "torus", k, "dim_order", 4, "uniform"))
    for vc in (1, 2, 4, 8):                               # E3 VC count
        for tr in ("uniform", "transpose"):
            E.append(S("E3", f"mesh 8x8 {vc}VC", "mesh", 8, "dim_order", vc, tr))
    for rt in ("dim_order","romm","valiant","min_adapt","adaptive_xy_yx","tcaxy"):   # E4
        for tr in ("uniform","transpose","bitcomp"):
            E.append(S("E4", rt, "mesh", 8, rt, 4, tr))
    for tr in ("uniform","transpose","bitcomp","bitrev","hotspot"):                  # E5
        E.append(S("E5", f"mesh 8x8 XY {tr}", "mesh", 8, "dim_order", 4, tr))
    for tr in ("uniform","transpose","bitcomp"):                                      # E6
        E.append(S("E6", "fat tree k4 n3", "fattree", 4, "nca", 4, tr))
    for tr in ("uniform","bitcomp","transpose"):                                      # E7
        E.append(S("E7", "butterfly k8 n2", "fly", 8, "dest_tag", 4, tr))
    for tr in ("uniform","transpose","bitcomp","bitrev","hotspot"):                   # T2
        E.append(S("T2", "cluster-hybrid (16)", "cluster", 4, "min", 4, tr))
        E.append(S("T2", "mesh 4x4 (XY)", "mesh", 4, "dim_order", 4, tr))
    for (topo, rts) in (("mesh", ("dim_order","adaptive_xy_yx","tcaxy")),
                        ("torus", ("dim_order","tcaxy"))):                            # T3
        for k in (8, 4):
            for tr in ("uniform","transpose","bitcomp","hotspot"):
                for rt in rts:
                    E.append(S("T3", f"{topo} {k}x{k} {rt}", topo, k, rt, 4, tr))
    for T in (0, 2, 4, 8):                                                            # T3b threshold
        for tr in ("transpose","uniform"):
            E.append(S("T3b", f"tcaxy T={T}", "mesh", 8, "tcaxy", 4, tr, f"tcaxy_threshold = {T};"))
    return E

TEMPLATE = """{net}
routing_function = {routing};
num_vcs = {vcs}; vc_buf_size = 8; packet_size = 4;
traffic = {traffic};
injection_rate = {rate}; injection_rate_uses_flits = 1;
injection_process = bernoulli;
sim_type = latency; warmup_periods = 3; sample_period = 1000; max_samples = 10;
latency_thres = 2000.0; seed = {seed};
{extra}
"""
PAT = {"lat": r"Packet latency average = ([\d.]+)", "net_lat": r"Network latency average = ([\d.]+)",
       "acc": r"Accepted flit rate average = ([\d.]+)", "hops": r"Hops average = ([\d.]+)"}

def run_one(spec, rate, seed):
    cfg = TEMPLATE.format(net=net_cfg(spec["topo"], spec["k"]), routing=spec["routing"],
            vcs=spec["vcs"], traffic=traffic_str(spec["traffic"], spec["topo"], spec["k"]),
            rate=rate, seed=seed, extra=spec["extra"])
    with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
        f.write(cfg); name = f.name
    try:
        p = subprocess.run([BOOKSIM, name], capture_output=True, text=True, timeout=1800)
        # NOTE: BookSim exits with code 255 even on success, so do not trust the return code
        out, ok = p.stdout, ("ssert" not in p.stderr)
    except subprocess.TimeoutExpired:
        out, ok = "", False
    finally:
        os.unlink(name)
    res = {}
    for key, pat in PAT.items():
        m = re.findall(pat, out); res[key] = float(m[-1]) if m else None
    res["unstable"] = (not ok) or ("unstable" in out) or res["lat"] is None
    return res

def series(spec, seed, quick):
    rates = RATES_HOT if spec["traffic"] == "hotspot" else RATES
    if quick: rates = rates[::3]
    rows, bad = [], 0
    for r in rates:
        d = run_one(spec, r, seed)
        rows.append([spec["group"], spec["label"], spec["topo"], spec["k"], spec["routing"], spec["vcs"],
                     spec["traffic"], spec["extra"], r, seed, d["lat"], d["net_lat"], d["acc"], d["hops"], d["unstable"]])
        bad = bad + 1 if d["unstable"] else 0
        if bad >= 2: break          # two unstable points in a row: past saturation
    return rows

def key_of(s, seed): return (s["group"], s["label"], s["traffic"], s["extra"], seed)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--seeds", nargs="*", type=int, default=[1, 2, 3])
    ap.add_argument("--quick", action="store_true"); ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args()
    exps = [e for e in experiments() if not a.only or e["group"] in a.only]
    if a.list:
        from collections import Counter
        for g, n in Counter(e["group"] for e in experiments()).items(): print(g, n, "series")
        sys.exit()
    if a.quick:
        OUT = "results_quick.csv"
        a.seeds = a.seeds[:1]
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh): done.add((r["group"], r["label"], r["traffic"], r["extra"], int(r["seed"])))
    new = not os.path.exists(OUT)
    todo = [(e, s) for e in exps for s in a.seeds if key_of(e, s) not in done]
    print(f"{len(todo)} series to run on {a.jobs} workers")
    with open(OUT, "a", newline="") as fh, ProcessPoolExecutor(a.jobs) as ex:
        w = csv.writer(fh)
        if new: w.writerow(COLS)
        futs = {ex.submit(series, e, s, a.quick): (e, s) for e, s in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            e, s = futs[fu]; w.writerows(fu.result()); fh.flush()
            print(f"[{i}/{len(todo)}] {e['group']} | {e['label']} | {e['traffic']} | seed {s}")
