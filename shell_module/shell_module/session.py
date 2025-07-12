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

PROMPT_MARKER = "_#_#_PROMPT_#_#_>"

class ShellSession:
    def __init__(self):
        self.process = None
        self.shell_type = None
        self.current_working_directory = "~"
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_type = constants.OS_TYPE
        self._running = True
        self.is_windows = self.os_type == "windows"
        self._internal_style = Style.from_dict({
            'info': 'fg:ansicyan', 'command': 'fg:ansiyellow', 'separator': 'fg:ansibrightblack',
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
                    prompt_cmd = f"function prompt {{'{PROMPT_MARKER}'}}"
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo", "-NonInteractive", "-Command", f"chcp 65001 | Out-Null; {prompt_cmd}"]
                else: raise FileNotFoundError
            except Exception:
                self.shell_type = "cmd"
                prompt_cmd = f"prompt {PROMPT_MARKER}"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD, "/K", f"chcp 65001 & {prompt_cmd}"]
        else:
            default_shell = constants.DEFAULT_SHELL_LINUX
            env_shell = os.environ.get("SHELL", default_shell)
            self.shell_type = os.path.basename(env_shell)
            resolved_shell_path = shutil.which(env_shell) or shutil.which(default_shell)
            if not resolved_shell_path: raise FileNotFoundError("Could not find a valid shell.")
            shell_cmd_list = [resolved_shell_path, "-c", f"export PS1='{PROMPT_MARKER}'; exec {resolved_shell_path} -i"]

        self.process = await asyncio.create_subprocess_exec(
            *shell_cmd_list, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        await self._read_until_prompt() # Consume startup messages
        await self._update_cwd() # Set initial CWD

    async def _read_until_prompt(self):
        output_buffer = ""
        while True:
            try:
                char_bytes = await asyncio.wait_for(self.process.stdout.read(1), timeout=2.0)
                if not char_bytes: break
                char = char_bytes.decode('utf-8', errors='replace')
                output_buffer += char
                if output_buffer.endswith(PROMPT_MARKER):
                    return output_buffer[:-len(PROMPT_MARKER)]
            except asyncio.TimeoutError: break
            except Exception: break
        return output_buffer

    async def _update_cwd(self):
        cwd_cmd = "$PWD.Path" if self.shell_type == "powershell" else ("cd" if self.is_windows else "pwd")
        self.process.stdin.write(f"{cwd_cmd}\n".encode('utf-8'))
        await self.process.stdin.drain()
        output = await self._read_until_prompt()
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if lines and lines[0].lower() == cwd_cmd.lower(): lines = lines[1:]
        if lines: self.current_working_directory = lines[-1]

    async def _get_return_code(self):
        rc_cmd = "$LASTEXITCODE" if self.shell_type == "powershell" else ("echo %errorlevel%" if self.is_windows else "echo $?")
        self.process.stdin.write(f"{rc_cmd}\n".encode('utf-8'))
        await self.process.stdin.drain()
        output = await self._read_until_prompt()
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if lines and lines[0].lower() == rc_cmd.lower(): lines = lines[1:]
        try: return int(lines[-1]) if lines else -1
        except (ValueError, IndexError): return -1

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        if not command.strip():
            await self._update_cwd()
            return "", "", 0

        self.process.stdin.write(f"{command}\n".encode('utf-8'))
        await self.process.stdin.drain()

        stdout = await self._read_until_prompt()

        lines = stdout.splitlines()
        # In interactive mode, the first line is often the command echo
        if lines and lines[0].strip() == command.strip():
            stdout = "\n".join(lines[1:])

        print(stdout)

        return_code = await self._get_return_code()
        await self._update_cwd()

        return stdout, "", return_code

    async def get_prompt(self) -> FormattedText:
        # (Same as previous version)
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
