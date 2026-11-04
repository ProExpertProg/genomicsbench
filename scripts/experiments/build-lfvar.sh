#!/bin/bash
# private variants of the LF runtime where a thief takes a larger share of the victim's remaining chunks.
# lf67: victim keeps floor(r/3), lf80: victim keeps floor(r/5) (the runtime keeps r/2). The installed builds are not touched.
set -e
SRC=~/OpenCilk/opencilk; W=~/gb/cl; mkdir -p $W; ln -sfn $SRC/cmake $W/cmake
export PATH=$HOME/OpenCilk/build/bin:$PATH CC=$HOME/OpenCilk/build/bin/clang CXX=$HOME/OpenCilk/build/bin/clang++
for v in "lf67 3" "lf80 5"; do set -- $v; name=$1; div=$2
  rm -rf $W/cheetah-$name; mkdir -p $W/cheetah-$name
  tar -C $SRC/cheetah --exclude='cmake-build-*' -cf - . | tar -C $W/cheetah-$name -xf -
  sed -i "s|uint64_t mid = (start + lf->end) / 2;|uint64_t mid = start + (lf->end - start) / $div;|" $W/cheetah-$name/runtime/loop-frames.c
  grep -n "uint64_t mid" $W/cheetah-$name/runtime/loop-frames.c
  cmake -S $W/cheetah-$name -B $W/cheetah-$name/cmake-build-release-lf -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCHEETAH_INCLUDE_TESTS=OFF -DCILK_DEFAULT_GRAINSIZE=2048 "-DCMAKE_C_FLAGS=-DCHEETAH_INTERNAL= -DINLINE_POP_LF=1" > $W/build-$name.log 2>&1
  ninja -C $W/cheetah-$name/cmake-build-release-lf >> $W/build-$name.log 2>&1
  ls $W/cheetah-$name/cmake-build-release-lf/lib/linux | grep -c "libopencilk"
done
echo BUILDVARDONE
