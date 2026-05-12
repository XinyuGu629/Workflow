from typing import Callable, Dict, List
import os
import glob

# Import submodules
from phase_models import build_phase_models_json
from activity import build_activity_json
from HM_SM import build_mix_hm_json, build_mix_sm_json
from FORM_HM_SM import build_hm_form_json, build_sm_form_json
from ZPF import build_zpf_json  # Newly added import

DATA_TYPE_REGISTRY: Dict[str, Callable] = {
    "phase_models": build_phase_models_json,  # Phase models
    "ACR": build_activity_json,  # Activity
    "HM_MIX": build_mix_hm_json,  # Enthalpy of mixing
    "SM_MIX": build_mix_sm_json,  # Entropy of mixing
    "HM_FORM": build_hm_form_json,  # Enthalpy of formation
    "SM_FORM": build_sm_form_json,  # Entropy of formation
    "ZPF": build_zpf_json,  # Zero phase fraction
}


def _get_input_files(input_path: str) -> List[str]:
    if os.path.isfile(input_path):
        # If it's a single file, return it directly
        return [input_path]

    elif os.path.isdir(input_path):
        # If it's a folder, find supported Excel/JSON files
        supported_extensions = ['.xlsx', '.xls', '.json']
        files = []

        for ext in supported_extensions:
            pattern = os.path.join(input_path, f'*{ext}')
            files.extend(glob.glob(pattern))

        # Filter out to keep only files (exclude subfolders)
        files = [f for f in files if os.path.isfile(f)]

        # Sort by file name for easier identification
        files.sort()

        return files

    else:
        raise ValueError(f"Input path does not exist: {input_path}")


def _ensure_output_path(output_path: str, is_folder_input: bool) -> str:
    """
    Ensure the output path exists
    Args:
        output_path: User-specified output path
        is_folder_input: Boolean indicating whether the input is a folder
    """
    if is_folder_input:
        # For folder inputs, the output path must be a directory
        if not os.path.isdir(output_path):
            # Create the directory if it does not exist
            os.makedirs(output_path, exist_ok=True)
        return output_path
    else:
        # For a single file input, ensure the parent directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        return output_path


def _process_single_file(input_file: str, output_path: str, handler: Callable, data_type: str, file_index: int,
                         total_files: int) -> bool:
    """
    Process a single file
    Args:
        input_file: Input file path
        output_path: Output path (file or directory)
        handler: Processing function handler
        data_type: Data type
        file_index: File index
        total_files: Total number of files
    """
    try:
        # Generate output file name
        if os.path.isdir(output_path):
            # If the output path is a directory, generate the output file name based on the input file name
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            output_file = os.path.join(output_path, f"{base_name}_{data_type}.json")
        else:
            # If the output path is a file, append an index when there are multiple files
            if total_files > 1:
                base_name, ext = os.path.splitext(output_path)
                output_file = f"{base_name}_{file_index}{ext}"
            else:
                output_file = output_path

        # Process the file
        print(f"  [{file_index}/{total_files}] Processing: {os.path.basename(input_file)}")
        result = handler(input_path=input_file, output_path=output_file)

        print(f"     -> Saved to: {output_file}")
        return True

    except Exception as e:
        print(f"  [{file_index}/{total_files}] Error processing {os.path.basename(input_file)}: {str(e)}")
        return False


def main():
    print("=" * 50)
    print("ESPEI input JSON generation workflow")
    print("Supports single file or batch folder processing")
    print("=" * 50)

    # Prompt user for the raw data path
    input_path = input("Please enter the input file or folder path: ").strip()
    output_path = input("Please enter the output JSON file path (or directory): ").strip()

    # Get the list of input files
    try:
        input_files = _get_input_files(input_path)
    except Exception as e:
        print(f"Error: {str(e)}")
        return

    if not input_files:
        print("Error: Could not find any supported files (Supported formats: .json, .xlsx, .xls)")
        return

    print(f"\nFound {len(input_files)} file(s):")
    for i, file in enumerate(input_files, 1):
        print(f"  [{i}] {os.path.basename(file)}")

    # Ask the user for confirmation to proceed
    confirm = input("\nDo you want to continue processing these files? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Operation cancelled")
        return

    # Determine if it's a folder input
    is_folder_input = os.path.isdir(input_path)

    # Ensure output path exists
    try:
        output_path = _ensure_output_path(output_path, is_folder_input)
    except Exception as e:
        print(f"Error: Could not create output path: {str(e)}")
        return

    # User selects the data type
    print("\nAvailable ESPEI data types:")
    data_types: List[str] = list(DATA_TYPE_REGISTRY.keys())
    for idx, key in enumerate(data_types, start=1):
        print(f"  [{idx}] {key}")

    selection = input("\nPlease select the data type (enter a number): ").strip()

    if not selection.isdigit():
        print("Error: Data type selection must be a number")
        return

    selection_idx = int(selection) - 1

    if selection_idx < 0 or selection_idx >= len(data_types):
        print("Error: Unsupported data type selection")
        return

    data_type = data_types[selection_idx]
    handler = DATA_TYPE_REGISTRY[data_type]

    # Remind the user if the type is FORM
    if data_type in ["HM_FORM", "SM_FORM"]:
        print(f"\nNote: {data_type} will generate multiple JSON files for each data point")
        print(f"The output path '{output_path}' will be used as the directory for the generated files")

    # Process files in batch
    print(f"\nStarting to process {len(input_files)} file(s)...")
    success_count = 0
    fail_count = 0

    for i, input_file in enumerate(input_files, 1):
        success = _process_single_file(
            input_file=input_file,
            output_path=output_path,
            handler=handler,
            data_type=data_type,
            file_index=i,
            total_files=len(input_files)
        )

        if success:
            success_count += 1
        else:
            fail_count += 1

    # Output processing statistics
    print(f"\n{'=' * 50}")
    print("Processing completed!")
    print(f"Success: {success_count} file(s)")
    print(f"Failed: {fail_count} file(s)")

    if success_count > 0:
        if is_folder_input or len(input_files) > 1:
            print(f"Output files are saved in: {output_path}")
        else:
            print(f"Output file: {output_path}")

    if fail_count > 0:
        print("\nSome files failed to process, please check:")
        print("  1. Is the input file format correct?")
        print("  2. Is the file extension .json, .xlsx, or .xls?")
        if data_type in ["HM_FORM", "SM_FORM"]:
            print("  3. Does the Excel file contain all required data for the FORM type?")
        elif data_type in ["HM_MIX", "SM_MIX"]:
            print("  3. Does the Excel file contain all required data for the HM/SM models?")
        elif data_type == "ZPF":
            print("  3. Does the Excel file contain all required data for the ZPF type?")


if __name__ == "__main__":
    main()