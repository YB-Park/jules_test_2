import asyncio
import sys
import os
from shell_module.session import create_shell_session # Import the factory
from shell_module import constants
from shell_module.styles import custom_style

async def automation_example():
    print("-" * 50)
    print("[INFO] Attempting to create shell session for this OS...")
    session = await create_shell_session()

    if not session:
        print("[FATAL] Could not create a shell session. Exiting.")
        return

    print(f"[INFO] Shell session created successfully. Type: {session.shell_type}")
    print("-" * 50)

    print("[INFO] Starting automated command sequence...")
    print("Each command will be 'typed out' after its prompt.")
    print("Output will be streamed.")
    print("-" * 50)
    await asyncio.sleep(1)

    commands = []
    if session.is_windows:
        commands = [
            "echo 'Hello from Windows Automation! 한글 테스트'",
            "dir",
            "cd ..",
            "echo 'Current directory should be parent.'",
            "cd",
        ]
    else: # Linux/macOS
        commands = [
            "echo 'Hello from Linux/macOS Automation!'",
            "ls -la",
            "cd ..",
            "echo 'Current directory should be parent.'",
            "pwd",
        ]

    commands.append("non_existent_command_test_12345")

    for cmd in commands:
        stdout, stderr, code = await session.run_command_for_automation(cmd, style=custom_style)
        # Reduced sleep time to better gauge command execution speed
        await asyncio.sleep(0.5)

    print("-" * 50)
    print("[INFO] Automated command sequence finished.")
    await session.close() # Close the session at the end
    print("-" * 50)

if __name__ == "__main__":
    try:
        asyncio.run(automation_example())
    except KeyboardInterrupt:
        print("\n[INFO] Automation example interrupted by user.")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred in main: {e}")
    finally:
        print("[INFO] Script finished.")
