import os
import sys
import re
import socketserver
from io import BytesIO
import http.server
from http import HTTPStatus
import html
import urllib.parse
import argparse
from argparse import HelpFormatter, SUPPRESS, OPTIONAL, ZERO_OR_MORE
import threading

from exceptions import ThePotataCommonException, UploadHTTPRequestException
from utils import bold, get_ipv4_address
from cli import CLI

BANNER = r'''
                )          )       
             ( /(    )  ( /(    )  
 `  )    (   )\())( /(  )\())( /(  
 /(/(    )\ (_))/ )(_))(_))/ )(_)) 
((_)_\  ((_)| |_ ((_)_ | |_ ((_)_  
| '_ \)/ _ \|  _|/ _` ||  _|/ _` | 
| .__/ \___/ \__|\__,_| \__|\__,_| 
|_|                                                    
'''


# Formatter for argparse
class CustomHelpFormatter(HelpFormatter):

    def __init__(self, prog: str):
        super().__init__(prog, max_help_position=50)

    def _get_help_string(self, action):
        """
        Add the default value to the option help message.

        ArgumentDefaultsHelpFormatter and BooleanOptionalAction when it isn't
        already present. This code will do that, detecting cornercases to
        prevent duplicates or cases where it wouldn't make sense to the end
        user.
        """
        help = action.help
        if help is None:
            help = ''

        if '%(default)' not in help:
            if action.default is not SUPPRESS:
                defaulting_nargs = [OPTIONAL, ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help += ' (default: %(default)s)'
        return help

    def _format_action_invocation(self, action):
        if not action.option_strings:
            default = self._get_default_metavar_for_positional(action)
            metavar, = self._metavar_formatter(action, default)(1)
            return metavar

        else:
            parts = []

            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend(action.option_strings)

            # if the Optional takes a value, format is:
            #    -s, --long ARGS
            else:
                default = self._get_default_metavar_for_optional(action)
                args_string = self._format_args(action, default)
                if len(action.option_strings) == 1:
                    parts.append('%s %s' % (action.option_strings[0], args_string))
                else:
                    parts.append(f'{action.option_strings[0]}, {action.option_strings[1]} {args_string}')

            return ', '.join(parts)


class UploadHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.error_message_format = '%(code)s - %(explain)s.\n'
        super().__init__(request, client_address, server, directory=server.serve_dir)

    def list_directory(self, path):
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        r = []
        try:
            displaypath = urllib.parse.unquote(self.path, errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(self.path)

        displaypath = html.escape(displaypath, quote=False)
        enc = sys.getfilesystemencoding()
        title = f'Directory listing for {displaypath}'
        r.append(title)
        for name in list:
            linkname = name + "/" if os.path.isdir(os.path.join(path, name)) else name
            r.append(f'• {urllib.parse.quote(linkname, errors="surrogatepass")}')
        r.append('\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        f = BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=%s" % enc)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def handle_one_request(self):
        """Handle a single HTTP request.

        You normally don't need to override this method; see the class
        __doc__ string for information on how to handle specific HTTP
        commands such as GET and POST.

        """
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ''
                self.request_version = ''
                self.command = ''
                self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
                return
            if not self.raw_requestline:
                self.close_connection = True
                return
            if not self.parse_request():
                # An error code has been sent, just exit
                return
            mname = 'do_' + self.command
            if not hasattr(self, mname):
                self.send_error(
                    HTTPStatus.NOT_IMPLEMENTED,
                    "Unsupported method (%r)" % self.command)
                return

            # todo: rewrite
            _, _directory, *_path = self.path.split('/')
            # if not _directory:
            #     _directory = '/'
            if _directory in self.server.path_map:
                self.directory = self.server.path_map[_directory]
                self.path = os.path.join(*['/'] + _path)
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return None

            # No redirects
            if (not self.path.endswith('/')) and os.path.isdir(os.path.join(self.directory, self.path.strip('/'))):
                self.path += '/'

            method = getattr(self, mname)
            method()
            self.wfile.flush() # actually send the response if not already done.
        except TimeoutError as e:
            # a read or a write timed out. Discard this connection
            self.log_error("Request timed out: %r", e)
            self.close_connection = True
            return

    def do_POST(self):
        try:
            file_name = self.deal_post_data()
            print(f'{file_name} is successfully uploaded from {self.client_address[0]}')
            self.send_in_response('File is uploaded successfully\n')
        except UploadHTTPRequestException as err:
            print(err)
            self.send_in_response(f'Upload error: {err}\n')

    def send_in_response(self, msg):
        if isinstance(msg, str):
            msg = msg.encode()
        f = BytesIO()
        f.write(msg)
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    def save_file(self, file_name, file_content):
        file_path = os.path.join(self.server.save_dir, file_name)
        with open(file_path, 'wb') as f:
            f.write(file_content.getbuffer())
        return file_path

    def read_line(self, remain_bytes):
        line = self.rfile.readline()
        remain_bytes -= len(line)
        return line, remain_bytes

    def deal_post_data(self):
        content_type = self.headers['content-type']
        if not content_type:
            raise UploadHTTPRequestException("No Content-Type")

        line, remain_bytes = self.read_line(int(self.headers['content-length']))

        boundary = content_type.split("=")[1].encode()
        if boundary not in line:
            raise UploadHTTPRequestException("Content NOT begin with boundary")

        line, remain_bytes = self.read_line(remain_bytes)

        fn = re.findall(r'Content-Disposition.*name="file"; filename="(.*)"', line.decode())
        if not fn:
            raise UploadHTTPRequestException("Can't find out file name...")

        while line != b'\r\n':
            line, remain_bytes = self.read_line(remain_bytes)

        file_content = BytesIO()

        preline, remain_bytes = self.read_line(remain_bytes)
        while remain_bytes > 0:
            line, remain_bytes = self.read_line(remain_bytes)
            if boundary in line:
                preline = preline[0:-1]
                if preline.endswith(b'\r'):
                    preline = preline[0:-1]
                file_content.write(preline)
                file_name = self.save_file(fn[0], file_content)
                return file_name
            else:
                file_content.write(preline)
                preline = line
        raise UploadHTTPRequestException("Unexpect Ends of data.")


def main():
    parser = argparse.ArgumentParser(
        description=f"Simple web server to ease pentester's needs in uploading and downloading shit to/from "
                    "target machine via improvised means like cURL.",
        formatter_class=CustomHelpFormatter)

    parser.add_argument('-p', '--port', default=7777, type=int, help='Port for the upload server to serve at')
    parser.add_argument('-i', '--ip', default=list(get_ipv4_address('tun0').values())[0], help='Ip to start the server on')
    parser.add_argument('-d', '--serve-dir', default=os.getcwd(), help='Directory to serve')
    parser.add_argument('-s', '--save-dir', default=os.getcwd(), help='Directory to save files')
    args = parser.parse_args()

    args.serve_dir = os.path.expanduser(args.serve_dir)
    if not os.path.isdir(args.serve_dir):
        print(bold(f'→ Path to serve {args.serve_dir} does not exists. Using: {os.getcwd()}'))
        args.serve_dir = os.getcwd()

    args.save_dir = os.path.expanduser(args.save_dir)
    if not os.path.isdir(args.save_dir):
        print(bold(f'→ Path to serve {args.save_dir} does not exists. Using: {os.getcwd()}'))
        args.save_dir = os.getcwd()

    httpd = socketserver.TCPServer((args.ip, args.port), UploadHTTPRequestHandler)
    httpd.serve_dir = args.serve_dir
    httpd.save_dir = args.save_dir

    httpd.path_map = {}

    args.server = httpd

    print(BANNER)

    cli = CLI(args)
    cli.run_command('path', 'add', args.serve_dir)
    cli.run_command('options')

    print(bold("→ Waiting for requests...\n"))

    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    try:
        while True:
            user_input = input('[print "help" to see available commands]: ')

            cmd = user_input
            cmd_args = ''

            if ' ' in user_input:
                cmd, *cmd_args = user_input.split(' ')

            cli.run_command(cmd, *cmd_args)

    except (ThePotataCommonException, KeyboardInterrupt):
        pass
    finally:
        print(bold('\n→ Shutting down the server...'))
        httpd.shutdown()
        server_thread.join()
