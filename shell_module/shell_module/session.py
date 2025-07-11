import asyncio
import platform
import os
import getpass
import socket
from . import constants

class ShellSession:
    def __init__(self):
        self.process = None
        self.shell_type = None # 'powershell', 'cmd', 'bash', 'zsh', etc.
        self.current_working_directory = "~" # Default or to be fetched
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_type = constants.OS_TYPE
        self._running = True

    async def _initialize_shell(self):
        """
        Initializes and starts the appropriate shell process based on the OS.
        Sets self.process and self.shell_type.
        """
        shell_cmd_list = []

        if self.os_type == "windows":
            # Try PowerShell first
            try:
                # Check if PowerShell is available and working by running a simple command
                proc_check = await asyncio.create_subprocess_shell(
                    f"{constants.DEFAULT_SHELL_WINDOWS_POWERSHELL} -Command \"{constants.POWERSHELL_CHECK_COMMAND}\"",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc_check.communicate()
                if proc_check.returncode == 0 and stdout:
                    self.shell_type = "powershell"
                    # For PowerShell, -NoExit and -Command - ensure it stays open and can run commands.
                    # Using -NoLogo to keep startup clean.
                    # We will send commands to its stdin.
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo", "-Command", "-"]
                    # The '-' command tells PowerShell to read commands from stdin.
                    # However, for continuous interaction, it's often better to run powershell.exe directly
                    # and feed commands to its stdin without -Command -.
                    # Let's try a simpler approach first for Popen.
                    # For create_subprocess_shell, we pass the shell executable itself.
                    # For create_subprocess_exec, we pass list of args.
                    # Using shell=True for create_subprocess_shell is simpler for path resolution.
                    # For a more robust solution, create_subprocess_exec is preferred.
                    # Here, we'll use create_subprocess_exec for clarity on args.
                    shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_POWERSHELL, "-NoExit", "-NoLogo"]

                else:
                    raise FileNotFoundError("PowerShell check failed or not found.")
            except (FileNotFoundError, asyncio.CancelledError, Exception) as e:
                print(f"PowerShell not found or failed to start ({e}), falling back to CMD.")
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD]

        elif self.os_type == "linux":
            self.shell_type = "bash" # Default to bash
            # Check SHELL env var for user's preferred shell
            user_shell = os.environ.get("SHELL")
            if user_shell and os.path.exists(user_shell):
                 shell_cmd_list = [user_shell]
            else:
                 shell_cmd_list = [constants.DEFAULT_SHELL_LINUX]

        elif self.os_type == "macos":
            self.shell_type = "zsh" # Default to zsh on modern macOS
            user_shell = os.environ.get("SHELL")
            if user_shell and os.path.exists(user_shell):
                shell_cmd_list = [user_shell]
            else:
                shell_cmd_list = [constants.DEFAULT_SHELL_MACOS]
        else:
            raise OSError(f"Unsupported OS type: {self.os_type}")

        if not shell_cmd_list:
            raise RuntimeError("Shell command list could not be determined.")

        # Start the shell process
        # Using PTYs (pseudo-terminals) would be better for full interactivity (e.g. sudo)
        # but are more complex. For now, use standard pipes.
        # We use create_subprocess_exec to avoid shell=True for security if possible,
        # but for shell executables themselves, this is how they are typically called.
        # If shell_cmd_list[0] is just "powershell.exe" or "bash", OS usually finds it.
        try:
            self.process = await asyncio.create_subprocess_exec(
                *shell_cmd_list,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # On Windows, creationflags can be used to control window visibility,
                # but for console apps, it's not usually needed for pipes.
                # For Linux/macOS, if you need a login shell behavior, there are other considerations.
            )
            print(f"Successfully started shell: {self.shell_type} with command: {' '.join(shell_cmd_list)}")
        except Exception as e:
            print(f"Failed to start shell {self.shell_type} with command {' '.join(shell_cmd_list)}: {e}")
            # Fallback for Windows if the specific powershell invocation failed, try simpler cmd
            if self.os_type == "windows" and self.shell_type == "powershell":
                print("Attempting fallback to CMD due to PowerShell startup failure.")
                self.shell_type = "cmd"
                shell_cmd_list = [constants.DEFAULT_SHELL_WINDOWS_CMD]
                self.process = await asyncio.create_subprocess_exec(
                    *shell_cmd_list,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                print(f"Successfully started shell: {self.shell_type} with command: {' '.join(shell_cmd_list)}")
            else:
                raise # Re-raise if not Windows PS or fallback also failed

        # Perform initial CWD update
        # In a real scenario, _update_cwd would be called after shell is confirmed running.
        # For now, we'll call it, and it will use a placeholder or Python's CWD.
        await self._update_cwd()

    async def _update_cwd(self, cwd_from_shell: str = None):
        """
        Updates the current working directory by querying the shell.
        Uses platform-specific commands and markers to reliably get CWD.
        """
        if not self.process or self.process.returncode is not None:
            # Shell not running, use Python's CWD or a sensible default
            self.current_working_directory = os.getcwd()
            # print(f"Debug: Shell not running, CWD defaulted to {self.current_working_directory}")
            return

        cwd_cmd = ""
        if self.os_type == "windows":
            if self.shell_type == "powershell":
                cwd_cmd = constants.CMD_PRINT_CWD_WINDOWS_POWERSHELL
            else: # cmd
                cwd_cmd = constants.CMD_PRINT_CWD_WINDOWS_CMD
        elif self.os_type in ["linux", "macos"]:
            cwd_cmd = constants.CMD_PRINT_CWD_LINUX # or MACOS, they are the same 'pwd'

        if not cwd_cmd:
            # print(f"Debug: CWD command not found for {self.os_type}/{self.shell_type}, using os.getcwd()")
            self.current_working_directory = os.getcwd()
            return

        # Construct command with markers
        # Example for Linux: echo "__CWD_START__"; pwd; echo "__CWD_END__"
        # For PowerShell: Write-Host "__CWD_START__"; $PWD.Path; Write-Host "__CWD_END__"
        # For CMD: echo __CWD_START__& cd & echo __CWD_END__
        # Note: CMD's `&` chaining and `echo` behavior needs care.
        # `echo` in CMD can be tricky with special characters or if the string is empty.
        # A more robust way for CMD might involve temp files or more complex echo commands.

        # Let's refine command construction for each shell
        full_command_with_markers = ""
        newline = b"\r\n" if self.os_type == "windows" else b"\n"

        if self.shell_type == "powershell":
            # PowerShell uses Write-Host for direct console output that isn't easily redirected by mistake.
            # $PWD.Path gives the string path.
            full_command_with_markers = (
                f"Write-Host '{constants.CWD_MARKER_START}'; "
                f"{constants.CMD_PRINT_CWD_WINDOWS_POWERSHELL}; "
                f"Write-Host '{constants.CWD_MARKER_END}'"
            )
        elif self.shell_type == "cmd":
            # CMD `echo` can be tricky. `echo.` prints a newline.
            # `cd` by itself prints current directory.
            # We need to ensure markers are on separate lines or clearly distinguishable.
            # A common pattern is `(echo marker_start & command & echo marker_end)`
            # but output parsing needs to be careful.
            # Let's try:
            full_command_with_markers = (
                f"echo {constants.CWD_MARKER_START}\n"
                f"{constants.CMD_PRINT_CWD_WINDOWS_CMD}\n"
                f"echo {constants.CWD_MARKER_END}"
            )
            # This might result in markers and CWD on different lines, which is fine for parsing.
        elif self.shell_type in ["bash", "zsh"]: # Linux/macOS
            full_command_with_markers = (
                f"echo '{constants.CWD_MARKER_START}'; "
                f"{constants.CMD_PRINT_CWD_LINUX}; "
                f"echo '{constants.CWD_MARKER_END}'"
            )
        else: # Should not happen if shell_type is set
            self.current_working_directory = os.getcwd()
            return

        # print(f"Debug: Sending CWD command: {full_command_with_markers}")
        self.process.stdin.write(full_command_with_markers.encode(constants.DEFAULT_ENCODING) + newline)
        await self.process.stdin.drain()

        # Read output to find markers and extract CWD
        output_lines = []
        capturing_cwd = False
        # print(f"Debug: Reading CWD from shell output...")
        for _ in range(10): # Limit reads to avoid infinite loop on unexpected output
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=0.5) # Increased timeout for CWD
                if not line_bytes:
                    # print("Debug: EOF on stdout while reading CWD")
                    break
                line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').strip()
                # print(f"Debug CWD Read: '{line}'")

                if constants.CWD_MARKER_START in line:
                    capturing_cwd = True
                    # If marker and CWD are on the same line (e.g. PowerShell without careful Write-Host)
                    # we might need to strip marker here.
                    # For now, assume CWD is on lines *after* START_MARKER and *before* END_MARKER
                    # For `echo MARKER; cmd; echo MARKER`, CWD is between them.
                    # For `echo MARKER & cmd & echo MARKER` (CMD), it's also between.
                    # If line IS the marker, continue. If line CONTAINS marker and data, parse.
                    # For `echo MARKER \n CMD_OUTPUT \n echo MARKER_END`, this logic is simpler.
                    line_after_marker_start = line.split(constants.CWD_MARKER_START, 1)[-1].strip()
                    if line_after_marker_start: # Content after marker on same line
                         # This case is more complex if CWD is also on this line vs next.
                         # Let's assume for now that if START_MARKER is found, the *next* relevant lines are CWD.
                         # Or, if the command structure is `Write-Host "START"; $PWD.Path; Write-Host "END"`,
                         # the $PWD.Path output will be its own line between marker lines.
                         pass # Marker found, start capturing from next relevant lines if CWD is not on this one.
                    continue # Move to next line if this line was just the marker

                if constants.CWD_MARKER_END in line:
                    capturing_cwd = False
                    # Potentially content on the same line as end marker, ignore it for CWD.
                    break # Found end marker

                if capturing_cwd and line: # Avoid adding empty lines if any
                    output_lines.append(line)

            except asyncio.TimeoutError:
                # print("Debug: Timeout while reading CWD output from shell.")
                break # Stop if shell doesn't respond quickly

        # print(f"Debug: Captured lines for CWD: {output_lines}")
        if output_lines:
            # Join lines and take the most relevant one.
            # For 'pwd' or 'cd', it's usually a single line.
            # If multiple lines were captured, the logic might need refinement based on shell.
            # Example: some shells might print blank lines around CWD output.
            # Taking the first non-empty captured line.
            for potential_cwd in output_lines:
                if potential_cwd.strip(): # Ensure it's not just whitespace
                    self.current_working_directory = potential_cwd.strip()
                    # print(f"Debug: CWD updated to '{self.current_working_directory}' from shell")
                    return # Successfully updated

        # If CWD couldn't be determined from shell, perhaps log it or stick to previous CWD.
        # For safety, if parsing fails, don't change it or revert to os.getcwd()
        # print(f"Debug: Failed to parse CWD from shell. Current CWD remains: '{self.current_working_directory}' or fallback to os.getcwd()")
        # As a fallback if markers not found or no output, use os.getcwd()
        # This is NOT the shell's CWD but Python process's CWD.
        # self.current_working_directory = os.getcwd() # Fallback if parsing fails. This is not ideal.
        # Better: keep the last known CWD if update fails, or handle error.
        # For now, if output_lines is empty, it means we didn't get a new CWD from shell.

    async def run_command_for_automation(self, command: str, typing_delay: float = None) -> tuple[str, str, int]:
        """
        Runs a command as if an automated system is typing it.
        Displays prompt, types command, then executes and streams output.
        Args:
            command (str): The command string to execute.
            typing_delay (float, optional): Delay between typing characters.
                                            Defaults to constants.TYPING_EFFECT_DELAY / 2.
        Returns:
            tuple[str, str, int]: Full stdout, full stderr, and return code from execute_command.
        """
        if typing_delay is None:
            typing_delay = constants.TYPING_EFFECT_DELAY / 1.5 # Slightly faster for automation

        current_prompt = await self.get_prompt()
        print(current_prompt, end="", flush=True)

        for char_to_type in command:
            print(char_to_type, end="", flush=True)
            if char_to_type != ' ': # Optionally skip delay for spaces
                await asyncio.sleep(typing_delay)
        print()  # Newline after typing the command

        # Execute the command (streams output internally)
        return await self.execute_command(command)

    async def get_prompt(self) -> str:
        """
        Generates the prompt string based on OS, shell type, username, hostname, and CWD.
        Replaces home directory with '~' for Linux/macOS.
        """
        home_dir = os.path.expanduser("~")
        display_cwd = self.current_working_directory

        if self.os_type in ["linux", "macos"]:
            if self.current_working_directory.startswith(home_dir):
                display_cwd = "~" + self.current_working_directory[len(home_dir):]
            # Ensure ~ is used for /home/user if cwd is /home/user not /home/user/something
            if self.current_working_directory == home_dir:
                display_cwd = "~"

            if self.os_type == "linux":
                return constants.PROMPT_FORMAT_LINUX.format(
                    username=self.username, hostname=self.hostname, cwd=display_cwd
                )
            else: # macos
                return constants.PROMPT_FORMAT_MACOS.format(
                    username=self.username, hostname=self.hostname, cwd=display_cwd
                )
        elif self.os_type == "windows":
            # Windows paths are typically not shortened with '~' in prompts
            display_cwd = self.current_working_directory
            if self.shell_type == "powershell":
                return constants.PROMPT_FORMAT_WINDOWS_POWERSHELL.format(cwd=display_cwd)
            else: # cmd
                return constants.PROMPT_FORMAT_WINDOWS_CMD.format(cwd=display_cwd)

        # Fallback generic prompt
        return f"({self.shell_type}) {self.username}@{self.hostname}:{display_cwd}$ "

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        """
        Executes a command in the shell and streams its stdout and stderr.
        Returns a tuple of (full_stdout, full_stderr, return_code).
        """
        if not self.process or self.process.returncode is not None:
            print("[ERROR] Shell process is not running.")
            return "", "Shell process not running.", -1

        full_stdout = []
        full_stderr = []

        try:
            # Ensure command is properly encoded and terminated with a newline
            # \r\n for Windows (cmd/powershell), \n for Linux/macOS
            newline = b"\r\n" if self.os_type == "windows" else b"\n"
            self.process.stdin.write(command.encode(constants.DEFAULT_ENCODING) + newline)
            await self.process.stdin.drain()

            # After sending the command, we need a way to know when the command output has ended.
            # This is a significant challenge with interactive shells.
            # A common technique is to send a unique marker command AFTER the user's command
            # and wait for that marker in the output.

            # Example: Command + Echo Marker
            # command_to_send = f"{command}\n" # User's command
            # unique_end_marker = "END_OF_COMMAND_OUTPUT_MARKER_12345"
            # command_to_send += f"echo {unique_end_marker}\n"
            # self.process.stdin.write(command_to_send.encode(constants.DEFAULT_ENCODING))
            # await self.process.stdin.drain()

            # For now, a simpler approach: read until no more output for a short period,
            # or until a specific pattern. This is less robust.
            # A robust solution needs a clear way to demarcate command output.
            # For this iteration, we'll try reading lines with a timeout. This is NOT ideal for long-running commands.

            # Let's refine this. We need to read both stdout and stderr concurrently.
            async def read_stream(stream, output_list, stream_name):
                while True:
                    try:
                        # Read with a timeout to avoid blocking indefinitely if command produces no output
                        # or if we're waiting for a marker that might not come with this simple approach.
                        # A better way is to use a clear end-of-output marker after each command.
                        line_bytes = await asyncio.wait_for(stream.readline(), timeout=0.1)
                        if not line_bytes: # EOF
                            # print(f"EOF received on {stream_name}")
                            break
                        line = line_bytes.decode(constants.DEFAULT_ENCODING, errors='replace').rstrip()
                        print(line) # Stream to console
                        output_list.append(line)
                    except asyncio.TimeoutError:
                        # print(f"Timeout reading from {stream_name}, assuming end of current output block.")
                        break # No more output for now
                    except Exception as e:
                        # print(f"Error reading {stream_name}: {e}")
                        break

            # This simple concurrent read won't robustly determine command completion.
            # A more robust approach involves sending a command to print a unique marker
            # AFTER each user command, then reading output until that marker is seen.
            # For example:
            # 1. Send user_command + newline
            # 2. Send echo "UNIQUE_MARKER_STDOUT" + newline
            # 3. Send echo "UNIQUE_MARKER_STDERR" >&2 + newline (if shell supports it)
            # Then read stdout/stderr until these markers are seen.

            # For this step, let's just read available output. This will be improved.
            # This is a placeholder for robust output reading.
            # It will likely only capture immediate output.
            await asyncio.gather(
                read_stream(self.process.stdout, full_stdout, "stdout"),
                read_stream(self.process.stderr, full_stderr, "stderr")
            )

            # The return code of the shell process itself isn't the command's return code here,
            # as the shell is persistent. We'd need to echo $? (Linux/macOS) or $LASTEXITCODE (PowerShell)
            # to get the last command's return code, also with markers.
            # For now, returning a placeholder.
            return_code = 0 # Placeholder

        except Exception as e:
            error_msg = f"Error executing command: {e}"
            print(error_msg)
            full_stderr.append(error_msg)
            return_code = -1 # Indicate error

        # IMPORTANT: After command execution, update CWD as it might have changed (e.g., 'cd' command)
        await self._update_cwd() # This needs to be the version that queries the shell for its CWD

        return "\n".join(full_stdout), "\n".join(full_stderr), return_code


    async def close(self):
        """Gracefully close the shell session."""
        if self.process and self.process.returncode is None:
            try:
                if self.os_type == "windows" and self.shell_type == "powershell":
                    # PowerShell might need 'exit' sent to stdin to close gracefully
                    # self.process.stdin.write(b"exit\r\n") # \r\n for Windows
                    # await self.process.stdin.drain()
                    pass # Often terminate/kill is more reliable for subprocesses

                self.process.terminate()
                await self.process.wait()
                print(f"Shell process {self.shell_type} terminated.")
            except ProcessLookupError:
                print(f"Shell process {self.shell_type} already exited.")
            except Exception as e:
                print(f"Error terminating shell process {self.shell_type}: {e}")
            finally:
                self.process = None
        self._running = False

# Example of how to test this part (can be moved to main.py later)
async def _test_shell_init():
    session = ShellSession()
    try:
        print(f"OS Type: {session.os_type}")
        print(f"Username: {session.username}, Hostname: {session.hostname}")
        await session._initialize_shell()
        if session.process:
            print(f"Shell Type: {session.shell_type}")
            print(f"Initial CWD: {session.current_working_directory}")
            prompt = await session.get_prompt()
            print(f"Generated Prompt: {prompt}")
        else:
            print("Shell process failed to initialize.")
    except Exception as e:
        print(f"An error occurred during test: {e}")
    finally:
        if session.process:
            await session.close()

if __name__ == '__main__':
    # This is for temporary testing of ShellSession initialization
    # The main interactive loop will be in main.py
    asyncio.run(_test_shell_init())
