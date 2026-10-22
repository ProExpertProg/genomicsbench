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
 * GB_LOOP_TRIPS(name, n) reports the trip count of a cilk_for on stderr as
 *   CILKFOR-ITERS <name> <n>
 * so a sweep can check how much parallelism each loop exposes. Define
 * GB_NO_LOOP_TRIPS to compile it out.
 */
#include <stdio.h>
#include <cilk/cilk.h>
#include <cilk/cilk_api.h>

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
