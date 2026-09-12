#ifndef IFACE_H
#define IFACE_H

/* Public interface for the sample module. */
int sample_init(void);
int sample_run(const char *config_path);
void sample_shutdown(void);

#endif /* IFACE_H */
