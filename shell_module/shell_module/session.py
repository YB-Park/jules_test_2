import asyncio
import platform
import os
import getpass
import socket
import shutil
import sys
from . import constants
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit import print_formatted_text
from prompt_toolkit.styles import Style

PROMPT_MARKER = "__PROMPT_END_MARKER__>"

class BaseShellSession:
    def __init__(self):
        self.process = None; self.shell_type = "base"; self.current_working_directory = os.getcwd()
        self.username = getpass.getuser(); self.hostname = socket.gethostname()
        self.os_type = constants.OS_TYPE; self.is_windows = self.os_type == "windows"
        self._internal_style = Style.from_dict({'info': 'fg:ansicyan', 'command': 'fg:ansiyellow', 'separator': 'fg:ansibrightblack'})
    async def _initialize_shell(self): raise NotImplementedError
    async def execute_command(self, command: str) -> tuple[str, str, int]: raise NotImplementedError
    async def get_prompt(self) -> FormattedText: raise NotImplementedError

    async def _read_streams_until_prompt(self, timeout=2.0):
        stdout_buffer = ""
        stderr_buffer = ""

        # Event to signal that the prompt has been found in stdout
        prompt_found = asyncio.Event()

        async def read_stdout():
            nonlocal stdout_buffer
            buffer = ""
            while not prompt_found.is_set():
                try:
                    # Use a short timeout to yield control frequently
                    line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=0.05)
                    if not line_bytes: break
                    line = line_bytes.decode('utf-8', 'replace')
                    if PROMPT_MARKER in line:
                        buffer += line.split(PROMPT_MARKER, 1)[0]
                        prompt_found.set() # Signal other tasks to stop
                        break
                    buffer += line
                except asyncio.TimeoutError:
                    # If stdout is quiet, continue waiting until the main task times out
                    if prompt_found.is_set(): break
                except Exception:
                    prompt_found.set(); break # Stop on any other error
            stdout_buffer = buffer

        async def read_stderr():
            nonlocal stderr_buffer
            while not prompt_found.is_set():
                try:
                    line_bytes = await asyncio.wait_for(self.process.stderr.readline(), timeout=0.05)
                    if not line_bytes: break
                    stderr_buffer += line_bytes.decode('utf-8', 'replace')
                except asyncio.TimeoutError:
                    if prompt_found.is_set(): break
                except Exception:
                    prompt_found.set(); break

        try:
            # Run readers concurrently with an overall timeout
            await asyncio.wait_for(asyncio.gather(read_stdout(), read_stderr()), timeout=timeout)
        except asyncio.TimeoutError:
            # This happens if the prompt is not found within the main timeout
            pass

        return stdout_buffer, stderr_buffer

    async def run_command_for_automation(self, command: str, typing_delay: float = None, style: Style = None) -> tuple[str, str, int]:
        if not self.process: print("[ERROR] Shell not initialized."); return "", "Shell not initialized.", -1
        active_style = style or self._internal_style
        if typing_delay is None: typing_delay = constants.TYPING_EFFECT_DELAY / 1.5
        separator_ft = FormattedText([('class:separator', f"\n{'-'*70}")])
        entry_message_ft = FormattedText([('class:info', "쉘 환경 진입 중... (명령어: "), ('class:command', command), ('class:info', ")")])
        print_formatted_text(separator_ft, style=active_style); print_formatted_text(entry_message_ft, style=active_style)
        current_prompt_ft = await self.get_prompt()
        print_formatted_text(current_prompt_ft, style=active_style, end="")
        for char in command:
            print_formatted_text(FormattedText([('class:command', char)]), style=active_style, end="")
            await asyncio.sleep(typing_delay if char > ' ' else 0)
        print()
        stdout, stderr, rc = await self.execute_command(command)
        exit_message_ft = FormattedText([('class:info', f"명령어 실행 완료 (종료 코드: {rc}). 쉘 환경 종료 중...")])
        print_formatted_text(exit_message_ft, style=active_style); print_formatted_text(separator_ft, style=active_style)
        return stdout, stderr, rc
    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                if self.is_windows: self.process.stdin.write(b"exit\r\n")
                else: self.process.stdin.write(b"exit\n")
                await self.process.stdin.drain()
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=1.0)
            except Exception:
                try: self.process.kill()
                except Exception: pass
            finally: self.process = None

