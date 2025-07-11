import asyncio
import platform
import os
import getpass
import socket
from . import constants
from prompt_toolkit.formatted_text import FormattedText, to_formatted_text
from prompt_toolkit import print_formatted_text
from prompt_toolkit.styles import Style

class ShellSession:
    def __init__(self):
        self.process = None
        self.shell_type = None
        self.current_working_directory = "~"
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_type = constants.OS_TYPE
        self._running = True
        # Basic style for internal messages if no external style is passed to run_command_for_automation
        self._internal_style = Style.from_dict({
            'info': 'fg:ansicyan',
            'command': 'fg:ansiyellow',
            'separator': 'fg:ansibrightblack', # Corrected from ansiblack to ansibrightblack for visibility
        })

    async def _initialize_shell(self):
        shell_cmd_list = []
        # Simplified shell initialization logic
        if self.os_type == "windows":
            try: # Try PowerShell
                proc_check = await asyncio.create_subprocess_shell(
                    f"{constants.DEFAULT_SHELL_WINDOWS_POWERSHELL} -Command \"{constants.POWERSHELL_CHECK_COMMAND}\"",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc_check.communicate()
                if proc_check.returncode == 0:
                    self.shell_type = "powershell"
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo", "-NonInteractive"]
                else: raise FileNotFoundError
            except Exception: # Fallback to CMD
                self.shell_type = "cmd"
                # /K keeps cmd open. `prompt $P$G` sets a standard prompt.
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "prompt $P$G"]
        elif self.os_type in ["linux", "macos"]:
            default_shell = constants.DEFAULT_SHELL_LINUX if self.os_type == "linux" else constants.DEFAULT_SHELL_MACOS
            env_shell = os.environ.get("SHELL", default_shell)
            self.shell_type = os.path.basename(env_shell) # e.g., 'bash', 'zsh'
            shell_cmd_list = [env_shell, "-i"] # Attempt interactive mode
            if not os.path.exists(shell_cmd_list[0]): # Fallback if SHELL points to non-existent
                 shell_cmd_list = [default_shell, "-i"]
                 self.shell_type = os.path.basename(default_shell)

        else: raise OSError(f"Unsupported OS type: {self.os_type}")

        common_creation_flags = 0 # Default for non-Windows or if no specific flags needed
        if self.os_type == "windows" and self.shell_type == "cmd": # For cmd.exe, ensure it has a window or handles pipes correctly.
             # subprocess.CREATE_NEW_CONSOLE or subprocess.CREATE_NO_WINDOW might be relevant
             # For now, default flags are used. If issues arise, this can be revisited.
             pass


        try:
            self.process = await asyncio.create_subprocess_exec(
                *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=common_creation_flags # Pass flags if any
            )
        except Exception as e:
            # Simplified fallback for Windows if initial powershell exec with args failed.
            if self.os_type == "windows" and shell_cmd_list[0] == constants.DEFAULT_SHELL_WINDOWS_POWERSHELL:
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "prompt $P$G"]
                self.process = await asyncio.create_subprocess_exec(
                    *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    creationflags=common_creation_flags
                )
            else: raise # Re-raise if not a Windows PowerShell specific startup issue

        await self._update_cwd()


    async def _update_cwd(self):
        if not self.process or self.process.returncode is not None:
            self.current_working_directory = os.getcwd(); return

        cwd_cmd_str = ""
        # Construct the CWD command with markers
        if self.shell_type == "powershell":
            cwd_cmd_str = f"Write-Host '{constants.CWD_MARKER_START}'; try {{ ($PWD.Path) }} catch {{ Write-Host 'ErrorGettingCWD' }}; Write-Host '{constants.CWD_MARKER_END}'"
        elif self.shell_type == "cmd":
            # CMD echo can be tricky. Ensure markers are distinct.
            cwd_cmd_str = f"echo {constants.CWD_MARKER_START}&{constants.CMD_PRINT_CWD_WINDOWS_CMD}&echo {constants.CWD_MARKER_END}"
        elif self.shell_type in ["bash", "zsh", "sh", "fish"]: # Added fish as common interactive shell
            cwd_cmd_str = f"printf '%s\\n' '{constants.CWD_MARKER_START}'; {constants.CMD_PRINT_CWD_LINUX} 2>/dev/null || printf 'ErrorGettingCWD\\n'; printf '%s\\n' '{constants.CWD_MARKER_END}'"
        else: # Fallback for unknown shells
            self.current_working_directory = os.getcwd(); return

        newline = b"\r\n" if self.os_type == "windows" else b"\n"

        # Clear buffer before sending CWD command to avoid reading old output
        # This is a bit of a hack; a more robust solution would use dedicated pipes or control sequences.
        # For now, try a very short non-blocking read.
        try:
            await asyncio.wait_for(self.process.stdout.read(1024*10), timeout=0.01) # Read up to 10KB
        except asyncio.TimeoutError:
            pass # No data or already empty

        self.process.stdin.write(cwd_cmd_str.encode(constants.DEFAULT_ENCODING) + newline)
        await self.process.stdin.drain()

        output_buffer = ""
        start_marker_found = False
        # Try to read lines until end marker or timeout
        for _ in range(20): # Max lines/attempts to find markers
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=0.2) # Slightly longer timeout for CWD
                if not line_bytes: break # EOF
                line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').strip()

                if constants.CWD_MARKER_START in line:
                    start_marker_found = True
                    # Extract content after start marker if on the same line
                    line_content = line.split(constants.CWD_MARKER_START, 1)[1]
                    if constants.CWD_MARKER_END in line_content: # Both markers on one line
                        self.current_working_directory = line_content.split(constants.CWD_MARKER_END, 1)[0].strip()
                        if self.current_working_directory == 'ErrorGettingCWD': self.current_working_directory = os.getcwd() # Fallback
                        return
                    output_buffer = line_content.strip() # Start collecting
                    continue

                if constants.CWD_MARKER_END in line and start_marker_found:
                    # Extract content before end marker if on the same line
                    output_buffer += "\n" + line.split(constants.CWD_MARKER_END, 1)[0].strip()
                    self.current_working_directory = "\n".join(filter(None, output_buffer.splitlines())).strip() # Take multi-line CWD, join, strip
                    if self.current_working_directory == 'ErrorGettingCWD': self.current_working_directory = os.getcwd() # Fallback
                    return

                if start_marker_found:
                    output_buffer += "\n" + line # Accumulate lines between markers

            except asyncio.TimeoutError:
                if start_marker_found: # If we started capturing but timed out before end marker
                    # Use what we have, assuming it might be a single line CWD
                    self.current_working_directory = "\n".join(filter(None, output_buffer.splitlines())).strip()
                    if self.current_working_directory == 'ErrorGettingCWD': self.current_working_directory = os.getcwd()
                    return
                break # Timeout before even start marker, or after non-capturing read
            except Exception: # Any other read error
                break

        # If markers were not properly found or CWD is empty, fallback or keep previous
        if not output_buffer.strip() or output_buffer.strip() == 'ErrorGettingCWD':
            # Could log a warning here: "Failed to parse CWD from shell, using fallback."
            # Keep previous CWD or use os.getcwd() if it's the first time.
            if self.current_working_directory == "~": # Initial state
                 self.current_working_directory = os.getcwd()
        elif output_buffer.strip(): # If something was captured
            self.current_working_directory = output_buffer.strip()


    async def get_prompt(self) -> FormattedText:
        home_dir = os.path.expanduser("~"); display_cwd = self.current_working_directory; prompt_parts = []
        if self.os_type in ["linux", "macos"]:
            # Normalize path separators for comparison and display consistency
            normalized_cwd = os.path.normpath(self.current_working_directory)
            normalized_home = os.path.normpath(home_dir)
            if normalized_cwd.startswith(normalized_home) and normalized_cwd != normalized_home:
                display_cwd = "~" + normalized_cwd[len(normalized_home):].replace("\\", "/") # Ensure forward slashes for ~
            elif normalized_cwd == normalized_home: display_cwd = "~"
            else: display_cwd = normalized_cwd.replace("\\", "/") # Ensure forward slashes for non-home paths too
            prompt_parts.extend([('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])
        elif self.os_type == "windows":
            display_cwd = self.current_working_directory # Keep Windows style paths
            if self.shell_type == "powershell": prompt_parts.extend([('class:prompt_symbol_ps', "PS "), ('class:path', display_cwd), ('class:prompt_symbol', "> ")])
            else: prompt_parts.extend([('class:path', display_cwd), ('class:prompt_symbol', "> ")])
        else: prompt_parts.extend([('class:default', f"({self.shell_type or 'unknown_shell'}) "), ('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])
        return FormattedText(prompt_parts)

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        if not self.process or self.process.returncode is not None: return "", "Shell process not running.", -1
        full_stdout, full_stderr = [], []
        newline = b"\r\n" if self.os_type == "windows" else b"\n"

        self.process.stdin.write(command.encode(constants.DEFAULT_ENCODING) + newline)
        await self.process.stdin.drain()

        async def read_stream(stream, output_list, stream_name):
            empty_reads = 0
            max_empty_reads = 3 # Increased slightly
            while empty_reads < max_empty_reads:
                try:
                    line_bytes = await asyncio.wait_for(stream.readline(), timeout=0.15) # Slightly increased timeout
                    if not line_bytes: empty_reads = max_empty_reads; break
                    line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').rstrip()
                    # Filter out CWD marker lines from actual command output.
                    # This is a basic filter; more robust would be to ensure CWD read is fully separate.
                    if not (constants.CWD_MARKER_START in line or constants.CWD_MARKER_END in line):
                        print(line)
                        output_list.append(line)
                    empty_reads = 0
                except asyncio.TimeoutError:
                    empty_reads +=1
                except Exception: empty_reads = max_empty_reads; break

        await asyncio.gather(read_stream(self.process.stdout, full_stdout, "stdout"), read_stream(self.process.stderr, full_stderr, "stderr"))

        # Rudimentary return code (actual implementation is more complex)
        # Requires echoing $? (Unix) or $LASTEXITCODE (PowerShell) and parsing with markers.
        # For now, if there's stderr and no stdout, assume an error.
        return_code = 1 if full_stderr and not full_stdout else 0

        await self._update_cwd() # Update CWD after every command
        return "\n".join(full_stdout), "\n".join(full_stderr), return_code

    async def run_command_for_automation(self, command: str, typing_delay: float = None, style: Style = None) -> tuple[str, str, int]:
        active_style = style if style else self._internal_style
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5 # Default fast typing

        separator_ft = to_formatted_text([('class:separator', f"\n{'-'*70}")], style=active_style)
        entry_message_parts = [
            ('class:info', "쉘 환경 진입 중... (명령어: "),
            ('class:command', command), # Command will use 'command' style class
            ('class:info', ")")
        ]
        entry_message_ft = to_formatted_text(entry_message_parts, style=active_style)

        print_formatted_text(separator_ft, style=active_style)
        print_formatted_text(entry_message_ft, style=active_style)

        current_prompt_ft = await self.get_prompt()
        print_formatted_text(current_prompt_ft, style=active_style, end="")

        for char_to_type in command:
            # Use a specific style for typing the command, or fallback to default print
            # Here, using print_formatted_text to allow styling if 'command' class is rich
            print_formatted_text(to_formatted_text([('class:command', char_to_type)], style=active_style), style=active_style, end="")
            await asyncio.sleep(typing_delay if char_to_type not in [' ', '\t'] else 0) # No delay for whitespace
        print() # Newline after typed command

        stdout, stderr, return_code = await self.execute_command(command)

        exit_message_parts = [
            ('class:info', f"명령어 실행 완료 (종료 코드: {return_code}). 쉘 환경 종료 중...")
        ]
        exit_message_ft = to_formatted_text(exit_message_parts, style=active_style)
        print_formatted_text(exit_message_ft, style=active_style)
        print_formatted_text(separator_ft, style=active_style) # Use the same separator FormattedText

        return stdout, stderr, return_code

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0) # Wait with timeout
            except ProcessLookupError: pass # Already exited
            except asyncio.TimeoutError: # Force kill if terminate hangs
                try: self.process.kill()
                except ProcessLookupError: pass
            except Exception: pass # Log other errors in a real app
            finally: self.process = None
        self._running = False
