import json
import pandas as pd
from typing import Dict, List, Any
import os


def build_phase_models_json(input_path: str, output_path: str):
    file_ext = os.path.splitext(input_path)[1].lower()  # Determine input format based on file extension (.xlsx, .xls, or .json)

    if file_ext == '.json':
        with open(input_path, "r", encoding="utf-8") as f:
            user_data = json.load(f)  # Read JSON text data
    elif file_ext in ['.xlsx', '.xls']:
        user_data = _read_excel_to_phase_data(input_path)  # Read Excel data
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .json, .xlsx, .xls")

    _validate_phase_model_input(user_data)  # Validate basic keywords
    # Construct the ESPEI phase_model .json file
    espei_json = {
        "components": user_data["components"],
        "refdata": user_data.get("refdata", None),
        "phases": {}
    }

    for phase_name, phase_info in user_data["phases"].items():
        espei_json["phases"][phase_name] = _build_single_phase(phase_info)

    # Extract to json format
    with open(output_path, "w", encoding="utf-8") as f:
        # Generate a compact but clear format
        json_str = _format_json_compact(espei_json)
        f.write(json_str)
    return espei_json


def _format_json_compact(data: Dict[str, Any]) -> str:
    class CompactJSONEncoder(json.JSONEncoder):
        def encode(self, obj):
            if isinstance(obj, dict):
                return self._encode_dict(obj)
            elif isinstance(obj, list):
                return self._encode_list(obj)
            else:
                return super().encode(obj)

        def _encode_dict(self, obj, indent_level=0):
            if not obj:
                return '{}'

            indent = ' ' * (indent_level * 2)  
            next_indent = ' ' * ((indent_level + 1) * 2)
            items = []

            for key, value in obj.items():
                key_str = f'"{key}"'
                if isinstance(value, dict):
                    value_str = self._encode_dict(value, indent_level + 1)
                elif isinstance(value, list):
                    value_str = self._encode_list(value, indent_level + 1)
                else:
                    value_str = self.encode(value)

                items.append(f'{next_indent}{key_str}: {value_str}')

            if indent_level == 0:
                # Top-level object: display each key on a new line
                return '{\n' + ',\n'.join(items) + '\n}'
            else:
                # Inner objects: keep on one line or insert line breaks appropriately
                if len(items) <= 1:  
                    inner = ', '.join(items)
                    return '{ ' + inner + ' }'
                else:
                    return '{\n' + ',\n'.join(items) + '\n' + indent + '}'

        def _encode_list(self, obj, indent_level=0):
            if not obj:
                return '[]'

            # Determine list content type
            has_complex_items = any(isinstance(x, (dict, list)) for x in obj)

            if has_complex_items:
                # For lists containing complex elements (like nested lists), put each element on a new line
                indent = ' ' * (indent_level * 2)
                next_indent = ' ' * ((indent_level + 1) * 2)
                items = []

                for item in obj:
                    if isinstance(item, dict):
                        item_str = self._encode_dict(item, indent_level + 1)
                    elif isinstance(item, list):
                        item_str = self._encode_list(item, indent_level + 1)
                    else:
                        item_str = self.encode(item)
                    items.append(f'{next_indent}{item_str}')

                return '[\n' + ',\n'.join(items) + '\n' + indent + ']'
            else:
                # For lists with simple elements (like strings, numbers), keep them on one line
                items = [self.encode(item) for item in obj]
                return '[ ' + ', '.join(items) + ' ]'

    # Apply the custom encoder
    return json.dumps(data, cls=CompactJSONEncoder, ensure_ascii=False)


def _read_excel_to_phase_data(excel_path: str) -> Dict[str, Any]:
    try:
        # Read Excel file
        return _read_excel_horizontal_format(excel_path)

    except Exception as e:
        raise ValueError(f"Error reading Excel file: {str(e)}")


