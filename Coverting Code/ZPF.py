import json
import pandas as pd
from typing import Dict, List, Any, Optional
import os
import re


def build_zpf_json(input_path: str, output_path: str) -> Dict[str, Any]:
    """
    Build the ZPF (Zero Phase Fraction) JSON file
    """
    file_ext = os.path.splitext(input_path)[1].lower()

    if file_ext == '.json':
        with open(input_path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    elif file_ext in ['.xlsx', '.xls']:
        user_data = _read_excel_to_zpf_data(input_path)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .json, .xlsx, .xls")

    # Build ESPEI ZPF JSON
    espei_json = _build_zpf_json_structure(user_data)

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        json_str = _format_zpf_json(espei_json)
        f.write(json_str)

    return espei_json


def _read_excel_to_zpf_data(excel_path: str) -> Dict[str, Any]:
    """
    Read ZPF data from Excel
    Standard table format:
    Row 1: components
    Row 2: phases
    Row 3: reference (Metadata)
    Row 4: bibtex (Metadata)
    Row 5: comment (Metadata)
    Row 6: Data column headers
    From Row 7: Data rows
    """
    try:
        # Read Excel, do not use headers
        df = pd.read_excel(excel_path, header=None)

        if df.empty:
            raise ValueError("Excel file is empty")

        # Require at least 7 rows of data (header rows + at least 1 row of data)
        if len(df) < 7:
            raise ValueError("Excel must have at least 7 rows of data (6 header rows + at least 1 data row)")

        # Row 1: components (Starting from Column B)
        components = []
        for col in range(1, df.shape[1]):  # From second column (Column B)
            cell_value = df.iloc[0, col]
            if pd.isna(cell_value):
                break
            comp = str(cell_value).strip()
            if comp:
                components.append(comp.upper())  # Convert to uppercase

        if not components:
            raise ValueError("Row 1: No components found")

        # Row 2: phases (Starting from Column B)
        phases = []
        for col in range(1, df.shape[1]):  # From second column (Column B)
            if col >= len(df.iloc[1]):
                break
            cell_value = df.iloc[1, col]
            if pd.isna(cell_value):
                break
            phase = str(cell_value).strip()
            if phase:
                phases.append(phase.upper())  # Convert to uppercase

        if not phases:
            raise ValueError("Row 2: No phases found")

        # Rows 3-5: Metadata
        # Based on table structure: Row 3 Col 1 is "参考文献" (Reference), Col 2 is "reference", Col 3 is the specific value
        # Row 4 Col 2 is "bibtex", Col 3 is the specific value
        # Row 5 Col 2 is "comment", Col 3 is the specific value

        reference = ""
        bibtex = ""
        comment = ""

        # Iterate over Rows 3-5 to find metadata
        for row in range(2, 5):  # Rows 3-5 (indices 2-4)
            if row >= len(df):
                break

            # Check if Column 1 has a label
            label_cell = df.iloc[row, 0]
            if pd.notna(label_cell):
                label = str(label_cell).strip().lower()
                if '参考' in label or '文献' in label or 'reference' in label:
                    # This is the reference row, specific value is in Column 3 (index 2)
                    if df.shape[1] > 2 and pd.notna(df.iloc[row, 2]):
                        reference = str(df.iloc[row, 2]).strip()

            # Check if Column 2 has a metadata label
            if df.shape[1] > 1:
                meta_label_cell = df.iloc[row, 1]
                if pd.notna(meta_label_cell):
                    meta_label = str(meta_label_cell).strip().lower()

                    if 'reference' in meta_label:
                        # reference value in Column 3
                        if df.shape[1] > 2 and pd.notna(df.iloc[row, 2]):
                            reference = str(df.iloc[row, 2]).strip()
                    elif 'bibtex' in meta_label:
                        # bibtex value in Column 3
                        if df.shape[1] > 2 and pd.notna(df.iloc[row, 2]):
                            bibtex = str(df.iloc[row, 2]).strip()
                    elif 'comment' in meta_label:
                        # comment value in Column 3
                        if df.shape[1] > 2 and pd.notna(df.iloc[row, 2]):
                            comment = str(df.iloc[row, 2]).strip()

        # If reference is still empty, try another method
        if not reference and df.shape[1] > 2:
            # Directly check Row 3 Column 3
            if pd.notna(df.iloc[2, 2]):
                reference = str(df.iloc[2, 2]).strip()

        # Row 6: Data column headers
        # Determine column indices
        index_col = 0  # Index column (Column A)
        phase1_col = 1  # Phase 1 column (Column B)
        phase2_col = 2  # Phase 2 column (Column C)
        temperature_col = None  # Temperature column
        element_cols = {}  # Element content columns

        # Look for reference element (the element before the bracket in the header of the last column in Row 6)
        reference_element = None
        reference_element_col = None

        for col in range(df.shape[1]):
            if col >= len(df.iloc[5]):  # Prevent index out of bounds
                break

            cell_value = df.iloc[5, col]
            if pd.isna(cell_value):
                continue

            header = str(cell_value).strip()
            header_lower = header.lower()

            # Look for temperature column
            if '温度' in header_lower or 'temperature' in header_lower:
                temperature_col = col
                # Check temperature unit
                temperature_unit = "K"  # Default
                if '℃' in header or '摄氏度' in header_lower or 'celsius' in header_lower:
                    temperature_unit = "℃"
                elif 'k' in header_lower and 'kelvin' not in header_lower:
                    temperature_unit = "K"

            # Look for element composition columns
            # Check if it's an element composition column (contains "含量的占比" or similar)
            for element in components:
                element_lower = element.lower()
                if element_lower in header_lower and ('含量' in header_lower or '占比' in header_lower or 'fraction' in header_lower):
                    element_cols[element] = col

                    # Check if it's the reference element (the last column)
                    if reference_element is None or col > reference_element_col:
                        # Extract element name before the bracket
                        # Format like: "Mg(含量的占比)" or "Si含量的占比"
                        if '(' in header:
                            element_part = header.split('(')[0].strip()
                        elif '（' in header:
                            element_part = header.split('（')[0].strip()
                        else:
                            # Try to extract the element name
                            element_part = header.replace('含量的占比', '').replace('占比', '').replace('fraction', '').strip()

                        if element_part.upper() == element:
                            reference_element = element
                            reference_element_col = col

        # Validate that necessary columns are found
        if temperature_col is None:
            raise ValueError("Cannot find temperature column, ensure header contains '温度' or 'temperature'")

        if not element_cols:
            raise ValueError("No element composition columns found")

        if reference_element is None:
            # If not explicitly found, use the last element composition column as the reference element
            if element_cols:
                # Sort by column index
                sorted_elements = sorted(element_cols.items(), key=lambda x: x[1])
                reference_element, reference_element_col = sorted_elements[-1]  # The last column
            else:
                raise ValueError("Cannot determine reference element")

        # From Row 7: Data rows
        temperatures = []
        phase1_list = []
        phase2_list = []
        reference_element_contents = []
        values = []  # Used to build the final values array

        for row in range(6, len(df)):
            # Check for data
            phase1_val = df.iloc[row, phase1_col]
            if pd.isna(phase1_val):
                break  # Stop when an empty row is encountered

            # Read Phase 1 and Phase 2
            phase1 = str(df.iloc[row, phase1_col]).strip().upper()
            phase2 = str(df.iloc[row, phase2_col]).strip().upper()

            phase1_list.append(phase1)
            phase2_list.append(phase2)

            # Read temperature
            temp_val = df.iloc[row, temperature_col]
            if pd.isna(temp_val):
                raise ValueError(f"Row {row + 1}, temperature value is empty")

            temperature = float(temp_val)
            temperatures.append(temperature)

            # Read reference element composition
            ref_content = df.iloc[row, reference_element_col]
            if pd.isna(ref_content):
                raise ValueError(f"Row {row + 1}, reference element {reference_element} content is empty")
            reference_element_contents.append(float(ref_content))

        if not temperatures:
            raise ValueError("No valid data rows found")

        # Temperature unit conversion (if Celsius is detected in column header)
        temp_header = str(df.iloc[5, temperature_col]).lower()
        if '℃' in temp_header or '摄氏度' in temp_header or 'celsius' in temp_header:
            # Convert to Kelvin
            temperatures = [t + 273.15 for t in temperatures]

        # Build values array
        for i in range(len(temperatures)):
            # Format: [["Phase1", ["ReferenceElement"], [ReferenceElementContent]], ["Phase2", ["ReferenceElement"], [null]]]
            value_item = [
                [phase1_list[i], [reference_element], [reference_element_contents[i]]],
                [phase2_list[i], [reference_element], [None]]
            ]
            values.append(value_item)

        # Fixed pressure
        pressure = 101325

        # broadcast_conditions defaults to false
        broadcast_conditions = False

        # Build user data dictionary
        user_data = {
            "components": components,
            "phases": phases,
            "pressure": pressure,
            "temperatures": temperatures,
            "broadcast_conditions": broadcast_conditions,
            "values": values,
            "reference": reference,
            "bibtex": bibtex,
            "comment": comment,
            "reference_element": reference_element
        }

        return user_data

    except Exception as e:
        raise ValueError(f"Error reading Excel file: {str(e)}")


def _build_zpf_json_structure(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build ESPEI ZPF JSON structure based on user data
    """
    # Retrieve data
    components = user_data["components"]
    phases = user_data["phases"]
    pressure = user_data["pressure"]
    temperatures = user_data["temperatures"]
    broadcast_conditions = user_data["broadcast_conditions"]
    values = user_data["values"]
    reference = user_data["reference"]
    bibtex = user_data.get("bibtex", "")
    comment = user_data.get("comment", "")

    # Build conditions
    conditions = {
        "P": pressure,
        "T": temperatures
    }

    # Build complete ESPEI JSON
    espei_json = {
        "components": components,
        "phases": phases,
        "conditions": conditions,
        "broadcast_conditions": broadcast_conditions,
        "output": "ZPF",
        "values": values,
        "reference": reference
    }

    # Optional fields
    if bibtex:
        espei_json["bibtex"] = bibtex
    if comment:
        espei_json["comment"] = comment

    return espei_json


def _format_zpf_json(data: Dict[str, Any]) -> str:
    """
    Format ZPF JSON, keeping the same format as examples
    """

    class ZPFJSONEncoder(json.JSONEncoder):
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
            # Use compact format for numeric arrays
            if all(isinstance(x, (int, float)) for x in obj):
                items = [self.encode(x) for x in obj]
                # Break line appropriately for long arrays
                if len(items) > 8:
                    indent = ' ' * (indent_level * 2)
                    next_indent = ' ' * ((indent_level + 1) * 2)
                    formatted_items = [f'{next_indent}{item}' for item in items]
                    return '[\n' + ',\n'.join(formatted_items) + '\n' + indent + ']'
                else:
                    return '[' + ', '.join(items) + ']'

            # For nested lists (values array)
            if all(isinstance(x, list) for x in obj):
                # Special format for values: each data point on a separate line
                if indent_level == 1:  # First level of values array
                    indent = ' ' * (indent_level * 2)
                    next_indent = ' ' * ((indent_level + 1) * 2)

                    items_str = []
                    for item in obj:
                        if isinstance(item, list):
                            # Handle each data point
                            inner_items = []
                            for inner in item:
                                if isinstance(inner, list):
                                    if len(inner) == 3:  # ["Phase", ["Element"], [Value/null]]
                                        phase_str = json.dumps(inner[0], ensure_ascii=False)
                                        element_str = self._encode_list(inner[1], indent_level + 2)

                                        # Handle the value part
                                        if inner[2] == [None]:
                                            value_str = '[null]'
                                        else:
                                            value_str = self._encode_list(inner[2], indent_level + 2)

                                        inner_str = f'[{phase_str}, {element_str}, {value_str}]'
                                        inner_items.append(inner_str)
                                    else:
                                        inner_items.append(self._encode_list(inner, indent_level + 2))
                                else:
                                    inner_items.append(self.encode(inner))
                            item_str = '[' + ', '.join(inner_items) + ']'
                            items_str.append(f'{next_indent}{item_str}')

                    return '[\n' + ',\n'.join(items_str) + '\n' + indent + ']'

            # Default case: standard format for others
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
    return json.dumps(data, cls=ZPFJSONEncoder, ensure_ascii=False, indent=2)


def _validate_zpf_input(data: Dict[str, Any]):
    """
    Validate ZPF data input
    """
    required_keys = ["components", "phases", "temperatures", "values", "reference"]

    for key in required_keys:
        if key not in data:
            raise KeyError(f"Missing required key: {key}")

    # Validate components
    if not isinstance(data["components"], list) or len(data["components"]) < 2:
        raise ValueError("components must be a list containing at least 2 elements")

    # Validate phases
    if not isinstance(data["phases"], list) or len(data["phases"]) < 2:
        raise ValueError("phases must be a list containing at least 2 phases")

    # Validate matching array lengths
    temp_len = len(data["temperatures"])
    values_len = len(data["values"])

    if temp_len != values_len:
        raise ValueError(f"Length of temperature data ({temp_len}) does not match length of values data ({values_len})")

    # Validate values structure
    for i, value_item in enumerate(data["values"]):
        if not isinstance(value_item, list) or len(value_item) != 2:
            raise ValueError(f"Data point {i + 1}: values format error, should be a list containing 2 phases")

        for j, phase_data in enumerate(value_item):
            if not isinstance(phase_data, list) or len(phase_data) != 3:
                raise ValueError(f"Data point {i + 1}, phase {j + 1}: format error, should be [PhaseName, [Element], [Value]]")