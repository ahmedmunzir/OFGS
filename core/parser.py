from pathlib import Path
import re


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


def parse_function_object_configurations(text):
    """Return direct function-object types and enabled states.

    This deliberately leaves ``parse_function_objects`` unchanged.  It provides
    the additional configuration detail needed to decide whether a supported
    post-processing file is expected without trying to expand OpenFOAM include
    directives.
    """
    text = re.sub(r"#\{.*?#\};", "", text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    tokens = re.findall(r"[{};]|[^\s{};]+", text)

    try:
        functions_index = tokens.index("functions")
        opening_index = tokens.index("{", functions_index + 1)
    except ValueError:
        return {}

    configurations = {}
    depth = 1
    candidate = None
    current_name = None
    current = None
    index = opening_index + 1
    while index < len(tokens) and depth:
        token = tokens[index]

        if depth == 1:
            if token == "}":
                depth = 0
            elif token == "{":
                depth = 2
                if candidate and not candidate.startswith("#"):
                    current_name = candidate
                    current = {"type": "", "enabled": True}
                candidate = None
            elif token == ";":
                candidate = None
            else:
                candidate = token
        else:
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth == 1 and current_name is not None:
                    configurations[current_name] = current
                    current_name = None
                    current = None
            elif depth == 2 and current is not None and token in {"type", "enabled"}:
                if index + 1 < len(tokens):
                    value = tokens[index + 1]
                    if token == "type":
                        current["type"] = value
                    else:
                        current["enabled"] = value.lower() not in {
                            "false", "no", "off", "0"
                        }
                    index += 1

        index += 1

    return configurations
