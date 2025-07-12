import asyncio
import sys
from shell_module.session import BashSession
from shell_module import constants

async def automation_example():
    print("-" * 50)
    print("[INFO] Attempting to create Bash shell session...")

    session = BashSession()
    try:
        await session.initialize()
    except Exception as e:
        print(f"[FATAL] Could not create a shell session: {e}")
        return

    print(f"[INFO] Shell session created successfully. Type: {session.shell_type}")
    print("-" * 50)

    print("[INFO] Starting automated command sequence...")
    print("Each command will be 'typed out' after its prompt.")
    print("Output will be streamed in real-time.")
    print("-" * 50)
    await asyncio.sleep(1)

    commands = [
        "echo 'Hello from Bash Automation!'",
        "ls -la",
        "cd ..",
        "pwd",
        "ls non_existent_file_12345", # This should produce stderr
        "echo 'Automation sequence complete.'"
    ]

    for cmd in commands:
        # 1. Get and print the pretty prompt
        display_prompt = await session.get_display_prompt()
        print(display_prompt, end="", flush=True)

        # 2. Simulate typing the command
        for char in cmd:
            print(char, end="", flush=True)
            await asyncio.sleep(constants.TYPING_EFFECT_DELAY / 2)
        print() # Newline after command

        # 3. Execute and get results. Output is already printed in real-time.
        full_output = await session.execute(cmd, print_output=True)

        # Optional: Do something with the full returned output
        # print("\n--- Returned output block ---")
        # print(full_output)
        # print("---------------------------\n")

        await asyncio.sleep(0.5)

    print("-" * 50)
    print("[INFO] Automated command sequence finished.")
    await session.close()
    print("[INFO] Shell session closed.")
    print("-" * 50)

if __name__ == "__main__":
    # Add project root to path to allow direct execution of this script
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from shell_module.session import BashSession
    from shell_module import constants

    try:
        asyncio.run(automation_example())
    except KeyboardInterrupt:
        print("\n[INFO] Automation example interrupted by user.")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred in main: {e}")
    finally:
        print("[INFO] Script finished.")
