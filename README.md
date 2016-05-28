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

Includes a srtace parser from https://github.com/dirtyharrycallahan/pystrace and ELF parser from https://github.com/larsks/dockerize