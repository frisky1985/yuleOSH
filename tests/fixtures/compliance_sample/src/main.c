#include "iface.h"
#include <stdio.h>
#include <string.h>

static int g_state = 0;

int sample_init(void) {
    g_state = 1;
    return 0;
}

int sample_run(const char *config_path) {
    if (config_path == NULL) return -1;
    printf("running with config: %s\n", config_path);
    return 0;
}

void sample_shutdown(void) {
    g_state = 0;
}
