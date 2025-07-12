from prompt_toolkit.styles import Style

custom_style = Style.from_dict({
    # Prompt styles
    'username':           'ansigreen bold',
    'hostname':           'ansicyan bold',
    'path':               'ansiblue bold',
    'prompt_symbol':      'ansiwhite bold',
    'prompt_symbol_ps':   'ansimagenta bold',
    'default':            'ansidefault',

    # Styles for automation UI messages
    'info':               'ansibrightcyan',
    'command':            'ansibrightyellow',
    'separator':          'ansibrightblack',
})
