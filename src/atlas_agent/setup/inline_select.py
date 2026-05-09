from typing import List, Tuple, Optional
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.shortcuts import prompt

def inline_radio_select(title: str, choices: List[Tuple[str, str]], default: Optional[str] = None) -> Optional[str]:
    from atlas_agent.setup.theme import atlas_theme
    
    current_index = 0
    for i, (val, _) in enumerate(choices):
        if val == default:
            current_index = i
            break

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        nonlocal current_index
        current_index = max(0, current_index - 1)

    @kb.add("down")
    def _(event):
        nonlocal current_index
        current_index = min(len(choices) - 1, current_index + 1)

    @kb.add("enter")
    @kb.add("space")
    def _(event):
        event.app.exit(result=choices[current_index][0])

    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        event.app.exit(result=None)

    def get_text() -> AnyFormattedText:
        lines = []
        lines.append(("class:title", f"{title}\n"))
        lines.append(("class:muted", "  ↑↓ navigate   ENTER/SPACE select   ESC cancel\n\n"))
        
        for i, (val, label) in enumerate(choices):
            is_selected = (i == current_index)
            prefix = "→ " if is_selected else "  "
            bullet = "(●)" if is_selected else "(○)"
            
            style = "class:selected" if is_selected else "class:normal"
            lines.append((style, f"{prefix}{bullet} {label}\n"))
            
        return lines

    app = Application(
        layout=Layout(Window(content=FormattedTextControl(get_text), dont_extend_height=True)),
        key_bindings=kb,
        style=atlas_theme,
        full_screen=False,
        erase_when_done=False
    )
    
    try:
        result = app.run()
        print("")  # visual spacing after selection
        return result
    except (KeyboardInterrupt, EOFError):
        print("")
        return None

def inline_input(title: str, text: str, default: str = "") -> Optional[str]:
    from atlas_agent.setup.theme import atlas_theme
    message = [
        ("class:title", f"{title}\n"),
        ("class:normal", f"{text} "),
    ]
    try:
        result = prompt(message, default=default, style=atlas_theme)
        print("")  # visual spacing
        return result
    except (KeyboardInterrupt, EOFError):
        print("")
        return None
