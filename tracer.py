#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
from strace import *

import argparse
import os
import sets
import fnmatch
import shlex
import json
import errno
import subprocess
import datetime
import time

from jinja2 import Environment, PackageLoader
from depsolver import DepSolver

IGNORE = [ '/proc', '/proc/*', '/dev', '/dev/*', '/etc/ld.so.cache' ]

MKDIRS = [ '/root', '/tmp' ]

COPYALL = [ '/etc/fonts', 
            '/usr/share/X11/xkb', 
            '/usr/share/fonts', 
            '/usr/share/poppler/cMap',
            '/usr/share/zoneinfo' ]

INCLUDE_ID = [  '/etc/machine-id', 
                '/var/lib/dbus/machine-id' ]
            
            
INCLUDE_LDD = [ '/usr/bin/ldd', 
                '/bin/sh',
                '/sbin/ldconfig',
                '/etc/ld.so.conf',
                '/etc/ld.so.conf.d' ]

INCLUDE_NSS = [             
            '/usr/lib64/libnss_dns.so.2', 
            '/usr/lib64/libnss_files.so.2', 
            '/usr/lib64/libnss_compat.so.2' ]

def make_path_or_exists(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

def abs_path(path, dir):
    if os.path.isabs(path):
        return path
        
    return os.path.normpath(os.path.join(dir, path))

def expand_dir(path, sym_set, files_set, found_set, no_cpy_all):
    for root, dirnames, filenames in os.walk(path):
        for name in filenames:
            expand_file(os.path.join(root, name), sym_set, files_set, found_set, no_cpy_all)
    
def expand_file(path, sym_set, files_set, found_set, no_cpy_all):
    if len([n for n in IGNORE if fnmatch.fnmatch(path, n)]) != 0:
        return
    
    if no_cpy_all != True:
        dirs = [n for n in COPYALL if fnmatch.fnmatch(path, os.path.join(n, '*'))]
        if len(dirs) != 0:
            for roots in dirs:
                expand_dir(roots, sym_set, files_set, found_set, True)
            return
        
    if os.path.islink(path):
        sym_set.add(path)
        lnk = os.readlink(path)
        if os.path.isabs(lnk) == False:
            lnk = os.path.join(os.path.dirname(path), lnk)
        
        expand_file(lnk, sym_set, files_set, found_set, no_cpy_all) 
    
    if os.path.isdir(path):
        expand_dir(path, sym_set, files_set, found_set, no_cpy_all)
        return
                
    if os.path.isfile(path):
        if path in files_set:
            return

        files_set.add(path)
        found_set.add(os.path.basename(path))
        
        deps = DepSolver()
        deps.add(path)
        for src in deps.deps:
            expand_file(src, sym_set, files_set, found_set, no_cpy_all)

def add_dir(path, mkdirs_set):
    dirs = [n for n in COPYALL if fnmatch.fnmatch(path, os.path.join(n, '*'))]
    if len(dirs) != 0:
        for roots in dirs:
            mkdirs_set.add(roots)    

def generate_dockerfile(docker):
    env = Environment(loader=PackageLoader('tracer', 'templates'))
    
    tmpl = env.get_template('Dockerfile.jinja2')
    with open('Dockerfile', 'w') as df:
        df.write(tmpl.render(docker=docker))

def generate_runc(entrypoint, cmd):
    try:
        os.remove('config.json')
    except OSError as e: 
        if e.errno != errno.ENOENT:
            raise # re-raise exception if not the not found error
            
    call = ['runc', 'spec']
    subprocess.check_call(call)
    with open('config.json', 'r+') as runc_file:    
        runc = json.load(runc_file)
        args = [ ]
        if entrypoint is None:
            args.append('sh')
        else:
            args += shlex.split(entrypoint)
            
        if cmd is not None:
            args += shlex.split(cmd)    
            
        runc['process']['args'] = args
        runc_file.seek(0)
        json.dump(runc, runc_file, indent=4)
        runc_file.truncate()
    
    
def make_path(path, scr):
    if scr is not None:
        scr.write('mkdir -p "%s"\n' % path)
    else:
        make_path_or_exists(path)

def copy_file(src, dir, scr, xtended, dst=None):
    if dst is None:
        dst = src

    target = os.path.join(dir, dst[1:])
    target_dir = os.path.dirname(target)

    make_path(target_dir, scr)
    
    opts = '-acl'
    if xtended is True:
        opts += 'X'
    
    cmd = ['rsync', opts, src, target]

    if scr is not None:
        scr.write('%s %s "%s" "%s"\n' % tuple(cmd))
    else:
        subprocess.check_call(cmd)

    
def main():
    
    parser = argparse.ArgumentParser(description='Process strace output and generate Dockerfile.')
    parser.add_argument('--chdir', default=os.getcwd(), help='Initial working directory for strace file')
    parser.add_argument('--build', '-b', default='./build', help='Directory to assemble Dockerfile in')
    
    parser.add_argument('--cmd', '-c', help='Docker CMD')
    parser.add_argument('--entrypoint', '-e', help='Docker ENTRYPOINT')    

    parser.add_argument('--script', '-s', help='Create a script file to assemble directory insead of doing it')
    parser.add_argument('--ignore', '-i',  type=int, help='Ignore pid from the strace', required=False)
    parser.add_argument('files', nargs='+', help='strace files to parse')
 
    inc_ldd_parser = parser.add_mutually_exclusive_group(required=False)
    inc_ldd_parser.add_argument('--ldd', dest='ldd', action='store_true', help='Include LDD configuration')
    inc_ldd_parser.add_argument('--no-ldd', dest='ldd', action='store_false')
    parser.set_defaults(ldd=True) 
 
    inc_nss_parser = parser.add_mutually_exclusive_group(required=False)
    inc_nss_parser.add_argument('--nss', dest='nss', action='store_true', help='Include resolover services')
    inc_nss_parser.add_argument('--no-nss', dest='nss', action='store_false')
    parser.set_defaults(nss=True) 
 
    inc_id_parser = parser.add_mutually_exclusive_group(required=False)
    inc_id_parser.add_argument('--ids', dest='ids', action='store_true', help='Include machine-id from host')
    inc_id_parser.add_argument('--no-ids', dest='ids', action='store_false')
    parser.set_defaults(ids=True) 
          
    inc_xattrs_parser = parser.add_mutually_exclusive_group(required=False)
    inc_xattrs_parser.add_argument('--xattrs', dest='xattrs', action='store_true', help='Copy extended attributes across')
    inc_xattrs_parser.add_argument('--no-xattrs', dest='xattrs', action='store_false')
    parser.set_defaults(xattrs=False) 

    inc_runc_parser = parser.add_mutually_exclusive_group(required=False)
    inc_runc_parser.add_argument('--runc', dest='runc', action='store_true', help='Generate a config.json OCI/runc (requires runc in path)')
    inc_runc_parser.add_argument('--no-runc', dest='runc', action='store_false')
    parser.set_defaults(runc=False) 
             
    args = parser.parse_args()
    
    in_files = [open(file, "r") for file in args.files]
        
#    if os.path.isabs(args.chdir) == False:
#        raise Exception('--chdir must be absolute')
    
    make_path_or_exists(args.build)
    os.chdir(args.build)
    
    root = './rootfs'
    
    docker = {}
    if args.cmd:
        docker['cmd'] = json.dumps(shlex.split(args.cmd))
    
    if args.entrypoint:
        docker['entrypoint'] = json.dumps(shlex.split(args.entrypoint))
            
    included = []
    
    if args.ldd is True:
        included += INCLUDE_LDD
        docker['ldd'] = True
        
    if args.ids is True:
        included += INCLUDE_ID
        
    if args.nss is True:
        included += INCLUDE_NSS
            
    generate_dockerfile(docker)
            
    error_set = sets.Set()
    files_set = sets.Set()
    sym_set = sets.Set()
    found_set = sets.Set()
    mkdirs_set = sets.Set(MKDIRS)

                       
    for forced in included:
        expand_file(forced, sym_set, files_set, found_set, False)
    
    i = 0
    ignore = []
    if args.ignore is not None:
        ignore.append(args.ignore)    
        
    for f_in in in_files:
        cdir = args.chdir
        strace_stream = StraceInputStream(f_in)
        for entry in strace_stream:
            i = i + 1
            if i % 128 == 0:
                sys.stdout.write('\n')
                
            sys.stdout.write('\r%i lines parsed' % (i))
            sys.stdout.flush()

            if entry is None:
                continue
                
            if entry.syscall_name in [ "chdir" ]:
                # TODO: Wrong with multiple processes
                ndir = entry.syscall_arguments[0]
                cdir = abs_path(ndir[1:-1], cdir)
                if int(entry.return_value) < 0:
                    error_set.add(path)
                else:
                    add_dir(cdir, mkdirs_set)
                continue

            if entry.pid in ignore:
                continue
            
            if entry.syscall_name in [ "statfs" ]:
                path = entry.syscall_arguments[0]
                path = abs_path(path[1:-1], cdir)                
                if int(entry.return_value) < 0:
                    error_set.add(path)
                else:
                    add_dir(path, mkdirs_set)
                    
            if entry.syscall_name in [ "open", "stat", "execve" ]:
                path = entry.syscall_arguments[0]
                path = abs_path(path[1:-1], cdir)
                    
                if int(entry.return_value) < 0:
                    error_set.add(path)
                else:
                    expand_file(path, sym_set, files_set, found_set, False)

    sys.stdout.write('\n')       
                    
    for path in sorted(error_set):
        if os.path.basename(path) not in found_set:
            sys.stderr.write("Warning, open error in trace: %s\n" % path)    

    scr = None
    if args.script is not None:
        f = args.script
        scr = open(f, 'w')
        st = os.stat(f)
        os.chmod(f, st.st_mode | 0111)
        scr.write('#!/bin/sh\n\n# Auto generated by tracer.py on %s\n\n' % datetime.datetime.utcnow())

    print('Making %i dirs' % len(mkdirs_set))
    for dir in mkdirs_set:
        make_path(os.path.join(root, dir[1:]), scr)
    
    print('Copying %i files' % len(files_set))    
    for path in sorted(files_set):   
        copy_file(path, root, scr, args.xattrs)

    print('Copying %i symlinks' % len(sym_set))
    for path in sorted(sym_set):   
        copy_file(path, root, scr, args.xattrs)
    
    if args.runc:
        generate_runc(args.entrypoint, args.cmd)
    
    print('==================================')
    if scr is None:
        print('cd %s && docker build .' % args.build)
    else:
        print('cd %s && ./%s && docker build .' % (args.build, args.script))    
        scr.close()
    
if __name__ == "__main__":
	main()    