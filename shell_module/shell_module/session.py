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
                    # Force UTF-8 encoding for PowerShell session
                    shell_cmd_list = [
                        constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo",
                        "-NonInteractive", "-Command", "chcp 65001; $OutputEncoding = [System.Text.UTF8Encoding]::new()"
                    ]
                else: raise FileNotFoundError("PowerShell check failed.")
            except (FileNotFoundError, Exception):
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "chcp 65001"] # Set code page for cmd as well
        elif self.os_type in ["linux", "macos"]:
            default_shell = constants.DEFAULT_SHELL_LINUX if self.os_type == "linux" else constants.DEFAULT_SHELL_MACOS
            env_shell = os.environ.get("SHELL", default_shell)
            self.shell_type = os.path.basename(env_shell) if env_shell else os.path.basename(default_shell)
            resolved_shell_path = env_shell or default_shell
            if not os.path.exists(resolved_shell_path):
                resolved_shell_path = shutil.which(resolved_shell_path.split()[0])
            if not resolved_shell_path:
                 resolved_shell_path = default_shell if os.path.exists(default_shell) else shutil.which(default_shell.split()[0])
                 if not resolved_shell_path: raise FileNotFoundError("Could not find a valid shell executable.")
                 self.shell_type = os.path.basename(resolved_shell_path)
            shell_cmd_list = [resolved_shell_path, "-i"] if resolved_shell_path else [default_shell, "-i"]
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
        await self._update_cwd()

    async def _update_cwd(self):
        if not self.process or self.process.returncode is not None:
            self.current_working_directory = os.getcwd(); return

        cwd_cmd_str = ""
        # Using a more robust marker command structure
        if self.shell_type == "powershell":
            # Use semicolons to chain commands in PowerShell
            cwd_cmd_str = f"Write-Host '{constants.CWD_MARKER_START}'; try {{ ($PWD.Path) }} catch {{ Write-Host 'ErrorGettingCWD' }}; Write-Host '{constants.CWD_MARKER_END}'"
        elif self.shell_type == "cmd":
            # Use '&' to chain commands in CMD
            cwd_cmd_str = f"echo {constants.CWD_MARKER_START}&cd&echo {constants.CWD_MARKER_END}"
        elif self.shell_type in ["bash", "zsh", "sh", "fish"]:
            cwd_cmd_str = f"printf '%s\\n' '{constants.CWD_MARKER_START}'; {constants.CMD_PRINT_CWD_LINUX} 2>/dev/null || printf 'ErrorGettingCWD\\n'; printf '%s\\n' '{constants.CWD_MARKER_END}'"
        else: self.current_working_directory = os.getcwd(); return

        newline = b"\r\n" if self.os_type == "windows" else b"\n"

        try: # Clear potential leftover stdout before CWD query
            await asyncio.wait_for(self.process.stdout.read(1024*10), timeout=0.02)
        except asyncio.TimeoutError: pass
        except Exception: pass

        self.process.stdin.write(cwd_cmd_str.encode('utf-8') + newline)
        await self.process.stdin.drain()

        output_buffer = []; start_marker_found = False
        for _ in range(20):
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=0.2)
                if not line_bytes: break
                line = line_bytes.decode('utf-8', errors='replace').strip()

                if constants.CWD_MARKER_END in line:
                    if start_marker_found:
                        line_content = line.split(constants.CWD_MARKER_END, 1)[0].strip()
                        if line_content: output_buffer.append(line_content)
                    break # End marker found, stop reading

                if constants.CWD_MARKER_START in line:
                    start_marker_found = True
                    line_content = line.split(constants.CWD_MARKER_START, 1)[1].strip()
                    if line_content: output_buffer.append(line_content)
                    continue

                if start_marker_found:
                    output_buffer.append(line)

            except asyncio.TimeoutError:
                break
            except Exception: break

        # Post-process the buffer
        if output_buffer:
            # Join all parts, then split by newlines to handle multi-line CWD outputs (less common)
            full_buffer = "\n".join(output_buffer)
            # Clean out any remaining marker text that might have been captured
            clean_buffer = full_buffer.replace(constants.CWD_MARKER_START, "").replace(constants.CWD_MARKER_END, "").strip()
            # Often the actual CWD is the last non-empty line
            lines = [l for l in clean_buffer.splitlines() if l.strip()]
            if lines and 'ErrorGettingCWD' not in lines[-1]:
                self.current_working_directory = lines[-1]
                return

        # Fallback if CWD parsing fails
        if self.current_working_directory == "~":
            self.current_working_directory = os.getcwd()


    async def get_prompt(self) -> FormattedText:
        # (Same as previous version)
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

        # A special, invisible marker to help identify the end of output
        # This is more reliable than timeouts.
        end_marker = "END_OF_COMMAND_98765"
        marker_cmd = f"echo {end_marker}"

        # Chain user command with the end marker command
        full_cmd_to_run = f"{command}\n{marker_cmd}\n"

        self.process.stdin.write(full_cmd_to_run.encode('utf-8'))
        await self.process.stdin.drain()

        async def read_stream(stream, output_list, stream_name, command_to_filter, end_marker_str):
            # Filter out the command echo itself
            # The prompt is not part of the stream, but the command might be echoed by the shell
            first_line_filtered = False

            while True:
                try:
                    line_bytes = await stream.readline()
                    if not line_bytes: break # EOF
                    line = line_bytes.decode('utf-8', errors='replace').rstrip()

                    # Check for our special end marker
                    if line.strip() == end_marker_str:
                        break

                    # Filter command echo
                    if not first_line_filtered and line.strip() == command_to_filter.strip():
                        first_line_filtered = True
                        continue

                    # Filter out CWD markers that might have bled through
                    if constants.CWD_MARKER_START in line or constants.CWD_MARKER_END in line:
                        continue

                    # Filter out the marker command echo itself
                    if line.strip() == marker_cmd:
                        continue

                    print(line)
                    output_list.append(line)
                except (asyncio.CancelledError, ConnectionResetError):
                    break
                except Exception:
                    break

        # Create separate reader tasks for stdout and stderr
        # We need to read both until the marker appears in stdout. Stderr doesn't get the marker.
        # This requires a more complex synchronization.

        # Simpler approach: Read both concurrently and stop when marker is seen in stdout.
        # This might miss some trailing stderr. A truly robust solution is much harder.

        # Let's stick with the timeout approach for now, but with the echo filter.
        # The marker-based approach above is complex to get right with asyncio.

        # Reverting to timeout-based read with echo filtering
        self.process.stdin.write(command.encode('utf-8') + newline)
        await self.process.stdin.drain()
        async def read_stream_timeout(stream, output_list, stream_name, command_to_filter):
            first_line_filtered = False
            empty_reads = 0
            max_empty_reads = 3
            while empty_reads < max_empty_reads:
                try:
                    line_bytes = await asyncio.wait_for(stream.readline(), timeout=0.2)
                    if not line_bytes: break
                    line = line_bytes.decode('utf-8', errors='replace').rstrip()
                    if not first_line_filtered and line.strip() == command_to_filter.strip():
                        first_line_filtered = True
                        continue
                    if constants.CWD_MARKER_START in line or constants.CWD_MARKER_END in line:
                        continue
                    print(line)
                    output_list.append(line)
                    empty_reads = 0
                except asyncio.TimeoutError:
                    empty_reads += 1
                except Exception:
                    break

        await asyncio.gather(
            read_stream_timeout(self.process.stdout, full_stdout, "stdout", command),
            read_stream_timeout(self.process.stderr, full_stderr, "stderr", command)
        )

        return_code = 1 if full_stderr and not full_stdout else 0
        await self._update_cwd()
        return "\n".join(full_stdout), "\n".join(full_stderr), return_code

    async def run_command_for_automation(self, command: str, typing_delay: float = None, style: Style = None) -> tuple[str, str, int]:
        # (Same as previous version)
        active_style = style if style else self._internal_style
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5
        separator_ft = FormattedText([('class:separator', f"\n{'-'*70}")])
        entry_message_parts = [('class:info', "쉘 환경 진입 중... (명령어: "), ('class:command', command), ('class:info', ")")]
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
        exit_message_parts = [('class:info', f"명령어 실행 완료 (종료 코드: {return_code}). 쉘 환경 종료 중...")]
        exit_message_ft = FormattedText(exit_message_parts)
        print_formatted_text(exit_message_ft, style=active_style)
        print_formatted_text(separator_ft, style=active_style)
        return stdout, stderr, return_code

    async def close(self):
        # (Same as previous version)
        if self.process and self.process.returncode is None:
            try:
                if self.os_type == "windows" and self.shell_type == "cmd":
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
