from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Tuple


class PostProcessingChangedError(RuntimeError):
    """Raised when post-processing inputs do not form one stable snapshot."""


@dataclass(frozen=True)
class _PathState:
    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class _DirectoryIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class _FunctionInputState:
    name: str
    timestep: str
    directory: _DirectoryIdentity
    files: Tuple[Tuple[str, _PathState], ...]


@dataclass(frozen=True)
class PostProcessingSnapshot:
    functions: Tuple[_FunctionInputState, ...]
    tracked_owners: FrozenSet[str]


def inspect_dat_file(file_path: Path):
    """
    Inspect a .dat file and extract metadata.
    
    Returns a dict with:
        - headers: list of comment lines (lines starting with '#')
        - first_row: the first non-comment, non-blank data row as a list of strings
        - num_columns: number of columns in the first data row
        - None if file cannot be read or no data found
    """
    try:
        with open(file_path, 'r') as f:
            headers = []
            first_row = None
            
            for line in f:
                line = line.strip()
                
                # Skip blank lines
                if not line:
                    continue
                
                # Collect comment/header lines
                if line.startswith('#'):
                    headers.append(line)
                    continue
                
                # First non-comment line is our data row
                if first_row is None:
                    first_row = line.split()
                    break
            
            if first_row is None:
                return None
            
            return {
                "headers": headers,
                "first_row": first_row,
                "num_columns": len(first_row),
            }
    except Exception:
        return None


def latest_time_directory(path: Path):
    """
    Return the latest numeric directory inside a function object.
    """

    if not path.exists():
        return None

    dirs = []

    for item in path.iterdir():

        if not item.is_dir():
            continue

        try:
            float(item.name)
            dirs.append(item)
        except ValueError:
            pass

    if not dirs:
        return None

    return max(dirs, key=lambda p: float(p.name))


def discover_post_processing(case_path: Path):

    root = case_path / "postProcessing"

    results = {}

    if not root.exists():
        return results

    try:
        datasets = sorted(root.iterdir())
    except OSError as error:
        raise PostProcessingChangedError(
            "OFGS error: OpenFOAM post-processing data changed during generation."
        ) from error

    for dataset in datasets:

        if not dataset.is_dir():
            continue

        try:
            latest = latest_time_directory(dataset)
        except OSError as error:
            raise PostProcessingChangedError(
                "OFGS error: OpenFOAM post-processing data changed during generation."
            ) from error

        if latest is None:
            continue

        try:
            files = sorted(latest.glob("*.dat"))
        except OSError as error:
            raise PostProcessingChangedError(
                "OFGS error: OpenFOAM post-processing data changed during generation."
            ) from error

        dataset_type = None

        if files:
            dataset_type = files[0].name

        results[dataset.name] = {
            "latest": latest,
            "files": files,
            "type": dataset_type,
        }
        
        # Inspect the first file to extract metadata
        if files:
            inspection = inspect_dat_file(files[0])
            if inspection:
                results[dataset.name]["inspection"] = inspection

    return results


def _path_state(path: Path):
    status = path.stat()
    return _PathState(
        device=status.st_dev,
        inode=status.st_ino,
        size=status.st_size,
        modified_ns=status.st_mtime_ns,
    )


def _directory_identity(path: Path):
    status = path.stat()
    return _DirectoryIdentity(device=status.st_dev, inode=status.st_ino)


def _snapshot_current_inputs(case_path, supported_filenames, tracked_owners):
    root = case_path / "postProcessing"
    functions = []
    if not root.exists():
        return PostProcessingSnapshot(tuple(functions), frozenset(tracked_owners))

    try:
        owners = sorted(path for path in root.iterdir() if path.is_dir())
        for owner_path in owners:
            latest = latest_time_directory(owner_path)
            if latest is None:
                continue
            files = sorted(
                path for path in latest.glob("*.dat")
                if path.name in supported_filenames
            )
            if not files and owner_path.name not in tracked_owners:
                continue
            functions.append(
                _FunctionInputState(
                    name=owner_path.name,
                    timestep=latest.name,
                    directory=_directory_identity(latest),
                    files=tuple((path.name, _path_state(path)) for path in files),
                )
            )
    except OSError as error:
        raise PostProcessingChangedError(
            "OFGS error: OpenFOAM post-processing data changed during generation."
        ) from error

    return PostProcessingSnapshot(tuple(functions), frozenset(tracked_owners))


def capture_post_processing_snapshot(
    case_path, outputs, supported_filenames, expected_owners=()
):
    """Capture the exact supported inputs selected by discovery.

    The extra comparison with ``outputs`` closes the window between discovery
    and this first snapshot.  Later callers use ``validate_post_processing_snapshot``
    to close the parsing window.
    """
    supported_filenames = frozenset(supported_filenames)
    tracked_owners = set(expected_owners)
    discovered = {}
    for name, info in outputs.items():
        latest = info.get("latest")
        if latest is None:
            continue
        latest = Path(latest)
        files = tuple(sorted(
            Path(path).name
            for path in info.get("files", ())
            if Path(path).name in supported_filenames
            and Path(path).parent.absolute() == latest.absolute()
        ))
        if files:
            tracked_owners.add(name)
            discovered[name] = (latest.name, files)

    snapshot = _snapshot_current_inputs(
        Path(case_path), supported_filenames, tracked_owners
    )
    current = {
        function.name: (
            function.timestep,
            tuple(filename for filename, _state in function.files),
        )
        for function in snapshot.functions
    }
    for name, selection in discovered.items():
        if current.get(name) != selection:
            raise PostProcessingChangedError(
                "OFGS error: OpenFOAM post-processing data changed during generation."
            )
    for name, selection in current.items():
        if selection[1] and name not in discovered:
            raise PostProcessingChangedError(
                "OFGS error: OpenFOAM post-processing data changed during generation."
            )
    return snapshot


def validate_post_processing_snapshot(case_path, snapshot, supported_filenames):
    """Ensure all selected supported inputs are unchanged after parsing."""
    current = _snapshot_current_inputs(
        Path(case_path), frozenset(supported_filenames), snapshot.tracked_owners
    )
    if current != snapshot:
        raise PostProcessingChangedError(
            "OFGS error: OpenFOAM post-processing data changed during generation."
        )
