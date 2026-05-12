# [file name]: run_param_gen.py
"""
ESPEI driver file generation tool
Standalone program for generating the run_param_gen.yaml file
"""

import yaml
import os
import sys
from typing import Dict, Any, Optional
from pathlib import Path


def extract_filename_only(path_str: str) -> str:
    """
    Extract the pure filename from a path (without the directory path)

    Args:
        path_str: File path

    Returns:
        Pure filename
    """
    # If it is an empty string, return directly
    if not path_str:
        return ""

    # Process path using os.path
    filename = os.path.basename(path_str)

    # If there is no filename (e.g., it is a directory and ends with a separator), try to get the parent directory name
    if not filename:
        # Remove the trailing separator
        clean_path = path_str.rstrip(os.sep).rstrip('/')
        filename = os.path.basename(clean_path)
        if filename:
            return filename + os.sep  # Keep the slash for directories

    return filename


def create_default_yaml_content(
        phase_models_filename: str,
        datasets_name: str,
        output_db_name: str,
        logfile_name: str,
        verbosity: int = 2
) -> Dict[str, Any]:
    """
    Create default YAML content

    Args:
        phase_models_filename: Phase models filename (filename only)
        datasets_name: Datasets directory name
        output_db_name: Output TDB filename
        logfile_name: Log filename
        verbosity: Verbosity level

    Returns:
        YAML dictionary content
    """
    return {
        "system": {
            "phase_models": phase_models_filename,
            "datasets": datasets_name,
            "tags": {
                "dft": {
                    "excluded_model_contributions": ["idmix", "mag"]
                },
                "estimated-entropy": {
                    "excluded_model_contributions": ["idmix", "mag"],
                    "weight": 0.1
                }
            }
        },
        "output": {
            "output_db": output_db_name,
            "verbosity": verbosity,
            "logfile": logfile_name
        },
        "generate_parameters": {
            "ref_state": "SGTE91",
            "excess_model": "linear",
            "aicc_penalty_factor": {
                "LIQUID": {
                    "HM": 1.4,
                    "SM": 1.4
                }
            }
        }
    }


def save_yaml_file(yaml_content: Dict[str, Any], output_path: Path) -> bool:
    """
    Save the YAML file

    Args:
        yaml_content: YAML content
        output_path: Output file path

    Returns:
        Whether the save was successful
    """
    try:
        # Ensure the directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the YAML file
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        return True
    except Exception as e:
        print(f"Failed to save file: {e}")
        return False


def get_valid_input(prompt: str, default: str = "", required: bool = True,
                    validate_func: Optional[callable] = None) -> str:
    """
    Get valid user input

    Args:
        prompt: Prompt message
        default: Default value
        required: Whether it is required
        validate_func: Validation function

    Returns:
        The value entered by the user
    """
    while True:
        if default:
            user_input = input(f"{prompt} [{default}]: ").strip()
        else:
            user_input = input(f"{prompt}: ").strip()

        # If the user enters nothing and there is a default value, use the default
        if not user_input and default:
            user_input = default

        # Check if empty (if it is a required field)
        if required and not user_input:
            print("Error: This field cannot be empty")
            continue

        # Perform validation if a validation function is provided
        if validate_func and user_input:
            try:
                validate_func(user_input)
            except ValueError as e:
                print(f"Error: {e}")
                continue

        return user_input


def validate_file_exists(path: str) -> bool:
    """
    Validate that the file exists
    """
    if not os.path.exists(path):
        raise ValueError(f"Path does not exist: {path}")
    return True


