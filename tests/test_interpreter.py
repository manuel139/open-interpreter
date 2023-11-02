import os
import time
from random import randint
import re
import pytest

import interpreter
from interpreter.utils.count_tokens import count_messages_tokens, count_tokens

interpreter.auto_run = True
interpreter.model = "gpt-4"
interpreter.temperature = 0


# this function will run before each test
# we're clearing out the messages Array so we can start fresh and reduce token usage
def setup_function():
    interpreter.reset()
    interpreter.temperature = 0
    interpreter.auto_run = True
    interpreter.model = "gpt-4"
    interpreter.debug_mode = False


# this function will run after each test
# we're introducing some sleep to help avoid timeout issues with the OpenAI API
def teardown_function():
    time.sleep(5)


def test_config_loading():
    # because our test is running from the root directory, we need to do some
    # path manipulation to get the actual path to the config file or our config
    # loader will try to load from the wrong directory and fail
    currentPath = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(currentPath, "./config.test.yaml")

    interpreter.extend_config(config_path=config_path)

    # check the settings we configured in our config.test.yaml file
    temperature_ok = interpreter.temperature == 0.25
    model_ok = interpreter.model == "gpt-3.5-turbo"
    debug_mode_ok = interpreter.debug_mode == True

    assert temperature_ok and model_ok and debug_mode_ok


def test_system_message_appending():
    ping_system_message = (
        "Respond to a `ping` with a `pong`. No code. No explanations. Just `pong`."
    )

    ping_request = "ping"
    pong_response = "pong"

    interpreter.system_message += ping_system_message

    messages = interpreter.chat(ping_request)

    assert messages == [
        {"role": "user", "message": ping_request},
        {"role": "assistant", "message": pong_response},
    ]


def test_reset():
    # make sure that interpreter.reset() clears out the messages Array
    assert interpreter.messages == []


def test_token_counter():
    system_tokens = count_tokens(
        text=interpreter.system_message, model=interpreter.model
    )

    prompt = "How many tokens is this?"

    prompt_tokens = count_tokens(text=prompt, model=interpreter.model)

    messages = [
        {"role": "system", "message": interpreter.system_message}
    ] + interpreter.messages

    system_token_test = count_messages_tokens(
        messages=messages, model=interpreter.model
    )

    system_tokens_ok = system_tokens == system_token_test[0]

    messages.append({"role": "user", "message": prompt})

    prompt_token_test = count_messages_tokens(
        messages=messages, model=interpreter.model
    )

    prompt_tokens_ok = system_tokens + prompt_tokens == prompt_token_test[0]

    assert system_tokens_ok and prompt_tokens_ok


def test_hello_world():
    hello_world_response = "Hello, World!"

    hello_world_message = f"Please reply with just the words {hello_world_response} and nothing else. Do not run code. No confirmation just the text."

    messages = interpreter.chat(hello_world_message)

    assert messages == [
        {"role": "user", "message": hello_world_message},
        {"role": "assistant", "message": hello_world_response},
    ]


@pytest.mark.skip(reason="Math is hard")
def test_math():
    # we'll generate random integers between this min and max in our math tests
    min_number = randint(1, 99)
    max_number = randint(1001, 9999)

    n1 = randint(min_number, max_number)
    n2 = randint(min_number, max_number)

    test_result = n1 + n2 * (n1 - n2) / (n2 + n1)

    order_of_operations_message = f"""
    Please perform the calculation `{n1} + {n2} * ({n1} - {n2}) / ({n2} + {n1})` then reply with just the answer, nothing else. No confirmation. No explanation. No words. Do not use commas. Do not show your work. Just return the result of the calculation. Do not introduce the results with a phrase like \"The result of the calculation is...\" or \"The answer is...\"
    
    Round to 2 decimal places.
    """.strip()

    messages = interpreter.chat(order_of_operations_message)

    assert str(round(test_result, 2)) in messages[-1]["message"]


def test_delayed_exec():
    interpreter.chat(
        """Can you write a single block of code and execute it that prints something, then delays 1 second, then prints something else? No talk just code. Thanks!"""
    )


@pytest.mark.skip(
    reason="This works fine when I run it but fails frequently in Github Actions... will look into it after the hackathon"
)
def test_nested_loops_and_multiple_newlines():
    interpreter.chat(
        """Can you write a nested for loop in python and shell and run them? Don't forget to properly format your shell script and use semicolons where necessary. Also put 1-3 newlines between each line in the code. Only generate and execute the code. No explanations. Thanks!"""
    )

@pytest.mark.skip(
    reason="Skipping until can verify it runs on the Github build server"
)
@pytest.mark.parametrize("expected_integers", [
    0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144,
    233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711,
    28657, 46368, 75025, 121393, 196418, 317811, 514229
])
def test_powershell_gen_exec(expected_integers):
    TASK_RESULT_PREFIX = "TaskResult:"
    num_fibs = str(len(expected_integers))  # Convert to string

    result = interpreter.chat(
        f"""Write a Powershell script to generate the first {num_fibs} Fibonacci numbers.
        Approach this task methodically by planning and implementing it one step at a time.
        Only generate and execute code - ie. do not explain, ask questions, seek assistance or offer unsolicited information.
        Make sure to always execute the Powershell code and provide the output in the following format: {TASK_RESULT_PREFIX} x0, x1, x2,...x(n)"""
    )

    is_valid = lambda d: d.get('role') == 'assistant' and d.get('message', '').startswith(TASK_RESULT_PREFIX)
    valid_result = next(filter(is_valid, result), None)
    
    if valid_result is not None:
        message = valid_result.get('message', '')
        pattern = r'{}\s*([\d\s,]+)'.format(re.escape(TASK_RESULT_PREFIX))  # Use re.escape() to handle any special characters
        match = re.search(pattern, message)
        if match:
            integer_series = match.group(1)
            extracted_integers = [int(num.strip()) for num in integer_series.split(',')]
            
            assert extracted_integers == expected_integers, "Extracted integers do not match expected integers."
            
            print(f"Extracted message for {num_fibs} Fibonacci numbers:", message)
    else:
        print(f"No valid message found in the list of results for {num_fibs} Fibonacci numbers.")

def test_markdown():
    interpreter.chat(
        """Hi, can you test out a bunch of markdown features? Try writing a fenced code block, a table, headers, everything. DO NOT write the markdown inside a markdown code block, just write it raw."""
    )
