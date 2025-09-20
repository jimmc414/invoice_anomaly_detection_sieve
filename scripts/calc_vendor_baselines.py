"""Wrapper script that recomputes anomaly baselines."""
from __future__ import annotations

from scripts.train_anomaly import main as run_train_anomaly


def main() -> None:
    run_train_anomaly()


if __name__ == "__main__":  # pragma: no cover
    main()
