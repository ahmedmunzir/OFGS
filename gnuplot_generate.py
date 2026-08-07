#!/usr/bin/env python3

from contextlib import contextmanager
import fcntl
from pathlib import Path
import sys

from core.dataset_parser import (
    IncompletePostProcessingError,
    SUPPORTED_FILENAMES,
    parse_datasets,
    supported_output_expectations,
)
from core.discovery import (
    PostProcessingChangedError,
    capture_post_processing_snapshot,
    discover_post_processing,
    validate_post_processing_snapshot,
)
from core.generator import AtomicPublicationError, write_monitor
from core.parser import (
    verify_case,
    read_control_dict,
    parse_function_object_configurations,
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
    configurations = parse_function_object_configurations(text)
    expectations = supported_output_expectations(configurations)

    print(f"Case: {case.name}")
    print()
    print("Discovering datasets...")
    outputs = discover_post_processing(case)
    snapshot = capture_post_processing_snapshot(
        case,
        outputs,
        SUPPORTED_FILENAMES,
        expected_owners=expectations,
    )
    selected_files = {
        function.name: {filename for filename, _state in function.files}
        for function in snapshot.functions
    }
    for name, required_groups in expectations.items():
        filenames = selected_files.get(name, set())
        if any(
            not filenames.intersection(alternatives)
            for alternatives in required_groups
        ):
            raise IncompletePostProcessingError(
                "OFGS error: OpenFOAM post-processing data is incomplete."
            )
    datasets = parse_datasets(outputs)
    validate_post_processing_snapshot(case, snapshot, SUPPORTED_FILENAMES)
    graph_count = len(datasets)
    graph_label = "graph" if graph_count == 1 else "graphs"
    print(f"Found {graph_count} supported {graph_label}.")
    print()

    write_monitor(case, datasets)
    if not graph_count:
        print("No supported OFGS datasets found. Nothing was generated.")
        return
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
    except (IncompletePostProcessingError, PostProcessingChangedError) as error:
        print(error, file=sys.stderr)
        print("Generation was not performed.", file=sys.stderr)
        case = Path.cwd()
        if (
            (case / "monitor.gp").is_file()
            or (case / "graphs" / "index.txt").is_file()
        ):
            print("Existing generated graphs have been preserved.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(entrypoint())
