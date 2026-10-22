#!/bin/bash
# Build an --opencilk-resource-dir that is the toolchain's own resource dir with
# the OpenCilk runtime libraries replaced by a cheetah build.
#
#   make-resource-dir.sh <toolchain resource dir> <cheetah build dir> <output dir>
#
# e.g. make-resource-dir.sh ~/OpenCilk/build/lib/clang/19 ~/cheetah/build-release ./rd
#
# The inlined ABI bitcode references runtime symbols that are hidden in the
# shared library (e.g. default_grainsize), so benchmarks must link the static
# runtime. The driver names libopencilk*.so explicitly, so those files are
# replaced by linker scripts that pull in the cheetah .a archives.
set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <toolchain resource dir> <cheetah build dir> <output dir>" >&2
    exit 1
fi
tc=$(realpath "$1"); cheetah=$(realpath "$2"); out=$3
triple=x86_64-unknown-linux-gnu

rm -rf "$out"
mkdir -p "$out/lib/$triple"
for entry in "$tc"/*; do
    [[ $(basename "$entry") == lib ]] || ln -s "$entry" "$out/$(basename "$entry")"
done
for f in "$tc/lib/$triple"/*; do
    case $(basename "$f") in libopencilk*) continue;; esac
    ln -s "$f" "$out/lib/$triple/$(basename "$f")"
done
# cheetah names its libraries libopencilk*-x86_64.*; the driver expects libopencilk*.*
for f in "$cheetah"/lib/linux/libopencilk*-x86_64.*; do
    base=$(basename "$f")
    case $base in
        *.so.*) ;;                                  # versioned names are not used
        *.so) printf 'INPUT(%s)\n' "${f%.so}.a" > "$out/lib/$triple/${base/-x86_64.so/.so}" ;;
        *) ln -sf "$f" "$out/lib/$triple/${base/-x86_64./.}" ;;
    esac
done
echo "resource dir: $(realpath "$out")"
