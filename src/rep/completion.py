import argparse
import shlex

SHELL_ZSH = "zsh"
SHELL_BASH = "bash"
SHELL_FISH = "fish"
SHELLS = (SHELL_ZSH, SHELL_BASH, SHELL_FISH)
FILE_DESTINATIONS = ("file", "output")
COMPLETION_COMMAND = "completion_command"
QUIET = "2>/dev/null"
ZSH_SPECIAL_CHARACTERS = ("\\", ":", "[", "]")


def visible_subcommands(root):
    subparsers = next(action for action in root._actions if isinstance(action, argparse._SubParsersAction))

    return [(choice.dest, choice.help, subparsers.choices[choice.dest]) for choice in subparsers._choices_actions]


def positionals(command_parser):
    return [action for action in command_parser._actions if not action.option_strings]


def options(command_parser):
    return [action for action in command_parser._actions
            if action.option_strings and not isinstance(action, argparse._HelpAction)]


def takes_value(option):
    return option.nargs != 0


def wants_file(action):
    return action.dest in FILE_DESTINATIONS


def dynamic_command(action):
    command = getattr(action, COMPLETION_COMMAND, None)

    return f"rep {' '.join(command)} {QUIET}" if command else None


def choice_words(action):
    return " ".join(str(choice) for choice in action.choices or ())


def bash_words(action):
    command = dynamic_command(action)

    return f"$({command})" if command else choice_words(action)


def long_flag(option):
    return max(option.option_strings, key=len)


def zsh_escape(text):
    for character in ZSH_SPECIAL_CHARACTERS:
        text = text.replace(character, "\\" + character)

    return text


def zsh_action(action):
    if wants_file(action):
        return "_files"

    if dynamic_command(action):
        return f'{{compadd -- ${{(f)"$({dynamic_command(action)})"}}}}'

    if action.choices:
        return f"({choice_words(action)})"

    return ""


def zsh_specs(command_parser):
    specs = [f"{position}:{action.dest}:{zsh_action(action)}"
             for position, action in enumerate(positionals(command_parser), start=1)]

    for option in options(command_parser):
        description = f"[{zsh_escape(option.help)}]" if option.help else ""
        value = f":{option.dest}:{zsh_action(option)}" if takes_value(option) else ""
        specs.append(f"{long_flag(option)}{description}{value}")

    return specs


def zsh_script(root):
    subcommands = visible_subcommands(root)
    described = "\n".join(f"    {shlex.quote(name + ':' + zsh_escape(help_text))}"
                          for name, help_text, _ in subcommands)
    cases = "\n".join(f"    ({name}) _arguments {' '.join(shlex.quote(spec) for spec in zsh_specs(command_parser))} ;;"
                      for name, _, command_parser in subcommands if zsh_specs(command_parser))

    return f"""#compdef rep

_rep() {{
  local -a commands
  commands=(
{described}
  )

  if (( CURRENT == 2 )); then
    _describe command commands
    return
  fi

  shift words
  (( CURRENT-- ))

  case $words[1] in
{cases}
  esac
}}

if [[ $zsh_eval_context[-1] == loadautofunc ]]; then
  _rep "$@"
else
  compdef _rep rep
fi
"""


def bash_compgen(words, with_files):
    file_flag = "-f " if with_files else ""
    word_flag = f"-W {shlex.quote(words)} " if words else ""

    return f'COMPREPLY=($(compgen {file_flag}{word_flag}-- "$current"))'


def bash_script(root):
    subcommands = visible_subcommands(root)
    names = " ".join(name for name, _, _ in subcommands)
    value_cases = []
    word_cases = []

    for name, _, command_parser in subcommands:
        for option in options(command_parser):

            if takes_value(option):
                compgen = bash_compgen(choice_words(option), wants_file(option))
                value_cases.append(f"    {name}:{long_flag(option)}) {compgen}; return ;;")

        arguments = positionals(command_parser)
        words = " ".join([bash_words(action) for action in arguments] + [long_flag(option) for option in options(command_parser)]).strip()
        with_files = any(wants_file(action) for action in arguments)

        if words or with_files:
            word_cases.append(f"    {name}) {bash_compgen(words, with_files)} ;;")

    value_block = "\n".join(value_cases)
    word_block = "\n".join(word_cases)

    return f"""_rep() {{
  local current=${{COMP_WORDS[COMP_CWORD]}} previous=${{COMP_WORDS[COMP_CWORD-1]}}

  if (( COMP_CWORD == 1 )); then
    {bash_compgen(names, False)}
    return
  fi

  case ${{COMP_WORDS[1]}}:$previous in
{value_block}
  esac

  case ${{COMP_WORDS[1]}} in
{word_block}
  esac
}}

complete -F _rep rep
"""


def fish_script(root):
    lines = ["complete -c rep -f"]

    for name, help_text, command_parser in visible_subcommands(root):
        lines.append(f"complete -c rep -n __fish_use_subcommand -a {name} -d {shlex.quote(help_text)}")
        condition = shlex.quote(f"__fish_seen_subcommand_from {name}")

        for action in positionals(command_parser):

            if wants_file(action):
                lines.append(f"complete -c rep -n {condition} -F")
            elif dynamic_command(action):
                lines.append(f"complete -c rep -n {condition} -a {shlex.quote('(' + dynamic_command(action) + ')')}")
            elif action.choices:
                lines.append(f"complete -c rep -n {condition} -a {shlex.quote(choice_words(action))}")

        for option in options(command_parser):
            line = f"complete -c rep -n {condition} -l {long_flag(option).lstrip('-')}"

            if option.help:
                line += f" -d {shlex.quote(option.help)}"

            if takes_value(option):
                line += " -r -F" if wants_file(option) else f" -x -a {shlex.quote(choice_words(option))}"

            lines.append(line)

    return "\n".join(lines) + "\n"


SCRIPTS = {SHELL_ZSH: zsh_script, SHELL_BASH: bash_script, SHELL_FISH: fish_script}


def completion_script(root, shell):
    return SCRIPTS[shell](root)