def select_file_or_directory(prompt: str, item_type: str = "file",
                             default_suggestions: list = None) -> tuple:
    """
    Select a file or directory, returning (Filename only, Full path)

    Args:
        prompt: Prompt message
        item_type: Type, 'file' or 'dir'
        default_suggestions: List of default suggestions

    Returns:
        tuple: (Filename only, Full path)
    """
    print("\n" + "=" * 50)
    print(prompt)
    print("=" * 50)

    current_dir = Path.cwd()

    # Display current directory
    print(f"Current directory: {current_dir}")
    print(f"\nSearching for {item_type == 'file' and 'files' or 'directories'} in the current directory...")

    found_items = []

    if default_suggestions:
        for suggestion in default_suggestions:
            item_path = current_dir / suggestion
            if item_path.exists():
                if item_type == "file" and item_path.is_file():
                    found_items.append((suggestion, str(item_path)))
                elif item_type == "dir" and item_path.is_dir():
                    found_items.append((suggestion, str(item_path)))

    # If no suggested items are found, try scanning the directory
    if not found_items:
        print(f"Scanning for {item_type == 'file' and 'files' or 'directories'} in the current directory...")
        try:
            if item_type == "file":
                # Look for JSON files
                for item in current_dir.iterdir():
                    if item.is_file() and item.suffix.lower() in ['.json']:
                        found_items.append((item.name, str(item)))
            else:  # directory
                # Look for directories
                for item in current_dir.iterdir():
                    if item.is_dir() and not item.name.startswith('.'):
                        found_items.append((item.name, str(item)))
        except Exception as e:
            print(f"Error occurred while scanning directory: {e}")

    if found_items:
        print(f"\nFound the following {item_type == 'file' and 'files' or 'directories'}:")
        for i, (name, path) in enumerate(found_items, 1):
            print(f"  [{i}] {name}")
        print(f"  [0] Manually specify path")

        while True:
            choice = get_valid_input(f"Please select (0-{len(found_items)})",
                                     default="1" if found_items else "0",
                                     required=False,
                                     validate_func=lambda x: x.isdigit() and 0 <= int(x) <= len(found_items))

            if choice == "0":
                break
            elif choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(found_items):
                    name, full_path = found_items[index]
                    print(f"Selected: {name}")
                    return name, full_path

    # Manual entry
    print(f"\nPlease manually specify the {item_type == 'file' and 'file' or 'directory'} path:")

    while True:
        full_path = get_valid_input(f"Full path", required=True)

        # Validate that the path exists
        if not os.path.exists(full_path):
            print(f"Error: Path does not exist: {full_path}")
            continue

        # Validate type
        if item_type == "file":
            if not os.path.isfile(full_path):
                print(f"Error: Not a file: {full_path}")
                continue
        else:  # directory
            if not os.path.isdir(full_path):
                print(f"Error: Not a directory: {full_path}")
                continue

        # Extract only the filename or directory name
        if item_type == "file":
            filename = extract_filename_only(full_path)
            if not filename:
                print(f"Error: Cannot extract filename from path: {full_path}")
                continue
            print(f"Will use filename: {filename}")
            return filename, full_path
        else:
            # For directories, extract the directory name
            dirname = extract_filename_only(full_path.rstrip(os.sep).rstrip('/'))
            if not dirname:
                dirname = os.path.basename(full_path.rstrip(os.sep).rstrip('/'))
            print(f"Will use directory name: {dirname}")
            return dirname, full_path


def get_phase_models_info() -> tuple:
    """
    Get phase models file information

    Returns:
        tuple: (Filename only, Full path)
    """
    suggested_files = ["phase_models.json", "phases.json", "input/phase_models.json"]
    return select_file_or_directory("1. Phase models file setup", "file", suggested_files)


def get_datasets_info() -> tuple:
    """
    Get datasets directory information

    Returns:
        tuple: (Directory name, Full path)
    """
    suggested_dirs = ["input-data", "datasets", "data", "input", "output"]
    return select_file_or_directory("2. Datasets directory setup", "dir", suggested_dirs)


def get_output_db_name() -> str:
    """
    Get the output TDB filename
    """
    print("\n" + "=" * 50)
    print("3. Output TDB file setup")
    print("=" * 50)

    # Suggest using the current directory name
    current_dir = Path.cwd()
    dir_name = current_dir.name
    if dir_name:
        default_name = f"{dir_name}-generated.tdb"
    else:
        default_name = "generated.tdb"

    print(f"Note: The TDB file will be generated in the current directory when ESPEI runs")
    return get_valid_input(
        "Please enter the output TDB filename",
        default=default_name,
        required=True
    )


def get_logfile_name() -> str:
    """
    Get the log filename
    """
    print("\n" + "=" * 50)
    print("4. Log file setup")
    print("=" * 50)

    print("Note: The log file will be generated in the current directory when ESPEI runs")
    return get_valid_input(
        "Please enter the log filename",
        default="espei_log.txt",
        required=True
    )


def get_verbosity() -> int:
    """
    Get the verbosity level
    """
    print("\n" + "=" * 50)
    print("5. Verbosity level setup")
    print("=" * 50)

    print("Verbosity level description:")
    print("  0: Show warnings only (Warnings)")
    print("  1: Show info and warnings (Info + Warnings)")
    print("  2: Show debug info, info, and warnings (Debug + Info + Warnings)")

    while True:
        choice = get_valid_input(
            "Please select a verbosity level (0/1/2)",
            default="2",
            required=True
        )

        if choice in ["0", "1", "2"]:
            return int(choice)
        else:
            print("Error: Please enter 0, 1, or 2")


