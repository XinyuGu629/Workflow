import json
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
import os
import re
import ast


def build_mix_hm_json(input_path: str, output_path: str) -> Dict[str, Any]:
    """
    Build the enthalpy of mixing (HM_MIX) JSON file

    Args:
        input_path: Input file path (.json or .xlsx/.xls)
        output_path: Output JSON file path

    Returns:
        Generated JSON dictionary
    """
    return _build_hmsm_json(input_path, output_path, "HM_MIX")


def build_mix_sm_json(input_path: str, output_path: str) -> Dict[str, Any]:
    """
    Build the entropy of mixing (SM_MIX) JSON file

    Args:
        input_path: Input file path (.json or .xlsx/.xls)
        output_path: Output JSON file path

    Returns:
        Generated JSON dictionary
    """
    return _build_hmsm_json(input_path, output_path, "SM_MIX")


def _build_hmsm_json(input_path: str, output_path: str, output_type: str) -> Dict[str, Any]:
    """
    Build enthalpy/entropy of mixing JSON file

    Args:
        input_path: Input file path
        output_path: Output JSON file path
        output_type: Output type, HM_MIX or SM_MIX

    Returns:
        Generated JSON dictionary
    """
    file_ext = os.path.splitext(input_path)[1].lower()

    if file_ext == '.json':
        with open(input_path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    elif file_ext in ['.xlsx', '.xls']:
        user_data = _read_excel_to_hmsm_data(input_path, output_type)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .json, .xlsx, .xls")

    # Build ESPEI enthalpy/entropy of mixing JSON
    espei_json = _build_hmsm_json_structure(user_data, output_type)

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        json_str = _format_hmsm_json(espei_json)
        f.write(json_str)

    return espei_json


def _read_excel_to_hmsm_data(excel_path: str, output_type: str) -> Dict[str, Any]:
    """
    Read enthalpy/entropy of mixing data from Excel

    Table format:
    Row 1: Header row (Phase name, Conditions, Data source)
    Row 2: Data row (Phase name, Temperature conditions, Reference)
    Row 3: components row
    Row 4: sublattice_configurations and sublattice_ratios
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

        # Row 1: Header row
        phase_name = str(df.iloc[0, 0]).strip()  # Phase name
        condition_str = str(df.iloc[0, 1]).strip() if pd.notna(df.iloc[0, 1]) else ""  # Conditions
        reference = str(df.iloc[0, 2]).strip() if pd.notna(df.iloc[0, 2]) else ""  # Data source

        # Row 2: Data row
        actual_phase = str(df.iloc[1, 0]).strip() if pd.notna(df.iloc[1, 0]) else phase_name
        temp_condition = str(df.iloc[1, 1]).strip() if pd.notna(df.iloc[1, 1]) else condition_str
        # Extract reference from the second row, third column
        actual_reference = str(df.iloc[1, 2]).strip() if pd.notna(df.iloc[1, 2]) else reference

        # Row 3: components
        components = []
        for col in range(df.shape[1]):
            cell_value = df.iloc[2, col]
            if pd.isna(cell_value):
                break
            comp = str(cell_value).strip()
            if comp.lower() != 'components' and comp:  # Skip "components" tag
                components.append(comp.upper())  # Convert to uppercase

        if not components:
            raise ValueError("No components found")

        # Row 4: sublattice_configurations and sublattice_ratios
        sublattice_config_str = str(df.iloc[3, 1]).strip() if pd.notna(df.iloc[3, 1]) else ""
        sublattice_ratios_str = str(df.iloc[3, 3]).strip() if pd.notna(df.iloc[3, 3]) else ""

        # Parse sublattice_configurations
        sublattice_configurations = _parse_sublattice_config(sublattice_config_str)

        # Parse sublattice_site_ratios
        sublattice_site_ratios = _parse_site_ratios(sublattice_ratios_str)

        # Row 5: Data column headers - Dynamically identify element columns
        element_cols = {}  # Store element name and corresponding column index
        hm_col = None
        sm_col = None
        comment_hm = ""
        comment_sm = ""

        for col in range(df.shape[1]):
            if col >= len(df.iloc[4]):  # Prevent index out of bounds
                break

            cell_value = df.iloc[4, col]
            if pd.isna(cell_value):
                continue

            header = str(cell_value).strip()
            header_lower = header.lower()

            # Check if it is the enthalpy of mixing column
            if '混合焓' in header or 'hm_mix' in header_lower:
                hm_col = col
                # Extract comment - handle standard and Chinese parentheses
                comment_match = re.search(r'[\(（]([^\)）]+)[\)）]', header)
                if comment_match:
                    comment_hm = comment_match.group(1)
                else:
                    comment_hm = "DFT"  # Default value

            # Check if it is the entropy of mixing column
            elif '混合熵' in header or 'sm_mix' in header_lower:
                sm_col = col
                # Extract comment - handle standard and Chinese parentheses
                comment_match = re.search(r'[\(（]([^\)）]+)[\)）]', header)
                if comment_match:
                    comment_sm = comment_match.group(1)
                else:
                    comment_sm = "EST"  # Default value

            else:
                # Check if it is an element composition column
                # Look for elements from components
                for element in components:
                    element_lower = element.lower()
                    if element_lower in header_lower and ('含量' in header_lower or '占比' in header_lower or 'fraction' in header_lower):
                        element_cols[element] = col
                        break

        # Validate that necessary columns are found
        if len(element_cols) < 2:
            raise ValueError(f"At least 2 element composition columns are required, currently found: {list(element_cols.keys())}")

        if output_type == "HM_MIX" and hm_col is None:
            raise ValueError("Cannot find enthalpy of mixing column")
        if output_type == "SM_MIX" and sm_col is None:
            raise ValueError("Cannot find entropy of mixing column")

        # Determine the two main elements (excluding VA)
        active_elements = [elem for elem in element_cols.keys() if elem != 'VA']
        if len(active_elements) < 2:
            raise ValueError(f"At least 2 active elements are required, currently found: {active_elements}")

        # Use the first two active elements as main elements
        element1 = active_elements[0]
        element2 = active_elements[1]

        # From Row 6: Data
        element1_contents = []
        element2_contents = []
        values = []

        for row in range(5, len(df)):
            # Check for data
            elem1_val = df.iloc[row, element_cols[element1]]
            if pd.isna(elem1_val):
                break  # Stop when an empty row is encountered

            # Read element compositions
            element1_contents.append(float(elem1_val))

            elem2_val = df.iloc[row, element_cols[element2]]
            if pd.isna(elem2_val):
                raise ValueError(f"Row {row + 1}, {element2} content is empty")
            element2_contents.append(float(elem2_val))

            # Read enthalpy or entropy of mixing value
            if output_type == "HM_MIX":
                value = df.iloc[row, hm_col]
                if pd.isna(value):
                    raise ValueError(f"Row {row + 1}, enthalpy of mixing value is empty")
            else:  # SM_MIX
                value = df.iloc[row, sm_col]
                if pd.isna(value):
                    raise ValueError(f"Row {row + 1}, entropy of mixing value is empty")

            values.append(float(value))

        if not values:
            raise ValueError("No valid data rows found")

        # Verify data length consistency
        if len(element1_contents) != len(element2_contents) or len(element1_contents) != len(values):
            raise ValueError("Data lengths do not match")

        # Build sublattice_occupancies - process according to instructions
        sublattice_occupancies = []

        for elem1_val, elem2_val in zip(element1_contents, element2_contents):
            if len(sublattice_site_ratios) == 1:
                # If sublattice_site_ratios is just [ ], directly write the ratio of compositions
                # Format: [[elem1_val, elem2_val]]
                sublattice_occupancies.append([[elem1_val, elem2_val]])
            elif len(sublattice_site_ratios) >= 2:
                # If sublattice_site_ratios is in the format [ , ]
                # According to the example, the format should be: [[elem1_val, elem2_val], [sublattice_site_ratios[1]]]
                occupancy = []

                # First sublattice: content of the two main elements
                occupancy.append([elem1_val, elem2_val])

                # Other sublattices: use values from sublattice_site_ratios
                # Starting from the second value (the first is 1)
                for i in range(1, len(sublattice_site_ratios)):
                    occupancy.append([sublattice_site_ratios[i]])

                sublattice_occupancies.append(occupancy)
            else:
                sublattice_occupancies.append([[elem1_val, elem2_val]])

        # Build sublattice_configurations - quantity consistent with occupancies
        # Use the same configuration for each data point
        sublattice_configs = []
        for _ in range(len(element1_contents)):
            sublattice_configs.append(sublattice_configurations)

        # Extract temperature value from temp condition
        temperature = _extract_temperature(temp_condition)

        # Default pressure - use 101325 as per example
        pressure = 101325

        # Build user data dictionary
        user_data = {
            "components": components,
            "phases": [actual_phase.upper()],  # Convert to uppercase
            "temperature": temperature,
            "pressure": pressure,
            "sublattice_site_ratios": sublattice_site_ratios,
            "sublattice_occupancies": sublattice_occupancies,
            "sublattice_configurations": sublattice_configs,
            "element1": element1,
            "element2": element2,
            "element1_contents": element1_contents,
            "element2_contents": element2_contents,
            "values": values,
            "reference": actual_reference,
            "comment": comment_hm if output_type == "HM_MIX" else comment_sm
        }

        return user_data

    except Exception as e:
        raise ValueError(f"Error reading Excel file: {str(e)}")


def _parse_sublattice_config(config_str: str) -> List[List[str]]:
    """
    Parse the sublattice_configurations string

    Handles formats like: [["MG","SI"],"VA"]
    Converts to: [["MG", "SI"], ["VA"]]
    """
    if not config_str:
        return []

    # Clean the string
    config_str = config_str.strip()

    # If the string starts with [ and ends with ], parse using ast
    if config_str.startswith('[') and config_str.endswith(']'):
        try:
            # Try parsing with ast
            config = ast.literal_eval(config_str)

            # Ensure the result is a list
            if not isinstance(config, list):
                raise ValueError("sublattice_configurations must be a list format")

            # Process each element
            result = []
            for item in config:
                if isinstance(item, list):
                    # Already a list, append directly
                    result.append([str(x).upper().strip('"\'') for x in item])
                elif isinstance(item, str):
                    # String, convert to list
                    result.append([item.upper().strip('"\'')])
                else:
                    # Convert other types to string
                    result.append([str(item).upper().strip('"\'')])

            return result

        except Exception as e:
            # Parsing failed, try manual parsing
            pass

    # Manual parsing
    # Remove outer brackets
    if config_str.startswith('['):
        config_str = config_str[1:]
    if config_str.endswith(']'):
        config_str = config_str[:-1]

    result = []
    i = 0
    config_str = config_str.strip()

    while i < len(config_str):
        # Skip spaces and commas
        while i < len(config_str) and config_str[i] in ' ,':
            i += 1

        if i >= len(config_str):
            break

        if config_str[i] == '[':
            # Find the matching ']'
            j = i + 1
            bracket_count = 1
            while j < len(config_str) and bracket_count > 0:
                if config_str[j] == '[':
                    bracket_count += 1
                elif config_str[j] == ']':
                    bracket_count -= 1
                j += 1

            inner_str = config_str[i:j]
            # Clean inner string
            inner_str = inner_str.strip('[]').strip()

            # Split inner elements
            if ',' in inner_str:
                items = [item.strip().strip('"\'').upper() for item in inner_str.split(',')]
            else:
                items = [inner_str.strip().strip('"\'').upper()]

            result.append(items)
            i = j
        else:
            # Find the next comma or end
            j = i
            while j < len(config_str) and config_str[j] not in [',', ']']:
                j += 1

            item_str = config_str[i:j].strip().strip('"\'')
            if item_str:
                result.append([item_str.upper()])
            i = j

    return result


def _parse_site_ratios(ratios_str: str) -> List[float]:
    """
    Parse the sublattice_site_ratios string

    Handles formats like: "1,0.5"
    Converts to: [1.0, 0.5]
    """
    if not ratios_str:
        return [1.0]  # Default value

    # Clean the string
    ratios_str = ratios_str.strip()

    # Try parsing directly as Python list
    if ratios_str.startswith('[') and ratios_str.endswith(']'):
        try:
            # Try parsing with ast
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


def _build_hmsm_json_structure(user_data: Dict[str, Any], output_type: str) -> Dict[str, Any]:
    """
    Build ESPEI enthalpy/entropy of mixing JSON structure based on user data
    """
    # Retrieve data
    components = user_data["components"]
    phases = user_data["phases"]
    temperature = user_data["temperature"]
    pressure = user_data["pressure"]
    sublattice_site_ratios = user_data["sublattice_site_ratios"]
    sublattice_occupancies = user_data["sublattice_occupancies"]
    sublattice_configurations = user_data["sublattice_configurations"]
    values = user_data["values"]
    reference = user_data["reference"]
    comment = user_data["comment"]

    # Build solver section - following the example format
    solver = {
        "mode": "manual",
        "sublattice_site_ratios": sublattice_site_ratios,
        "sublattice_occupancies": sublattice_occupancies,
        "sublattice_configurations": sublattice_configurations
    }

    # Build conditions
    conditions = {
        "P": pressure,
        "T": temperature
    }

    # Build values as a three-level nested array
    # Format: [[[value1, value2, value3, ...]]]
    values_3d = [[values]]

    # Build complete ESPEI JSON
    espei_json = {
        "components": components,
        "phases": phases,
        "solver": solver,
        "conditions": conditions,
        "output": output_type,
        "values": values_3d,
        "reference": reference,
        "comment": comment
    }

    return espei_json


def _format_hmsm_json(data: Dict[str, Any]) -> str:
    """
    Format enthalpy/entropy of mixing JSON, keeping the same format as examples
    """

    class HmsmJSONEncoder(json.JSONEncoder):
        def encode(self, obj):
            if isinstance(obj, dict):
                return self._encode_dict(obj, 0)
            elif isinstance(obj, list):
                return self._encode_list(obj, 0)
            else:
                return super().encode(obj)

        def _encode_dict(self, obj, indent_level):
            indent = ' ' * (indent_level * 2)
            next_indent = ' ' * ((indent_level + 1) * 2)

            items = []
            for key, value in obj.items():
                key_str = json.dumps(key, ensure_ascii=False)

                if isinstance(value, dict):
                    value_str = self._encode_dict(value, indent_level + 1)
                elif isinstance(value, list):
                    value_str = self._encode_list(value, indent_level + 1)
                else:
                    value_str = self.encode(value)

                items.append(f'{next_indent}{key_str}: {value_str}')

            # Adjust indentation based on example format
            if indent_level == 0:
                # Top level: Each key-value pair on a separate line
                return '{\n' + ',\n'.join(items) + '\n' + indent + '}'
            elif indent_level == 1:
                # Second level: Format depending on content
                if len(items) == 2:  # conditions
                    inner = ', '.join(items)
                    return '{' + inner + '}'
                else:  # solver
                    return '{\n' + ',\n'.join(items) + '\n' + indent + '}'
            else:
                return '{' + ', '.join(items) + '}'

        def _encode_list(self, obj, indent_level):
            # Use compact format for numeric arrays
            if all(isinstance(x, (int, float)) for x in obj):
                # Keep numeric lists compact
                items = [self.encode(x) for x in obj]
                return '[' + ', '.join(items) + ']'

            # For nested lists
            if all(isinstance(x, list) for x in obj):
                # values array - three-level nesting
                if indent_level == 1 and len(obj) == 1 and all(isinstance(y, list) for y in obj[0]):
                    # Handle [[[value1, value2, ...]]] format
                    inner_list = obj[0]
                    if all(isinstance(y, (int, float)) for y in inner_list):
                        inner_items = [self.encode(y) for y in inner_list]
                        return '[[' + ', '.join(inner_items) + ']]'

                # sublattice_occupancies and sublattice_configurations inside solver
                if indent_level == 2:
                    # This is the list inside solver
                    items_str = []
                    for item in obj:
                        if isinstance(item, list):
                            # Handle configuration for each data point
                            inner_items = []
                            for inner in item:
                                if isinstance(inner, list):
                                    if all(isinstance(x, (int, float)) for x in inner):
                                        # Numeric list
                                        inner_items.append('[' + ', '.join([self.encode(x) for x in inner]) + ']')
                                    elif all(isinstance(x, str) for x in inner):
                                        # String list
                                        inner_items.append('[' + ', '.join([self.encode(x) for x in inner]) + ']')
                                    else:
                                        inner_items.append(self._encode_list(inner, indent_level + 1))
                                else:
                                    inner_items.append(self.encode(inner))
                            items_str.append('[' + ', '.join(inner_items) + ']')
                        else:
                            items_str.append(self.encode(item))

                    # Determine if a line break is needed based on data volume
                    if len(items_str) > 3:
                        indent_str = ' ' * ((indent_level - 1) * 2)
                        return '[\n' + ',\n'.join(items_str) + '\n' + indent_str + ']'
                    else:
                        return '[' + ', '.join(items_str) + ']'

            # Default case: each element on its own line
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

    # Apply custom encoder
    return json.dumps(data, cls=HmsmJSONEncoder, ensure_ascii=False, indent=2)


def _validate_hmsm_input(data: Dict[str, Any]):
    """
    Validate enthalpy/entropy of mixing data input
    """
    required_keys = ["components", "phases", "sublattice_site_ratios",
                     "sublattice_occupancies", "sublattice_configurations",
                     "values", "reference"]

    for key in required_keys:
        if key not in data:
            raise KeyError(f"Missing required key: {key}")

    # Validate components
    if not isinstance(data["components"], list) or len(data["components"]) < 2:
        raise ValueError("components must be a list containing at least 2 elements")

    # Validate phases
    if not isinstance(data["phases"], list) or len(data["phases"]) != 1:
        raise ValueError("phases must be a list containing exactly 1 phase")

    # Validate matching lengths for sublattice_occupancies and sublattice_configurations
    occ_len = len(data["sublattice_occupancies"])
    config_len = len(data["sublattice_configurations"])

    if occ_len != config_len:
        raise ValueError(f"Length of sublattice_occupancies ({occ_len}) does not match length of sublattice_configurations ({config_len})")