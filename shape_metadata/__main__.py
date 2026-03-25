from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SHAPE metadata artifacts and site.")
    parser.add_argument("--root", default=".", help="Workspace root containing data/ and output folders.")
    args = parser.parse_args()

    outputs = run_pipeline(Path(args.root))
    print(f"Wrote artifacts to {outputs['artifacts_dir']}")
    print(f"Wrote site to {outputs['site_dir']}")


if __name__ == "__main__":
    main()
