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


class lPaths:
    """
    Local paths.
    """
    home = str(Path.home())
    tmuxNOC = f'{home}/tmuxNOC'
    log_dir = f'{tmuxNOC}/local/log'


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


def get_split_command(split_direction):
    if split_direction == 'vertical':
        return ['split-window', '-v']
    elif split_direction == 'horizontal':
        return ['split-window', '-h']
    else:
        return ['new-window']


def save_pane_history(output_file_name, pane_id='*', pipe='o', only_once=False):
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
    sessions_metadata = load_sessions_metadata()
    if connection_type == 'l':
        last_session_index = '--'
    else:
        last_session_index = sessions_metadata['last_session_index']
    year = datetime.datetime.now().strftime("%Y")
    month = datetime.datetime.now().strftime("%m")
    day = datetime.datetime.now().strftime("%d")
    current_time = datetime.datetime.now().strftime("%H_%M_%S")
    log_filename = f'{home}/tmuxNOC/local/log/{year}/{month}/{day}/{current_time}---!{last_session_index}_{connection_type}_{host}.log'
    create_dir(log_filename)

    subprocess.run([
        'tmux',
        'pipe-pane',
        '-o',
        f'{home}/tmuxNOC/scripts/tmux_noc.py save_pane_history --file_name "{log_filename}"\
          --pane_id #{{pane_id}} -i -'
    ])


def search_logs():
    home = str(Path.home())
    rename_window()
    query = input(f'{ANSIColors.WARNING}grep in logs:{ANSIColors.ENDC} ')
    if not query.isspace() and query != "":
        subprocess.run(
            ['grep', '--color=always', '-n', '-r', query, '.'],
            cwd=f'{home}/tmuxNOC/local/log/'
        )
    else:
        print(f'{ANSIColors.FAIL}Empty query.{ANSIColors.ENDC}')
    search_logs()


def open_log(history_index, split_direction):
    log_file = None
    for path in Path(lPaths.log_dir).rglob(f'*{history_index}*'):
        log_file = str(path)
    if log_file is None:
        subprocess.run(
            ['tmux', 'display-message', f'Log file with index {history_index} not found.']
        )
    else:
        host = log_file.split('_')[-1].replace('.log', '')
        log_file_short = log_file.replace(lPaths.log_dir + '/', '')
        subprocess.run(['tmux'] + get_split_command(split_direction) + [f'less -m "{log_file}"'])
        subprocess.run(['tmux', 'select-pane', '-T', f'Log:{log_file_short}'])
        rename_window()


def load_sessions_metadata():
    home = str(Path.home())
    with open(f'{home}/tmuxNOC/sessions.json', 'r') as f:
        sessions = json.load(f)
    return sessions


def save_session(connection_type, host):
    home = str(Path.home())
    sessions_metadata = load_sessions_metadata()
    if 'last_session_index' in sessions_metadata:
        sessions_metadata['last_session_index'] += 1
    else:
        sessions_metadata['last_session_index'] = 1
    if 'last_five_sessions' in sessions_metadata:
        last_five_sessions = sessions_metadata['last_five_sessions']
        if host not in str(last_five_sessions):
            if len(last_five_sessions) >= 5:
                last_five_sessions.pop(4)
            last_five_sessions.insert(0, {
                'connection_type': connection_type,
                'host': host
            })
        else:
            last_connection = None
            for index, session in enumerate(last_five_sessions):
                if connection_type == session['connection_type'] and host == session['host']:
                    last_connection = index
            if last_connection is None:
                if len(last_five_sessions) >= 5:
                    last_five_sessions.pop(4)
                last_five_sessions.insert(0, {
                    'connection_type': connection_type,
                    'host': host
                })
            else:
                last_five_sessions.pop(last_connection)
                last_five_sessions.insert(0, {
                    'connection_type': connection_type,
                    'host': host
                })

    else:
        last_five_sessions = [{
            'connection_type': connection_type,
            'host': host
        }]
    sessions_metadata['last_five_sessions'] = last_five_sessions
    sessions_metadata[f'last_{connection_type}_session'] = host
    with open(f'{home}/tmuxNOC/sessions.json', 'w') as f:
        json.dump(sessions_metadata, f)

    sessions_history_filename = f'{home}/tmuxNOC/local/sessions_history.log'
    with open(sessions_history_filename, 'r+') as sessions_history_file:
        sessions_history = sessions_history_file.read()
        current_date = datetime.datetime.now().strftime("%d.%m.%Y")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        if f'# {current_date}' not in sessions_history:
            sessions_history_file.write(f'# {current_date}\n')
        sessions_history_file.write(
            f'    {sessions_metadata["last_session_index"]} {current_date} {current_time} {connection_type} {host}\n'
        )


