import importlib.util, random, numpy as np
src=open('/home/luka/.claude/jobs/099eeab7/tmp/sim-diag.py').read().split('print(f"chain costs')[0]
exec(src)                      # defines run/stats/chunks_G with the module-level cost/pre
orig=np.load('traces/chain-cost.npy')
def setcost(c):
    global cost, pre
    cost=c; pre=np.concatenate([[0.0],np.cumsum(c)])
rng=np.random.default_rng(7)
for G in (4,8,64):
    ratios=[]; ratios80=[]; dcs=[]; lfs=[]
    for k in range(40):
        setcost(rng.permutation(orig))
        dc=stats('dc',G,None,trials=4,seed=k)[0]; lf=stats('lf',G,chunks_G(G),.5,trials=4,seed=k)[0]; lf8=stats('lf',G,chunks_G(G),.8,trials=4,seed=k)[0]
        ratios.append(lf/dc); ratios80.append(lf8/dc); dcs.append(dc); lfs.append(lf)
    r=np.array(ratios); r8=np.array(ratios80)
    print(f"G={G:<2d} over 40 random arrangements of the same costs: LF/DC mean {r.mean():.3f} (std {r.std():.3f}, range {r.min():.3f}-{r.max():.3f}), LF80/DC mean {r8.mean():.3f}; mean spans dc {np.mean(dcs):.3f} lf {np.mean(lfs):.3f}")
setcost(orig)
print("measured arrangement (30 trials):", {G:(round(stats('dc',G,None,trials=30)[0],3), round(stats('lf',G,chunks_G(G),.5,trials=30)[0],3)) for G in (4,8,64)})