class PowerShellSession(BaseShellSession):
    def __init__(self): super().__init__(); self.shell_type = "powershell"
    async def _initialize_shell(self):
        prompt_cmd = f"function prompt {{'{PROMPT_MARKER}'}}"
        shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo", "-NonInteractive", "-Command", f"chcp 65001 | Out-Null; {prompt_cmd}"]
        self.process = await asyncio.create_subprocess_exec(*shell_cmd_list, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await self._read_streams_until_prompt(); await self._update_cwd()
    async def _update_cwd(self):
        self.process.stdin.write(b"$PWD.Path\n"); await self.process.stdin.drain()
        stdout, _ = await self._read_streams_until_prompt()
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        if lines and lines[0].lower() == '$pwd.path': lines = lines[1:]
        if lines: self.current_working_directory = lines[-1]
    async def _get_return_code(self):
        self.process.stdin.write(b"echo $LASTEXITCODE\n"); await self.process.stdin.drain()
        stdout, _ = await self._read_streams_until_prompt()
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        if lines and lines[0].lower() == 'echo $lastexitcode': lines = lines[1:]
        try: return int(lines[-1]) if lines else -1
        except (ValueError, IndexError): return -1
    async def execute_command(self, command):
        if not command.strip(): return "", "", await self._get_return_code()
        self.process.stdin.write(f"{command}\n".encode('utf-8')); await self.process.stdin.drain()
        stdout, stderr = await self._read_streams_until_prompt(timeout=10.0)
        if stdout: print(stdout.strip())
        if stderr: print(stderr.strip(), file=sys.stderr)
        rc = await self._get_return_code(); await self._update_cwd()
        return stdout, stderr, rc
    async def get_prompt(self):
        return FormattedText([('class:prompt_symbol_ps', "PS "), ('class:path', self.current_working_directory), ('class:prompt_symbol', "> ")])

class PosixShellSession(BaseShellSession):
    def __init__(self, shell_path, shell_name): super().__init__(); self.shell_path = shell_path; self.shell_type = shell_name
    async def _initialize_shell(self):
        cmd = [self.shell_path, "-c", f"export PS1='{PROMPT_MARKER}'; exec {self.shell_path} -i"]
        self.process = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await self._read_streams_until_prompt(); await self._update_cwd()
    async def _update_cwd(self):
        self.process.stdin.write(b"pwd\n"); await self.process.stdin.drain()
        stdout, _ = await self._read_streams_until_prompt()
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        if lines and lines[0] == 'pwd': lines = lines[1:]
        if lines: self.current_working_directory = lines[-1]
    async def _get_return_code(self):
        self.process.stdin.write(b"echo $?\n"); await self.process.stdin.drain()
        stdout, _ = await self._read_streams_until_prompt()
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        if lines and lines[0] == 'echo $?': lines = lines[1:]
        try: return int(lines[-1]) if lines else -1
        except (ValueError, IndexError): return -1
    async def execute_command(self, command):
        if not command.strip(): return "", "", await self._get_return_code()
        self.process.stdin.write(f"{command}\n".encode('utf-8')); await self.process.stdin.drain()
        stdout, stderr = await self._read_streams_until_prompt(timeout=10.0)
        lines = stdout.splitlines()
        if lines and lines[0].strip() == command.strip(): stdout = "\n".join(lines[1:])
        if stdout: print(stdout.strip())
        if stderr: print(stderr.strip(), file=sys.stderr)
        rc = await self._get_return_code(); await self._update_cwd()
        return stdout, stderr, rc
    async def get_prompt(self):
        home = os.path.expanduser("~"); cwd = self.current_working_directory
        norm_cwd = os.path.normpath(cwd); norm_home = os.path.normpath(home)
        display_cwd = f"~{os.path.sep}{os.path.relpath(norm_cwd, norm_home)}" if norm_cwd.startswith(norm_home) else norm_cwd
        display_cwd = display_cwd.replace("\\", "/")
        return FormattedText([('class:username', self.username), ('class:default', '@'), ('class:hostname', self.hostname), ('class:default', ':'), ('class:path', display_cwd), ('class:prompt_symbol', '$ ')])

class CmdSession(PosixShellSession):
     def __init__(self): super().__init__(constants.DEFAULT_SHELL_WINDOWS_CMD, "cmd")
     async def _initialize_shell(self):
        prompt_cmd = f"prompt {PROMPT_MARKER.replace('>', '$G')}"
        cmd = [self.shell_path, "/K", f"chcp 65001 & {prompt_cmd}"]
        self.process = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await self._read_streams_until_prompt(); await self._update_cwd()
     async def _update_cwd(self):
        self.process.stdin.write(b"cd\n"); await self.process.stdin.drain()
        stdout, _ = await self._read_streams_until_prompt()
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        if lines and lines[0].lower() == 'cd': lines = lines[1:]
        if lines: self.current_working_directory = lines[-1]
     async def _get_return_code(self):
        self.process.stdin.write(b"echo %errorlevel%\n"); await self.process.stdin.drain()
        stdout, _ = await self._read_streams_until_prompt()
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        if lines and lines[0].lower() == 'echo %errorlevel%': lines = lines[1:]
        try: return int(lines[-1]) if lines else -1
        except (ValueError, IndexError): return -1
     async def get_prompt(self):
        return FormattedText([('class:path', self.current_working_directory), ('class:prompt_symbol', "> ")])

async def create_shell_session() -> BaseShellSession:
    session = None
    if platform.system() == "Windows":
        try:
            proc_check = await asyncio.create_subprocess_shell(
                f"powershell.exe -Command \"Get-Host\"",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc_check.communicate()
            if proc_check.returncode == 0: session = PowerShellSession()
            else: session = CmdSession()
        except (FileNotFoundError, Exception): session = CmdSession()
    else:
        default_shell = "/bin/bash"
        env_shell = os.environ.get("SHELL", default_shell)
        resolved_shell_path = shutil.which(env_shell) or shutil.which(default_shell)
        if not resolved_shell_path: raise FileNotFoundError("Could not find a valid shell.")
        session = PosixShellSession(resolved_shell_path, os.path.basename(resolved_shell_path))

    try: await session._initialize_shell(); return session
    except Exception as e:
        print(f"[ERROR] Failed to initialize shell session ({getattr(session, 'shell_type', 'unknown')}): {e}")
        return None