def ssh_config_hosts():
    home = str(Path.home())
    if not os.path.exists(f'{home}/.ssh/config'):
        return 1

    with open(f'{home}/.ssh/config') as f:
        ssh_config = f.readlines()
    hosts = []
    for line in ssh_config:
        if line.startswith('Host'):
            hosts.append(line.replace('Host ', '').replace('\n', ''))
    return hosts


def short_word(word):
    terminal_width = int(subprocess.check_output([
        'tmux',
        'display-message',
        '-p',
        '#{window_width}'
    ]).decode('utf-8'))

    if len(word) > 53:
        word_short = word[:50] + '...'
    else:
        word_short = word
    if len(word_short) >= terminal_width:
        word_short = word_short[:terminal_width - 20] + '...'

    return word_short


def ssh_menu(split_direction):
    home = str(Path.home())
    command = [
        'tmux', 'display-menu',
        '-T', '#[align=centre]SSH Config Hosts',
        '-x', 'P',
        '-y', 'S',
    ]
    ssh_hosts_list = ssh_config_hosts()
    if ssh_hosts_list != 1:
        for index, host in enumerate(ssh_hosts_list):
            index += 1
            if index == 10:
                index = 0
            elif 20 > index > 10:
                index = f'M-{index - 10}'
            elif index == 20:
                index = 'M-0'
            elif 30 > index > 20:
                index = f'C-{index - 20}'
            elif index == 30:
                index = 'C-0'
            command += [
                short_word(host),
                str(index),
                (f'run "{home}/tmuxNOC/scripts/tmux_noc.py connect_ssh --host \'{host}\' '
                 f'--split_direction {split_direction}"'),
            ]
    subprocess.run(command)


def clipboard_menu(split_direction):
    home = str(Path.home())
    clipboard_first_line = subprocess.run(
        f'{home}/tmuxNOC/scripts/paste.sh', stdout=subprocess.PIPE
    ).stdout.decode('UTF-8').split('\n')[0]
    clipboard_first_word = [word for word in clipboard_first_line.split(' ') if len(word) != 0]
    if len(clipboard_first_word) != 0:
        clipboard_first_word = clipboard_first_word[0]
        clipboard_first_word_short = short_word(clipboard_first_word)
        subprocess.run([
            'tmux', 'display-menu',
            '-T', '#[align=centre]Clipboard',
            '-x', 'P',
            '-y', 'S',
            f'telnet {clipboard_first_word_short}', 'v',
            (f'run "{home}/tmuxNOC/scripts/tmux_noc.py connect_telnet '
             f'--host \'{clipboard_first_word}\' --split_direction {split_direction}"'),

            f'ssh {clipboard_first_word_short}', 'V',
            (f'run "{home}/tmuxNOC/scripts/tmux_noc.py connect_ssh '
             f'--host \'{clipboard_first_word}\' --split_direction {split_direction}"'),
        ])
    else:
        subprocess.run({
            'tmux', 'display-message',
            'No content in clipboard.'
        })


