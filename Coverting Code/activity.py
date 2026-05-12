import json
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
import os
import re


def build_activity_json(input_path: str, output_path: str) -> Dict[str, Any]:
    file_ext = os.path.splitext(input_path)[1].lower()

    if file_ext == '.json':
        with open(input_path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    elif file_ext in ['.xlsx', '.xls']:
        user_data = _read_excel_to_activity_data(input_path)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .json, .xlsx, .xls")

    # Construct ESPEI activity JSON
    espei_json = _build_activity_json(user_data)

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        json_str = _format_activity_json(espei_json)
        f.write(json_str)

    return espei_json


def _read_excel_to_activity_data(excel_path: str) -> Dict[str, Any]:
    """
    Read activity data from Excel
    Table format:
    Row 1: Header row (Phase name, Conditions, Data source)
    Row 2: Data row (Phase name, Temperature condition, Reference)
    Row 3: components row
    Row 4: Data column headers
    From Row 5: Data rows
    """
    try:
        # Read Excel
        df = pd.read_excel(excel_path, header=None)

        if df.empty:
            raise ValueError("Excel file is empty")

        if len(df) < 5:
            raise ValueError("Excel must have at least 5 rows of data")

        # Row 1: Header row
        phase_name = str(df.iloc[0, 0]).strip()  # Phase name
        condition_str = str(df.iloc[0, 1]).strip() if pd.notna(df.iloc[0, 1]) else ""  # Condition
        reference = str(df.iloc[0, 2]).strip() if pd.notna(df.iloc[0, 2]) else ""  # Data source

        # Row 2: Data row
        actual_phase = str(df.iloc[1, 0]).strip() if pd.notna(df.iloc[1, 0]) else phase_name
        temp_condition = str(df.iloc[1, 1]).strip() if pd.notna(df.iloc[1, 1]) else condition_str
        actual_reference = str(df.iloc[1, 2]).strip() if pd.notna(df.iloc[1, 2]) else reference

        # Row 3: components
        components = []
        for col in range(df.shape[1]):
            cell_value = df.iloc[2, col]
            if pd.isna(cell_value):
                break
            comp = str(cell_value).strip()
            if comp.lower() != 'components' and comp:  # Skip "components" label
                components.append(comp.upper())  # Convert to uppercase

        if len(components) < 2:
            raise ValueError(f"At least 2 components required, found: {components}")

        # Row 4: Data column headers
        # Dynamically identify element composition columns and activity columns
        element_cols = {}  # Store element names and corresponding column indices
        activity_col = None

        for col in range(df.shape[1]):
            if col >= len(df.iloc[3]):  # Prevent index out of bounds
                break

            cell_value = df.iloc[3, col]
            if pd.isna(cell_value):
                continue

            header = str(cell_value).strip().lower()

            # Check if it is an activity column
            if '活度' in header:
                activity_col = col
                continue

            # Check if it is an element composition column
            # Assuming formats like: "Mg content ratio", "Si content ratio", "Fe content ratio", etc.
            # Or abbreviations like: "Mg", "Si", "Fe"
            for element in components:
                element_lower = element.lower()
                if element_lower in header:
                    element_cols[element] = col
                    break
            else:
                # If no specific element is matched, check if it's an abbreviation
                # Assume the column header is the element symbol
                if header.upper() in components:
                    element_cols[header.upper()] = col

        # Validate that necessary columns are found
        if len(element_cols) < 2:
            raise ValueError(f"At least 2 element composition columns must be found, currently found: {list(element_cols.keys())}")

        if activity_col is None:
            # Try to find other possible activity column names
            for col in range(df.shape[1]):
                if col >= len(df.iloc[3]):
                    break
                cell_value = df.iloc[3, col]
                if pd.isna(cell_value):
                    continue
                header = str(cell_value).strip().lower()
                if any(keyword in header for keyword in ['activity', 'acr', 'act', '活度系数']):
                    activity_col = col
                    break

            if activity_col is None:
                raise ValueError("Cannot find activity column, please ensure column header contains '活度' (activity)")

        # From Row 5: Data
        element_data = {element: [] for element in element_cols.keys()}
        activities = []

        for row in range(4, len(df)):
            # Check for data presence
            first_element = list(element_cols.keys())[0]
            first_val = df.iloc[row, element_cols[first_element]]

            if pd.isna(first_val):
                break  # Stop when an empty row is encountered

            # Read all element compositions
            for element, col_idx in element_cols.items():
                value = df.iloc[row, col_idx]
                if pd.isna(value):
                    raise ValueError(f"Row {row+1}, element {element} composition is empty")
                element_data[element].append(float(value))

            # Read activity
            activity_val = df.iloc[row, activity_col]
            if pd.isna(activity_val):
                raise ValueError(f"Row {row+1}, activity value is empty")
            activities.append(float(activity_val))

        if not activities:
            raise ValueError("No valid data rows found")

        # Verify all element data lengths are consistent
        data_length = len(activities)
        for element, values in element_data.items():
            if len(values) != data_length:
                raise ValueError(f"Element {element} data length ({len(values)}) does not match activity data length ({data_length})")

        # Extract temperature value from temperature condition
        temperature = _extract_temperature(temp_condition)

        # Default pressure
        pressure = 101325

        # Determine which element is the reference state element and which is the varying element
        # Based on instructions: X_ in reference_state corresponds to Row 4 Col 2, and X_ in conditions corresponds to Row 4 Col 3
        # Row 4 (index 3) Column 2 (index 1) and Column 3 (index 2)

        # Get reference state element and varying element
        ref_col_idx = 1  # Row 4 Column 2 (index 1)
        var_col_idx = 2  # Row 4 Column 3 (index 2)

        # Find corresponding elements through column indices
        reference_element = None
        varying_element = None

        for element, col_idx in element_cols.items():
            if col_idx == ref_col_idx:
                reference_element = element
            elif col_idx == var_col_idx:
                varying_element = element

        # If not found via specific indices, try to determine by column order
        if reference_element is None or varying_element is None:
            element_col_items = list(element_cols.items())
            if len(element_col_items) >= 2:
                # Sort by column index
                sorted_elements = sorted(element_col_items, key=lambda x: x[1])
                reference_element = sorted_elements[0][0]  # First column element
                varying_element = sorted_elements[1][0]   # Second column element

        if reference_element is None or varying_element is None:
            raise ValueError("Cannot determine reference state element and varying element")

        # Get composition data for the varying element
        varying_compositions = element_data[varying_element]

        # Determine the X value for the reference state
        # Rule: If the varying composition decreases from top to bottom in the table, 
        # then the X_ value in reference_state is 1.0, otherwise it is 0.0
        first_val = varying_compositions[0]
        last_val = varying_compositions[-1]

        if first_val > last_val:  # Composition decreases
            ref_x_value = 1.0
        else:  # Composition increases
            ref_x_value = 0.0

        # Build user data dictionary
        user_data = {
            "components": components,
            "phases": [actual_phase.upper()],  # Convert to uppercase
            "temperature": temperature,
            "pressure": pressure,
            "reference_state": {
                "phases": [actual_phase.upper()],
                "conditions": {
                    "P": pressure,
                    "T": temperature,
                    f"X_{reference_element}": ref_x_value
                }
            },
            "varying_element": varying_element,
            "varying_compositions": varying_compositions,
            "activities": activities,
            "output_element": reference_element,  # Activity belongs to the reference state element
            "reference": actual_reference
        }

        return user_data

    except Exception as e:
        raise ValueError(f"Error reading Excel file: {str(e)}")


def _extract_temperature(condition_str: str) -> float:
    """
    Extract temperature value from condition string
    """
    if not condition_str:
        return 1350.15  # Default value

    # Try matching various formats: T=1350.15K, T:1350.15, T 1350.15, 1350.15K, etc.
    patterns = [
        r'T[=:\s]+([\d.]+)\s*K?',  # T=1350.15 or T:1350.15K
        r'([\d.]+)\s*K',           # 1350.15K
        r'T\s*=\s*([\d.]+)',       # T = 1350.15
    ]

    for pattern in patterns:
        match = re.search(pattern, condition_str, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue

    # If no pattern matches, try to extract numbers directly
    numbers = re.findall(r'[\d.]+', condition_str)
    if numbers:
        try:
            # Assume the largest number is the temperature
            return float(max(numbers, key=float))
        except:
            pass

    return 1350.15  # Default value


def _build_activity_json(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build ESPEI activity JSON based on user data
    """
    # Retrieve data
    components = user_data["components"]
    phases = user_data["phases"]
    temperature = user_data["temperature"]
    pressure = user_data["pressure"]
    reference_state = user_data["reference_state"]
    varying_element = user_data["varying_element"]
    varying_compositions = user_data["varying_compositions"]
    activities = user_data["activities"]
    output_element = user_data["output_element"]
    reference = user_data["reference"]

    # Build conditions
    conditions = {
        "P": pressure,
        "T": temperature,
        f"X_{varying_element}": varying_compositions
    }

    # Build values (3D array)
    # ESPEI format requirement: [[[list of activity values]]]
    values = [[activities]]

    # Build full ESPEI JSON
    espei_json = {
        "components": components,
        "phases": phases,
        "reference_state": reference_state,
        "conditions": conditions,
        "output": f"ACR_{output_element}",
        "values": values,
        "reference": reference
    }

    return espei_json


def _format_activity_json(data: Dict[str, Any]) -> str:
    """
    Format activity JSON to match the style of example formats
    """
    class ActivityJSONEncoder(json.JSONEncoder):
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

            return '{\n' + ',\n'.join(items) + '\n' + indent + '}'

        def _encode_list(self, obj, indent_level):
            if all(isinstance(x, (int, float)) for x in obj):          
                items = [self.encode(x) for x in obj]
                return '[' + ', '.join(items) + ']'

            # For nested lists
            if all(isinstance(x, list) for x in obj):
                if indent_level == 1:  # First level of values array
                    # Second level
                    inner_lists = []
                    for inner_list in obj:
                        if all(isinstance(y, (int, float)) for y in inner_list):
                            inner_items = [self.encode(y) for y in inner_list]
                            inner_lists.append('[' + ', '.join(inner_items) + ']')
                        else:
                            inner_lists.append(self._encode_list(inner_list, indent_level + 1))
                    return '[' + ', '.join(inner_lists) + ']'

            # Use standard format for other cases
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

    # Use the custom encoder
    return json.dumps(data, cls=ActivityJSONEncoder, ensure_ascii=False, indent=2)


def _validate_activity_input(data: Dict[str, Any]):
    """
    Validate activity data input
    """
    required_keys = ["components", "phases", "reference_state",
                    "varying_element", "varying_compositions",
                    "activities", "output_element", "reference"]

    for key in required_keys:
        if key not in data:
            raise KeyError(f"Missing required key: {key}")

    # Validate components
    if not isinstance(data["components"], list) or len(data["components"]) < 2:
        raise ValueError("components must be a list with at least 2 elements")

    # Validate phases
    if not isinstance(data["phases"], list) or len(data["phases"]) != 1:
        raise ValueError("phases must be a list with exactly 1 phase")

    # Validate consistency of array lengths
    comp_len = len(data["varying_compositions"])
    act_len = len(data["activities"])

    if comp_len != act_len:
        raise ValueError(f"Length of varying_compositions ({comp_len}) does not match activities ({act_len})")

    # Validate reference_state structure
    ref_state = data["reference_state"]
    if "phases" not in ref_state or "conditions" not in ref_state:
        raise ValueError("reference_state must contain 'phases' and 'conditions'")