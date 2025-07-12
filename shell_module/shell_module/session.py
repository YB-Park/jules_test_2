import asyncio
import platform
import os
import getpass
import socket
import shutil
import re
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
            'info': 'fg:ansicyan', 'command': 'fg:ansiyellow', 'separator': 'fg:ansibrightblack',
        })
        # For filtering out the prompt from shell's own output in some interactive modes
        self._prompt_regex = None

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
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo", "-NonInteractive", "-Command", "chcp 65001; $OutputEncoding = [System.Text.UTF8Encoding]::new()"]
                else: raise FileNotFoundError("PowerShell check failed.")
            except (FileNotFoundError, Exception):
                self.shell_type = "cmd"; shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "chcp 65001"]
        elif self.os_type in ["linux", "macos"]:
            default_shell = constants.DEFAULT_SHELL_LINUX if self.os_type == "linux" else constants.DEFAULT_SHELL_MACOS
            env_shell = os.environ.get("SHELL", default_shell)
            self.shell_type = os.path.basename(env_shell) if env_shell else os.path.basename(default_shell)
            resolved_shell_path = shutil.which(env_shell or default_shell) or shutil.which(default_shell)
            if not resolved_shell_path: raise FileNotFoundError(f"Could not find a valid shell executable.")
            self.shell_type = os.path.basename(resolved_shell_path)
            # Use -i for interactive, but also PS1 to set a minimal prompt we can filter.
            # This helps avoid filtering the *output* of a command that looks like a prompt.
            self._prompt_regex = re.compile(r"__PROMPT_END__\s*$")
            shell_cmd_list = [resolved_shell_path, "-i", "-c", f"PS1='__PROMPT_END__ ' exec {resolved_shell_path}"]
            # A simpler -i might be enough and less complex than the PS1 trick. Let's start simple.
            shell_cmd_list = [resolved_shell_path, "-i"]
            self._prompt_regex = None # Disable regex filtering for now to simplify
        else: raise OSError(f"Unsupported OS type: {self.os_type}")

        self.process = await asyncio.create_subprocess_exec(
            *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        # Clear startup messages and get initial CWD
        await self._update_cwd()

    async def _read_until_marker(self, end_marker, timeout=2.0, print_output=False):
        output_buffer = ""
        while True:
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
                if not line_bytes: break
                line = line_bytes.decode('utf-8', errors='replace')

                # Check for marker before printing
                if end_marker in line:
                    output_buffer += line.split(end_marker, 1)[0]
                    break

                output_buffer += line

                # Print output only if flag is set
                if print_output:
                    # We print the raw line with its original ending to preserve formatting
                    print(line.rstrip('\r\n'))

            except asyncio.TimeoutError: break
            except Exception: break
        return output_buffer

    async def _update_cwd(self):
        if not self.process or self.process.returncode is not None:
            self.current_working_directory = os.getcwd(); return

        end_marker = "__END_OF_CWD_UPDATE__"
        cwd_cmd = "pwd" if self.os_type in ["linux", "macos"] else "cd"
        if self.shell_type == "powershell": cwd_cmd = "$PWD.Path"

        cmd_block = f"{cwd_cmd}\necho {end_marker}\n"
        if self.shell_type == "powershell":
            # Use Write-Host to avoid redirection issues and ensure clean output
            cmd_block = f"Write-Host -NoNewline \"$({cwd_cmd})\"; echo \"{end_marker}\""
        elif self.shell_type == "cmd":
            # Use parentheses to group commands and avoid issues with echo and redirection
            cmd_block = f"({cwd_cmd} & echo {end_marker})"

        newline = b"\r\n" if self.os_type == "windows" else b"\n"

        self.process.stdin.write(cmd_block.encode('utf-8') + newline)
        await self.process.stdin.drain()

        # Call with print_output=False to run silently
        full_output = await self._read_until_marker(end_marker, print_output=False)

        # The last non-empty line of the output should be the CWD
        lines = [line.strip() for line in full_output.splitlines() if line.strip()]
        # Filter out the command echo itself if it appears
        if lines and lines[0] == cwd_cmd:
            lines = lines[1:]

        if lines:
            self.current_working_directory = lines[-1]

    async def execute_command(self, command: str, print_output=True) -> tuple[str, str, int]:
        if not self.process or self.process.returncode is not None: return "", "Shell process not running.", -1

        end_marker = "__END_OF_CMD_EXEC__"
        rc_cmd = "echo $?" if self.os_type in ["linux", "macos"] else "echo %errorlevel%"
        if self.shell_type == "powershell": rc_cmd = "echo $LASTEXITCODE"

        # Construct command block more carefully for Windows
        if self.os_type == "windows":
            cmd_block = f"({command}) & echo {rc_cmd} & echo {end_marker}"
        else:
            cmd_block = f"{command}; {rc_cmd}; echo {end_marker}"

        newline = b"\r\n" if self.os_type == "windows" else b"\n"

        self.process.stdin.write(cmd_block.encode('utf-8') + newline)
        await self.process.stdin.drain()

        # Call with print_output=True to stream results to console
        full_output = await self._read_until_marker(end_marker, timeout=10.0, print_output=print_output)

        # Process the collected output
        lines = [line for line in full_output.splitlines()]

        # The last line should be the return code
        rc_str = "-1"
        if lines:
            # Find last line that could be a return code
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip().isdigit():
                    rc_str = lines.pop(i).strip()
                    break

        # Filter out command echo
        if lines and lines[0].strip() == command:
            lines = lines[1:]
        # Filter out rc_cmd echo
        if lines and lines[0].strip() == rc_cmd:
            lines = lines[1:]

        stdout_str = "\n".join(lines)
        if print_output and stdout_str:
            print(stdout_str)

        try: return_code = int(rc_str)
        except ValueError: return_code = -1

        return stdout_str, "", return_code # Stderr not separated in this model

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

    async def run_command_for_automation(self, command: str, typing_delay: float = None, style: Style = None) -> tuple[str, str, int]:
        active_style = style if style else self._internal_style
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5

        separator_ft = FormattedText([('class:separator', f"\n{'-'*70}")])
        entry_message_parts = [('class:info', "쉘 환경 진입 중... (명령어: "), ('class:command', command), ('class:info', ")")]
        entry_message_ft = FormattedText(entry_message_parts)

        print_formatted_text(separator_ft, style=active_style)
        print_formatted_text(entry_message_ft, style=active_style)

        await self._update_cwd() # Update CWD right before showing prompt
        current_prompt_ft = await self.get_prompt()
        print_formatted_text(current_prompt_ft, style=active_style, end="")

        for char_to_type in command:
            char_ft = FormattedText([('class:command', char_to_type)])
            print_formatted_text(char_ft, style=active_style, end="")
            await asyncio.sleep(typing_delay if char_to_type not in [' ', '\t'] else 0)
        print()

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
            except Exception:
                try: self.process.kill()
                except Exception: pass
            finally: self.process = None
        self._running = False
