import asyncio
import platform
import os
import getpass
import socket
from . import constants
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit import print_formatted_text # For run_command_for_automation

class ShellSession:
    def __init__(self):
        self.process = None
        self.shell_type = None
        self.current_working_directory = "~"
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_type = constants.OS_TYPE
        self._running = True

    async def _initialize_shell(self):
        shell_cmd_list = []
        if self.os_type == "windows":
            try:
                proc_check = await asyncio.create_subprocess_shell(
                    f"{constants.DEFAULT_SHELL_WINDOWS_POWERSHELL} -Command \"{constants.POWERSHELL_CHECK_COMMAND}\"",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc_check.communicate()
                if proc_check.returncode == 0 and stdout:
                    self.shell_type = "powershell"
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo"]
                else:
                    raise FileNotFoundError("PowerShell check failed.")
            except Exception:
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD]
        elif self.os_type == "linux":
            env_shell = os.environ.get("SHELL", constants.DEFAULT_SHELL_LINUX)
            self.shell_type = env_shell.split('/')[-1] if env_shell else "bash" # Default to bash if SHELL is empty
            shell_cmd_list = [env_shell or constants.DEFAULT_SHELL_LINUX]
        elif self.os_type == "macos":
            env_shell = os.environ.get("SHELL", constants.DEFAULT_SHELL_MACOS)
            self.shell_type = env_shell.split('/')[-1] if env_shell else "zsh" # Default to zsh if SHELL is empty
            shell_cmd_list = [env_shell or constants.DEFAULT_SHELL_MACOS]
        else:
            raise OSError(f"Unsupported OS type: {self.os_type}")

        try:
            self.process = await asyncio.create_subprocess_exec(
                *shell_cmd_list,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            if self.os_type == "windows" and self.shell_type == "powershell":
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD]
                self.process = await asyncio.create_subprocess_exec(*shell_cmd_list, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            else:
                raise
        await self._update_cwd()

    async def _update_cwd(self):
        if not self.process or self.process.returncode is not None:
            self.current_working_directory = os.getcwd()
            return

        cwd_cmd_str = ""
        if self.shell_type == "powershell":
            cwd_cmd_str = f"Write-Host '{constants.CWD_MARKER_START}'; $PWD.Path; Write-Host '{constants.CWD_MARKER_END}'"
        elif self.shell_type == "cmd":
            cwd_cmd_str = f"echo {constants.CWD_MARKER_START}\n{constants.CMD_PRINT_CWD_WINDOWS_CMD}\necho {constants.CWD_MARKER_END}"
        elif self.shell_type in ["bash", "zsh", "sh"]: # Common Unix shells
            cwd_cmd_str = f"echo '{constants.CWD_MARKER_START}'; {constants.CMD_PRINT_CWD_LINUX}; echo '{constants.CWD_MARKER_END}'"
        else:
            self.current_working_directory = os.getcwd(); return

        newline = b"\r\n" if self.os_type == "windows" else b"\n"
        self.process.stdin.write(cwd_cmd_str.encode(constants.DEFAULT_ENCODING) + newline)
        await self.process.stdin.drain()
        output_lines = []
        capturing_cwd = False
        for _ in range(10):
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=0.5)
                if not line_bytes: break
                line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').strip()
                if constants.CWD_MARKER_START in line:
                    capturing_cwd = True
                    line_after_marker = line.split(constants.CWD_MARKER_START, 1)[-1].strip()
                    if line_after_marker: # If CWD is on the same line as start marker
                        if constants.CWD_MARKER_END in line_after_marker: # And end marker too
                            self.current_working_directory = line_after_marker.split(constants.CWD_MARKER_END,1)[0].strip()
                            return
                        output_lines.append(line_after_marker) # Assume CWD is on next line or this line if no end marker
                    continue # Process next line or this line if it had content
                if constants.CWD_MARKER_END in line:
                    capturing_cwd = False
                    line_before_marker = line.split(constants.CWD_MARKER_END, 1)[0].strip()
                    if line_before_marker: output_lines.append(line_before_marker)
                    break
                if capturing_cwd and line: output_lines.append(line)
            except asyncio.TimeoutError: break # Stop if shell doesn't respond quickly

        if output_lines: # Process captured lines
            # Filter out empty strings and take the first valid one
            # This handles cases where markers might be on their own lines.
            processed_cwd = ""
            for potential_cwd_part in output_lines:
                # Some shells (like cmd's `cd`) might output the marker again if not careful.
                # We should strip markers from the CWD lines themselves if they appear.
                # This logic assumes CWD is a single coherent line among captured lines.
                temp_cwd = potential_cwd_part.replace(constants.CWD_MARKER_START, "").replace(constants.CWD_MARKER_END, "").strip()
                if temp_cwd:
                    processed_cwd = temp_cwd
                    break
            if processed_cwd:
                self.current_working_directory = processed_cwd
                return

    async def get_prompt(self) -> FormattedText:
        home_dir = os.path.expanduser("~")
        display_cwd = self.current_working_directory; prompt_parts = []
        if self.os_type in ["linux", "macos"]:
            if self.current_working_directory.startswith(home_dir) and self.current_working_directory != home_dir:
                display_cwd = "~" + self.current_working_directory[len(home_dir):]
            elif self.current_working_directory == home_dir: display_cwd = "~"
            prompt_parts.extend([('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])
        elif self.os_type == "windows":
            display_cwd = self.current_working_directory
            if self.shell_type == "powershell": prompt_parts.extend([('class:prompt_symbol_ps', "PS "), ('class:path', display_cwd), ('class:prompt_symbol', "> ")])
            else: prompt_parts.extend([('class:path', display_cwd), ('class:prompt_symbol', "> ")])
        else: # Fallback
            prompt_parts.extend([('class:default', f"({self.shell_type or 'unknown_shell'}) "), ('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])
        return FormattedText(prompt_parts)

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        if not self.process or self.process.returncode is not None: return "", "Shell process not running.", -1
        full_stdout, full_stderr = [], []
        newline = b"\r\n" if self.os_type == "windows" else b"\n"
        self.process.stdin.write(command.encode(constants.DEFAULT_ENCODING) + newline)
        await self.process.stdin.drain()
        async def read_stream(stream, output_list, stream_name):
            while True:
                try:
                    line_bytes = await asyncio.wait_for(stream.readline(), timeout=0.2) # Slightly increased timeout
                    if not line_bytes: break
                    line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').rstrip()
                    print(line)
                    output_list.append(line)
                except asyncio.TimeoutError: break
                except Exception: break # Should log this error
        await asyncio.gather(read_stream(self.process.stdout, full_stdout, "stdout"), read_stream(self.process.stderr, full_stderr, "stderr"))

        # Placeholder for actual return code fetching. This is complex.
        # For now, we'll assume 0 unless stderr was populated and stdout was not.
        # This is a very rough heuristic.
        return_code = 0
        if full_stderr and not full_stdout: # Very basic error heuristic
             return_code = 1 # Assume error if only stderr has content

        await self._update_cwd()
        return "\n".join(full_stdout), "\n".join(full_stderr), return_code

    async def run_command_for_automation(self, command: str, typing_delay: float = None, style = None) -> tuple[str, str, int]:
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5
        current_prompt_ft = await self.get_prompt()
        # Use print_formatted_text for the styled prompt
        print_formatted_text(current_prompt_ft, style=style, end="")

        # Type out the command
        for char_to_type in command:
            # For command characters, using standard print is fine, or style them too
            print(char_to_type, end="", flush=True)
            if char_to_type != ' ': await asyncio.sleep(typing_delay)
        print() # Newline after typing the command

        return await self.execute_command(command)

    async def close(self):
        if self.process and self.process.returncode is None:
            try: self.process.terminate(); await self.process.wait()
            except ProcessLookupError: pass # Process already exited
            except Exception: pass # Log this error in a real app
            finally: self.process = None
        self._running = False
