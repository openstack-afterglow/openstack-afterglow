/* No network, filesystem, environment, or user command processing. */
#include <signal.h>
#include <unistd.h>

static void terminate(int signo) { (void)signo; _exit(0); }

int main(void) {
    struct sigaction action = {0};
    action.sa_handler = terminate;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, 0);
    sigaction(SIGINT, &action, 0);
    for (;;) pause();
}