def _read_excel_horizontal_format(excel_path: str) -> Dict[str, Any]:
    """Read horizontal format Excel"""
    # Read the entire sheet
    df = pd.read_excel(excel_path, header=None)  # Do not use headers, read raw data

    if df.empty:
        raise ValueError("Excel file is empty")

    # Ensure there are enough data rows
    if len(df) < 4:
        raise ValueError("Excel must have enough data (components, phases, sublattice_models and sublattice_site_ratios)")

    user_data = {}

    # Parse components (First row, starting from the second column)
    if df.iloc[0, 0] != "components":
        raise ValueError("First cell of first row must be 'components'")

    # Get components
    components = []
    for i in range(1, len(df.columns)):
        cell_value = df.iloc[0, i]
        if pd.isna(cell_value):
            break  # Stop when an empty value is encountered
        components.append(str(cell_value).strip())

    if not components:
        raise ValueError("No components found in the table")

    user_data["components"] = components

    # Parse phase names (Second row, starting from the second column)
    if df.iloc[1, 0] != "phases":
        raise ValueError("First cell of second row must be 'phases'")

    phase_names = []
    for i in range(1, len(df.columns)):
        cell_value = df.iloc[1, i]
        if pd.isna(cell_value):
            break  # Stop when an empty value is encountered
        phase_names.append(str(cell_value).strip())

    if not phase_names:
        raise ValueError("No phase names found in the table")

    # Parse sublattice_model (Third row)
    if df.iloc[2, 0] != "sublattice_model":
        raise ValueError("First cell of third row must be 'sublattice_model'")

    sublattice_models = []
    for i in range(1, len(df.columns)):
        if i - 1 >= len(phase_names):  # Only process columns with corresponding phases
            break
        cell_value = df.iloc[2, i]
        if pd.isna(cell_value):
            sublattice_models.append(None)
        else:
            try:
                model = _parse_sublattice_model(cell_value)
                sublattice_models.append(model)
            except Exception as e:
                raise ValueError(f"Error parsing sublattice_model for phase '{phase_names[i - 1]}': {str(e)}")

    # Parse sublattice_site_ratios (Fourth row)
    if df.iloc[3, 0] != "sublattice_site_ratios":
        raise ValueError("First cell of fourth row must be 'sublattice_site_ratios'")

    site_ratios_list = []
    for i in range(1, len(df.columns)):
        if i - 1 >= len(phase_names):  # Only process columns with corresponding phases
            break
        cell_value = df.iloc[3, i]
        if pd.isna(cell_value):
            site_ratios_list.append(None)
        else:
            try:
                ratios = _parse_site_ratios(cell_value)
                site_ratios_list.append(ratios)
            except Exception as e:
                raise ValueError(f"Error parsing sublattice_site_ratios for phase '{phase_names[i - 1]}': {str(e)}")

    # Build phases dictionary
    user_data["phases"] = {}

    for i, phase_name in enumerate(phase_names):
        # Check if corresponding data exists
        if i >= len(sublattice_models) or sublattice_models[i] is None:
            print(f"Warning: Phase '{phase_name}' has no sublattice_model, skipping")
            continue

        if i >= len(site_ratios_list) or site_ratios_list[i] is None:
            print(f"Warning: Phase '{phase_name}' has no sublattice_site_ratios, skipping")
            continue

        user_data["phases"][phase_name] = {
            "sublattice_model": sublattice_models[i],
            "sublattice_site_ratios": site_ratios_list[i]
        }

    if not user_data["phases"]:
        raise ValueError("No valid phases found in the Excel file")

    return user_data


def _parse_sublattice_model(model_input) -> List[List[str]]:
    if pd.isna(model_input):
        raise ValueError("sublattice_model cannot be empty")

    if isinstance(model_input, str):
        model_str = model_input.strip()

        # Clean up excess quotes in the string
        model_str = model_str.strip('"\'')

        # If the entire string is a comma-separated list without brackets, split it directly
        # Example: "MG, SI" -> [["MG", "SI"]]
        if ',' in model_str and not (model_str.startswith('[') and model_str.endswith(']')):
            items = [item.strip() for item in model_str.split(',')]
            return [items]

        # First try parsing with double quotes, if it fails, try single quotes
        try:
            import ast
            result = ast.literal_eval(model_str)
            return _validate_sublattice_structure(result)
        except:
            # If it's represented as a Python list with double quotes
            if model_str.startswith('[[') and model_str.endswith(']]'):
                try:
                    # Replace double quotes with single quotes and then parse
                    model_str_single = model_str.replace('"', "'")
                    result = ast.literal_eval(model_str_single)
                    return _validate_sublattice_structure(result)
                except:
                    pass

            # Try splitting bracketed strings by commas
            try:
                # Remove outer brackets and split by commas
                inner_str = model_str.strip('[]')
                if not inner_str:
                    raise ValueError("Empty sublattice model")

                # Check if it has a double-layered list structure
                if inner_str.startswith('[') and inner_str.endswith(']'):
                    # Handle cases like '[["MG","SI"]]' where ast parsing failed
                    # Manually parse nested lists
                    inner_str = inner_str.strip('[]')
                    if '"' in inner_str:
                        items = [item.strip().strip('"') for item in inner_str.split(',')]
                    elif "'" in inner_str:
                        items = [item.strip().strip("'") for item in inner_str.split(',')]
                    else:
                        items = [item.strip() for item in inner_str.split(',')]
                    return [items]
                else:
                    # Single-layer list
                    items = [item.strip().strip('"\'').strip() for item in inner_str.split(',')]
                    return [items]
            except:
                raise ValueError(f"Cannot parse sublattice_model string: {model_str}")

    elif isinstance(model_input, list):
        return _validate_sublattice_structure(model_input)

    else:
        raise ValueError(f"Cannot parse sublattice_model: {model_input}")


