#include "iface.h"
#include <assert.h>

static void test_init(void) {
    assert(sample_init() == 0);
    sample_shutdown();
}

static void test_run(void) {
    assert(sample_run("config.yaml") == 0);
    assert(sample_run(NULL) == -1);
}

int main(void) {
    test_init();
    test_run();
    return 0;
}
