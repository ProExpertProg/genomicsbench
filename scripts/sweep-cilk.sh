#!/bin/bash
# Sweep the OpenCilk ports of the GenomicsBench CPU kernels over
#   * C: the compile-time loop coarsening factor (-mllvm -stripmine-coarsen-factor=C), and
#   * G: the runtime grainsize (CILK_GRAINSIZE=G; "default" leaves it unset),
# and print one CSV row per run. It can also just report loop trip counts.
#
# Usage: sweep-cilk.sh [options]
#   -i <dir>   input-datasets directory                  (default: ../../input-datasets, or $INPUTS_DIR)
#   -s <size>  small | large                              (default: small)
#   -b <list>  benchmarks, space/comma separated          (default: all of them)
#   -c <list>  coarsening factors                         (default: "1 4 16 64")
#   -g <list>  runtime grainsizes, "default" allowed      (default: "default 1 2 4 8 16 64 256")
#   -w <n>     CILK_NWORKERS                              (default: nproc)
#   -n <n>     repetitions per configuration              (default: 3)
#   -o <dir>   output directory (binaries, logs, CSV)     (default: ./sweep-out)
#   -t <sec>   timeout per run                            (default: 900)
#   -p         pin workers to cores 0..w-1 with taskset
#   -T         trip counts only: run each benchmark once with 2 workers and
#              print the CILKFOR-ITERS lines (no sweep, no CSV)
#   -B         build only
#   -h         this help
#
# Environment:
#   CLANG_BIN_DIR     directory of the OpenCilk clang/clang++    (default: dir of `clang` in PATH)
#   RESOURCE_DIR      --opencilk-resource-dir to use             (default: the toolchain's own)
#   CHEETAH_BUILD     a cheetah build dir; if set (and RESOURCE_DIR is not), a resource dir
#                     with that runtime is made with make-resource-dir.sh. The runtime must be
#                     built with -DCILK_DEFAULT_GRAINSIZE=<n>, or CILK_GRAINSIZE is ignored.
#   TOOLCHAIN_RD      toolchain resource dir used with CHEETAH_BUILD (default: <clang>/../lib/clang/*)
#   CPATH, LIBRARY_PATH   extra header/library search paths for the benchmark builds
#
# CSV columns: bench,size,coarsen,grainsize,workers,rep,wall_s,kernel_s,iters,status
#   kernel_s is the time the benchmark reports for its parallel kernel; iters is
#   the trip count printed by GB_LOOP_TRIPS (several loops/calls are joined with '+').
# Every benchmark ignores its own thread-count argument: the worker count is CILK_NWORKERS.
#
# Needs: the benchmarks' dependencies built (see the top-level README / Makefile).

set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname "$here")

inputs=${INPUTS_DIR:-$root/../input-datasets}
size=small
benches="fmi bsw phmm dbg chain poa pileup kmer-cnt"
coarsen="1 4 16 64"
grains="default 1 2 4 8 16 64 256"
workers=$(nproc)
reps=3
out=./sweep-out
tmo=900
pin=0
trips_only=0
build_only=0

while getopts "i:s:b:c:g:w:n:o:t:pTBh" opt; do
    case $opt in
        i) inputs=$OPTARG ;;
        s) size=$OPTARG ;;
        b) benches=${OPTARG//,/ } ;;
        c) coarsen=${OPTARG//,/ } ;;
        g) grains=${OPTARG//,/ } ;;
        w) workers=$OPTARG ;;
        n) reps=$OPTARG ;;
        o) out=$OPTARG ;;
        t) tmo=$OPTARG ;;
        p) pin=1 ;;
        T) trips_only=1 ;;
        B) build_only=1 ;;
        h) sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) exit 1 ;;
    esac
done

[[ $size == small || $size == large ]] || { echo "-s must be small or large" >&2; exit 1; }
inputs=$(realpath "$inputs")
mkdir -p "$out"; out=$(realpath "$out")
mkdir -p "$out/bin" "$out/logs"

clang_dir=${CLANG_BIN_DIR:-$(dirname "$(command -v clang)")}
CC=$clang_dir/clang
CXX=$clang_dir/clang++

