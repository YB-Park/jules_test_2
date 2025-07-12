import asyncio
import platform
import os
import getpass
import socket
import shutil
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
                    shell_cmd_list = [
                        constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo",
                        "-NonInteractive", "-Command", "chcp 65001; $OutputEncoding = [System.Text.UTF8Encoding]::new()"
                    ]
                else: raise FileNotFoundError("PowerShell check failed.")
            except (FileNotFoundError, Exception):
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "chcp 65001"]
        elif self.os_type in ["linux", "macos"]:
            default_shell = constants.DEFAULT_SHELL_LINUX if self.os_type == "linux" else constants.DEFAULT_SHELL_MACOS
            env_shell = os.environ.get("SHELL", default_shell)
            self.shell_type = os.path.basename(env_shell) if env_shell else os.path.basename(default_shell)
            resolved_shell_path = shutil.which(env_shell or default_shell)
            if not resolved_shell_path:
                 resolved_shell_path = shutil.which(default_shell)
                 if not resolved_shell_path: raise FileNotFoundError(f"Could not find a valid shell executable.")
            self.shell_type = os.path.basename(resolved_shell_path)
            shell_cmd_list = [resolved_shell_path, "-i"]
        else: raise OSError(f"Unsupported OS type: {self.os_type}")

        try:
            self.process = await asyncio.create_subprocess_exec(
                *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except Exception as e:
            if self.os_type == "windows" and "powershell" in shell_cmd_list[0].lower():
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "chcp 65001"]
                self.process = await asyncio.create_subprocess_exec(
                    *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            else: raise
        await self.execute_command("") # Run an empty command to get initial CWD and clear startup messages

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

    async def execute_command(self, command: str, print_output=True) -> tuple[str, str, int]:
        if not self.process or self.process.returncode is not None: return "", "Shell process not running.", -1

        # Define markers for each piece of information
        STDOUT_START_MARKER, STDOUT_END_MARKER = "__STDOUT_START__", "__STDOUT_END__"
        STDERR_START_MARKER, STDERR_END_MARKER = "__STDERR_START__", "__STDERR_END__"
        RC_START_MARKER, RC_END_MARKER = "__RC_START__", "__RC_END__"
        CWD_START_MARKER, CWD_END_MARKER = "__CWD_START__", "__CWD_END__"

        # Determine commands to get RC and CWD based on shell type
        rc_cmd = "echo $?" if self.os_type in ["linux", "macos"] else "echo %errorlevel%"
        if self.shell_type == "powershell": rc_cmd = "echo $LASTEXITCODE"
        cwd_cmd = "pwd" if self.os_type in ["linux", "macos"] else "cd"
        if self.shell_type == "powershell": cwd_cmd = "$PWD.Path"

        # Construct the full command block to be executed
        if self.os_type == "windows":
            # For PowerShell and CMD, use '&' to chain commands.
            # PowerShell can handle this well. CMD can be tricky with complex commands.
            command_block = (
                f"echo {STDOUT_START_MARKER} & "
                f"{command} & "
                f"echo {STDOUT_END_MARKER} & "
                f"echo {RC_START_MARKER} & "
                f"{rc_cmd} & "
                f"echo {RC_END_MARKER} & "
                f"echo {CWD_START_MARKER} & "
                f"{cwd_cmd} & "
                f"echo {CWD_END_MARKER}"
            )
        else: # Linux/macOS
            # Use semicolons for sequencing. Use printf for reliability.
            command_block = (
                f"printf '%s\\n' '{STDOUT_START_MARKER}';"
                f"{command};"
                f"printf '%s\\n' '{STDOUT_END_MARKER}';"
                f"printf '%s\\n' '{RC_START_MARKER}';"
                f"{rc_cmd};"
                f"printf '%s\\n' '{RC_END_MARKER}';"
                f"printf '%s\\n' '{CWD_START_MARKER}';"
                f"{cwd_cmd};"
                f"printf '%s\\n' '{CWD_END_MARKER}';"
            )

        newline = b"\r\n" if self.os_type == "windows" else b"\n"
        self.process.stdin.write(command_block.encode('utf-8') + newline)
        await self.process.stdin.drain()

        # --- Unified Stream Reading and Parsing Logic ---
        full_output = []
        async def read_stream(stream):
            while True:
                try:
                    # Use a timeout to prevent hanging forever if a marker is missed
                    line_bytes = await asyncio.wait_for(stream.readline(), timeout=5.0)
                    if not line_bytes: break
                    full_output.append(line_bytes.decode('utf-8', errors='replace'))
                except asyncio.TimeoutError: break
                except Exception: break

        # Read both stdout and stderr concurrently
        await asyncio.gather(read_stream(self.process.stdout), read_stream(self.process.stderr))

        # --- Parse the collected output ---
        full_output_str = "".join(full_output)

        # Helper to parse content between markers
        def parse_between(text, start_marker, end_marker):
            try:
                start_idx = text.index(start_marker) + len(start_marker)
                end_idx = text.index(end_marker, start_idx)
                # Split by newline and filter out empty strings
                content_lines = [line.strip() for line in text[start_idx:end_idx].splitlines() if line.strip()]
                return "\n".join(content_lines)
            except ValueError:
                return "" # Marker not found

        stdout_str = parse_between(full_output_str, STDOUT_START_MARKER, STDOUT_END_MARKER)
        # stderr is not marked, so it's everything that's not stdout (this is a simplification)
        # A better way would be to mark stderr too, but that's more complex.
        # For now, we'll assume stderr is mixed in with stdout for parsing purposes.
        # A more robust approach would tag every line, e.g. `command | sed 's/^/OUT /'`.

        rc_str = parse_between(full_output_str, RC_START_MARKER, RC_END_MARKER)
        cwd_str = parse_between(full_output_str, CWD_START_MARKER, CWD_END_MARKER)

        # Update state
        if cwd_str:
            self.current_working_directory = cwd_str

        try:
            return_code = int(rc_str.strip())
        except (ValueError, TypeError):
            return_code = -1 # Parsing failed

        # Print output if requested
        if print_output and stdout_str:
            # Filter out command echo if present (often the first line)
            lines = stdout_str.splitlines()
            if lines and lines[0].strip() == command.strip():
                lines = lines[1:]

            for line in lines:
                print(line)

        # For now, stderr is not separated in this model. All non-stdout is considered mixed.
        return stdout_str, "", return_code


    async def run_command_for_automation(self, command: str, typing_delay: float = None, style: Style = None) -> tuple[str, str, int]:
        active_style = style if style else self._internal_style
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5

        separator_ft = FormattedText([('class:separator', f"\n{'-'*70}")])
        entry_message_parts = [('class:info', "쉘 환경 진입 중... (명령어: "),('class:command', command),('class:info', ")")]
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

        # Pass print_output=True to the new execute_command
        stdout, stderr, return_code = await self.execute_command(command, print_output=True)

        exit_message_parts = [('class:info', f"명령어 실행 완료 (종료 코드: {return_code}). 쉘 환경 종료 중...")]
        exit_message_ft = FormattedText(exit_message_parts)
        print_formatted_text(exit_message_ft, style=active_style)
        print_formatted_text(separator_ft, style=active_style)

        return stdout, stderr, return_code

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                if self.os_type == "windows":
                    self.process.stdin.write(b"exit\r\n")
                    await self.process.stdin.drain()
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=1.0)
            except ProcessLookupError: pass
            except asyncio.TimeoutError:
                try: self.process.kill()
                except ProcessLookupError: pass
            except Exception: pass
            finally: self.process = None
        self._running = False
