from pathlib import Path


def verify_case(case_path: Path):
    control_dict = case_path / "system" / "controlDict"

    if not control_dict.exists():
        raise FileNotFoundError(
            f"{control_dict} not found.\n"
            "Current directory does not appear to be an OpenFOAM case."
        )

    return control_dict


def read_control_dict(control_dict: Path):
    return control_dict.read_text()

def parse_function_objects(text):
    """
    Return the top-level function object names from the
    functions { } block, ignoring embedded C++ code blocks.
    """

    lines = text.splitlines()

    objects = []

    in_functions = False
    waiting_for_functions_brace = False

    dict_depth = 0
    cpp_depth = 0

    candidate = None

    for raw in lines:

        line = raw.strip()

        # Ignore comments
        if line.startswith("//"):
            continue

        # Find "functions"
        if not in_functions:
            if line == "functions":
                waiting_for_functions_brace = True
                continue

            if waiting_for_functions_brace and line == "{":
                in_functions = True
                dict_depth = 1
                continue

            continue

        # Enter C++ block (#{
        if "#{" in line:
            cpp_depth += 1
            continue

        # Inside C++ block
        if cpp_depth > 0:

            if "#};" in line:
                cpp_depth -= 1

            continue

        # Leaving functions block
        if line == "}":
            dict_depth -= 1

            if dict_depth == 0:
                break

            continue

        # Opening dictionary
        if line == "{":

            dict_depth += 1

            if dict_depth == 2 and candidate:
                objects.append(candidate)

            continue

        # Closing nested dictionary
        if line.startswith("}"):
            dict_depth -= 1
            continue

        # Candidate object name
        if (
            dict_depth == 1
            and line
            and ";" not in line
        ):
            candidate = line

    return objects