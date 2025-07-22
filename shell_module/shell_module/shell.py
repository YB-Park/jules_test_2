import subprocess
import sys
from dataclasses import dataclass
from typing import Optional
import time
import select  # For non-blocking I/O on Unix-like systems
import os  # For non-blocking pipe operations
import platform  # To detect OS
import threading  # For Windows streaming
import io  # For TextIOWrapper
import locale  # To get preferred encoding

from rich.console import Console
from rich.live import Live  # For typing effect

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


class Shell:
    """A class to execute shell commands and maintain the working directory."""

    def __init__(self, stdout_console: Console = console, stderr_console: Console = error_console):
        """
        Initializes the Shell.

        Args:
            stdout_console: Console for stdout.
            stderr_console: Console for stderr.
        """
        self.cwd = os.getcwd()
        self.stdout_console = stdout_console
        self.stderr_console = stderr_console

    def _read_stream_text(self, stream, buffer_list, console_obj, color):
        """Helper function to read a stream as text in a separate thread."""
        if platform.system() == "Windows":
            encoding = locale.getpreferredencoding(False)
        else:
            encoding = 'utf-8'

        text_stream = io.TextIOWrapper(stream.buffer, encoding=encoding, errors='replace', newline='\n')
        for line in iter(text_stream.readline, ''):
            decoded_line = line.strip()
            console_obj.print(f"[{color}]{decoded_line}[/{color}]")
            buffer_list.append(line)

    def execute_command(self, command: str) -> CommandResult:
        """
        Executes a shell command and captures its output, maintaining the working directory.
        """
        prompt_prefix = "[bold blue]>"
        prompt_postfix = "[/bold blue]"

        with Live(console=self.stdout_console, screen=False, refresh_per_second=60) as live:
            typed_text = f"{prompt_prefix}"
            live.update(typed_text)

            for char in command:
                typed_text += char
                live.update(typed_text)
                time.sleep(0.02)

            typed_text += prompt_postfix
            live.update(typed_text)

        self.stdout_console.print("")

        full_stdout_list = []
        full_stderr_list = []

        try:
            # Command to get the current directory after execution
            get_cwd_command = 'cd' if platform.system() == "Windows" else 'pwd'
            full_command = f"{command} && {get_cwd_command}"

            if platform.system() == "Windows":
                process = subprocess.Popen(
                    full_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    encoding=None,
                    errors='replace',
                    bufsize=0,
                    cwd=self.cwd
                )

                stdout_thread = threading.Thread(
                    target=self._read_stream_text,
                    args=(process.stdout, full_stdout_list, self.stdout_console, "green")
                )
                stderr_thread = threading.Thread(
                    target=self._read_stream_text,
                    args=(process.stderr, full_stderr_list, self.stderr_console, "red")
                )

                stdout_thread.start()
                stderr_thread.start()
                process.wait()
                stdout_thread.join()
                stderr_thread.join()
                process.stdout.close()
                process.stderr.close()

            else:  # Unix-like systems
                process = subprocess.Popen(
                    full_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    encoding=None,
                    errors='replace',
                    bufsize=0,
                    cwd=self.cwd
                )

                os.set_blocking(process.stdout.fileno(), False)
                os.set_blocking(process.stderr.fileno(), False)

                stdout_buffer = b""
                stderr_buffer = b""

                while True:
                    rlist = [r for r in [process.stdout, process.stderr] if r]
                    if not rlist and process.poll() is not None:
                        break

                    readable, _, _ = select.select(rlist, [], [], 0.01)

                    for fd in readable:
                        if fd == process.stdout:
                            data = os.read(process.stdout.fileno(), 4096)
                            if data:
                                stdout_buffer += data
                                while b'\n' in stdout_buffer:
                                    line, stdout_buffer = stdout_buffer.split(b'\n', 1)
                                    decoded_line = line.decode('utf-8', errors='replace').strip()
                                    self.stdout_console.print(f"[green]{decoded_line}[/green]")
                                    full_stdout_list.append(decoded_line + '\n')
                        elif fd == process.stderr:
                            data = os.read(process.stderr.fileno(), 4096)
                            if data:
                                stderr_buffer += data
                                while b'\n' in stderr_buffer:
                                    line, stderr_buffer = stderr_buffer.split(b'\n', 1)
                                    decoded_line = line.decode('utf-8', errors='replace').strip()
                                    self.stderr_console.print(f"[red]{decoded_line}[/red]")
                                    full_stderr_list.append(decoded_line + '\n')

                    if process.poll() is not None:
                        for fd, buffer, console_obj, color, lst in [
                            (process.stdout, stdout_buffer, self.stdout_console, "green", full_stdout_list),
                            (process.stderr, stderr_buffer, self.stderr_console, "red", full_stderr_list)
                        ]:
                            try:
                                remaining_data = os.read(fd.fileno(), 4096)
                                if remaining_data:
                                    buffer += remaining_data
                            except BlockingIOError:
                                pass
                            if buffer:
                                decoded_data = buffer.decode('utf-8', errors='replace').strip()
                                console_obj.print(f"[{color}]{decoded_data}[/{color}]")
                                lst.append(decoded_data)
                        process.stdout.close()
                        process.stderr.close()
                        break

            returncode = process.returncode
            stdout_str = "".join(full_stdout_list)

            # Extract the new CWD from the last line of stdout
            lines = stdout_str.strip().split('\n')
            if lines and returncode == 0:
                new_cwd = lines[-1].strip()
                if os.path.isdir(new_cwd):
                    self.cwd = new_cwd
                    # Remove the CWD from the stdout that is returned
                    stdout_str = "\n".join(lines[:-1])


            return CommandResult(
                command=command,
                stdout=stdout_str,
                stderr="".join(full_stderr_list),
                returncode=returncode
            )
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            self.stderr_console.print(f"[bold red]{error_message}[/bold red]")
            return CommandResult(
                command=command,
                stdout="".join(full_stdout_list),
                stderr=error_message,
                returncode=-1,
                error=e
            )