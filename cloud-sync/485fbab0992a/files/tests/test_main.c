/* Auto-generated unit tests by yuleOSH */
#include <assert.h>
#include "../code/src/main.c"

void test_toggle_beam(void) {
    g_beam = LOW_BEAM;
    headlight_toggle_beam();
    assert(g_beam == HIGH_BEAM);
    headlight_toggle_beam();
    assert(g_beam == LOW_BEAM);
}

void test_is_night(void) {
    /* stub sensor returns night */
    assert(is_night() == 1);
}
