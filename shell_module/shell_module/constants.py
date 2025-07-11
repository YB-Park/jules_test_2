import platform

# Shell executable paths
DEFAULT_SHELL_LINUX = "/bin/bash"
DEFAULT_SHELL_MACOS = "/bin/zsh" # Or /bin/bash
DEFAULT_SHELL_WINDOWS_POWERSHELL = "powershell.exe"
DEFAULT_SHELL_WINDOWS_CMD = "cmd.exe"

# Command to check if PowerShell is available and functional
POWERSHELL_CHECK_COMMAND = "Get-Host"

# Markers for CWD (Current Working Directory) extraction
# Using unlikely sequences to avoid collision with actual command output.
CWD_MARKER_START = "__CWD_START__"
CWD_MARKER_END = "__CWD_END__"

# Commands to print CWD, platform specific
# These commands will be wrapped with markers.
# For example, on Linux: echo "__CWD_START__"; pwd; echo "__CWD_END__"
CMD_PRINT_CWD_LINUX = "pwd"
CMD_PRINT_CWD_MACOS = "pwd"
# For PowerShell, $PWD.Path is more reliable than 'cd' or 'echo %CD%'
CMD_PRINT_CWD_WINDOWS_POWERSHELL = "$PWD.Path"
# For CMD, 'cd' prints the current directory.
CMD_PRINT_CWD_WINDOWS_CMD = "cd"

# Default encoding for shell communication
DEFAULT_ENCODING = "utf-8"

# Small delay for typing effect (in seconds)
TYPING_EFFECT_DELAY = 0.03 # Adjust for desired speed

# Prompt format strings - will be filled with username, hostname, cwd
# These are basic examples and can be customized further.
# ~ will represent the home directory.
PROMPT_FORMAT_LINUX = "{username}@{hostname}:{cwd}$ "
PROMPT_FORMAT_MACOS = "{username}@{hostname}:{cwd}$ " # Similar to Linux
PROMPT_FORMAT_WINDOWS_POWERSHELL = "PS {cwd}> "
PROMPT_FORMAT_WINDOWS_CMD = "{cwd}> "

# Special command to exit the shell session
EXIT_COMMANDS = ["exit", "quit"]


def get_os_type():
    """Determines the OS type."""
    system = platform.system().lower()
    if "linux" in system:
        return "linux"
    elif "darwin" in system: # macOS
        return "macos"
    elif "windows" in system:
        return "windows"
    return "unknown"

OS_TYPE = get_os_type()
