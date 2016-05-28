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

from jinja2 import Environment, PackageLoader
from depsolver import DepSolver

IGNORE = [ '/proc', '/proc/*', '/dev', '/dev/*', '/etc/ld.so.cache', '/app' ]

COPYALL = [ '/etc/fonts', '/usr/share/X11/xkb', '/usr/share/fonts', '/usr/share/poppler/cMap', '/usr/share/zoneinfo' ]

MKDIRS = [ '/root', '/tmp', '/var/lib', '/var/cache', '/usr/local/share/fonts' ]

INCLUDE = [ '/etc/machine-id', 
            '/var/lib/dbus/machine-id', 
            '/usr/bin/ldd', 
            '/bin/sh',
            '/sbin/ldconfig',
            '/etc/ld.so.conf',
            '/etc/ld.so.conf.d', 
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

def expand_dir(path, sym_set, files_set, found_set):
    for root, dirnames, filenames in os.walk(path):
        for name in filenames:
            expand_file(os.path.join(root, name), sym_set, files_set, found_set)
    
def expand_file(path, sym_set, files_set, found_set):
    if os.path.islink(path):
        sym_set.add(path)
        lnk = os.readlink(path)
        if os.path.isabs(lnk) == False:
            lnk = os.path.join(os.path.dirname(path), lnk)
        
        expand_file(lnk, sym_set, files_set, found_set) 
    
    if os.path.isdir(path):
        expand_dir(path, sym_set, files_set, found_set)
        return
                
    if os.path.isfile(path):
        if path in files_set:
            return
  
        files_set.add(path)
        found_set.add(os.path.basename(path))
        
        deps = DepSolver()
        deps.add(path)
        for src in deps.deps:
            expand_file(src, sym_set, files_set, found_set)

def generate_dockerfile(target, docker):
    env = Environment(loader=PackageLoader('tracer', 'templates'))
    
    tmpl = env.get_template('Dockerfile.jinja2')
    with open(os.path.join(target, 'Dockerfile'), 'w') as df:
        df.write(tmpl.render(docker=docker))

def copy_file(src, dir, dst=None):
    if dst is None:
        dst = src

    target = os.path.join(dir, dst[1:])
    target_dir = os.path.dirname(target)

    make_path_or_exists(target_dir)

    cmd = ['rsync', '-a']
    # Symlinks
    cmd.append('-l')
    cmd += [src, target]
    subprocess.check_call(cmd)

    
def main():
    
    parser = argparse.ArgumentParser(description='Process strace output and generate Dockerfile.')
    parser.add_argument('--chdir', default=os.getcwd(), help='Initial working directory for strace file')
    parser.add_argument('--build', default='./build', help='Directory to assemble Dockerfile in')
    
    parser.add_argument('--cmd', '-c', help='Docker CMD')
    parser.add_argument('--entrypoint', '-e', help='Docker ENTRYPOINT')    
    
    parser.add_argument('files', nargs='+', help='strace files to parse')
      
    args = parser.parse_args()
    
    if os.path.isabs(args.chdir) == False:
        raise Exception('--chdir must be absolute')
    
    make_path_or_exists(args.build)
    root = os.path.join(args.build, 'root')
    
    docker = {}
    if args.cmd:
        docker['cmd'] = json.dumps(shlex.split(args.cmd))
    
    if args.entrypoint:
        docker['entrypoint'] = json.dumps(shlex.split(args.entrypoint))
           
    generate_dockerfile(args.build, docker)
    
    for dir in MKDIRS:
        make_path_or_exists(os.path.join(root, dir[1:]))
            
    error_set = sets.Set()
    files_set = sets.Set()
    sym_set = sets.Set()
    found_set = sets.Set()
    
    for forced in INCLUDE:
        expand_file(forced, sym_set, files_set, found_set)
        
    for input_file in args.files:
        cdir = args.chdir
        f_in = open(input_file, "r")
        strace_stream = StraceInputStream(f_in)
        for entry in strace_stream:
            if entry is None:
                continue
            if entry.syscall_name in [ "chdir" ]:
                ndir = entry.syscall_arguments[0]
                cdir = abs_path(ndir[1:-1], cdir)
                print(cdir)
                continue
                
            if entry.syscall_name in [ "open", "stat", "execve" ]:
                path = entry.syscall_arguments[0]
                path = abs_path(path[1:-1], cdir)
                 
                if int(entry.return_value) < 0:
                    error_set.add(path)
                else:
                    if len([n for n in IGNORE if fnmatch.fnmatch(path, n)]) == 0:
                        expand_file(path, sym_set, files_set, found_set)

                    
    for path in sorted(error_set):
        if os.path.basename(path) not in found_set:
            sys.stderr.write("Warning, open error: %s\n" % path)    
        
    for path in sorted(files_set):   
        copy_file(path, root)

    for path in sorted(sym_set):   
        copy_file(path, root)
    
    print('Files copied: %i, Links copied: %i' % (len(files_set), len(sym_set)))
    print('==================================')
    print('cd %s && docker build .' % args.build)
if __name__ == "__main__":
	main()    