import os
import netifaces
from exceptions import ThePotataCommonException


# Source: https://brandonrozek.com/blog/ipaddressesinpython/
def get_ipv4_address(iface='') -> dict:
    result = {}
    interface_list = [interface for interface in netifaces.interfaces()]
    for _iface in interface_list:
        addr = netifaces.ifaddresses(_iface)
        if netifaces.AF_INET in addr:
            result[_iface] = addr[netifaces.AF_INET][0]['addr']

    if iface == '':
        return result

    if iface in interface_list:
        return {iface: result[iface]}

    # just getting one of them
    iface = list(result)[-1]
    return {iface: result[iface]}


def bold(text):
    BOLD = '\033[1m'
    END = '\033[0m'
    return BOLD + text + END


def italic(text):
    ITALIC = '\033[3m'
    END = '\033[0m'
    return ITALIC + text + END


def create_dir(path):
    try:
        os.makedirs(path)
    except PermissionError as err:
        raise ThePotataCommonException(f'Cannot create the directory {path}: {err}')
    except FileExistsError:
        raise ThePotataCommonException(f'Cannot create the directory {path}: directory already exists')
