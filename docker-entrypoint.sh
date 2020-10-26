#!/bin/sh

# useful when running the script locally in a virtualenv,
# otherwise, the OS env is already populated in the container
if [ -f '.env' ] ; then
    echo 'Environment file found, sourcing it...'

    set -a
    . ./.env
    set +a

    export PYTHON_LOG_LEVEL=debug
    export LOGIN_STORE_PATH=./store
fi

echo 'Starting the Python app...'
python src/main.py
