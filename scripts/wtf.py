import time

start = time.time()
import os
import platform
import time

import pyperclip
from pynput.keyboard import Controller, Key
from yaspin import yaspin
from yaspin.spinners import Spinners

spinner = yaspin()
spinner.start()

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
import litellm

SYSTEM_MESSAGE = """
# Terminal History Analysis Prompt

You are a fast, efficient AI assistant specialized in analyzing terminal history and providing quick solutions. Your task is to:

1. Quickly scan the provided terminal history.
2. Identify the most recent error or issue.
3. Determine the most likely solution or debugging step.
4. Respond with a brief explanation followed by a markdown code block containing a shell command to address the issue.

Rules:
- Provide a single shell command in your code block, using line continuation characters (\\ for Unix-like systems, ^ for Windows) for multiline commands.
- Ensure the entire command is on one logical line, requiring the user to press enter only once to execute.
- If multiple steps are needed, explain the process briefly, then provide only the first command or a combined command using && or ;.
- Keep any explanatory text extremely brief and concise.
- Place explanatory text before the code block.
- NEVER USE COMMENTS IN YOUR CODE.
- Focus on the most recent error, ignoring earlier unrelated commands.
- Prioritize speed and conciseness in your response. Don't use markdown headings. Don't say more than a sentence or two. Be incredibly concise.
"""
'''
import textwrap
import shutil

def print_with_margins(text, margin=4):
    terminal_width = shutil.get_terminal_size().columns
    text_width = terminal_width - 2 * margin
    
    wrapper = textwrap.TextWrapper(width=text_width)
    lines = text.split('\n')
    for line in lines:
        wrapped_lines = wrapper.wrap(line)
        for wrapped_line in wrapped_lines:
            print(' ' * margin + wrapped_line + ' ' * margin)

# Example usage
print("")
text = """\nThis is an example of text that will be printed with margins on either side.
If the line is very long, it will be wrapped to fit within the specifieds very long, it will be wrapped to fit within the specifieds very long, it will be wrapped to fit within the specifieds very long, it will be wrapped to fit within the specifieds very long, it will be wrapped to fit within the specifieds very long, it will be wrapped to fit within the specified width based on the terminal size.\n"""
print_with_margins(text, margin=4)
print("")

'''


def main():
    keyboard = Controller()

    # Save clipboard
    clipboard = pyperclip.paste()

    # Select all text
    shortcut_key = Key.cmd if platform.system() == "Darwin" else Key.ctrl
    with keyboard.pressed(shortcut_key):
        keyboard.press("a")
        keyboard.release("a")

    # Copy selected text
    with keyboard.pressed(shortcut_key):
        keyboard.press("c")
        keyboard.release("c")

    # Deselect
    keyboard.press(Key.backspace)
    keyboard.release(Key.backspace)

    # Wait for the clipboard to update
    time.sleep(0.1)

    # Get terminal history from clipboard
    history = pyperclip.paste()

    # Reset clipboard to stored one
    pyperclip.copy(clipboard)

    # Trim history
    history = "..." + history[-3000:].strip()

    # Remove any trailing spinner commands
    spinner_commands = [
        "⠴",
        "⠦",
        "⠇",
        "⠉",
        "⠙",
        "⠸",
        "⠼",
        "⠤",
        "⠴",
        "⠂",
        "⠄",
        "⠈",
        "⠐",
        "⠠",
    ]
    for command in spinner_commands:
        if history.endswith(command):
            history = history[: -len(command)].strip()
            break

    commands_to_remove = ["poetry run wtf", "wtf"]
    for command in commands_to_remove:
        if history.endswith(command):
            history = history[: -len(command)].strip()
            break

    # Prepare messages for LLM
    messages = [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": history},
    ]

    # Process LLM response
    in_code = False
    backtick_count = 0
    language_buffer = ""

    start = None

    for chunk in litellm.completion(
        model="gpt-3.5-turbo", messages=messages, temperature=0, stream=True
    ):
        if not start:
            start = time.time()
            spinner.stop()

        content = chunk.choices[0].delta.content
        if content:
            for char in content:
                if char == "`":
                    backtick_count += 1
                    if backtick_count == 3:
                        in_code = not in_code
                        backtick_count = 0
                        language_buffer = ""
                        if not in_code:  # We've just exited a code block
                            return  # Exit after typing the command
                        else:  # Entered code block
                            print("Press `enter` to run: ", end="", flush=True)
                elif in_code:
                    if language_buffer is not None:
                        if char.isalnum():
                            language_buffer += char
                        elif char.isspace():
                            language_buffer = None
                    elif char not in ["\n", "\\"]:
                        keyboard.type(char)
                else:
                    if backtick_count:
                        print("`" * backtick_count, end="", flush=True)
                        backtick_count = 0

                    # if "\n" in char:
                    #     char.replace("\n", "\n    ")

                    print(char, end="", flush=True)

                    backtick_count = 0


if __name__ == "__main__":
    main()
