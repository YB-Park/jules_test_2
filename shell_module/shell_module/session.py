import asyncio
import os
import getpass
import socket
import shutil
import sys
from abc import ABC, abstractmethod
from . import constants # typing_delay might be used

PROMPT_MARKER = "___PROMPT_MARKER___"

class Session(ABC):
    @abstractmethod
    async def execute(self, command: str, print_output: bool = True) -> str:
        pass

    @abstractmethod
    async def get_display_prompt(self) -> str:
        pass

    @abstractmethod
    async def initialize(self):
        pass

    @abstractmethod
    async def close(self):
        pass

class BashSession(Session):
    def __init__(self):
        self.process = None
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.current_working_directory = "~"

    async def initialize(self):
        bash_path = shutil.which("bash")
        if not bash_path:
            raise FileNotFoundError("bash executable not found.")

        # Start bash in interactive mode and set a unique, simple PS1 prompt
        cmd = [bash_path, "-c", f"export PS1='{PROMPT_MARKER}'; exec {bash_path} -i"]
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # Consume the initial prompt and messages
        await self._read_until_prompt()
        self.current_working_directory = await self._get_cwd()

    async def _read_until_prompt(self) -> tuple[str, str]:
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        prompt_marker_bytes = PROMPT_MARKER.encode('utf-8')

        tasks = {
            asyncio.create_task(self.process.stdout.read(1024)): self.process.stdout,
            asyncio.create_task(self.process.stderr.read(1024)): self.process.stderr,
        }

        output_ended = False
        while not output_ended:
            done, pending = await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED, timeout=5.0)

            if not done: # Timeout
                break

            for task in done:
                stream = tasks.pop(task)
                try:
                    data = task.result()
                    if not data: continue

                    if stream is self.process.stdout:
                        stdout_buffer.extend(data)
                        if prompt_marker_bytes in stdout_buffer:
                            output_ended = True
                            # Cancel pending tasks as we've found the end
                            for p_task in pending: p_task.cancel()
                            break
                    else: # stderr
                        stderr_buffer.extend(data)
                        # Print stderr as it arrives
                        sys.stderr.write(data.decode('utf-8', 'replace'))
                        sys.stderr.flush()

                except Exception:
                    continue # Ignore errors from closed streams

                # Resubmit the read task for the next chunk
                if not output_ended:
                    tasks[asyncio.create_task(stream.read(1024))] = stream

        stdout_str = stdout_buffer.decode('utf-8', 'replace')
        stderr_str = stderr_buffer.decode('utf-8', 'replace')

        # Clean up the output
        if PROMPT_MARKER in stdout_str:
            stdout_str = stdout_str.split(PROMPT_MARKER, 1)[0]

        return stdout_str, stderr_str

    async def execute(self, command: str, print_output: bool = True) -> str:
        if not self.process: raise ConnectionError("Session is not initialized.")

        self.process.stdin.write((command + "\n").encode('utf-8'))
        await self.process.stdin.drain()

        stdout, stderr = await self._read_until_prompt()

        # Filter out the echoed command from the beginning of the output
        full_output = stdout
        lines = full_output.splitlines()
        if lines and lines[0].strip() == command.strip():
            full_output = "\n".join(lines[1:])

        if print_output and full_output:
            print(full_output)

        # Update CWD after command execution for the next prompt
        self.current_working_directory = await self._get_cwd()

        return stdout + stderr # Return combined output

    async def _get_cwd(self) -> str:
        # This is a quiet command execution
        self.process.stdin.write(b"pwd\n")
        await self.process.stdin.drain()
        stdout, _ = await self._read_until_prompt()
        lines = stdout.splitlines()
        if lines and lines[0].strip() == "pwd":
            lines = lines[1:]
        return lines[-1].strip() if lines else self.current_working_directory

    async def get_display_prompt(self) -> str:
        home = os.path.expanduser("~")
        cwd = self.current_working_directory
        norm_cwd = os.path.normpath(cwd)
        norm_home = os.path.normpath(home)

        display_cwd = cwd
        if norm_cwd.startswith(norm_home):
             display_cwd = "~" + norm_cwd[len(norm_home):].replace("\\", "/")

        return f"{self.username}@{self.hostname}:{display_cwd}$ "

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                self.process.stdin.write(b"exit\n")
                await self.process.stdin.drain()
                await asyncio.wait_for(self.process.wait(), timeout=1.0)
            except Exception:
                self.process.kill()
