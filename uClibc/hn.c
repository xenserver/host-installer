#include <stdio.h>
#include <netdb.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

int
main(int argc, char *argv[])
{
    char *ip = NULL;
    struct hostent *he = NULL;

    if (argc == 1) {
        return 1;
    }

    he = gethostbyname(argv[1]);

    if (he == NULL) {
        return 2;
    }

    ip = inet_ntoa(*(struct in_addr*)he->h_addr);

    printf("%s=%s\n", argv[1], ip);

    return 0;
}
