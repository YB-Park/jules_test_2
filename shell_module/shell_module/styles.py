from prompt_toolkit.styles import Style

# Define a custom style for the shell prompt and potentially other UI elements.
# Colors can be specified by name (e.g., 'red', 'ansigreen') or hex codes (e.g., '#ff0000').
# Attributes like 'bold', 'italic', 'underline' can also be used.
custom_style = Style.from_dict({
    # Prompt styles
    'username':           '#ansibrightgreen bold',   # Bright Green, Bold (e.g., for user part)
    'hostname':           '#ansibrightcyan bold',    # Bright Cyan, Bold (e.g., for host part)
    'path':               '#ansibrightblue bold',    # Bright Blue, Bold (e.g., for current directory)
    'prompt_symbol':      '#ansibrightwhite bold',   # Bright White, Bold (e.g., $, > symbols)
    'prompt_symbol_ps':   '#ansibrightmagenta bold', # Bright Magenta, Bold (e.g., "PS" in PowerShell)
    'default':            '#ansidefault',            # Default terminal color (for @, : etc.)

    # Potentially for other UI elements if needed later
    # 'error_message': 'fg:ansired bg:ansiblack',
    # 'info_message':  'fg:ansicyan',
    # 'typing_effect_command': '#ansiyellow', # If command typing effect needs specific style
})

# You can also define multiple styles or themes if needed, e.g.:
# light_theme_style = Style.from_dict({ ... })
# dark_theme_style = Style.from_dict({ ... })

# For now, we'll just export the one custom_style.
# This can be imported into main.py and run_automation_example.py.
