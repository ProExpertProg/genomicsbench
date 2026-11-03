#!/bin/bash
# Compare the loop-frame (lf) and divide-and-conquer (dc) cilk_for runtimes on the OpenCilk ports of the GenomicsBench
# kernels, for the full datasets, over worker counts and runtime grainsizes (CILK_GRAINSIZE).
#
# As in run-pbbsv2.sh / job.sh: dc runs each grainsize G, lf runs G and G/2 (the effective grainsize of dc is between G/2 and
# G), workers are pinned with the same rule (second NUMA node if they fit there, else the first cores), the address space is
# not randomised (setarch -R) and a session probe brackets every block. Unlike job.sh the two runtimes are interleaved per
# grainsize: for every G the order is dc@G, lf@G, lf@G/2 (a point is run once), so a comparison never spans more than a
# few runs.
#
# Every benchmark except kmer-cnt is run as ONE process per configuration with GB_REPEAT=<trials+1>: the input is loaded
# once, repetition 0 is the warm-up and is dropped, repetitions 1..trials are the results (see benchmarks/cilk_util.h).
# kmer-cnt cannot repeat its kernel and gets trials+1 processes. The benchmarks with the longest input loading run last.
#
# Usage: sweep-lfdc.sh [options]
#   -i <dir>   input-datasets directory                                  [~/gb/data/input-datasets]
#   -B <dir>   cheetah checkout, config <c> is its cmake-build-release-<c> [~/OpenCilk/opencilk/cheetah]
#   -T <dir>   OpenCilk toolchain install (bin/clang)                    [~/OpenCilk/build]
#   -o <dir>   output: binaries, logs, results.csv                       [~/logs/<yymmdd>-genomicsbench]
#   -b <list>  benchmarks, in this order   [phmm,poa,kmer-cnt,pileup,bsw,dbg,fmi,chain]
#   -g <list>  grainsizes G                                               [1,2,4,8,16,64]
#   -w <list>  worker counts                                              [128,64,32]
#   -x <n>     trials (after one warm-up)                                 [10]
#   -r <list>  runtime configs                                            [dc,lf]
#   -t <sec>   timeout per process                                        [3600]
#   -b/-g/-w/... can be combined with:
#   -n         print the schedule (processes, no run)
#   -C         only build the binaries
#   -S         do not build (use the binaries already in <out>/bin)
# The run is resumable: a (benchmark, config, workers, grainsize) whose trials are all in results.csv is skipped.
# CSV: bench,config,workers,grain,trial,kernel_s,iters   (trial 1..n; kmer-cnt rows come from separate processes)

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname "$here")
inputs=~/gb/data/input-datasets cheetah=~/OpenCilk/opencilk/cheetah tapir=~/OpenCilk/build out=
benches=phmm,poa,kmer-cnt,pileup,bsw,dbg,fmi,chain grains=1,2,4,8,16,64 workers=128,64,32 trials=10 configs=dc,lf
tmo=3600 dry=0 build_only=0 skip_build=0
while getopts i:B:T:o:b:g:w:x:r:t:nCS o; do case $o in
    i) inputs=$OPTARG;; B) cheetah=$OPTARG;; T) tapir=$OPTARG;; o) out=$OPTARG;; b) benches=$OPTARG;; g) grains=$OPTARG;;
    w) workers=$OPTARG;; x) trials=$OPTARG;; r) configs=$OPTARG;; t) tmo=$OPTARG;; n) dry=1;; C) build_only=1;; S) skip_build=1;;
    *) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2;;
esac; done
inputs=$(realpath "$inputs"); cheetah=$(realpath "$cheetah"); tapir=$(realpath "$tapir")
[ -n "$out" ] || out=~/logs/$(date +%y%m%d)-genomicsbench
mkdir -p "$out/bin" "$out/logs"; out=$(realpath "$out")
csv=$out/results.csv
fl=$root/tools/Flye/flye/config/bin_cfg/asm_raw_reads.cfg

cmd() { # <bench> <binary>: the command line of the full-size run
    local d=$inputs
    case $1 in
    fmi)      echo "$2 ${FMI_INDEX:-$d/fmi/broad} $d/fmi/large/SRR7733443_10m_1.fastq 512 19 1";;
    bsw)      echo "$2 -pairs $d/bsw/large/bandedSWA_SRR7733443_1m_input.txt -t 1 -b 512";;
    phmm)     echo "$2 -f $d/phmm/large/large.in -t 1";;
    dbg)      echo "$2 $d/dbg/large/ERR194147-mem2-chr22.bam chr22:0-50818468 $d/dbg/large/Homo_sapiens_assembly38.fasta 1";;
    chain)    echo "$2 -i $d/chain/large/c_elegans_40x.10k.in -o /dev/null";;
    poa)      echo "$2 -s $d/poa/large/input.fasta -t 1";;
    pileup)   echo "$2 $d/pileup/large/HG002_prom_R941_guppy360_2_GRCh38_ch20.bam chr20:1-64444167 1";;
    kmer-cnt) echo "$2 --reads $d/kmer-cnt/large/Loman_E.coli_MAP006-1_2D_50x.fasta --config $fl --threads 1 --debug";;
    *) echo "unknown benchmark $1" >&2; return 1;;
    esac
}

