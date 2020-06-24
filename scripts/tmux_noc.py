#!/usr/bin/python3
import subprocess
import time
import argparse
import json
import datetime
from pathlib import Path
import os
from errno import EEXIST
import sys
import re


class ANSIColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def create_dir(filename):
    """
    Creates path for file, if directories doesn't exists.
    """
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != EEXIST:
                raise


def record_history(output_file_name, pane_id='*', pipe='o', only_once=False):
    for _ in pipe:
        output_b = subprocess.run([
            'tmux',
            'capture-pane',
            '-J',
            '-p',
            '-S',
            '-20000',
            '-t',
            pane_id,
        ], stdout=subprocess.PIPE).stdout
        output = output_b.decode('UTF-8')
        if output == '':
            continue
        with open(output_file_name, 'w') as f:
            f.write(output)
        if only_once:
            break
        time.sleep(1)


def pane_log(connection_type, host):
    home = str(Path.home())
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d__%H_%M_%S")
    log_filename = f'{home}/tmuxNOC/local/log/{timestamp}---{connection_type}_{host}.log'
    create_dir(log_filename)

    subprocess.run([
        'tmux',
        'pipe-pane',
        '-o',
        f'{home}/tmuxNOC/scripts/tmux_noc.py record_history --file_name {log_filename}\
          --pane_id #{{pane_id}} -i -'
    ])


def load_sessions():
    home = str(Path.home())
    with open(f'{home}/tmuxNOC/sessions.json', 'r') as f:
        sessions = json.load(f)
    return sessions


def save_session(connection_type, host):
    home = str(Path.home())
    sessions = load_sessions()
    session = {
        'connection_type': connection_type,
        'host': host,
        'time': datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    }
    sessions[time.time()] = session
    if connection_type == 'telnet':
        sessions['last_telnet_session'] = host
    with open(f'{home}/tmuxNOC/sessions.json', 'w') as f:
        json.dump(sessions, f)


def setup_telnet():
    home = str(Path.home())
    sessions = load_sessions()
    if 'last_telnet_session' in sessions:
        hostname = sessions['last_telnet_session']
    else:
        hostname = 'hostname'
    command = [
        'tmux',
        'command-prompt',
        '-p',
        'telnet:',
        '-I',
        hostname,
        f'run "{home}/tmuxNOC/scripts/tmux_noc.py connect_telnet --host %1"'
    ]
    subprocess.run(command)


def connect_telnet(host):
    home = str(Path.home())
    subprocess.run(
        [
            'tmux',
            'new-window',
            '-n', host,
            f'PROMPT_COMMAND="{home}/tmuxNOC/scripts/kbdfix.sh telnet {host}";TERM=vt100-w bash \
              --rcfile {home}/tmuxNOC/misc/tmux_noc_bashrc'
        ]
    )
    pane_log('t', host)
    save_session('telnet', host)


def tmux_send(string, conformation_symbol='Enter', target_pane='*'):
    subprocess.run(
        ['tmux', 'send-keys', '-t', target_pane, string, f'{conformation_symbol}'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def tmux_wait_for(string, timeout=3):
    found = False
    for _ in range(timeout*10):
        screen_content_b = subprocess.run([
            'tmux',
            'capture-pane',
            '-J',
            '-p'
        ], stdout=subprocess.PIPE).stdout
        screen_content_list = screen_content_b.decode('UTF-8').split('\n')
        screen_content_list_filtered = [line for line in screen_content_list if len(line) != 0]
        for line in screen_content_list_filtered[-2:]:
            if string in line:
                found = True
                break
        if found:
            break
        else:
            time.sleep(0.1)

    return found


def send_login_pwd(login_number):
    home = str(Path.home())
    with open(f'{home}/tmuxNOC/.logins', 'r') as f:
        logins = f.readlines()
    for line in logins:
        if f'LOGIN{login_number}' in line:
            login = line.replace(f'LOGIN{login_number}=', '').replace('\n', '')
        if f'PASS{login_number}' in line:
            password = line.replace(f'PASS{login_number}=', '').replace('\n', '')
    tmux_send(login)
    if tmux_wait_for('assword'):
        tmux_send(password)
    else:
        subprocess.run(['tmux', 'display-message', 'Password prompt not found.'])


def send_with_delay(pane_id):
    print(f'{ANSIColors.WARNING}What to send? To end list enter a single dot{ANSIColors.ENDC}\n.')
    commands, s = [], ''
    while s != '.':
        s = input()
        if s != '.':
            commands.append(s)
    while True:
        try:
            line_delay = input(
                f'{ANSIColors.WARNING}Enter LINE delay in milliseconds [500]: {ANSIColors.ENDC}'
            ) or 500
            line_delay = int(line_delay)
        except ValueError:
            print(f'{ANSIColors.FAIL}Enter an integer.{ANSIColors.ENDC}')
            continue
        if line_delay < 0:
            print(f'{ANSIColors.FAIL}Enter a positive integer or 0.{ANSIColors.ENDC}')
            continue
        else:
            break
    while True:
        try:
            character_delay = input(
                f'{ANSIColors.WARNING}Enter CHARACTER delay in milliseconds [0]: {ANSIColors.ENDC}'
            ) or 0
            character_delay = int(character_delay)
        except ValueError:
            print(f'{ANSIColors.FAIL}Enter an integer.{ANSIColors.ENDC}')
            continue
        if character_delay < 0:
            print(f'{ANSIColors.FAIL}Enter a positive integer or 0.{ANSIColors.ENDC}')
            continue
        else:
            break

    rows, columns = subprocess.check_output(['stty', 'size']).decode().split()
    rows = int(rows) - 2
    rows_offset = 0
    for index, command in enumerate(commands):
        subprocess.call('clear', shell=True)
        if len(commands) > rows:
            if index > 5:
                rows_offset = index - 5
        print('\n'.join(commands[rows_offset:index]))
        print(f'{ANSIColors.OKGREEN}{ANSIColors.BOLD}{command}{ANSIColors.ENDC}')
        print('\n'.join(commands[index + 1:rows + rows_offset]))

        if character_delay > 0:
            characters = list(command)
            for character in characters:
                tmux_send(character, '', pane_id)
                time.sleep(character_delay / 1000)
            tmux_send('', 'Enter', pane_id)
        else:
            tmux_send(command, target_pane=pane_id)
        if not index + 1 == len(commands):
            time.sleep(line_delay / 1000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Connect to telnet or ssh from tmux.')
    parser.add_argument('type', choices=[
        'login',
        'send_with_delay',
        'setup_telnet',
        'connect_telnet',
        'toggle_log',
        'record_history',
    ])
    parser.add_argument('--login_number', nargs='?')
    parser.add_argument('--host', nargs='?')
    parser.add_argument('--pane_id', nargs='?')
    parser.add_argument('--file_name', nargs='?')
    parser.add_argument(
        '-i',
        '--input',
        type=argparse.FileType('r'),
        default=(None if sys.stdin.isatty() else sys.stdin)
    )
    args = parser.parse_args()

    if args.type == 'login':
        send_login_pwd(args.login_number)
    elif args.type == 'send_with_delay':
        send_with_delay(args.pane_id)
    elif args.type == 'setup_telnet':
        setup_telnet()
    elif args.type == 'connect_telnet':
        connect_telnet(args.host)
    elif args.type == 'toggle_log':
        pane_log('l', 'local')
    elif args.type == 'record_history':
        record_history(args.file_name, args.pane_id, args.input)
