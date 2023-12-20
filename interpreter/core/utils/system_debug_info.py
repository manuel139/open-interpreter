import platform
import subprocess

import pkg_resources
import psutil


def get_python_version():
    return platform.python_version()


def get_pip_version():
    try:
        pip_version = subprocess.check_output(["pip", "--version"]).decode().split()[1]
    except Exception as e:
        pip_version = str(e)
    return pip_version


def get_oi_version():
    try:
        oi_version_cmd = (
            subprocess.check_output(["interpreter", "--version"]).decode().split()[1]
        )
    except Exception as e:
        oi_version_cmd = str(e)
    oi_version_pkg = pkg_resources.get_distribution("open-interpreter").version
    oi_version = oi_version_cmd, oi_version_pkg
    return oi_version


def get_os_version():
    return platform.platform()


def get_cpu_info():
    return platform.processor()


def get_ram_info():
    vm = psutil.virtual_memory()
    used_ram_gb = vm.used / (1024**3)
    free_ram_gb = vm.free / (1024**3)
    total_ram_gb = vm.total / (1024**3)
    return f"{total_ram_gb:.2f} GB, used: {used_ram_gb:.2f}, free: {free_ram_gb:.2f}"


def interpreter_info(interpreter):
    try:
        if interpreter.offline and interpreter.llm.api_base:
            try:
                curl = subprocess.check_output(f"curl {interpreter.llm.api_base}")
            except Exception as e:
                curl = str(e)
        else:
            curl = "Not local"

        messages_to_display = []
        for message in interpreter.messages:
            message = message.copy()
            try:
                if len(message["content"] > 600):
                    message["content"] = (
                        message["content"][:300] + "..." + message["content"][-300:]
                    )
            except Exception as e:
                print(str(e), "for message:", message)
            messages_to_display.append(message)

        return f"""

        # Interpreter Info
        
        Vision: {interpreter.llm.supports_vision}
        Model: {interpreter.llm.model}
        Function calling: {interpreter.llm.supports_functions}
        Context window: {interpreter.llm.context_window}
        Max tokens: {interpreter.llm.max_tokens}

        Auto run: {interpreter.auto_run}
        API base: {interpreter.llm.api_base}
        Offline: {interpreter.offline}

        Curl output: {curl}

        # Messages

        System Message: {interpreter.system_message}

        """ + "\n\n".join(
            [str(m) for m in messages_to_display]
        )
    except:
        return "Error, couldn't get interpreter info"


def system_info(interpreter):
    oi_version = get_oi_version()
    print(
        f"""
        Python Version: {get_python_version()}
        Pip Version: {get_pip_version()}
        Open-interpreter Version: cmd:{oi_version[0]}, pkg: {oi_version[1]}
        OS Version and Architecture: {get_os_version()}
        CPU Info: {get_cpu_info()}
        RAM Info: {get_ram_info()}
        {interpreter_info(interpreter)}
    """
    )