def _validate_sublattice_structure(model_structure) -> List[List[str]]:
    """Validate and normalize the sublattice structure"""
    if not isinstance(model_structure, list):
        raise ValueError(f"Expected list, got {type(model_structure)}")

    # If it's a single-layer list, wrap it into a double-layer list
    if all(isinstance(x, str) for x in model_structure):
        # Check if any strings contain commas (requiring further splitting)
        new_structure = []
        for item in model_structure:
            if ',' in item:
                # Split strings that contain commas (e.g., "MG, SI")
                split_items = [subitem.strip() for subitem in item.split(',')]
                new_structure.append(split_items)
            else:
                new_structure.append([item])
        return new_structure

    # If it's a double-layer list, verify each sublist is a string list
    if all(isinstance(x, list) for x in model_structure):
        new_structure = []
        for sublist in model_structure:
            if all(isinstance(item, str) for item in sublist):
                # Normal case, append directly
                new_structure.append(sublist)
            else:
                # If there are non-strings in the sublist, try to convert them
                converted = []
                for item in sublist:
                    if isinstance(item, str):
                        # If string contains a comma, split it
                        if ',' in item:
                            converted.extend([subitem.strip() for subitem in item.split(',')])
                        else:
                            converted.append(item)
                    else:
                        converted.append(str(item))
                new_structure.append(converted)
        return new_structure

    raise ValueError(f"Invalid sublattice structure: {model_structure}")


def _parse_site_ratios(ratios_input) -> List[float]:
    if pd.isna(ratios_input):
        raise ValueError("sublattice_site_ratios cannot be empty")

    if isinstance(ratios_input, str):
        ratios_str = ratios_input.strip()

        # If the string looks like a Python list
        if ratios_str.startswith('[') and ratios_str.endswith(']'):
            try:
                import ast
                result = ast.literal_eval(ratios_str)
                # Ensure the result is a list
                if isinstance(result, (int, float)):
                    return [float(result)]
                return [float(x) for x in result]
            except:
                # If eval fails, try splitting by comma
                inner_str = ratios_str.strip('[]')
                if not inner_str:
                    raise ValueError("Empty site ratios")
                if ',' in inner_str:
                    ratios = [float(x.strip()) for x in inner_str.split(',')]
                else:
                    ratios = [float(inner_str)]
                return ratios
        else:
            # Comma-separated or single numeric value
            if ',' in ratios_str:
                return [float(x.strip()) for x in ratios_str.split(',')]
            else:
                return [float(ratios_str)]

    elif isinstance(ratios_input, (int, float)):
        return [float(ratios_input)]

    elif isinstance(ratios_input, list):
        return [float(x) for x in ratios_input]

    else:
        raise ValueError(f"Cannot parse sublattice_site_ratios: {ratios_input}")


def _build_single_phase(phase_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a single phase entry.
    """
    sublattice_model = phase_info["sublattice_model"]
    site_ratios = phase_info["sublattice_site_ratios"]

    if len(sublattice_model) != len(site_ratios):
        raise ValueError(
            f"Length of sublattice_model ({len(sublattice_model)}) and "
            f"sublattice_site_ratios ({len(site_ratios)}) must match"
        )

    return {
        "sublattice_model": sublattice_model,
        "sublattice_site_ratios": site_ratios
    }


def _validate_phase_model_input(data: Dict[str, Any]):
    required_keys = ["components", "phases"]
    for key in required_keys:
        if key not in data:
            raise KeyError(f"Missing required key: {key}")

    if not isinstance(data["phases"], dict):
        raise TypeError("'phases' must be a dict")

    for phase_name, phase_info in data["phases"].items():
        if "sublattice_model" not in phase_info:
            raise KeyError(f"{phase_name}: missing sublattice_model")
        if "sublattice_site_ratios" not in phase_info:
            raise KeyError(f"{phase_name}: missing sublattice_site_ratios")

        # Validate matching lengths for sublattice_model and site_ratios
        model_len = len(phase_info["sublattice_model"])
        ratios_len = len(phase_info["sublattice_site_ratios"])
        if model_len != ratios_len:
            raise ValueError(
                f"{phase_name}: sublattice_model length ({model_len}) "
                f"does not match site_ratios length ({ratios_len})"
            )