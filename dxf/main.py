#pylint: disable=wrong-import-position,wrong-import-order,superfluous-parens
import os
import argparse
import sys
import tqdm
import dxf
import dxf.exceptions

_choices = ['auth',
            'push-blob',
            'pull-blob',
            'blob-size',
            'del-blob',
            'set-alias',
            'get-alias',
            'del-alias',
            'list-aliases',
            'list-repos']

_parser = argparse.ArgumentParser()
_subparsers = _parser.add_subparsers(dest='op')
for c in _choices:
    sp = _subparsers.add_parser(c)
    if c != 'list-repos':
        sp.add_argument("repo")
        sp.add_argument('args', nargs='*')

def _flatten(l):
    return [item for sublist in l for item in sublist]

# pylint: disable=too-many-statements
def doit(args, environ):
    if environ.get('DXF_PROGRESS') == '1':
        bars = {}
        def progress(dgst, chunk, size):
            if dgst not in bars:
                bars[dgst] = tqdm.tqdm(desc=dgst[0:8],
                                       total=size,
                                       leave=True)
            if len(chunk) > 0:
                bars[dgst].update(len(chunk))
            if bars[dgst].n >= bars[dgst].total:
                bars[dgst].close()
                del bars[dgst]
    else:
        progress = None

    def auth(dxf_obj, response):
        # pylint: disable=redefined-outer-name
        username = environ.get('DXF_USERNAME')
        password = environ.get('DXF_PASSWORD')
        if username and password:
            dxf_obj.auth_by_password(username, password, response=response)

    # pylint: disable=redefined-variable-type
    args = _parser.parse_args(args)
    if args.op != 'list-repos':
        dxf_obj = dxf.DXF(environ['DXF_HOST'],
                          args.repo,
                          auth,
                          environ.get('DXF_INSECURE') == '1')
    else:
        dxf_obj = dxf.DXFBase(environ['DXF_HOST'],
                              auth,
                              environ.get('DXF_INSECURE') == '1')

    def _doit():
        # pylint: disable=too-many-branches
        if args.op == "auth":
            token = dxf_obj.auth_by_password(environ['DXF_USERNAME'],
                                             environ['DXF_PASSWORD'],
                                             actions=args.args)
            if token:
                print(token)
            return

        token = environ.get('DXF_TOKEN')
        if token:
            dxf_obj.token = token

        if args.op == "push-blob":
            if len(args.args) < 1:
                _parser.error('too few arguments')
            if len(args.args) > 2:
                _parser.error('too many arguments')
            if len(args.args) == 2 and not args.args[1].startswith('@'):
                _parser.error('invalid alias')
            dgst = dxf_obj.push_blob(args.args[0], progress)
            if len(args.args) == 2:
                dxf_obj.set_alias(args.args[1][1:], dgst)
            print(dgst)

        elif args.op == "pull-blob":
            if len(args.args) == 0:
                dgsts = dxf_obj.get_alias(manifest=sys.stdin.read())
            else:
                dgsts = _flatten([dxf_obj.get_alias(name[1:])
                                  if name.startswith('@') else [name]
                                  for name in args.args])
            for dgst in dgsts:
                it, size = dxf_obj.pull_blob(dgst, size=True)
                if environ.get('DXF_BLOB_INFO') == '1':
                    print(dgst + ' ' + str(size))
                if progress:
                    progress(dgst, b'', size)
                for chunk in it:
                    if progress:
                        progress(dgst, chunk, size)
                    sys.stdout.write(chunk)

        elif args.op == 'blob-size':
            if len(args.args) == 0:
                sizes = [dxf_obj.get_alias(manifest=sys.stdin.read(),
                                           sizes=True)]
            else:
                sizes = [dxf_obj.get_alias(name[1:], sizes=True)
                         if name.startswith('@') else
                         [(name, dxf_obj.blob_size(name))]
                         for name in args.args]
            for tuples in sizes:
                print(sum([size for _, size in tuples]))

        elif args.op == 'del-blob':
            if len(args.args) == 0:
                dgsts = dxf_obj.get_alias(manifest=sys.stdin.read())
            else:
                dgsts = _flatten([dxf_obj.del_alias(name[1:])
                                  if name.startswith('@') else [name]
                                  for name in args.args])
            for dgst in dgsts:
                dxf_obj.del_blob(dgst)

        elif args.op == "set-alias":
            if len(args.args) < 2:
                _parser.error('too few arguments')
            dgsts = [dxf.hash_file(dgst) if os.sep in dgst else dgst
                     for dgst in args.args[1:]]
            sys.stdout.write(dxf_obj.set_alias(args.args[0], *dgsts))

        elif args.op == "get-alias":
            if len(args.args) == 0:
                dgsts = dxf_obj.get_alias(manifest=sys.stdin.read())
            else:
                dgsts = _flatten([dxf_obj.get_alias(name) for name in args.args])
            for dgst in dgsts:
                print(dgst)

        elif args.op == "del-alias":
            for name in args.args:
                for dgst in dxf_obj.del_alias(name):
                    print(dgst)

        elif args.op == 'list-aliases':
            if len(args.args) > 0:
                _parser.error('too many arguments')
            for name in dxf_obj.list_aliases():
                print(name)

        elif args.op == 'list-repos':
            for name in dxf_obj.list_repos():
                print(name)

    try:
        _doit()
        return 0
    except dxf.exceptions.DXFUnauthorizedError:
        import traceback
        traceback.print_exc()
        import errno
        return errno.EACCES

def main():
    exit(doit(sys.argv[1:], os.environ))
