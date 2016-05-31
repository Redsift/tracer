# Installation
    
    # Install pip if required
    easy_install pip

    pip install -r requirements.txt

# Usage

    # Strace the ls command and write the syscalls to ls.out
    strace -ttt -o ls.out ls

    # Run tracer to process ls.out and write a Docker file
    # Set ENTRYPOINT to /usr/bin/ls
    ./tracer.py -e /usr/bin/ls ls.out

    # Build the image
    cd build
    docker build -t traced-ls .
    
    # Run the scratch image
    docker run -ti traced-ls
    
## Advanced usage
    
    # Strace all commands for the current shell in the background
    strace -ttt -o $$.out -p $$ -f &
    
    # Run my command(s)
    ls
    
    # Exit the shell
    exit
    
    # <pid-of-shell>.out now contains the syscall trace of the shell and the child ls  
    # Assuming the pid of the shell was 22092, make a runc rootfs of the executed ls
    # while ignoring the parent shell process
    
    ./tracer.py -e /bin/ls --runc -i 22092 22092.out  

# Help

    usage: tracer.py [-h] [--chdir CHDIR] [--build BUILD] [--cmd CMD]
                    [--entrypoint ENTRYPOINT] [--script SCRIPT]
                    [--ldd | --no-ldd] [--nss | --no-nss] [--ids | --no-ids]
                    files [files ...]

    Process strace output and generate Dockerfile.

    positional arguments:
    files                 strace files to parse

    optional arguments:
    -h, --help            show this help message and exit
    --chdir CHDIR         Initial working directory for strace file
    --build BUILD         Directory to assemble Dockerfile in
    --cmd CMD, -c CMD     Docker CMD
    --entrypoint ENTRYPOINT, -e ENTRYPOINT
                            Docker ENTRYPOINT
    --script SCRIPT, -s SCRIPT
                            Create a script file to assemble directory insead of
                            doing it
    --ldd                 Include LDD configuration
    --no-ldd
    --nss                 Include resolover services
    --no-nss
    --ids                 Include machine-id from host
    --no-ids

# OCI/runc

Use the `--runc` flag to create a `config.json` that can be used in tools like runc. `--entrypoint` and `--cmd` will be used to generate the spec. This flag requires `runc` installed and in the path.

# Issues

- Ensure your system `strace` is up to date. 
- You typically cannot trace from inside a Docker container. 
- Ensure you use the -ttt flag to create parseable timestamps.
- When attempting to create small distributions from Red Hat based distros, /usr/lib/locale/locale-archive can be large.

# Acknowledgements

Includes a srtace parser from https://github.com/dirtyharrycallahan/pystrace and ELF parser from https://github.com/larsks/dockerize