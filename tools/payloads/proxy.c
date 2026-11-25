/* SPDX-License-Identifier: GPL-3.0-or-later */
/* proxy.c - minimal HTTP CONNECT proxy for the TL-WR841N lab firmware.
 *
 * One purpose: turn the router into a LAN pivot. Accepts HTTP CONNECT
 * host:port requests (IP or hostname), opens the tunnel and relays bytes
 * both ways. Plain (non-CONNECT) requests are rejected - there is no
 * caching, no filtering, no logging: smallest artifact possible.
 *
 * Usage: proxy [-p PORT]        (default 8888)
 *
 * Target: MIPS big-endian, soft-float, statically linked (see build.sh).
 */
#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

static int connect_target(const char *host, const char *port)
{
    struct sockaddr_in peer = {0};
    peer.sin_family = AF_INET;
    peer.sin_port = htons((unsigned short)atoi(port));
    peer.sin_addr.s_addr = inet_addr(host);
    if (peer.sin_addr.s_addr == INADDR_NONE) {
        struct hostent *he = gethostbyname(host); /* musl static resolver */
        if (!he || he->h_addrtype != AF_INET || !he->h_addr_list[0])
            return -1;
        memcpy(&peer.sin_addr.s_addr, he->h_addr_list[0],
               sizeof(peer.sin_addr.s_addr));
    }
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        return -1;
    if (connect(fd, (struct sockaddr *)&peer, sizeof(peer)) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

/* Bidirectional relay until either side closes. */
static void relay(int a, int b)
{
    fd_set rfds;
    char buf[8192];
    for (;;) {
        FD_ZERO(&rfds);
        FD_SET(a, &rfds);
        FD_SET(b, &rfds);
        if (select((a > b ? a : b) + 1, &rfds, NULL, NULL, NULL) < 0) {
            if (errno == EINTR)
                continue;
            return;
        }
        if (FD_ISSET(a, &rfds)) {
            ssize_t n = read(a, buf, sizeof(buf));
            if (n <= 0 || write(b, buf, (size_t)n) < 0)
                return;
        }
        if (FD_ISSET(b, &rfds)) {
            ssize_t n = read(b, buf, sizeof(buf));
            if (n <= 0 || write(a, buf, (size_t)n) < 0)
                return;
        }
    }
}

static void reply(int cfd, const char *status)
{
    write(cfd, status, strlen(status));
}

/* Handle one client: parse "CONNECT host:port HTTP/x.y", tunnel it. */
static void handle(int cfd)
{
    char buf[8192];
    size_t got = 0;
    while (got < sizeof(buf) - 1) {
        ssize_t n = read(cfd, buf + got, sizeof(buf) - 1 - got);
        if (n <= 0)
            return;
        got += (size_t)n;
        buf[got] = '\0';
        if (strstr(buf, "\r\n\r\n"))
            break;
    }
    if (strncmp(buf, "CONNECT ", 8) != 0) {
        reply(cfd, "HTTP/1.1 405 Method Not Allowed\r\n\r\n");
        return;
    }
    char *sp = strchr(buf + 8, ' '); /* end of the host:port token */
    if (!sp)
        return;
    *sp = '\0';
    char *colon = strrchr(buf + 8, ':');
    if (!colon || colon == buf + 8 || !colon[1] || atoi(colon + 1) <= 0) {
        reply(cfd, "HTTP/1.1 400 Bad Request\r\n\r\n");
        return;
    }
    *colon = '\0';
    int up = connect_target(buf + 8, colon + 1);
    if (up < 0) {
        reply(cfd, "HTTP/1.1 502 Bad Gateway\r\n\r\n");
        return;
    }
    reply(cfd, "HTTP/1.1 200 Connection established\r\n\r\n");
    relay(cfd, up);
    close(up);
}

int main(int argc, char **argv)
{
    signal(SIGPIPE, SIG_IGN);
    signal(SIGCHLD, SIG_IGN); /* reap children, no zombies */

    int port = 8888;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-p") && i + 1 < argc) {
            port = atoi(argv[++i]);
        } else {
            fprintf(stderr, "Usage: %s [-p PORT]\n", argv[0]);
            return 2;
        }
    }

    struct sockaddr_in self = {0}, cli;
    socklen_t cl = sizeof(cli);
    self.sin_family = AF_INET;
    self.sin_addr.s_addr = htonl(INADDR_ANY);
    self.sin_port = htons((unsigned short)port);

    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    if (lfd < 0) {
        perror("socket");
        return 1;
    }
    int one = 1;
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    if (bind(lfd, (struct sockaddr *)&self, sizeof(self)) < 0) {
        perror("bind");
        return 1;
    }
    if (listen(lfd, 8) < 0) {
        perror("listen");
        return 1;
    }
    for (;;) {
        int cfd = accept(lfd, (struct sockaddr *)&cli, &cl);
        if (cfd < 0) {
            if (errno == EINTR)
                continue;
            return 1;
        }
        if (fork() == 0) {
            close(lfd);
            handle(cfd);
            close(cfd);
            _exit(0);
        }
        close(cfd);
    }
}
