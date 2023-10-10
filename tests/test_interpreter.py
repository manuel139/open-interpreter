from random import randint
import interpreter
from interpreter.utils.count_tokens import count_tokens, count_messages_tokens
import time

interpreter.auto_run = True
interpreter.model = "gpt-4"
interpreter.temperature = 0


# this function will run before each test
# we're clearing out the messages Array so we can start fresh and reduce token usage
def setup_function():
    interpreter.reset()


# this function will run after each test
# we're introducing some sleep to help avoid timeout issues with the OpenAI API
def teardown_function():
    time.sleep(5)


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
    system_tokens = count_tokens(text=interpreter.system_message, model=interpreter.model)
    
    prompt = "How many tokens is this?"

    prompt_tokens = count_tokens(text=prompt, model=interpreter.model)

    messages = [{"role": "system", "message": interpreter.system_message}] + interpreter.messages

    system_token_test = count_messages_tokens(messages=messages, model=interpreter.model)

    system_tokens_ok = system_tokens == system_token_test[0]

    messages.append({"role": "user", "message": prompt})

    prompt_token_test = count_messages_tokens(messages=messages, model=interpreter.model)

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

"""
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

    print(messages)

    assert str(round(test_result, 2)) in messages[-1]["message"]
"""


def test_delayed_exec():
    interpreter.chat(
        """Can you write a single block of code and run_code it that prints something, then delays 1 second, then prints something else? No talk just code. Thanks!"""
    )


def test_nested_loops_and_multiple_newlines():
    interpreter.chat(
        """Can you write a nested for loop in python and shell and run them? Don't forget to properly format your shell script and use semicolons where necessary. Also put 1-3 newlines between each line in the code. Only generate and execute the code. No explanations. Thanks!"""
    )


def test_markdown():
    interpreter.chat(
        """Hi, can you test out a bunch of markdown features? Try writing a fenced code block, a table, headers, everything. DO NOT write the markdown inside a markdown code block, just write it raw."""
    )
