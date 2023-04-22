from subprocess import Popen, PIPE
from shlex      import split as shsplit

import output_utils as output


STD_CODES = {
    "stdout" : 4,
    "stderr" : 2,
    "stdin"  : 1
}


def execute(command: str, pipe_mode: int=2):
    std = {
        "stdout" : None,
        "stderr" : None,
        "stdin"  : None
    }

    for std_code in STD_CODES:
        if pipe_mode - STD_CODES[std_code] >= 0:
            std[std_code] = PIPE
            pipe_mode -= STD_CODES[std_code]

    process = Popen(shsplit(command), stdout=std["stdout"],
                                      stderr=std["stderr"],
                                      stdin =std["stdin"])
    
    # If there are any errors, print them and exit with a non-zero return code
    if std["stderr"] and (errors := process.stderr.readlines()):
        for eline in errors:
            output.error(f":: {eline.decode()}", end="")

    return process


