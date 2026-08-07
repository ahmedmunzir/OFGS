#!/usr/bin/env python3

from contextlib import contextmanager
import fcntl
from pathlib import Path
import sys

from core.dataset_parser import parse_datasets
from core.discovery import discover_post_processing
from core.generator import AtomicPublicationError, write_monitor
from core.parser import (
    verify_case,
    read_control_dict,
    parse_function_objects,
)


def banner():
    print("OFGS - OpenFOAM Gnuplot Suite")
    print()


@contextmanager
def generation_lock(case: Path):
    """Serialize generation for one case without blocking other cases."""
    lock_path = case / ".ofgs-generation.lock"
    with lock_path.open("a") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _generate_case(case: Path, control: Path):
    """Generate one complete case while its per-case lock is held."""
    text = read_control_dict(control)
    parse_function_objects(text)

    print(f"Case: {case.name}")
    print()
    print("Discovering datasets...")
    outputs = discover_post_processing(case)
    datasets = parse_datasets(outputs)
    graph_count = len(datasets)
    graph_label = "graph" if graph_count == 1 else "graphs"
    print(f"Found {graph_count} supported {graph_label}.")
    print()

    write_monitor(case, datasets)
    if graph_count:
        print("Generated:")
        print("  monitor.gp")
        print(f"  graphs/ ({graph_count} {graph_label})")
        print()
    print("Generation complete.")


def main():

    banner()

    case = Path.cwd()

    try:
        control = verify_case(case)
    except Exception as e:
        print(e)
        return

    with generation_lock(case):
        _generate_case(case, control)


def entrypoint():
    try:
        main()
    except KeyboardInterrupt:
        return 130
    except AtomicPublicationError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(entrypoint())
