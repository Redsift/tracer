#!/usr/bin/env python

from __future__ import print_function
from strace import *

import argparse

def main():
    
    parser = argparse.ArgumentParser(description='Process strace output and generate Dockerfile.')
    
    parser.add_argument('files', nargs='+',
                    help='strace files to parse')
                    
    args = parser.parse_args()
    
    for input_file in args.files:
        f_in = open(input_file, "r")
        strace_stream = StraceInputStream(f_in)
        for entry in strace_stream:
            print(entry)
    
    
if __name__ == "__main__":
	main()    