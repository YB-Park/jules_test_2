import asyncio
import platform
import os
import getpass
import socket
from . import constants
from prompt_toolkit.formatted_text import FormattedText
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
        self._internal_style = Style.from_dict({
            'info': 'fg:ansicyan',
            'command': 'fg:ansiyellow',
            'separator': 'fg:ansibrightblack',
        })

    async def _initialize_shell(self):
        shell_cmd_list = []
        if self.os_type == "windows":
            try:
                proc_check = await asyncio.create_subprocess_shell(
                    f"{constants.DEFAULT_SHELL_WINDOWS_POWERSHELL} -Command \"{constants.POWERSHELL_CHECK_COMMAND}\"",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc_check.communicate()
                if proc_check.returncode == 0:
                    self.shell_type = "powershell"
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo", "-NonInteractive"]
                else: raise FileNotFoundError("PowerShell check failed.") # Explicit raise
            except Exception:
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "prompt $P$G"]
        elif self.os_type in ["linux", "macos"]:
            default_shell = constants.DEFAULT_SHELL_LINUX if self.os_type == "linux" else constants.DEFAULT_SHELL_MACOS
            env_shell = os.environ.get("SHELL", default_shell)
            self.shell_type = os.path.basename(env_shell) if env_shell else (os.path.basename(default_shell) if default_shell else "sh")

            # Ensure shell_cmd_list[0] is a valid path or command
            resolved_shell_path = env_shell or default_shell
            if not os.path.exists(resolved_shell_path) and not shutil.which(resolved_shell_path.split()[0]): # Check if command in PATH
                # Fallback if preferred shell is not found
                resolved_shell_path = default_shell if os.path.exists(default_shell) else shutil.which(default_shell.split()[0])
                if not resolved_shell_path: # Absolute last resort
                    raise FileNotFoundError(f"Could not find a valid shell executable. Tried: {env_shell}, {default_shell}")
                self.shell_type = os.path.basename(resolved_shell_path)

            shell_cmd_list = [resolved_shell_path, "-i"] if resolved_shell_path else [default_shell, "-i"]


        else: raise OSError(f"Unsupported OS type: {self.os_type}")

        common_creation_flags = 0
        if self.os_type == "windows":
             # No specific flags needed for console subprocesses usually
             pass

        try:
            self.process = await asyncio.create_subprocess_exec(
                *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=common_creation_flags
            )
        except Exception as e:
            if self.os_type == "windows" and shell_cmd_list[0] == constants.DEFAULT_SHELL_WINDOWS_POWERSHELL:
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "prompt $P$G"]
                self.process = await asyncio.create_subprocess_exec(
                    *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    creationflags=common_creation_flags )
            else: raise
        await self._update_cwd()

    async def _update_cwd(self):
        if not self.process or self.process.returncode is not None:
            self.current_working_directory = os.getcwd(); return
        cwd_cmd_str = ""
        if self.shell_type == "powershell":
            cwd_cmd_str = f"Write-Host '{constants.CWD_MARKER_START}'; try {{ ($PWD.Path) }} catch {{ Write-Host 'ErrorGettingCWD' }}; Write-Host '{constants.CWD_MARKER_END}'"
        elif self.shell_type == "cmd":
            # Using a more robust way for CMD to print CWD between markers
            cwd_cmd_str = f"for /f \"tokens=*\" %%i in ('echo {constants.CWD_MARKER_START}') do @echo %%i & {constants.CMD_PRINT_CWD_WINDOWS_CMD} & for /f \"tokens=*\" %%i in ('echo {constants.CWD_MARKER_END}') do @echo %%i"
        elif self.shell_type in ["bash", "zsh", "sh", "fish"]:
            cwd_cmd_str = f"printf '%s\\n' '{constants.CWD_MARKER_START}'; {constants.CMD_PRINT_CWD_LINUX} 2>/dev/null || printf 'ErrorGettingCWD\\n'; printf '%s\\n' '{constants.CWD_MARKER_END}'"
        else: self.current_working_directory = os.getcwd(); return

        newline = b"\r\n" if self.os_type == "windows" else b"\n"
        try: # Clear potential leftover stdout before CWD query
            await asyncio.wait_for(self.process.stdout.read(1024*10), timeout=0.02)
        except asyncio.TimeoutError: pass
        except Exception: pass # Ignore other read errors before CWD query

        self.process.stdin.write(cwd_cmd_str.encode(constants.DEFAULT_ENCODING) + newline)
        await self.process.stdin.drain()

        output_buffer = ""; start_marker_found = False; lines_after_start = 0
        for _ in range(20):
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=0.2)
                if not line_bytes: break
                line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').strip()

                if constants.CWD_MARKER_START in line:
                    start_marker_found = True
                    # Content after marker on the same line
                    line_content = line.split(constants.CWD_MARKER_START, 1)[1].strip()
                    if constants.CWD_MARKER_END in line_content: # Both markers on one line
                        parsed_cwd = line_content.split(constants.CWD_MARKER_END, 1)[0].strip()
                        if parsed_cwd and parsed_cwd != 'ErrorGettingCWD': self.current_working_directory = parsed_cwd
                        return
                    if line_content: output_buffer = line_content # Start collecting
                    lines_after_start = 0
                    continue

                if constants.CWD_MARKER_END in line and start_marker_found:
                    # Content before end marker on the same line
                    output_buffer += ("\n" if output_buffer else "") + line.split(constants.CWD_MARKER_END, 1)[0].strip()
                    parsed_cwd = "\n".join(filter(None, output_buffer.splitlines())).strip()
                    if parsed_cwd and parsed_cwd != 'ErrorGettingCWD': self.current_working_directory = parsed_cwd
                    return

                if start_marker_found:
                    output_buffer += ("\n" if output_buffer else "") + line
                    lines_after_start += 1
                    if self.shell_type == "cmd" and lines_after_start >= 1: # CMD 'cd' usually prints CWD on one line
                         # If next line is already end marker, then this line was CWD
                         # This logic needs to be careful not to break if end marker is delayed
                         pass # Accumulate, wait for end marker

            except asyncio.TimeoutError:
                if start_marker_found: # Timeout after start_marker, assume collected buffer is CWD
                    parsed_cwd = "\n".join(filter(None, output_buffer.splitlines())).strip()
                    if parsed_cwd and parsed_cwd != 'ErrorGettingCWD': self.current_working_directory = parsed_cwd
                    return
                break
            except Exception: break

        # Fallback if parsing was incomplete or yielded error string
        final_cwd = "\n".join(filter(None, output_buffer.splitlines())).strip()
        if final_cwd and final_cwd != 'ErrorGettingCWD':
            self.current_working_directory = final_cwd
        elif self.current_working_directory == "~": # If still initial value and failed to get
            self.current_working_directory = os.getcwd()


    async def get_prompt(self) -> FormattedText:
        home_dir = os.path.expanduser("~"); display_cwd = self.current_working_directory; prompt_parts = []
        if self.os_type in ["linux", "macos"]:
            normalized_cwd = os.path.normpath(self.current_working_directory)
            normalized_home = os.path.normpath(home_dir)
            if normalized_cwd.startswith(normalized_home) and normalized_cwd != normalized_home:
                display_cwd = "~" + normalized_cwd[len(normalized_home):].replace("\\", "/")
            elif normalized_cwd == normalized_home: display_cwd = "~"
            else: display_cwd = normalized_cwd.replace("\\", "/")
            prompt_parts.extend([('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])
        elif self.os_type == "windows":
            display_cwd = self.current_working_directory
            if self.shell_type == "powershell": prompt_parts.extend([('class:prompt_symbol_ps', "PS "), ('class:path', display_cwd), ('class:prompt_symbol', "> ")])
            else: prompt_parts.extend([('class:path', display_cwd), ('class:prompt_symbol', "> ")])
        else: prompt_parts.extend([('class:default', f"({self.shell_type or 'unknown_shell'}) "), ('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])
        return FormattedText(prompt_parts)

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        if not self.process or self.process.returncode is not None: return "", "Shell process not running.", -1
        full_stdout, full_stderr = [], []
        newline = b"\r\n" if self.os_type == "windows" else b"\n"

        # Clear buffers before sending command
        try: await asyncio.wait_for(self.process.stdout.read(1024*10), timeout=0.01)
        except asyncio.TimeoutError: pass
        try: await asyncio.wait_for(self.process.stderr.read(1024*10), timeout=0.01)
        except asyncio.TimeoutError: pass

        self.process.stdin.write(command.encode(constants.DEFAULT_ENCODING) + newline)
        await self.process.stdin.drain()

        async def read_stream(stream, output_list, stream_name):
            empty_reads = 0; max_empty_reads = 4 # Increased for potentially slower/chunked output
            while empty_reads < max_empty_reads:
                try:
                    line_bytes = await asyncio.wait_for(stream.readline(), timeout=0.1) # Maintained short timeout for responsiveness
                    if not line_bytes: empty_reads = max_empty_reads; break
                    line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').rstrip()
                    # Basic filter for CWD markers, though ideally CWD query is fully separate
                    if not (constants.CWD_MARKER_START in line or constants.CWD_MARKER_END in line):
                        print(line)
                        output_list.append(line)
                    empty_reads = 0
                except asyncio.TimeoutError: empty_reads +=1
                except Exception: empty_reads = max_empty_reads; break

        await asyncio.gather(read_stream(self.process.stdout, full_stdout, "stdout"), read_stream(self.process.stderr, full_stderr, "stderr"))

        return_code = 1 if full_stderr and not full_stdout else 0 # Still a placeholder

        await self._update_cwd()
        return "\n".join(full_stdout), "\n".join(full_stderr), return_code

    async def run_command_for_automation(self, command: str, typing_delay: float = None, style: Style = None) -> tuple[str, str, int]:
        active_style = style if style else self._internal_style
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5

        separator_ft = FormattedText([('class:separator', f"\n{'-'*70}")])
        entry_message_parts = [
            ('class:info', "쉘 환경 진입 중... (명령어: "),
            ('class:command', command),
            ('class:info', ")")
        ]
        entry_message_ft = FormattedText(entry_message_parts)

        print_formatted_text(separator_ft, style=active_style)
        print_formatted_text(entry_message_ft, style=active_style)

        current_prompt_ft = await self.get_prompt()
        print_formatted_text(current_prompt_ft, style=active_style, end="")

        for char_to_type in command:
            char_ft = FormattedText([('class:command', char_to_type)])
            print_formatted_text(char_ft, style=active_style, end="")
            await asyncio.sleep(typing_delay if char_to_type not in [' ', '\t'] else 0)
        print()

        stdout, stderr, return_code = await self.execute_command(command)

        exit_message_parts = [
            ('class:info', f"명령어 실행 완료 (종료 코드: {return_code}). 쉘 환경 종료 중...")
        ]
        exit_message_ft = FormattedText(exit_message_parts)
        print_formatted_text(exit_message_ft, style=active_style)
        print_formatted_text(separator_ft, style=active_style)

        return stdout, stderr, return_code

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                if self.os_type == "windows" and self.shell_type == "cmd":
                    # CMD with /K might not exit with terminate alone, try sending exit
                    self.process.stdin.write(b"exit\r\n")
                    await self.process.stdin.drain()
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=1.0) # Reduced timeout
            except ProcessLookupError: pass
            except asyncio.TimeoutError:
                try: self.process.kill()
                except ProcessLookupError: pass
            except Exception: pass
            finally: self.process = None
        self._running = False

# Need to import shutil for shutil.which
import shutil
