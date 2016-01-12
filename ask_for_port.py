import os
import sys
import serial
from serial.tools.list_ports import comports

# code comes from PySerial example
# https://github.com/pyserial/pyserial/blob/master/serial/tools/miniterm.py

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def ask_for_port():
    """\
    Show a list of ports and ask the user for a choice. To make selection
    easier on systems with long device names, also allow the input of an
    index.
    """

    try:
        raw_input
    except NameError:
        raw_input = input   # in python3 it's "raw"
        unichr = chr

    sys.stderr.write('\n--- Available ports:\n')
    ports = []
    for n, (port, desc, hwid) in enumerate(sorted(comports()), 1):
        #~ sys.stderr.write('--- %-20s %s [%s]\n' % (port, desc, hwid))
        sys.stderr.write('--- {:2}: {:20} {}\n'.format(n, port, desc))
        ports.append(port)
    while True:
        port = raw_input('--- Enter port index or full name [1]: ') or 1
        try:
            index = int(port) - 1
            if not 0 <= index < len(ports):
                sys.stderr.write('--- Invalid index!\n')
                continue
        except ValueError:
            pass
        else:
            port = ports[index]
        return port
