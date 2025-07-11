from prompt_toolkit.styles import Style

# Define a custom style for the shell prompt and potentially other UI elements.
# Colors can be specified by name (e.g., 'red', 'ansigreen') or hex codes (e.g., '#ff0000').
# Attributes like 'bold', 'italic', 'underline' can also be used.
custom_style = Style.from_dict({
    # Prompt styles - Using more basic/standard ANSI names
    'username':           'ansigreen bold',         # 'ansibrightgreen' -> 'ansigreen'
    'hostname':           'ansicyan bold',          # 'ansibrightcyan' -> 'ansicyan'
    'path':               'ansiblue bold',          # 'ansibrightblue' -> 'ansiblue'
    'prompt_symbol':      'ansiwhite bold',         # 'ansibrightwhite' -> 'ansiwhite'
    'prompt_symbol_ps':   'ansimagenta bold',       # 'ansibrightmagenta' -> 'ansimagenta'
    'default':            'ansidefault',            # 그대로 유지

    # Styles for automation UI messages (used in run_command_for_automation)
    'info':               'ansibrightcyan',        # 정보 메시지 (진입/종료 등)
    'command':            'ansibrightyellow',      # 타이핑되는 명령어
    'separator':          'ansibrightblack',       # 구분선 (흐릿한 색으로)

    # Potentially for other UI elements if needed later
    # 'error_message': 'fg:ansired bg:ansiblack',
})

# You can also define multiple styles or themes if needed, e.g.:
# light_theme_style = Style.from_dict({ ... })
# dark_theme_style = Style.from_dict({ ... })

# For now, we'll just export the one custom_style.
# This can be imported into main.py and run_automation_example.py.
