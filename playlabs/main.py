import click
import os
import pexpect
import re
import sh
import shlex
import shutil
import subprocess
import sys


LOCAL_BIN = f'{os.getenv("HOME")}/.local/bin'
LOCAL_BIN_PLAYLABS = f'{LOCAL_BIN}/playlabs'
BASH_PROFILE = f'{os.getenv("HOME")}/.bash_profile'

with open(os.path.join(os.path.dirname(__file__), 'help')) as f:
    HELP = f.read()

def patch():
    with open(BASH_PROFILE, 'a+') as f:
        f.write(
            'export PATH=$PATH:$HOME/.local/bin # playlabs'
        )

if os.path.abspath(sys.argv[0]) == LOCAL_BIN_PLAYLABS:
    if LOCAL_BIN not in os.getenv('PATH').split(':'):
        if not os.path.exists(BASH_PROFILE):
            patch()
        else:
            with open(BASH_PROFILE, 'r') as f:
                res = f.read()
            if '# playlabs' not in res:
                result = click.confirm(
                    'Patch ~/.local/bin in ~/.bash_profile $PATH ?',
                    default=True,
                )
                if result:
                    patch()
                else:
                    with open(BASH_PROFILE, 'a+') as f:
                        f.write('# playlabs')

os.environ['PATH'] = f'{os.getenv("PATH")}:'


class Ansible(object):
    def __init__(
        self,
        inventory,
        playbooks,
    ):
        self.inventory = os.path.abspath(inventory)
        self.playbooks = os.path.abspath(playbooks)

    def sudo(self, options):
        if '--become' not in options:
            options.append('--become')

        if '--become-method' not in options:
            options += [
                '--become-method', 'sudo',
            ]

        if '--become-user' not in options:
            options += [
                '--become-user', 'root'
            ]

        return options


    def playbook(self, name, args):
        cmd = ['ansible-playbook']
        cmd.append('-v')
        find = [
            'inventory.yaml',
            'inventory.yml',
            'inventory/inventory.yaml',
            'inventory/inventory.yml',
        ]
        for i in find:
            if os.path.exists(i):
                cmd += ['--inventory', i]
        cmd += args
        cmd.append(os.path.join(self.playbooks, name))
        cmd = [shlex.quote(i) for i in cmd]

        vault_pass_file = None
        if 'ANSIBLE_VAULT_PASSWORD_FILE' in os.environ:
            if not os.path.exists(os.getenv('ANSIBLE_VAULT_PASSWORD_FILE')):
                vault_pass_file = os.environ.pop('ANSIBLE_VAULT_PASSWORD_FILE')
        os.environ['ANSIBLE_STDOUT_CALLBACK'] = 'debug'
        click.echo(' '.join(cmd))
        child = pexpect.spawn(' '.join(cmd))
        if self.password:
            child.expect('SSH password.*')
            child.sendline(self.password)
            child.expect('SUDO password.*')
            child.sendline(self.password)
        if sys.stdout.isatty():
            child.interact()
        child.wait()
        if vault_pass_file:
            os.environ['ANSIBLE_VAULT_PASSWORD_FILE'] = vault_pass_file
        return child.exitstatus

    def bootstrap(self, target, extra_args):
        user = None

        if '@' in target:
            user, host = target.split('@')
        else:
            host = target

        if not user:
            user = os.getenv('USER')

        options = [
            f'--user={user}',
            '--limit',
            f'{host},',
            '--inventory',
            f'{host},',
        ]

        if user != 'root':
            options = self.sudo(options)

        options += extra_args

        return ansible.playbook('bootstrap.yml', options)

    def role(self, name, hosts, options):
        options += ['-e', f'role={name}']

        if '--noroot' not in options:
            options += self.sudo(options)

        if hosts:
            options += [
                '--inventory',
                ','.join(hosts) + ',',
                '--limit',
                ','.join(hosts) + ',',
            ]
            playbook = 'role-all.yml'
        else:
            playbook = 'role.yml'

        if os.path.exists('inventory.yml'):
            options += ['-i', 'inventory.yml']
        elif os.path.exists('group_vars') or os.path.exists('host_vars'):
            options += ['-i', '.']

        return ansible.playbook(playbook, options)

    def play(self, hosts, options, roles, password):
        self.password = None

        if password and not sh.which('sshpass'):
            args = ['ansible', '-m', 'package', '-a', 'name=sshpass']
            args += [
                '-c',
                'local',
                '-i',
                'localhost,',
                'localhost',
            ]
            user = os.getenv('USER')
            if user != 'root':
                args = self.sudo(args)
            print(' '.join(args))
            res = subprocess.call(args)
            if res != 0:
                click.echo('Passing passwords requires sshpass command')
                return res

        self.password = password

        retcode = 0

        if not roles:
            click.echo('Bootstrapping (no role argument found)')
            for host in hosts:
                retcode = self.bootstrap(host, options)
                if retcode:
                    sys.exit(retcode)

        click.echo(f'Applying {",".join(roles)}')
        for role in roles:
            retcode = self.role(role, hosts, options)
            if retcode:
                sys.exit(retcode)

        return retcode


ansible = Ansible(
    '.',
    os.path.dirname(__file__),
)


def init(target):
    if os.path.exists(target):
        if click.confirm(f'Drop existing {target}?', default=False):
            shutil.rmtree(target)
        else:
            click.echo('Aborting')
            sys.exit(1)
    click.echo(f'Provisioning {target}')
    shutil.copytree(
        os.path.join(
            os.path.dirname(__file__),
            'inventory_template',
        ),
        target,
    )
    click.echo(f'{target} ready ! run playlabs in there to execute')


def cli():
    if len(sys.argv) == 1:
        click.echo(HELP)
        sys.exit(0)
    elif sys.argv[1] == 'init':
        target = os.path.abspath(sys.argv[2])
        init(target)
        sys.exit(0)

    hosts = []
    options = []
    roles = []
    password = None
    args = sys.argv[1:]
    for arg in args:
        if arg == '--nostrict':
            options += [
                '--ssh-extra-args', 
                '-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no',
            ]
        elif '@' in arg:
            hosts.append(arg.split('@')[-1])
            if not arg.startswith('@'):
                left = arg.split('@')[0]
                if ':' in left:
                    user, password = left.split(':')
                    options.append('--ask-become-pass')
                    options.append('--ask-pass')
                else:
                    user = left
                options += ['--user', user]
        elif arg.startswith('-'):
            options.append(arg)
        elif not roles and not options:
            roles = arg.split(',')
        else:
            options.append(arg)

    if hosts == ['localhost']:
        options += ['-c', 'local']

    for i, role in enumerate(roles):
        if role == 'paas':
            del roles[i]
            roles.insert(i, 'nginx')
            roles.insert(i, 'firewall')
            roles.insert(i, 'docker')

    if hosts:
        click.echo(f'Play hosts: {hosts}')
    if roles:
        click.echo(f'Play roles: {roles}')
    if options:
        click.echo(f'Options: {options}')

    sys.exit(ansible.play(hosts, options, roles, password=password))
