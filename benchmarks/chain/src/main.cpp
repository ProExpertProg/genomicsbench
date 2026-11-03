#include <cstdio>
#include <vector>
#include <time.h>
#include <sys/time.h>
#include <getopt.h>
#include <string>
#include <iostream>
#include "../../cilk_util.h"
#include "host_data_io.h"
#include "host_data.h"
#include "host_kernel.h"

// #define PRINT_OUTPUT 1

// #define VTUNE_ANALYSIS 1

#ifdef VTUNE_ANALYSIS
    #include <ittnotify.h>
#endif

void help() {
    std::cout <<
        "\n"
        "usage: ./chain [options ...]\n"
        "\n"
        "    options:\n"
        "        -i <input file>\n"
        "            default: NULL\n"
        "            the input anchor set\n"
        "        -o <output file>\n"
        "            default: NULL\n"
        "            the output scores, best predecessor set\n"
        "        -t <int>\n"
        "            default: 1\n"
        "            number of CPU threads\n"
        "        -h \n"
        "            prints the usage\n";
}


int main(int argc, char **argv) {
#ifdef VTUNE_ANALYSIS
    __itt_pause();
#endif
    FILE *in, *out;
    std::string inputFileName, outputFileName;

    int opt, numThreads = 1;
    while ((opt = getopt(argc, argv, ":i:o:t:h")) != -1) {
        switch (opt) {
            case 'i': inputFileName = optarg; break;
            case 'o': outputFileName = optarg; break;
            case 't': numThreads = atoi(optarg); break;
            case 'h': help(); return 0;
            default: help(); return 1;
        }
    }

    if (argc == 1 || argc != optind) {
        help();
        exit(EXIT_FAILURE);
    }

    fprintf(stderr, "Input file: %s\n", inputFileName.c_str());
    fprintf(stderr, "Output file: %s\n", outputFileName.c_str());

    in = fopen(inputFileName.c_str(), "r");
    out = fopen(outputFileName.c_str(), "w");

    std::vector<call_t> calls;
    std::vector<return_t> rets;

    for (call_t call = read_call(in);
            call.n != ANCHOR_NULL;
            call = read_call(in)) {
        calls.push_back(call);
    }

    rets.resize(calls.size());

    fprintf(stderr, "Running with threads: %d\n", gb_num_workers()); // -t is ignored (use CILK_NWORKERS)

    struct timeval start_time, end_time;
    double runtime = 0;

    gettimeofday(&start_time, NULL);
#ifdef VTUNE_ANALYSIS
    __itt_resume();
#endif
    for (int gb_rep = 0; gb_rep < gb_repeat(); gb_rep++) { // the kernel overwrites rets: safe to repeat
        const double gb_t0 = gb_now();
        host_chain_kernel(calls, rets, numThreads);
        GB_KERNEL_TIME("chain", gb_rep, gb_now() - gb_t0);
    }
#ifdef VTUNE_ANALYSIS
    __itt_pause();
#endif
    gettimeofday(&end_time, NULL);

    runtime += (end_time.tv_sec - start_time.tv_sec) * 1e6 + (end_time.tv_usec - start_time.tv_usec);
    
#ifdef PRINT_OUTPUT
    for (auto it = rets.begin(); it != rets.end(); it++) {
        print_return(out, *it);
    }
#endif

    fprintf(stderr, "Time in kernel: %.2f sec\n", runtime * 1e-6);

    fclose(in);
    fclose(out);

    return 0;
}
