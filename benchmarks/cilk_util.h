#ifndef GENOMICSBENCH_CILK_UTIL_H
#define GENOMICSBENCH_CILK_UTIL_H
/*
 * Small helpers shared by the OpenCilk ports of the benchmarks.
 *
 * The OpenMP originals index per-thread scratch state by omp_get_thread_num().
 * Here the same state is indexed by the OpenCilk worker number, and the number
 * of slots is the worker count chosen at run time (CILK_NWORKERS), so the old
 * "-t <threads>" arguments are only advisory.
 *
 * GB_REPEAT=<n> runs the timed kernel n times in one process (rep 0 .. n-1, so the input is loaded and
 * parsed once instead of once per trial) and reports every repetition on stderr as
 *   GB-KERNEL <name> <rep> <seconds>
 * Rep 0 is meant as the warm-up. Supported by every benchmark but kmer-cnt (a multi-pass pipeline whose
 * index is modified by each pass); state that the kernel modifies is restored outside the timed region.
 *
 * GB_LOOP_TRIPS(name, n) reports the trip count of a cilk_for on stderr as
 *   CILKFOR-ITERS <name> <n>
 * so a sweep can check how much parallelism each loop exposes. Define
 * GB_NO_LOOP_TRIPS to compile it out.
 */
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include <cilk/cilk.h>
#include <cilk/cilk_api.h>

/* Number of kernel repetitions requested by GB_REPEAT (1 if unset). */
static inline int gb_repeat(void) {
    const char *e = getenv("GB_REPEAT");
    int n = e ? atoi(e) : 1;
    return n > 0 ? n : 1;
}

static inline double gb_now(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (double)tv.tv_sec + (double)tv.tv_usec * 1e-6;
}

#define GB_KERNEL_TIME(name, rep, seconds) fprintf(stderr, "GB-KERNEL %s %d %.6f\n", (name), (rep), (seconds))

static inline int gb_num_workers(void) { return (int)__cilkrts_get_nworkers(); }

/* Worker slot of the calling strand: 0 <= id < gb_num_workers(). */
static inline int gb_worker_id(void) {
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    return (int)__cilkrts_get_worker_number();
#pragma GCC diagnostic pop
}

#ifndef GB_NO_LOOP_TRIPS
#define GB_LOOP_TRIPS(name, n) fprintf(stderr, "CILKFOR-ITERS %s %lld\n", (name), (long long)(n))
#else
#define GB_LOOP_TRIPS(name, n) ((void)0)
#endif

#endif