build() { # <config>
    local c=$1 b cc rd; rd=$(realpath "$cheetah/cmake-build-release-$c") || return 1
    mkdir -p "$out/bin/$c"
    for b in ${benches//,/ }; do
        cc=$tapir/bin/clang; [ "$b" = phmm ] && cc=$tapir/bin/clang++   # its Makefile compiles C++ through $(CC)
        echo "build $c $b"
        make -C "$root/benchmarks/$b" -B -j"$(nproc)" CXX="$tapir/bin/clang++" CC="$cc" arch=avx2 \
            CILK_FLAGS="-fopencilk -mllvm -cilk-use-runtime-cilkfor --opencilk-resource-dir=$rd" > "$out/logs/build-$c-$b.log" 2>&1 \
            && cp "$root/benchmarks/$b/$b" "$out/bin/$c/$b" || { echo "BUILD FAILED: $c $b"; return 1; }
    done
}

# Pin P workers to the second NUMA node (cores N/2..N/2+P-1) if they fit there, else to cores 0..P-1 (SMT must be off).
pin() { local n; n=$(getconf _NPROCESSORS_ONLN); local f=0; [ "$1" -le $((n / 2)) ] && f=$((n / 2)); echo $f-$((f + $1 - 1)); }

session_probe() { [ -x ~/session-probe ] && ~/session-probe 2>&1; true; }

done_trials() { # <bench> <config> <workers> <grain>: trials already in the csv
    [ -f "$csv" ] || { echo 0; return; }
    awk -F, -v b="$1" -v c="$2" -v w="$3" -v g="$4" '$1 == b && $2 == c && $3 == w && $4 == g { n++ } END { print n + 0 }' "$csv"
}

# One process (or trials+1 for kmer-cnt) for <bench> <config> <workers> <grain>.
point() {
    local b=$1 c=$2 w=$3 g=$4 bin=$out/bin/$c/$1 log reps rc k t=0 prefix
    [ "$(done_trials "$b" "$c" "$w" "$g")" -ge "$trials" ] && return 0
    prefix="$out/logs/run-$b-$c-w$w-g$g"
    reps=$((trials + 1))
    local procs=1 rep_env=$reps
    [ "$b" = kmer-cnt ] && { procs=$reps; rep_env=1; }
    local p
    for ((p = 0; p < procs; p++)); do
        log=$prefix-p$p.log
        echo "== $b $c workers=$w grain=$g process $((p + 1))/$procs $(date +%T)"
        env GB_REPEAT=$rep_env CILK_NWORKERS=$w CILK_GRAINSIZE=$g LD_LIBRARY_PATH=$root/tools/GKL/build/native \
            setarch x86_64 -R taskset -c "$(pin "$w")" ionice -c 2 -n 0 timeout "$tmo" $(cmd "$b" "$bin") > "$log" 2>&1
        rc=$?
        if [ $rc -ne 0 ]; then echo "FAILED rc=$rc: $b $c w=$w g=$g (see $log)"; return 1; fi
        local iters; iters=$(grep -oE 'CILKFOR-ITERS [^ ]+ [0-9]+' "$log" | sort -u | awk '{ a = a (a == "" ? "" : "+") $3 } END { print a }')
        if [ "$b" = kmer-cnt ]; then
            # one run per process: the kernel time the benchmark reports; process 0 is the warm-up
            k=$(grep -oE 'Kernel time: [0-9.]+' "$log" | tail -1 | awk '{ print $3 }')
            [ -n "$k" ] || { echo "NO KERNEL TIME: $log"; return 1; }
            [ $p -gt 0 ] && echo "$b,$c,$w,$g,$p,$k,$iters" >> "$csv"
        else
            # GB-KERNEL <bench> <rep> <seconds>; rep 0 is the warm-up
            local n; n=$(grep -c '^GB-KERNEL ' "$log")
            [ "$n" = "$reps" ] || { echo "EXPECTED $reps GB-KERNEL lines, got $n: $log"; return 1; }
            grep '^GB-KERNEL ' "$log" | awk -v b="$b" -v c="$c" -v w="$w" -v g="$g" -v it="$iters" '$3 > 0 { print b "," c "," w "," g "," $3 "," $4 "," it }' >> "$csv"
        fi
    done
}

grains_of() { # <config> <G>: grainsizes run for G (G/2 too for lf, if it is not run for another G of the list)
    echo "$2"
    [ "$1" = lf ] && [ "$2" -ge 2 ] && echo $(($2 / 2))
}

schedule() { # prints "bench config workers grain" in execution order, each point once
    local b w g c x; declare -A seen
    for b in ${benches//,/ }; do
        for w in ${workers//,/ }; do
            for g in ${grains//,/ }; do
                for c in ${configs//,/ }; do
                    for x in $(grains_of "$c" "$g"); do
                        [ -n "${seen[$b $c $w $x]}" ] && continue
                        seen[$b $c $w $x]=1; echo "$b $c $w $x"
                    done
                done
            done
        done
    done
}

if [ $dry = 1 ]; then
    schedule | awk '{ print } END { print NR " points" > "/dev/stderr" }'
    exit 0
fi

date; echo "Arguments: $*"
if [ $skip_build = 0 ]; then for c in ${configs//,/ }; do build "$c" || exit 1; done; fi
[ $build_only = 1 ] && exit 0
[ "$(getconf _NPROCESSORS_ONLN)" = 128 ] || echo "WARNING: $(getconf _NPROCESSORS_ONLN) cores online, expected 128 (run bench_prepare_amd.sh)"
[ -f "$csv" ] || echo "bench,config,workers,grain,trial,kernel_s,iters" > "$csv"

rc=0 prev=
while read -r b c w g; do
    key="$b $w"
    if [ "$key" != "$prev" ]; then [ -n "$prev" ] && session_probe; session_probe; prev=$key; fi
    point "$b" "$c" "$w" "$g" || rc=1
done < <(schedule)
session_probe
echo "ALLDONE rc=$rc $(date)"
exit $rc