def noc_menu(split_direction='new'):
    home = str(Path.home())
    script_path = f'{home}/tmuxNOC/scripts/tmux_noc.py'

    if ssh_config_hosts() == 1:
        ssh_config_hosts_exists = False
    else:
        ssh_config_hosts_exists = True

    sessions_metadata = load_sessions_metadata()
    if 'last_five_sessions' in sessions_metadata:
        last_five_sessions = sessions_metadata['last_five_sessions']
        last_sessions_menu_block = ['']
        for index, session in enumerate(last_five_sessions):
            connection_type = session['connection_type']
            host = session['host']
            host_short = short_word(host)
            last_sessions_menu_block.append(f'{connection_type} {host_short}')
            last_sessions_menu_block.append(f'{index + 1}')
            last_sessions_menu_block.append(
                (f'run "{script_path} connect_{connection_type} '
                 f'--host \'{host}\' --split_direction {split_direction}"')
            )
    else:
        last_sessions_menu_block = None

    if split_direction == 'vertical':
        split_command = 'split-window -v'
        split_name = 'Vertical'
        split_variants = [
            'Split Horizontal', '|', f'run "{script_path} noc_menu --split_direction horizontal"',
            'Open in New Window', 'n', f'run "{script_path} noc_menu --split_direction new"',
            '',
        ]
    elif split_direction == 'horizontal':
        split_command = 'split-window -h'
        split_name = 'Horizontal'
        split_variants = [
            'Split Vertical', '_', f'run "{script_path} noc_menu --split_direction vertical"',
            'Open in New Window', 'n', f'run "{script_path} noc_menu --split_direction new"',
            '',
        ]
    else:
        split_command = 'new-window'
        split_name = 'New Window'
        split_variants = [
            'Split Vertical', '_', f'run "{script_path} noc_menu --split_direction vertical"',
            'Split Horizontal', '|', f'run "{script_path} noc_menu --split_direction horizontal"',
            '',
        ]

    command = [
        'tmux', 'display-menu',
        '-T', f'#[align=centre]NOC {split_name}',
        '-x', 'P',
        '-y', 'S',
    ] + split_variants + [
        # -----
        'Show Sessions History', 'h',
        (f'{split_command} "less +G $HOME/tmuxNOC/local/sessions_history.log"; '
         f'select-pane -T "Sessions History"; run "{script_path} rename_window"'),

        'Open Log File', 'l',
        (f'command-prompt -p "Open Log Number:" \'run "{script_path} open_log '
         f'--history_index %1 --split_direction {split_direction}"\''),

        'Search in Logs', 'L',
        f'{split_command} "{script_path} search_logs"; select-pane -T "grep in logs"',
        # -----
    ]
    if split_direction == 'new':
        command += [
            '',
            'Send Commands with Delay', 'd',
            (f'split-window -h "{script_path} send_with_delay '
             f'--pane_id $(tmux display -pt - \'#{{pane_id}}\')"'),
        ]
    command += [
        # -----
        '',
        'Connect from Clipboard', 'v',
        f'run "{script_path} clipboard_menu --split_direction {split_direction}"',

        'New Telnet', 'q',
        (f'run "{script_path} setup_connection --connection_type telnet '
         f'--split_direction {split_direction}"'),

        'New SSH', 's',
        (f'run "{script_path} setup_connection --connection_type ssh '
         f'--split_direction {split_direction}"'),
    ]
    if ssh_config_hosts_exists:
        command += [
            'SSH Config Hosts', 'S',
            f'run "{script_path} ssh_menu --split_direction {split_direction}"',
        ]
    if last_sessions_menu_block is not None:
        command += last_sessions_menu_block
    subprocess.run(command)


def setup_connection(connection_type, split_direction):
    home = str(Path.home())
    sessions_metadata = load_sessions_metadata()
    if f'last_{connection_type}_session' in sessions_metadata:
        hostname = sessions_metadata[f'last_{connection_type}_session']
    else:
        hostname = 'hostname'
    command = [
        'tmux',
        'command-prompt',
        '-p',
        f'{connection_type}:',
        '-I',
        hostname,
        (f'run "{home}/tmuxNOC/scripts/tmux_noc.py connect_{connection_type} --host \'%1\' '
         f'--split_direction {split_direction}"'),
    ]
    subprocess.run(command)


