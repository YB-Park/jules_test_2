import asyncio
from prompt_toolkit import PromptSession as ToolkitPromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from pathlib import Path

from .session import ShellSession # Assuming ShellSession is in session.py
from . import constants

async def interactive_shell_loop():
    """
    Main interactive loop for the shell.
    """
    print(f"[INFO] Shell module started. OS: {constants.OS_TYPE}")
    print("Initializing shell session...")

    session = ShellSession()
    await session._initialize_shell() # Initialize the actual shell subprocess

    if not session.process:
        print("[ERROR] Failed to initialize shell process. Exiting.")
        return

    # Use prompt_toolkit for rich command line interface
    # History file will be stored in user's home directory
    history_file = Path.home() / ".shell_module_history"
    pt_session = ToolkitPromptSession(
        history=FileHistory(str(history_file))
    )

    print("-" * 40)
    print("[INFO] Entering interactive shell mode...")
    print("Type 'exit' or 'quit' to leave the shell.")
    print("-" * 40)

    try:
        while session._running: # Use a flag in ShellSession to control the loop
            try:
                current_prompt = await session.get_prompt()
                user_input = await pt_session.prompt_async(
                    current_prompt,
                    auto_suggest=AutoSuggestFromHistory(),
                    # refresh_interval=0.5 # Can be used if prompt needs dynamic updates while typing
                )

                if user_input.strip().lower() in constants.EXIT_COMMANDS:
                    break

                if not user_input.strip(): # Empty input
                    continue

                # User has entered a command. Execute it directly.
                # The execute_command method in ShellSession is responsible for:
                # 1. Sending the command to the shell.
                # 2. Streaming stdout/stderr to the console.
                # 3. Updating CWD after command execution.
                # Return values (full_stdout, full_stderr, return_code) can be used if needed,
                # but for a basic interactive loop, direct streaming is often sufficient.
                await session.execute_command(user_input)

                # The loop will then fetch the updated prompt and wait for next input.

            except KeyboardInterrupt:
                # Handle Ctrl+C during prompt_async (e.g., to clear current input line)
                # Or, if you want Ctrl+C to exit the shell, handle it here.
                # For now, prompt_toolkit handles Ctrl+C to clear line by default.
                # If a command is running, Ctrl+C should interrupt that command.
                # This needs more sophisticated handling in execute_command.
                print("\nKeyboardInterrupt (Ctrl+C) received. Type 'exit' to quit.")
                continue # Or break, depending on desired Ctrl+C behavior for the loop itself
            except EOFError:
                # Handle Ctrl+D as a way to exit
                print("\nEOF (Ctrl+D) received.")
                break

    finally:
        print("-" * 40)
        print("[INFO] Exiting interactive shell mode...")
        await session.close() # Gracefully close the shell subprocess
        print("[INFO] Shell session closed.")

def main():
    try:
        asyncio.run(interactive_shell_loop())
    except Exception as e:
        print(f"An unexpected error occurred in main: {e}")

if __name__ == "__main__":
    main()
