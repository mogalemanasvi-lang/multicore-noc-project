BookSim 2 project kit  (all tested on BookSim 2 master, Ubuntu 24.04)
  apply_patch.py      adds the TCAXY routing algorithm (mesh + torus) to BookSim
  cluster16.txt       Assignment-2 cluster-based hybrid NoC (anynet topology file)
  check_topology.py   connectivity / diameter / hops / bisection, cluster vs 4x4 mesh
  run_experiments.py  runs every sweep (E1-E7, T2, T3, T3b) -> results.csv
  analyze.py          summary.csv + latency/throughput plots in plots/
Copy ALL of these into booksim2/src and run from there.
