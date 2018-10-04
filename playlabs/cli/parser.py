import collections
import json
import os


class Parser(object):
    def __init__(self):
        self.handles = {
            'install': self.handle_install,
            'deploy': self.handle_deploy,
            'init': self.handle_init,
            '-i': self.handle_inventory,
            '-p': self.handle_plugins,
        }
        self.primary_tokens = self.handles.keys()
        self.makeinstall = False
        self.makedeploy = False
        self.makeinit = False
        self._user = None
        self.roles = []
        self.hosts = []
        self.options = []
        self.password = None
        self.subvars = dict()
        self.options_dict = dict()
        self.argcount = 0

    @property
    def user(self):
        return self._user

    @user.setter
    def user(self, name):
        if self._user:
            raise NameError('User should only be defined once')
        else:
            self._user = name

    def handle_install(self, arg):
        if arg:
            self.makeinstall = True
            self.roles = arg.split(',')
        else:
            print('no role to install')

    def handle_deploy(self, arg):
        self.makedeploy = True

    def handle_init(self, arg):
        self.makeinit = True

    def handle_host(self, arg):
        host = arg.split('@')[-1]
        if host:
            self.hosts.append(host)
        if not arg.startswith('@'):
            left = arg.split('@')[0]
            if ':' in left:
                self.user, self.password = arg.split('@')[0].split(':')
                if '--ask-become-pass' not in self.options:
                    self.options.append('--ask-become-pass')
                    self.options.append('--ask-pass')
            else:
                self.user = left

        if self.user:
            self.options += ['--user', self.user]

    def handle_inventory(self, arg):
        if not arg:
            raise Exception('Inventory: missing parameter')
        for i in arg.split(','):
            if os.path.exists(i):
                self.options += ['-i', i]
            else:
                raise NameError(f'Inventory not found: {i}')
                print(f'command line inventory {i} cannot be found')

    def handle_plugins(self, arg):
        if not arg:
            raise Exception('Plugins: missing parameter')
        plugins_path = os.path.join(os.path.dirname(__file__), '../plugins')
        if os.path.exists(plugins_path):
            plugins_list = os.listdir(plugins_path)
            plugins = []
            for p in arg.split(','):
                if p in plugins_list:
                    plugins.append(p)
                else:
                    self.argcount += 1
                    raise NameError(f'Plugin not found: {p}')
            if plugins:
                self.options.append('-e')
                if len(plugins) > 1:
                    self.options.append(f'plugins={",".join(plugins)}')
                else:
                    self.options.append(f'plugins={plugins[0]}')
            else:  # should be useless
                raise NameError('Plugin: "-p" found but no plugins specified')

    def handle_vars(self, arg):
        if arg == '-e':
            return

        if '=' in arg and not arg.startswith('--'):
            if arg[0] == '=' or arg[-1] == '=':
                raise NameError(f'Wrong variable format {arg}, \
variable definition cannot start neither end with "="')
            name = arg.split('=')[0]
            if '.' in name:
                if name[0] == '.' or name[-1] == '.':
                    raise NameError(f'Wrong variable format {name}, \
variable name cannot start neither end with "."')

                def setattribute(a, v):
                    if len(a) > 1:
                        return {a[0]: setattribute(a[1:], v)}
                    else:
                        return {a[0]: v}
                descriptor, val = arg.split('=')
                variable = descriptor.split('.')[0]
                descarray = descriptor.split('.')[1:]
                if variable not in self.subvars.keys():
                    self.subvars[variable] = setattribute(descarray, val)
                else:
                    self.subvars[variable].update(setattribute(descarray, val))
            else:
                self.options += ['-e', arg]
                self.options_dict[name] = arg.split('=')[1]
        else:
            self.options.append(arg)

    def skip(self, arg):
        return

    def ssh_config(self):
        ssh = collections.OrderedDict()

        ssh['ControlMaster'] = 'auto'
        ssh['ControlPersist'] = '60s'
        if self.user:
            ssh['ControlPath'] = f'.ssh_control_path_{self.user}'
        self.options += ['--ssh-extra-args', ' '.join([
            f'-o {key}={value}' for key, value in ssh.items()
        ])]

    def parse(self, args):
        while args:
            arg = args.pop(0)
            self.argcount += 1

            if arg in ('-u', '--user'):
                self.user = args.pop(0)
                self.argcount += 1
            elif arg.startswith('-u=') or arg.startswith('--user='):
                self.user = arg.split('=')[-1]
            else:
                if '@' in arg and '=' not in arg:
                    self.handle_host(arg)
                elif arg in ['init', 'deploy']:
                    self.handles[arg](None)
                elif arg in self.primary_tokens:
                    self.handles[arg](args.pop(0) if args else None)
                    self.argcount += 1
                else:
                    self.handle_vars(arg)

        if not self.user:
            self.user = os.getenv("USER")

        if self.hosts == ['localhost']:
            self.options += ['-c', 'local']
        else:
            self.ssh_config()

        if self.subvars:
            self.options += ['-e', json.dumps(self.subvars)]

        if not self.user:
            self.user = os.getenv('USER')

        self.print()

    def checksudo(self, data):
        for user in data.get('users'):
            if user['name'] != self.user:
                continue

            roles = user.get('roles', {})
            if 'ssh' in roles:
                if 'sudo' not in roles.get('ssh', []):
                    return False
            else:
                return False
        return True

    def print(self):
        if self.user:
            print(f'Play user: {self.user}')
        if self.hosts:
            print(f'Play hosts: {self.hosts}')
        if self.roles:
            print(f'Play roles: {self.roles}')
        if self.options:
            print(f'Options: {self.options}')