# ---- resource dir -----------------------------------------------------------
rd=${RESOURCE_DIR:-}
if [[ -z $rd && -n ${CHEETAH_BUILD:-} ]]; then
    tc=${TOOLCHAIN_RD:-$(ls -d "$clang_dir"/../lib/clang/* | head -1)}
    "$here/make-resource-dir.sh" "$tc" "$CHEETAH_BUILD" "$out/rd" || exit 1
    rd=$out/rd
fi
cilk_flags="-fopencilk -mllvm -cilk-use-runtime-cilkfor"
[[ -n $rd ]] && cilk_flags="$cilk_flags --opencilk-resource-dir=$rd"

# ---- how each benchmark is built and run ------------------------------------
# exe name inside benchmarks/<b>/
exe_of() { case $1 in kmer-cnt) echo kmer-cnt ;; *) echo "$1" ;; esac; }

# run command (relative to benchmarks/<b>), with $1 = binary path
run_cmd() {
    local b=$1 bin=$2 d=$inputs
    case $b in
    fmi)
        if [[ $size == large ]]; then echo "$bin $d/fmi/broad $d/fmi/large/SRR7733443_10m_1.fastq 512 19 1"
        else echo "$bin $d/fmi/broad $d/fmi/small/SRR7733443_1m_1.fastq 512 19 1"; fi ;;
    bsw)
        if [[ $size == large ]]; then echo "$bin -pairs $d/bsw/large/bandedSWA_SRR7733443_1m_input.txt -t 1 -b 512"
        else echo "$bin -pairs $d/bsw/small/bandedSWA_SRR7733443_100k_input.txt -t 1 -b 512"; fi ;;
    phmm)
        if [[ $size == large ]]; then echo "$bin -f $d/phmm/large/large.in -t 1"
        else echo "$bin -f $d/phmm/small/5m.in -t 1"; fi ;;
    dbg)
        if [[ $size == large ]]; then echo "$bin $d/dbg/large/ERR194147-mem2-chr22.bam chr22:0-50818468 $d/dbg/large/Homo_sapiens_assembly38.fasta 1"
        else echo "$bin $d/dbg/small/ERR194147-mem2-chr22.bam chr22:16000000-16500000 $d/dbg/large/Homo_sapiens_assembly38.fasta 1"; fi ;;
    chain)
        if [[ $size == large ]]; then echo "$bin -i $d/chain/large/c_elegans_40x.10k.in -o /dev/null"
        else echo "$bin -i $d/chain/small/in-1k.txt -o /dev/null"; fi ;;
    poa)
        if [[ $size == large ]]; then echo "$bin -s $d/poa/large/input.fasta -t 1"
        else echo "$bin -s $d/poa/small/input-1000.fasta -t 1"; fi ;;
    pileup)
        if [[ $size == large ]]; then echo "$bin $d/pileup/large/HG002_prom_R941_guppy360_2_GRCh38_ch20.bam chr20:1-64444167 1"
        else echo "$bin $d/pileup/small/saureus.bam tig00000061:1-1499707 1"; fi ;;
    kmer-cnt)
        local cfg=$root/tools/Flye/flye/config/bin_cfg/asm_raw_reads.cfg
        if [[ $size == large ]]; then echo "$bin --reads $d/kmer-cnt/large/Loman_E.coli_MAP006-1_2D_50x.fasta --config $cfg --threads 1 --debug"
        else echo "$bin --reads $d/kmer-cnt/small/Loman_E.coli_MAP006-1_2D_50x_1000.fasta --config $cfg --threads 1 --debug"; fi ;;
    *) echo "unknown benchmark $b" >&2; return 1 ;;
    esac
}

# kernel seconds from a log, empty if not found
kernel_time() {
    local b=$1 log=$2
    case $b in
        bsw) grep -oE 'Overall SW cycles = [0-9]+, [0-9.]+ s' "$log" | tail -1 | sed -E 's/.*, ([0-9.]+) s/\1/' ;;
        fmi) grep -oE 'Consumed: [0-9]+ cycles, [0-9.]+ sec' "$log" | tail -1 | sed -E 's/.*, ([0-9.]+) sec/\1/' ;;
        poa) grep -oE 'Runtime: [0-9.]+,' "$log" | tail -1 | sed -E 's/Runtime: ([0-9.]+),/\1/' ;;
        *)   grep -oE '(Kernel runtime|Kernel time|Time in kernel): [0-9.]+' "$log" | tail -1 | sed -E 's/.*: ([0-9.]+)/\1/' ;;
    esac
}

# trip counts: "name:n1+n2" per loop name in a log (progress bars may share a line, hence -o)
trip_counts() {
    grep -oE 'CILKFOR-ITERS [^ ]+ [0-9]+' "$1" | awk '{ a[$2] = a[$2] (a[$2] == "" ? "" : "+") $3 } END { for (k in a) printf "%s%s:%s", (n++ ? ";" : ""), k, a[k] }'
}

# ---- build ------------------------------------------------------------------
build() {
    local b=$1 c=$2 bin=$out/bin/$1-c$2
    [[ -x $bin ]] && return 0
    local cc=$CC
    [[ $b == phmm ]] && cc=$CXX      # its Makefile compiles C++ through $(CC)
    echo "build $b C=$c" >&2
    if make -C "$root/benchmarks/$b" -B -j"$(nproc)" CXX="$CXX" CC="$cc" arch=avx2 \
            CILK_FLAGS="$cilk_flags -mllvm -stripmine-coarsen-factor=$c" > "$out/logs/build-$b-c$c.log" 2>&1; then
        cp "$root/benchmarks/$b/$(exe_of "$b")" "$bin"
    else
        echo "  BUILD FAILED: $b C=$c (see $out/logs/build-$b-c$c.log)" >&2
        return 1
    fi
}

run_one() {  # bench coarsen grain rep workers
    local b=$1 c=$2 g=$3 rep=$4 w=$5
    local bin=$out/bin/$b-c$c log=$out/logs/run-$b-c$c-g$g-w$w-r$rep.log
    local cmd; cmd=$(run_cmd "$b" "$bin") || return 1
    local env=(CILK_NWORKERS="$w")
    [[ $g != default ]] && env+=(CILK_GRAINSIZE="$g")
    local pre=()
    (( pin )) && pre=(taskset -c "0-$((w - 1))")
    local t0=$EPOCHREALTIME
    env LD_LIBRARY_PATH="$root/tools/GKL/build/native:${LD_LIBRARY_PATH:-}" "${env[@]}" \
        timeout "$tmo" "${pre[@]}" $cmd > "$log" 2>&1
    local st=$?
    local t1=$EPOCHREALTIME
    local wall; wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.3f", b - a }')
    local status=ok
    (( st == 124 )) && status=timeout
    (( st != 0 && st != 124 )) && status=exit$st
    echo "$b,$size,$c,$g,$w,$rep,$wall,$(kernel_time "$b" "$log"),$(trip_counts "$log"),$status"
}

# ---- main -------------------------------------------------------------------
if (( trips_only )); then
    for b in $benches; do
        build "$b" 1 || continue
        run_one "$b" 1 default 0 2 > /dev/null
        printf '%-9s %s\n' "$b" "$(trip_counts "$out/logs/run-$b-c1-gdefault-w2-r0.log")"
    done
    exit 0
fi

for b in $benches; do
    for c in $coarsen; do build "$b" "$c" || true; done
done
(( build_only )) && exit 0

csv=$out/results.csv
[[ -s $csv ]] || echo "bench,size,coarsen,grainsize,workers,rep,wall_s,kernel_s,iters,status" > "$csv"
for b in $benches; do
    for c in $coarsen; do
        [[ -x $out/bin/$b-c$c ]] || continue
        for g in $grains; do
            for ((rep = 1; rep <= reps; rep++)); do
                run_one "$b" "$c" "$g" "$rep" "$workers" | tee -a "$csv"
            done
        done
    done
done
echo "results: $csv" >&2
