from pathlib import Path


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

    for dataset in sorted(root.iterdir()):

        if not dataset.is_dir():
            continue

        latest = latest_time_directory(dataset)

        if latest is None:
            continue

        files = sorted(latest.glob("*.dat"))

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