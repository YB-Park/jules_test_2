import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console

from shell_module.shell import execute_command

console = Console()

async def interactive_shell():
    """
    An interactive shell using prompt_toolkit for a better user experience.
    """
    session = PromptSession()
    console.print("[bold green]Interactive Shell.[/bold green] Type 'exit' or press Ctrl+D to quit.")

    while True:
        try:
            command_input = await session.prompt_async("[bold yellow]>> [/bold yellow]")
            command_input = command_input.strip()

            if not command_input:
                continue
            if command_input.lower() == 'exit':
                break

            execute_command(command_input)

        except (EOFError, KeyboardInterrupt):
            break

    console.print("[bold green]Exiting interactive shell.[/bold green]")


def main():
    """
    Main entry point for the shell module.
    """
    try:
        asyncio.run(interactive_shell())
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]", stderr=True)


if __name__ == "__main__":
    main()