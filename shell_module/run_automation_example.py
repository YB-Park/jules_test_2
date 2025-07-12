import asyncio
import sys
import os
from shell_module.session import ShellSession
from shell_module import constants
from shell_module.styles import custom_style

async def automation_example():
    session = ShellSession()
    print("-" * 50)
    print("[INFO] Shell session created.")
    print(f"[INFO] Target OS: {session.os_type}")
    print("-" * 50)

    # This is the line to be added as per user request
    await session._initialize_shell()

    print("-" * 50)
    print("[INFO] Starting automated command sequence...")
    print("Each command will be 'typed out' after its prompt.")
    print("Output will be streamed.")
    print("-" * 50)
    await asyncio.sleep(1)

    commands = []
    if session.os_type == "windows":
        commands = [
            "echo 'Hello from Windows Automation! 한글 테스트'",
            "dir /ad",
            "cd ..",
            "echo 'Current directory should be parent.'",
            "cd",
            "timeout /t 2 /nobreak > nul",
            "echo 'Automation sequence complete.'"
        ]
    else: # Linux/macOS
        commands = [
            "echo 'Hello from Linux/macOS Automation!'",
            "ls -a",
            "cd ..",
            "echo 'Current directory should be parent.'",
            "pwd",
            "sleep 2",
            "echo 'Automation sequence complete.'"
        ]

    commands.append("non_existent_command_test_12345")

    for cmd in commands:
        stdout, stderr, code = await session.run_command_for_automation(cmd, style=custom_style)
        await asyncio.sleep(1)

    print("-" * 50)
    print("[INFO] Automated command sequence finished.")
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