def get_output_yaml_path() -> Path:
    """
    Get the output YAML file path
    """
    print("\n" + "=" * 50)
    print("6. Output YAML file setup")
    print("=" * 50)

    default_path = Path.cwd() / "run_param_gen.yaml"

    while True:
        user_input = get_valid_input(
            "Please enter the output YAML file path",
            default=str(default_path),
            required=True
        )

        output_path = Path(user_input)

        # Ensure correct extension
        if output_path.suffix.lower() not in ['.yaml', '.yml']:
            output_path = output_path.with_suffix('.yaml')

        # Check if the file already exists
        if output_path.exists():
            print(f"Warning: File '{output_path}' already exists")
            overwrite = get_valid_input("Overwrite? (y/n)", default="n", required=False)
            if overwrite.lower() != 'y':
                continue

        return output_path


def preview_yaml_content(yaml_content: Dict[str, Any]) -> None:
    """
    Preview YAML content
    """
    print("\n" + "=" * 60)
    print("Preview of generated YAML file content:")
    print("=" * 60)

    yaml_str = yaml.dump(yaml_content, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(yaml_str)

    print("=" * 60)


def display_config_summary(phase_models_filename: str, phase_models_path: str,
                           datasets_name: str, datasets_path: str,
                           output_db_name: str, logfile_name: str,
                           verbosity: int) -> None:
    """
    Display configuration summary
    """
    print("\n" + "=" * 60)
    print("Configuration Summary:")
    print("=" * 60)

    print("\nWill write to YAML file:")
    print(f"  Phase models file: {phase_models_filename}")
    print(f"  Datasets directory: {datasets_name}")
    print(f"  Output TDB file: {output_db_name}")
    print(f"  Log file: {logfile_name}")
    print(f"  Verbosity level: {verbosity}")

    print("\nActual file locations:")
    print(f"  Phase models file: {phase_models_path}")
    print(f"  Datasets directory: {datasets_path}")

    print("\nImportant Note:")
    print("  When running ESPEI, ensure the above files/directories are in the current working directory")
    print("=" * 60)


def main():
    """
    Main function
    """
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          ESPEI Driver File Generation Tool v1.0          ║")
    print("║          Standalone - Generates run_param_gen.yaml       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    current_dir = Path.cwd()
    print(f"\nCurrent working directory: {current_dir}")
    print("\nImportant Notes:")
    print("1. ESPEI will look for files and create outputs in the current directory when running")
    print("2. Only filenames are written in the YAML file, not full paths")
    print("3. Ensure files are in the current directory or subdirectories when running ESPEI")

    try:
        # Collect all configuration information
        print("\nPlease enter the following configuration information as prompted:")

        # 1. Phase models file - Get filename only
        phase_models_filename, phase_models_path = get_phase_models_info()

        # 2. Datasets directory - Get directory name only
        datasets_name, datasets_path = get_datasets_info()

        # 3. Output TDB filename
        output_db_name = get_output_db_name()

        # 4. Log filename
        logfile_name = get_logfile_name()

        # 5. Verbosity level
        verbosity = get_verbosity()

        # Display configuration summary
        display_config_summary(
            phase_models_filename=phase_models_filename,
            phase_models_path=phase_models_path,
            datasets_name=datasets_name,
            datasets_path=datasets_path,
            output_db_name=output_db_name,
            logfile_name=logfile_name,
            verbosity=verbosity
        )

        # 6. Output YAML file path
        output_yaml_path = get_output_yaml_path()

        # Generate YAML content
        print("\n" + "=" * 60)
        print("Generating YAML configuration...")

        yaml_content = create_default_yaml_content(
            phase_models_filename=phase_models_filename,
            datasets_name=datasets_name,
            output_db_name=output_db_name,
            logfile_name=logfile_name,
            verbosity=verbosity
        )

        # Preview content
        preview_yaml_content(yaml_content)

        # Confirm to save
        confirm = get_valid_input("\nDo you want to save this configuration? (y/n)", default="y", required=False)
        if confirm.lower() != 'y':
            print("Operation cancelled")
            return

        # Save file
        print("\nSaving file...")
        if save_yaml_file(yaml_content, output_yaml_path):
            print(f"\n✅ Success! Driver file saved to: {output_yaml_path}")

            # Display usage instructions
            print("\n" + "=" * 60)
            print("Usage Instructions:")
            print("=" * 60)
            print("Before running ESPEI, make sure to:")
            print(f"1. Copy the '{phase_models_filename}' file to the run directory")
            print(f"2. Copy the '{datasets_name}' directory to the run directory")
            print(f"3. Expected run directory structure:")
            print(f"   - {phase_models_filename}")
            print(f"   - {datasets_name}/ (contains all JSON data files)")
            print(f"\nRun command:")
            print(f"  cd /path/to/your/project  # Navigate to the directory containing the above files")
            print(f"  espei run run_param_gen.yaml")
            print(f"\nESPEI will generate:")
            print(f"  - TDB file: {output_db_name}")
            print(f"  - Log file: {logfile_name}")
            print("=" * 60)

        else:
            print("❌ Failed to save!")

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user")
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        sys.exit(1)


def quick_mode():
    """
    Quick mode: Uses default settings
    """
    print("Quick Mode - Using default settings")
    print("=" * 50)

    current_dir = Path.cwd()
    print(f"Current directory: {current_dir}")

    # Auto-detect phase models file
    phase_models_candidates = ["phase_models.json", "phases.json"]

    phase_models_filename = None
    phase_models_path = None
    for candidate in phase_models_candidates:
        candidate_path = current_dir / candidate
        if candidate_path.exists() and candidate_path.is_file():
            phase_models_filename = candidate
            phase_models_path = candidate_path
            break

    if not phase_models_path:
        print("Error: Phase models file not found")
        print("Please place the phase_models.json file in the current directory")
        return

    # Auto-detect datasets directory
    datasets_candidates = ["input-data", "datasets", "data", "input", "output"]
    datasets_name = None
    datasets_path = None
    for candidate in datasets_candidates:
        candidate_path = current_dir / candidate
        if candidate_path.exists() and candidate_path.is_dir():
            datasets_name = candidate
            datasets_path = candidate_path
            break

    if not datasets_path:
        datasets_name = "input-data"
        datasets_path = current_dir / datasets_name
        print(f"Warning: Datasets directory does not exist: {datasets_name}")
        print("This directory will be created, please put your JSON data files inside it")
        datasets_path.mkdir(exist_ok=True)

    # Generate output filenames
    dir_name = current_dir.name or "espei"
    output_db_name = f"{dir_name}-generated.tdb"
    logfile_name = "espei_run.log"
    output_yaml_path = current_dir / "run_param_gen.yaml"

    print("\nConfiguration:")
    print(f"  Phase models file: {phase_models_filename}")
    print(f"  Datasets directory: {datasets_name}")
    print(f"  Output TDB file: {output_db_name}")
    print(f"  Log file: {logfile_name}")
    print(f"  Output YAML file: {output_yaml_path}")

    print(f"\nActual file locations:")
    print(f"  Phase models file: {phase_models_path}")
    print(f"  Datasets directory: {datasets_path}")

    print(f"\nWill write to YAML file:")
    print(f"  phase_models: {phase_models_filename}")
    print(f"  datasets: {datasets_name}")

    confirm = input("\nGenerate driver file? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Operation cancelled")
        return

    # Generate YAML content
    yaml_content = create_default_yaml_content(
        phase_models_filename=phase_models_filename,
        datasets_name=datasets_name,
        output_db_name=output_db_name,
        logfile_name=logfile_name,
        verbosity=2
    )

    if save_yaml_file(yaml_content, output_yaml_path):
        print(f"\n✅ Success! Driver file saved to: {output_yaml_path}")

        # Display the generated YAML content
        print("\nGenerated YAML file content:")
        print("-" * 40)
        with open(output_yaml_path, 'r', encoding='utf-8') as f:
            print(f.read())
        print("-" * 40)

        print(f"\nRun command:")
        print(f"  espei run run_param_gen.yaml")
        print(f"\nEnsure the run directory contains:")
        print(f"  - {phase_models_filename}")
        print(f"  - {datasets_name}/ (contains JSON data files)")
    else:
        print("❌ Failed to save!")


if __name__ == "__main__":
    # Check command-line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--quick" or sys.argv[1] == "-q":
            quick_mode()
        elif sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print("ESPEI Driver File Generation Tool")
            print("=" * 50)
            print("Usage: python run_param_gen.py [options]")
            print()
            print("Options:")
            print("  --quick, -q    Quick mode (uses default settings)")
            print("  --help, -h     Show this help message")
            print()
            print("No arguments: Enter interactive configuration mode")
            print()
            print("Important Notes:")
            print("  - The generated YAML file only contains filenames, not full paths")
            print("  - ESPEI will look for these files in the current directory when running")
            print("  - Ensure files are in the current directory when running ESPEI")
        else:
            print(f"Unknown parameter: {sys.argv[1]}")
            print("Use --help to view help")
    else:
        # Interactive mode
        main()