import asyncio

from prompt_toolkit import PromptSession
from rich.console import Console

from shell_module.shell import Shell

console = Console()


async def interactive_shell():
    """
    An interactive shell using prompt_toolkit for a better user experience.
    """
    session = PromptSession()
    shell = Shell()
    console.print("[bold green]Interactive Shell.[/bold green] Type 'exit' or press Ctrl+D to quit.")

    while True:
        try:
            # Display the current working directory in the prompt
            prompt_text = f"[bold yellow]({shell.cwd})[/bold yellow] [bold yellow]>> [/bold yellow]"
            command_input = await session.prompt_async(prompt_text, refresh_interval=0.5)
            command_input = command_input.strip()

            if not command_input:
                continue
            if command_input.lower() == 'exit':
                break

            shell.execute_command(command_input)

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