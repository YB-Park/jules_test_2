import asyncio
import sys

# Adjust import path if running from root of a larger project
# For example, if shell_module is a subdir of your main project.
# from .shell_module.session import ShellSession
# from .shell_module import constants

# If running this script directly from within the shell_module directory,
# or if shell_module is in PYTHONPATH:
try:
    from shell_module.session import ShellSession
    from shell_module import constants
    from shell_module.styles import custom_style # Import the style
except ModuleNotFoundError:
    # Fallback for running script from parent directory (e.g., project root)
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from shell_module.shell_module.session import ShellSession
    from shell_module.shell_module import constants
    from shell_module.shell_module.styles import custom_style # Import the style

# Ensure os is imported if not already, for sys.path.abspath
import os


async def automation_example():
    """
    Demonstrates using ShellSession for automated command execution
    with UI effects.
    """
    session = ShellSession()
    print("-" * 50)
    print("[INFO] Shell session created (stateless mode).")
    print(f"[INFO] Target OS: {session.os_type}")
    print("-" * 50)

    # No longer need to initialize or check for a persistent process
    # if not session.process or session.process.returncode is not None:
    #     print("[ERROR] Shell process failed to initialize. Exiting.")
    #     return

    print("-" * 50)
    print("[INFO] Starting automated command sequence...")
    print("Each command will be 'typed out' after its prompt.")
    print("Output will be streamed.")
    print("-" * 50)
    await asyncio.sleep(1) # Pause for user to read intro

    commands = []
    if session.os_type == "windows":
        commands = [
            "echo 'Hello from Windows Automation! 한글 테스트'", # Use single quotes
            "dir /ad", # List directories
            "cd ..",
            "echo 'Current directory should be parent.'", # Use single quotes
            "cd", # Print current directory
            "timeout /t 2 /nobreak > nul", # Sleep for 2 seconds
            "echo 'Automation sequence complete.'" # Use single quotes
        ]
    else: # Linux/macOS
        commands = [
            "echo 'Hello from Linux/macOS Automation!'",
            "ls -a",
            "cd ..",
            "echo 'Current directory should be parent.'",
            "pwd", # Print current directory
            "sleep 2",
            "echo 'Automation sequence complete.'"
        ]

    commands.append("non_existent_command_test_12345") # Test error handling

    for cmd in commands:
        # Default typing_delay in run_command_for_automation is TYPING_EFFECT_DELAY / 1.5
        # Pass the custom_style to the method
        stdout, stderr, code = await session.run_command_for_automation(cmd, style=custom_style)

        # Optional: print collected stdout/stderr if needed for logging,
        # though it's already printed line-by-line during streaming.
        # if code != 0 and stderr:
        #    print(f"[DEBUG] Command '{cmd}' exited with {code}. Stderr: {stderr[:200]}...") # Log snippet

        await asyncio.sleep(1) # Pause between commands for readability

    print("-" * 50)
    print("[INFO] Automated command sequence finished.")
    # No longer need to close a persistent session
    # await session.close()
    print("-" * 50)

if __name__ == "__main__":
    # Ensure the script can be run from different locations relative to the module
    # This basic example assumes you might run it from shell_module's parent or shell_module itself.
    # For more robust execution, consider packaging or setting PYTHONPATH.

    # Example: if you are in project_root and run `python shell_module/run_automation_example.py`
    # the ModuleNotFoundError fallback for imports should work.
    # If you are in project_root/shell_module and run `python run_automation_example.py`
    # the direct imports should work.

    # Modern and simpler way to run asyncio main function, avoids DeprecationWarning.
    try:
        asyncio.run(automation_example())
    except KeyboardInterrupt:
        print("\n[INFO] Automation example interrupted by user.")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred in main: {e}")
    finally:
        print("[INFO] Script finished.")
