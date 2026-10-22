//(c) 2016 by Authors
//This file is a part of ABruijn program.
//Released under the BSD license (see LICENSE file)

#include <vector>
#include <functional>
#include <atomic>
#include <thread>
#include "../cilk_util.h"

#include "progress_bar.h"

//simple thread pool implementation
//updateFun should be thread-safe!
template <class T>
void processInParallel(const std::vector<T>& scheduledTasks,
					   std::function<void(const T&)> updateFun,
					   size_t maxThreads, bool progressBar)
{
	if (scheduledTasks.empty()) return;

	ProgressPercent progress(scheduledTasks.size());
	if (progressBar) progress.advance(0);

	// one task per iteration, as with the original dynamic job queue; the
	// number of workers is set by CILK_NWORKERS, maxThreads is ignored
	GB_LOOP_TRIPS("kmer-cnt", scheduledTasks.size());
	cilk_for (size_t i = 0; i < scheduledTasks.size(); ++i)
	{
		updateFun(scheduledTasks[i]);
		if (progressBar) progress.advance();
	}
}

