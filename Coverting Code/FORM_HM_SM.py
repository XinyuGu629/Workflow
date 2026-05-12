import json
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
import os
import re
import ast


def build_hm_form_json(input_path: str, output_path: str) -> List[Dict[str, Any]]:
    """
    Build the enthalpy of formation (HM_FORM) JSON file, generating a separate JSON file for each data point

    Args:
        input_path: Input file path (.json or .xlsx/.xls)
        output_path: Output JSON file path (can be a directory path)

    Returns:
        List of generated JSON dictionaries
    """
    return _build_form_json(input_path, output_path, "HM_FORM")


def build_sm_form_json(input_path: str, output_path: str) -> List[Dict[str, Any]]:
    return _build_form_json(input_path, output_path, "SM_FORM")


def _build_form_json(input_path: str, output_path: str, output_type: str) -> List[Dict[str, Any]]:
    file_ext = os.path.splitext(input_path)[1].lower()

    if file_ext == '.json':
        with open(input_path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    elif file_ext in ['.xlsx', '.xls']:
        user_data = _read_excel_to_form_data(input_path, output_type)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .json, .xlsx, .xls")

    # Validate output path
    if os.path.isdir(output_path):
        # If output path is a directory, generate multiple files in this directory
        output_dir = output_path
    else:
        # If output path is a file, use its parent directory
        output_dir = os.path.dirname(output_path)

    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Generate a JSON file for each data point
    all_json_data = []
    for i, single_data in enumerate(user_data):
        # Build ESPEI enthalpy/entropy of formation JSON
        espei_json = _build_form_json_structure(single_data, output_type)

        # Generate file name
        if os.path.isdir(output_path):
            # Use directory + auto-generated file name
            phase_name = single_data["phase"].replace(" ", "_").replace("+", "_").replace("(", "").replace(")", "")
            ref = single_data["reference"].replace(" ", "_")
            filename = f"{phase_name}-{output_type}-{ref}.json"
            file_path = os.path.join(output_path, filename)
        else:
            # Use user-specified file name, but append index
            base_name, ext = os.path.splitext(output_path)
            file_path = f"{base_name}_{i + 1}{ext}"

        # Write to file
        with open(file_path, "w", encoding="utf-8") as f:
            json_str = _format_form_json(espei_json)
            f.write(json_str)

        all_json_data.append(espei_json)
        print(f"Generated file: {file_path}")

    return all_json_data


def _read_excel_to_form_data(excel_path: str, output_type: str) -> List[Dict[str, Any]]:
    """
    Read enthalpy/entropy of formation data from Excel

    Table format:
    Row 1: Phase name
    Row 2: components
    Row 3: sublattice_configurations
    Row 4: sublattice_ratios
    Row 5: Data column headers
    From Row 6: Data rows
    """
    try:
        # Read Excel, do not use headers
        df = pd.read_excel(excel_path, header=None)

        if df.empty:
            raise ValueError("Excel file is empty")

        # Require at least 6 rows of data
        if len(df) < 6:
            raise ValueError("Excel must have at least 6 rows of data")

        # Row 1: Phase name (Column 2)
        phase_name = str(df.iloc[0, 1]).strip() if pd.notna(df.iloc[0, 1]) else ""
        if not phase_name:
            raise ValueError("Row 1 Column 2: Phase name cannot be empty")

        # Convert to uppercase
        phase_upper = phase_name.upper()

        # Row 2: components (starting from Column 2)
        components = []
        for col in range(1, df.shape[1]):
            cell_value = df.iloc[1, col]
            if pd.isna(cell_value):
                break
            comp = str(cell_value).strip()
            if comp:
                components.append(comp.upper())  # Convert to uppercase

        if not components:
            raise ValueError("Row 2: components not found")

        # Row 3: sublattice_configurations (Column 2)
        sublattice_config_str = str(df.iloc[2, 1]).strip() if pd.notna(df.iloc[2, 1]) else ""

        # Parse sublattice_configurations
        sublattice_configurations = _parse_sublattice_config(sublattice_config_str)

        # Row 4: sublattice_ratios (Column 2)
        sublattice_ratios_str = str(df.iloc[3, 1]).strip() if pd.notna(df.iloc[3, 1]) else ""

        # Parse sublattice_site_ratios
        sublattice_site_ratios = _parse_site_ratios(sublattice_ratios_str)

        # Row 5: Data column headers
        # Determine column indices
        index_col = 0  # Index column
        form_col = None  # Enthalpy/Entropy of formation column
        condition_col = None  # Conditions column
        reference_col = None  # Data source column

        for col in range(df.shape[1]):
            if col >= len(df.iloc[4]):  # Prevent index out of bounds
                break

            cell_value = df.iloc[4, col]
            if pd.isna(cell_value):
                continue

            header = str(cell_value).strip().lower()

            if '序号' in header or 'index' in header:
                index_col = col
            elif output_type == "HM_FORM" and ('形成焓' in header or 'hm_form' in header):
                form_col = col
            elif output_type == "SM_FORM" and ('形成熵' in header or 'sm_form' in header):
                form_col = col
            elif '条件' in header or 'condition' in header:
                condition_col = col
            elif '数据来源' in header or '文献' in header or '来源' in header or 'reference' in header:
                reference_col = col

        # Validate that necessary columns are found
        if form_col is None:
            if output_type == "HM_FORM":
                raise ValueError("Cannot find enthalpy of formation column, ensure header contains '形成焓' or 'hm_form'")
            else:
                raise ValueError("Cannot find entropy of formation column, ensure header contains '形成熵' or 'sm_form'")
        if condition_col is None:
            raise ValueError("Cannot find conditions column, ensure header contains '条件' or 'condition'")
        if reference_col is None:
            raise ValueError("Cannot find data source column, ensure header contains '数据来源' or 'reference'")

        # From Row 6: Data rows
        all_data_points = []

        for row in range(5, len(df)):
            # Check for data
            form_val = df.iloc[row, form_col]
            if pd.isna(form_val):
                continue  # Skip empty rows

            # Read enthalpy/entropy of formation value
            try:
                form_value = float(form_val)
            except ValueError:
                raise ValueError(f"Row {row + 1}, enthalpy/entropy value format error: {form_val}")

            # Read conditions
            condition_str = str(df.iloc[row, condition_col]).strip() if pd.notna(df.iloc[row, condition_col]) else ""

            # Extract temperature
            temperature = _extract_temperature(condition_str)

            # Read data source reference
            reference = str(df.iloc[row, reference_col]).strip() if pd.notna(df.iloc[row, reference_col]) else ""

            # Build dictionary for a single data point
            data_point = {
                "phase": phase_upper,
                "components": components,
                "sublattice_configurations": sublattice_configurations,
                "sublattice_site_ratios": sublattice_site_ratios,
                "form_value": form_value,
                "temperature": temperature,
                "reference": reference
            }

            all_data_points.append(data_point)

        if not all_data_points:
            raise ValueError("No valid data rows found")

        return all_data_points

    except Exception as e:
        raise ValueError(f"Error reading Excel file: {str(e)}")


def _parse_sublattice_config(config_str: str) -> List[List[str]]:
    """
    Parse the sublattice_configurations string

    Handles formats like: [["MG", "SI"]] or [["MG"], ["SI"]]
    Ensures a nested list structure is returned
    """
    if not config_str:
        return []

    # Clean the string
    config_str = config_str.strip()

    try:
        # Try parsing using ast
        config = ast.literal_eval(config_str)

        # Ensure the result is a list
        if not isinstance(config, list):
            raise ValueError("sublattice_configurations must be a list format")

        # Process each element to ensure it's a nested list
        result = []
        for item in config:
            if isinstance(item, list):
                # Already a list, append directly
                result.append([str(x).upper().strip('"\'').strip() for x in item])
            elif isinstance(item, str):
                # String, convert to list
                result.append([item.upper().strip('"\'').strip()])
            else:
                # Convert other types to string
                result.append([str(item).upper().strip('"\'').strip()])

        return result

    except Exception as e:
        # If parsing fails, try other methods
        # Remove outer brackets
        if config_str.startswith('['):
            config_str = config_str[1:]
        if config_str.endswith(']'):
            config_str = config_str[:-1]

        # Check for inner brackets
        if '[' in config_str and ']' in config_str:
            # Contains inner brackets, try parsing as nested list
            # Example: [["MG", "SI"]] -> extract "MG", "SI"
            inner_match = re.search(r'\[([^\]]+)\]', config_str)
            if inner_match:
                inner_content = inner_match.group(1)
                items = [item.strip().strip('"\'').upper() for item in inner_content.split(',')]
                return [items]

        # Otherwise split by comma and wrap as nested list
        items = [item.strip().strip('"\'').upper() for item in config_str.split(',') if item.strip()]
        return [items] if items else []


def _parse_site_ratios(ratios_str: str) -> List[float]:
    """
    Parse the sublattice_site_ratios string

    Handles formats like: "2,1" or "[2, 1]"
    """
    if not ratios_str:
        return [1.0]  # Default value

    # Clean string
    ratios_str = ratios_str.strip()

    # Try parsing directly as Python list
    if ratios_str.startswith('[') and ratios_str.endswith(']'):
        try:
            # Try using ast parse
            ratios = ast.literal_eval(ratios_str)

            if isinstance(ratios, (int, float)):
                return [float(ratios)]
            elif isinstance(ratios, list):
                return [float(r) for r in ratios]
        except Exception as e:
            # Process after removing brackets
            ratios_str = ratios_str.strip('[]')

    # Handle comma-separated strings
    if ',' in ratios_str:
        parts = ratios_str.split(',')
        result = []
        for part in parts:
            part = part.strip()
            if part:
                try:
                    result.append(float(part))
                except ValueError:
                    # Try other formats if conversion fails
                    pass
        return result if result else [1.0]
    else:
        # Single numerical value
        try:
            return [float(ratios_str)]
        except ValueError:
            return [1.0]  # Default value


def _extract_temperature(condition_str: str) -> float:
    """
    Extract temperature value from condition string
    """
    if not condition_str:
        return 300.0  # Default value

    # Try matching various formats: T=300K, T:300, T 300, 300K, etc.
    patterns = [
        r'T[=:\s]+([\d.]+)\s*K?',  # T=300 or T:300K
        r'([\d.]+)\s*K',  # 300K
        r'T\s*=\s*([\d.]+)',  # T = 300
    ]

    for pattern in patterns:
        match = re.search(pattern, condition_str, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue

    # Try extracting numbers directly if no match found
    numbers = re.findall(r'[\d.]+', condition_str)
    if numbers:
        try:
            # Take the largest number (assuming it's the temperature)
            return float(max(numbers, key=float))
        except:
            pass

    return 300.0  # Default value


def _build_form_json_structure(single_data: Dict[str, Any], output_type: str) -> Dict[str, Any]:
    """
    Build ESPEI enthalpy/entropy of formation JSON structure based on a single data point
    """
    # Retrieve data
    phase = single_data["phase"]
    components = single_data["components"]
    sublattice_configurations = single_data["sublattice_configurations"]
    sublattice_site_ratios = single_data["sublattice_site_ratios"]
    form_value = single_data["form_value"]
    temperature = single_data["temperature"]
    reference = single_data["reference"]

    # Fixed pressure
    pressure = 101325

    # Build solver section
    solver = {
        "mode": "manual",
        "sublattice_site_ratios": sublattice_site_ratios,
        "sublattice_configurations": sublattice_configurations
    }

    # Build conditions
    conditions = {
        "P": pressure,
        "T": temperature
    }

    # Build values as a three-level nested array
    values_3d = [[[form_value]]]

    # Build complete ESPEI JSON
    espei_json = {
        "components": components,
        "phases": [phase],
        "solver": solver,
        "conditions": conditions,
        "output": output_type,
        "values": values_3d,
        "reference": reference
    }

    return espei_json


def _format_form_json(data: Dict[str, Any]) -> str:
    """
    Format enthalpy/entropy of formation JSON, keeping the same format as examples
    """

    # Custom formatting function
    def format_value(value, indent=0, key=None):
        indent_str = ' ' * indent
        next_indent_str = ' ' * (indent + 2)

        if isinstance(value, dict):
            items = []
            for k, v in value.items():
                key_str = json.dumps(k, ensure_ascii=False)
                val_str = format_value(v, indent + 2, k)
                items.append(f'{next_indent_str}{key_str}: {val_str}')
            return '{\n' + ',\n'.join(items) + '\n' + indent_str + '}'

        elif isinstance(value, list):
            if not value:
                return '[]'

            # Check if it's a numeric list
            if all(isinstance(x, (int, float)) for x in value):
                items = [json.dumps(x) for x in value]
                return '[' + ', '.join(items) + ']'

            # Check if it's a string list (like components)
            if all(isinstance(x, str) for x in value):
                items = [json.dumps(x, ensure_ascii=False) for x in value]
                # Keep components in multiline format
                if key == "components" and len(items) > 1:
                    formatted_items = [f'{next_indent_str}{item}' for item in items]
                    return '[\n' + ',\n'.join(formatted_items) + '\n' + indent_str + ']'
                else:
                    return '[' + ', '.join(items) + ']'

            # Check if it's a nested list (like sublattice_configurations)
            if all(isinstance(x, list) for x in value):
                # Check if the second level is a string list
                if all(all(isinstance(y, str) for y in inner) for inner in value if isinstance(inner, list)):
                    # Double-layered string list, e.g., [["MG", "SI"]]
                    inner_strs = []
                    for inner in value:
                        inner_items = [json.dumps(y, ensure_ascii=False) for y in inner]
                        inner_strs.append('[' + ', '.join(inner_items) + ']')

                    # If there's only one inner list and few elements, keep compact
                    if len(inner_strs) == 1 and len(value[0]) <= 3:
                        return '[' + inner_strs[0] + ']'
                    else:
                        formatted_inner = [f'{next_indent_str}{inner}' for inner in inner_strs]
                        return '[\n' + ',\n'.join(formatted_inner) + '\n' + indent_str + ']'

                # Check if it's a three-level nested numerical list (like values)
                if (len(value) == 1 and isinstance(value[0], list) and
                        len(value[0]) == 1 and isinstance(value[0][0], list) and
                        all(isinstance(y, (int, float)) for y in value[0][0])):
                    # Three levels, e.g., [[[single_value]]]
                    inner_val = value[0][0][0]
                    return f'[[[{json.dumps(inner_val)}]]]'

            # Default case: each element on its own line
            items = []
            for item in value:
                item_str = format_value(item, indent + 2)
                items.append(f'{next_indent_str}{item_str}')
            return '[\n' + ',\n'.join(items) + '\n' + indent_str + ']'

        else:
            return json.dumps(value, ensure_ascii=False)

    # Apply custom formatting
    return format_value(data)


def _validate_form_input(data: Dict[str, Any]):
    """
    Validate enthalpy/entropy of formation data input
    """
    required_keys = ["phase", "components", "sublattice_configurations",
                     "sublattice_site_ratios", "form_value", "temperature", "reference"]

    for key in required_keys:
        if key not in data:
            raise KeyError(f"Missing required key: {key}")

    # Validate components
    if not isinstance(data["components"], list) or len(data["components"]) < 1:
        raise ValueError("components must be a list containing at least 1 element")

    # Validate matching lengths for sublattice_configurations and sublattice_site_ratios
    config_len = len(data["sublattice_configurations"])
    ratios_len = len(data["sublattice_site_ratios"])

    if config_len != ratios_len:
        raise ValueError(f"Length of sublattice_configurations ({config_len}) does not match length of sublattice_site_ratios ({ratios_len})")