def connect_telnet(host, split_direction):
    home = str(Path.home())
    if split_direction == 'vertical':
        split_command = ['tmux', 'split-window', '-v']
    elif split_direction == 'horizontal':
        split_command = ['tmux', 'split-window', '-h']
    else:
        split_command = ['tmux', 'new-window']
    subprocess.run(
        split_command + [
            f'PROMPT_COMMAND="{home}/tmuxNOC/scripts/kbdfix.sh telnet {host}";TERM=vt100-w bash \
              --rcfile {home}/tmuxNOC/misc/tmux_noc_bashrc'
        ]
    )
    subprocess.run(['tmux', 'select-pane', '-T', f't/{host}'])
    rename_window()
    save_session('telnet', host)
    pane_log('t', host)

def connect_ssh(host, split_direction):
    home = str(Path.home())
    if split_direction == 'vertical':
        split_command = ['tmux', 'split-window', '-v']
    elif split_direction == 'horizontal':
        split_command = ['tmux', 'split-window', '-h']
    else:
        split_command = ['tmux', 'new-window']
    subprocess.run(
        split_command + [
            f'PROMPT_COMMAND="ssh {host}" bash --rcfile {home}/tmuxNOC/misc/tmux_noc_bashrc'
        ]
    )
    subprocess.run(['tmux', 'select-pane', '-T', f's/{host}'])
    rename_window()
    save_session('ssh', host)
    pane_log('s', host)


def rename_window():
    panes_list = subprocess.check_output(
        ['tmux', 'list-panes', '-F', '#{pane_title}']
    ).decode('utf-8').split('\n')[:-1]
    rename = False
    window_title = []
    for pane_title in panes_list:
        if pane_title == '':
            window_title.append('local')
        else:
            rename = True
            window_title.append(pane_title)
    if rename:
        subprocess.run(['tmux', 'rename-window', '\u2503'.join(window_title)])
    else:
        subprocess.run(['tmux', 'set', '-w', 'automatic-rename'])



def tmux_send(string, conformation_symbol='Enter', target_pane=':'):
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
    subprocess.run(['tmux', 'select-pane', '-T', 'Send with delay'])
    rename_window()
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
        'noc_menu',
        'ssh_menu',
        'clipboard_menu',
        'setup_connection',
        'connect_telnet',
        'connect_ssh',
        'toggle_log',
        'save_pane_history',
        'search_logs',
        'open_log',
        'rename_window',
    ])
    parser.add_argument('--login_number', nargs='?')
    parser.add_argument('--host', nargs='?')
    parser.add_argument('--connection_type', nargs='?')
    parser.add_argument('--pane_id', nargs='?')
    parser.add_argument('--split_direction', nargs='?')
    parser.add_argument('--file_name', nargs='?')
    parser.add_argument(
        '-i',
        '--input',
        type=argparse.FileType('r'),
        default=(None if sys.stdin.isatty() else sys.stdin)
    )
    parser.add_argument('--history_index', nargs='?')
    args = parser.parse_args()

    if args.type == 'login':
        send_login_pwd(args.login_number)
    elif args.type == 'send_with_delay':
        send_with_delay(args.pane_id)
    elif args.type == 'noc_menu':
        noc_menu(args.split_direction)
    elif args.type == 'ssh_menu':
        ssh_menu(args.split_direction)
    elif args.type == 'clipboard_menu':
        clipboard_menu(args.split_direction)
    elif args.type == 'setup_connection':
        setup_connection(args.connection_type, args.split_direction)
    elif args.type == 'connect_telnet':
        connect_telnet(args.host, args.split_direction)
    elif args.type == 'connect_ssh':
        connect_ssh(args.host, args.split_direction)
    elif args.type == 'toggle_log':
        pane_log('l', 'local')
    elif args.type == 'save_pane_history':
        save_pane_history(args.file_name, args.pane_id, args.input)
    elif args.type == 'search_logs':
        search_logs()
    elif args.type == 'open_log':
        open_log(args.history_index, args.split_direction)
    elif args.type == 'rename_window':
        rename_window()
