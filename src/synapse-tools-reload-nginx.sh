#! /usr/bin/env bash

set -ue -o pipefail

pidfile="$1"

# See http://nginx.org/en/docs/control.html#upgrade for details about nginx
# reload process.

# At this moment we have the current master with PID in `$pidfile` (and its workers).
# We also might have the old master with PID in `$pidfile.oldbin` (and its
# workers) are still gracefully shutting down after the previous reload.

# If the old master process from the previous reload is still running, kill it
if [ -e "$pidfile.oldbin" ] && pkill -0 --pidfile "$pidfile.oldbin" -f 'nginx: master'; then
    oldpid=$(cat "$pidfile.oldbin") || true  # The old master could quit at any moment
    if [ -e "$pidfile.oldbin" ]; then
        # Tell the old master and its workers to fast shutdown.
        kill -TERM "-${oldpid}" || true  # The old master could quit at any moment
        died=0
        for _ in $(seq 50); do
            sleep .1
            if ! kill -0 "$oldpid"; then
                died=1
                break
            fi
        done
        if [ $died -eq 0 ]; then
            # 5 seconds is more than enough to shutdown, hard kill the old
            # master and all its workers.
            kill -KILL "-${oldpid}" || true  # The old master could quit at any moment
            sleep 1
        fi
    fi
fi

curpid=$(cat "$pidfile")

# Tell the current master to launch a new master and wait for it to be running
# The new master is expected to rename `$pidfile` into `$pidfile.oldbin`
# and write its PID into `$pidfile`.  So, at the end there should be
# `$pidfile` with the new master's PID and `$pidfile.oldbin` with the
# current master's PID.
kill -USR2 "$curpid"
for _ in $(seq 50); do
    sleep .1
    newpid=$(cat "$pidfile")
    if [ "$curpid" -ne "$newpid" ]; then
        break
    fi
done

# If the new master didn't manage to write its pid into `$pidfile` during
# the previous 5 sec, then something is very wrong with it (most likely an
# invalid config file), so just give up.
if [ "$curpid" -eq "$newpid" ]; then
    exit 1
fi

# At this moment we have the current master with its PID in
# `$pidfile.oldbin` (and its workers) and the new master with its PID in
# `$pidfile` (and its workers).  Both are accepting new conections.
# Now let's gracefully shutdown the current master and its workers, so only
# the new master and its workers will accept and process the new
# connections.  The current master and its workers will be alive until all
# their already accepted connections are alive, which could take a lot
# of time.

curpid=$(cat "$pidfile.oldbin")

# Tell the current master to gracefully shutdown its worker processes
kill -WINCH "$curpid"

# Tell the current master to gracefully shutdown
kill -QUIT "$curpid"
