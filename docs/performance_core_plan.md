# Performance Core Plan

Sprint 03.3 keeps the production detector in Python/NumPy behind a swappable core interface. Rust/PyO3 should be considered only after:

- profiling proves the NumPy core is still too slow for normal research iteration;
- detector semantics and output columns have stabilized;
- expected speedup justifies Windows build, packaging, and CI complexity.

Until those conditions are met, production work should optimize Polars IO, contiguous NumPy arrays, linear-time rolling windows, multiprocessing, checkpoint/resume, and profiling visibility first.
