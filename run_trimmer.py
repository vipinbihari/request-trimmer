import sys
import os
import subprocess

if __name__ == "__main__":
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script_path = os.path.join(script_dir, "main.py")

    # Check if main.py exists
    if not os.path.exists(main_script_path):
        print(f"Error: {main_script_path} not found.")
        sys.exit(1)

    # Construct the command to run main.py directly
    # Pass along all arguments given to this run_trimmer.py script
    command = [
        "python3",  # Explicitly use python3
        main_script_path,
    ] + sys.argv[1:]

    print(f"Executing: {' '.join(command)}")
    # Run the command
    # Execute in the script's directory so main.py can find other files like utils.py
    process = subprocess.run(command, check=False, cwd=script_dir)

    # Exit with the same code as the subprocess
    sys.exit(process.returncode)
