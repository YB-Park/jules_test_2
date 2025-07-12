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
        self.current_working_directory = os.getcwd()
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_type = constants.OS_TYPE
        self._running = True
        self.is_windows = self.os_type == "windows"
        self._internal_style = Style.from_dict({
            'info': 'fg:ansicyan',
            'command': 'fg:ansiyellow',
            'separator': 'fg:ansibrightblack',
        })

    async def _initialize_shell(self):
        shell_cmd_list = []
        if self.is_windows:
            try:
                proc_check = await asyncio.create_subprocess_shell(
                    f"{constants.DEFAULT_SHELL_WINDOWS_POWERSHELL} -Command \"{constants.POWERSHELL_CHECK_COMMAND}\"",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc_check.communicate()
                if proc_check.returncode == 0:
                    self.shell_type = "powershell"
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo", "-NonInteractive", "-Command", "chcp 65001 | Out-Null; $OutputEncoding = [System.Text.UTF8Encoding]::new()"]
                else: raise FileNotFoundError
            except Exception:
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "chcp 65001"]
        else:
            default_shell = constants.DEFAULT_SHELL_LINUX
            env_shell = os.environ.get("SHELL", default_shell)
            self.shell_type = os.path.basename(env_shell)
            resolved_shell_path = shutil.which(env_shell) or shutil.which(default_shell)
            if not resolved_shell_path: raise FileNotFoundError("Could not find a valid shell.")
            shell_cmd_list = [resolved_shell_path, "-i"]

        try:
            self.process = await asyncio.create_subprocess_exec(
                *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except Exception as e:
            if self.os_type == "windows" and "powershell" in shell_cmd_list[0]:
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", "chcp 65001"]
                self.process = await asyncio.create_subprocess_exec(
                    *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            else: raise
        await self._update_cwd()

    async def _update_cwd(self):
        if not self.process or self.process.returncode is not None: return
        cwd_cmd = "$PWD.Path" if self.shell_type == "powershell" else ("cd" if self.is_windows else "pwd")
        end_marker = "__END_OF_CWD_UPDATE__"
        cmd_block = f"Write-Host -NoNewline \"$({cwd_cmd})\"; echo \"{end_marker}\"" if self.shell_type == "powershell" else f"({cwd_cmd} & echo {end_marker})" if self.shell_type == "cmd" else f"{cwd_cmd}; echo {end_marker}"
        newline = b"\r\n" if self.is_windows else b"\n"
        self.process.stdin.write(cmd_block.encode('utf-8') + newline)
        await self.process.stdin.drain()
        full_output = await self._read_until_marker(end_marker, print_output=False)
        lines = [line.strip() for line in full_output.splitlines() if line.strip()]
        if lines and lines[0].lower() == cwd_cmd.lower(): lines = lines[1:]
        if lines: self.current_working_directory = lines[-1]

    async def _read_until_marker(self, end_marker, timeout=2.0, print_output=False):
        output_buffer = ""
        while True:
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
                if not line_bytes: break
                line = line_bytes.decode('utf-8', errors='replace')
                if end_marker in line:
                    output_buffer += line.split(end_marker, 1)[0]
                    break
                output_buffer += line
                if print_output: print(line.rstrip('\r\n'))
            except asyncio.TimeoutError: break
            except Exception: break
        return output_buffer

    async def execute_command(self, command: str, print_output=True) -> tuple[str, str, int]:
        if not self.process or self.process.returncode is not None: return "", "Shell not running.", -1
        end_marker = "__END_OF_CMD_EXEC__"
        rc_cmd = "$LASTEXITCODE" if self.shell_type == "powershell" else ("echo %errorlevel%" if self.is_windows else "echo $?")
        cmd_block = f"({command}) & echo {rc_cmd} & echo {end_marker}" if self.is_windows else f"{command}; {rc_cmd}; echo {end_marker}"
        newline = b"\r\n" if self.is_windows else b"\n"
        self.process.stdin.write(cmd_block.encode('utf-8') + newline)
        await self.process.stdin.drain()
        full_output = await self._read_until_marker(end_marker, timeout=10.0, print_output=print_output)
        lines = [line for line in full_output.splitlines()]
        rc_str = "-1"
        if lines:
            if lines[-1].strip().isdigit(): rc_str = lines.pop(-1).strip()
        stdout = "\n".join(lines)
        try: return_code = int(rc_str)
        except ValueError: return_code = -1
        return stdout, "", return_code # Stderr not separated

    async def get_prompt(self) -> FormattedText:
        home_dir = os.path.expanduser("~"); display_cwd = self.current_working_directory; prompt_parts = []
        if not self.is_windows:
            normalized_cwd = os.path.normpath(self.current_working_directory)
            normalized_home = os.path.normpath(home_dir)
            if normalized_cwd.startswith(normalized_home) and normalized_cwd != normalized_home:
                display_cwd = "~" + normalized_cwd[len(normalized_home):].replace("\\", "/")
            elif normalized_cwd == normalized_home: display_cwd = "~"
            else: display_cwd = normalized_cwd.replace("\\", "/")
            prompt_parts.extend([('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])
        else:
            display_cwd = self.current_working_directory
            if self.shell_type == "powershell": prompt_parts.extend([('class:prompt_symbol_ps', "PS "), ('class:path', display_cwd), ('class:prompt_symbol', "> ")])
            else: prompt_parts.extend([('class:path', display_cwd), ('class:prompt_symbol', "> ")])
        return FormattedText(prompt_parts)

    async def run_command_for_automation(self, command: str, typing_delay: float = None, style: Style = None) -> tuple[str, str, int]:
        if not self.process: return "", "Shell not initialized.", -1
        active_style = style if style else self._internal_style
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5

        separator_ft = FormattedText([('class:separator', f"\n{'-'*70}")])
        entry_message_parts = [('class:info', "쉘 환경 진입 중... (명령어: "), ('class:command', command), ('class:info', ")")]
        entry_message_ft = FormattedText(entry_message_parts)

        print_formatted_text(separator_ft, style=active_style)
        print_formatted_text(entry_message_ft, style=active_style)

        await self._update_cwd()
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
                if self.is_windows:
                    self.process.stdin.write(b"exit\r\n")
                    await self.process.stdin.drain()
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=1.0)
            except Exception:
                try: self.process.kill()
                except Exception: pass
            finally: self.process = None
        self._running = False
