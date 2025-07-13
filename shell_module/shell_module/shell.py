import subprocess
import sys
from dataclasses import dataclass
from typing import Optional
import time
import select # For non-blocking I/O on Unix-like systems
import os # For non-blocking pipe operations
import platform # To detect OS
import threading # For Windows streaming
import io # For TextIOWrapper
import locale # To get preferred encoding

from rich.console import Console
from rich.live import Live # For typing effect

console = Console()
error_console = Console(file=sys.stderr)

@dataclass
class CommandResult:
    """Represents the result of a shell command execution."""
    command: str
    stdout: str
    stderr: str
    returncode: int
    error: Optional[Exception] = None

def _read_stream_text(stream, buffer_list, console_obj, color):
    """Helper function to read a stream as text in a separate thread."""
    # Determine encoding based on OS
    if platform.system() == "Windows":
        # Use locale's preferred encoding for Windows console output
        # This is often CP949 for Korean Windows systems
        encoding = locale.getpreferredencoding(False)
    else:
        encoding = 'utf-8'

    # Wrap the byte stream in a TextIOWrapper for line-by-line reading with encoding
    text_stream = io.TextIOWrapper(stream.buffer, encoding=encoding, errors='replace', newline='\n')
    for line in iter(text_stream.readline, ''):
        decoded_line = line.strip()
        console_obj.print(f"[{color}]{decoded_line}[/{color}]")
        buffer_list.append(line) # Append original line with newline for full_stdout_list

def execute_command(
    command: str,
    stdout_console: Console = console,
    stderr_console: Console = error_console
) -> CommandResult:
    """
    Executes a shell command in a cross-platform way and captures its output.
    Output is streamed in real-time to the console.

    Args:
        command: The command string to execute.
        stdout_console: Console instance for stdout. Defaults to global console.
        stderr_console: Console instance for stderr. Defaults to global error_console.

    Returns:
        A CommandResult object containing the execution details.
    """
    prompt_prefix = "[bold blue]>"
    prompt_postfix = "[/bold blue]"

    with Live(console=stdout_console, screen=False, refresh_per_second=60) as live:
        typed_text = ""

        typed_text += prompt_prefix
        live.update(typed_text)

        for char in command:
            typed_text += char
            live.update(typed_text)
            time.sleep(0.02) # Small delay for typing effect

        typed_text += prompt_postfix
        live.update(typed_text)

    stdout_console.print("") # Add an empty line after the command display

    full_stdout_list = []
    full_stderr_list = []

    try:
        if platform.system() == "Windows":
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False, # Read as bytes
                encoding=None, # No encoding for Popen
                errors='replace',
                bufsize=0 # Unbuffered
            )

            stdout_thread = threading.Thread(
                target=_read_stream_text,
                args=(process.stdout, full_stdout_list, stdout_console, "green")
            )
            stderr_thread = threading.Thread(
                target=_read_stream_text,
                args=(process.stderr, full_stderr_list, stderr_console, "red")
            )

            stdout_thread.start()
            stderr_thread.start()

            # Wait for the process to terminate
            process.wait()

            # Ensure all output is read from threads before proceeding
            stdout_thread.join()
            stderr_thread.join()

            # Ensure pipes are closed after threads are done
            process.stdout.close()
            process.stderr.close()

        else: # Unix-like systems (Linux, macOS)
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False, # Read as bytes, then decode
                encoding=None, # No encoding for Popen, handle manually
                errors='replace',
                bufsize=0 # Unbuffered
            )

            # Set pipes to non-blocking mode
            os.set_blocking(process.stdout.fileno(), False)
            os.set_blocking(process.stderr.fileno(), False)

            stdout_buffer = b""
            stderr_buffer = b""

            # Stream stdout and stderr in real-time using select.select and os.read
            while True:
                rlist = []
                if process.stdout:
                    rlist.append(process.stdout)
                if process.stderr:
                    rlist.append(process.stderr)

                # If no more pipes to read from, and process is done, break
                if not rlist and process.poll() is not None:
                    break
                
                # Wait for data to be available on stdout or stderr, with a timeout
                readable, _, _ = select.select(rlist, [], [], 0.01) # 0.01 second timeout

                for fd in readable:
                    if fd == process.stdout:
                        data = os.read(process.stdout.fileno(), 4096) # Read up to 4KB
                        if data:
                            stdout_buffer += data
                            while b'\n' in stdout_buffer:
                                line, stdout_buffer = stdout_buffer.split(b'\n', 1)
                                decoded_line = line.decode('utf-8', errors='replace')
                                stdout_console.print(f"[green]{decoded_line.strip()}[/green]")
                                full_stdout_list.append(decoded_line + '\n')
                    elif fd == process.stderr:
                        data = os.read(process.stderr.fileno(), 4096) # Read up to 4KB
                        if data:
                            stderr_buffer += data
                            while b'\n' in stderr_buffer:
                                line, stderr_buffer = stderr_buffer.split(b'\n', 1)
                                decoded_line = line.decode('utf-8', errors='replace')
                                stderr_console.print(f"[red]{decoded_line.strip()}[/red]")
                                full_stderr_list.append(decoded_line + '\n')
                
                # Check if the process has terminated after attempting to read
                if process.poll() is not None:
                    # Read any remaining output after the process has terminated
                    # This is crucial to ensure all output is captured, especially if
                    # the process exits quickly after a final burst of output.
                    # Read remaining data from pipes
                    try:
                        remaining_stdout = os.read(process.stdout.fileno(), 4096)
                        stdout_buffer += remaining_stdout
                    except BlockingIOError:
                        pass
                    try:
                        remaining_stderr = os.read(process.stderr.fileno(), 4096)
                        stderr_buffer += remaining_stderr
                    except BlockingIOError:
                        pass

                    # Process any remaining buffered data (without splitting by newline)
                    if stdout_buffer:
                        decoded_data = stdout_buffer.decode('utf-8', errors='replace')
                        stdout_console.print(f"[green]{decoded_data.strip()}[/green]")
                        full_stdout_list.append(decoded_data)
                    if stderr_buffer:
                        decoded_data = stderr_buffer.decode('utf-8', errors='replace')
                        stderr_console.print(f"[red]{decoded_data.strip()}[/red]")
                        full_stderr_list.append(decoded_data)

                    # Explicitly close pipes
                    process.stdout.close()
                    process.stderr.close()
                    break # Exit the loop after processing remaining output

        returncode = process.returncode

        return CommandResult(
            command=command,
            stdout="".join(full_stdout_list),
            stderr="".join(full_stderr_list),
            returncode=returncode
        )
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        stderr_console.print(f"[bold red]{error_message}[/bold red]")
        return CommandResult(
            command=command,
            stdout="".join(full_stdout_list),
            stderr=error_message,
            returncode=-1,
            error=e
        )