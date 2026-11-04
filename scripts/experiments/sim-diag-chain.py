import importlib.util, random, heapq, numpy as np
spec=importlib.util.spec_from_file_location('sim','genomicsbench/scripts/sim-cilk-for.py'); sim=importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
cost=np.load('traces/chain-cost.npy'); n=len(cost); P=64; pre=np.concatenate([[0.0],np.cumsum(cost)]); ideal=cost.sum()/P

def run(policy, G, rng, chunks=None, frac=0.5):
    """returns span, list of (start, cost) per chunk; policy 'dc' or 'lf' on explicit chunk boundaries"""
    if policy=='dc':
        # reuse the DC simulator but record leaf starts
        dq=[[] for _ in range(P)]; ev=[]; idle=set(range(P)); starts=[]; span=0.0
        def start_task(w,t,lo,hi):
            nonlocal span
            while hi-lo>G:
                mid=lo+(hi-lo)//2; dq[w].append((mid,hi)); hi=mid
            f=t+pre[hi]-pre[lo]; span=max(span,f); starts.append((t,lo,hi)); heapq.heappush(ev,(f,w)); idle.discard(w)
        def feed(t):
            prog=True
            while prog and idle:
                prog=False
                for w in sorted(idle):
                    if dq[w]: lo,hi=dq[w].pop(); start_task(w,t,lo,hi); prog=True; continue
                    vs=[v for v in range(P) if dq[v]]
                    if vs: v=rng.choice(vs); lo,hi=dq[v].pop(0); start_task(w,t,lo,hi); prog=True
        start_task(0,0.0,0,n); feed(0.0)
        while ev:
            t,w=heapq.heappop(ev); idle.add(w); feed(t)
        return span,starts
    nch=len(chunks); ccost=np.array([pre[hi]-pre[lo] for lo,hi in chunks])
    rs=[0]*P; re=[0]*P; re[0]=nch; ev=[]; idle=set(range(P)); starts=[]; span=0.0
    def run_next(w,t):
        nonlocal span
        k=rs[w]; rs[w]+=1; f=t+ccost[k]; span=max(span,f); starts.append((t,chunks[k][0],chunks[k][1])); heapq.heappush(ev,(f,w)); idle.discard(w)
    def feed(t):
        prog=True
        while prog and idle:
            prog=False
            for w in sorted(idle):
                if rs[w]<re[w]: run_next(w,t); prog=True; continue
                vs=[v for v in range(P) if rs[v]<re[v]]
                if vs:
                    v=rng.choice(vs); mid=rs[v]+int(np.floor((re[v]-rs[v])*(1-frac))); rs[w],re[w]=mid,re[v]; re[v]=mid; run_next(w,t); prog=True
    run_next(0,0.0); feed(0.0)
    while ev:
        t,w=heapq.heappop(ev); idle.add(w); feed(t)
    return span,starts

def chunks_G(G): return [(k*G,min((k+1)*G,n)) for k in range(-(-n//G))]
def chunks_spread(G):                      # the spread-remainder branch: halve G if there is a remainder, spread what is left
    end,rem=divmod(n,G)
    if rem==0: return chunks_G(G)
    g=G>>1; end2,rem2=divmod(n,g); q,r2=divmod(rem2,end2); sizes=[g+q+(1 if i<r2 else 0) for i in range(end2)]
    b=np.concatenate([[0],np.cumsum(sizes)]); return [(int(b[i]),int(b[i+1])) for i in range(end2)]

def stats(policy,G,chunks,frac=0.5,trials=30,seed=1):
    rng=random.Random(seed); spans=[]; crit_cost=[]; crit_start=[]; nheavy_late=[]
    for _ in range(trials):
        span,starts=run(policy,G,rng,chunks,frac); spans.append(span)
        # critical iteration: the one with the latest end
        best=(0,0,0)
        for t,lo,hi in starts:
            tt=t
            for i in range(lo,hi):
                e=tt+cost[i]
                if e>best[0]: best=(e,cost[i],tt)
                tt=e
        crit_cost.append(best[1]); crit_start.append(best[2])
    return np.median(spans),np.median(crit_cost)*1e3,np.median(crit_start)

print(f"chain costs, P={P}, ideal span {ideal:.3f}s; columns: median span | cost (ms) and start time (s) of the iteration that ends last")
for G in (4,8,64):
    print(f"G={G}")
    for name,pol,ch,fr in (("DC",'dc',None,.5),("LF stock (chunks of G, thief takes 1/2)",'lf',chunks_G(G),.5),("LF spread-remainder branch (chunks ~G/2)",'lf',chunks_spread(G),.5),("LF stock, thief takes 4/5",'lf',chunks_G(G),.8)):
        s,c,st=stats(pol,G,ch,fr); print(f"   {name:44s} span {s:.3f}  last-ending iteration: {c:6.1f} ms starting at {st:.3f}s")
# does the effect need the heavy tail / index structure?
print("\ncontrols (G=8): LF stock / DC span ratio, and LF thief-4/5 / DC")
rng0=np.random.default_rng(0)
for lab,c in (("measured costs",cost),("costs shuffled",rng0.permutation(cost)),("uniform costs (all = mean)",np.full(n,cost.mean()))):
    cost=c; pre=np.concatenate([[0.0],np.cumsum(cost)])
    dc=stats('dc',8,None,trials=20)[0]; lf=stats('lf',8,chunks_G(8),.5,trials=20)[0]; lf8=stats('lf',8,chunks_G(8),.8,trials=20)[0]
    print(f"   {lab:28s} dc {dc:.3f} lf {lf:.3f} ({lf/dc:.3f}) lf80 {lf8:.3f} ({lf8/dc:.3f})  ideal {cost.sum()/P:.3f}")

print("\n=== structure of the chain costs along the index")
cost=np.load('traces/chain-cost.npy'); pre=np.concatenate([[0.0],np.cumsum(cost)])
lc=np.log(cost)
print("lag autocorrelation of log-cost:", {k: round(float(np.corrcoef(lc[:-k],lc[k:])[0,1]),3) for k in (1,2,4,8,16,64,256)})
for B in (1,8,64,512):
    bs=cost[:len(cost)//B*B].reshape(-1,B).sum(1); print(f"   blocks of {B:4d} iterations: coefficient of variation of the block cost {bs.std()/bs.mean():.3f}")
print("\ncontrols at G=8 (span ratios to DC, 20 trials):")
rng0=np.random.default_rng(1)
def blockshuf(c,B):
    nb=len(c)//B; idx=np.arange(nb*B).reshape(nb,B); p=rng0.permutation(nb); out=np.concatenate([c[idx[i]] for i in p]); return np.concatenate([out,c[nb*B:]])
for lab,c in (("measured",cost),("reversed index",cost[::-1].copy()),("shuffled",rng0.permutation(cost)),("block-shuffled (64)",blockshuf(cost,64)),("block-shuffled (8)",blockshuf(cost,8)),("sorted ascending",np.sort(cost)),("sorted descending",np.sort(cost)[::-1].copy())):
    cost=c; pre=np.concatenate([[0.0],np.cumsum(cost)])
    dc=stats('dc',8,None,trials=20)[0]; lf=stats('lf',8,chunks_G(8),.5,trials=20)[0]; lf8=stats('lf',8,chunks_G(8),.8,trials=20)[0]
    print(f"   {lab:22s} dc {dc:.3f}  lf {lf:.3f} ({lf/dc:.3f})  lf80 {lf8:.3f} ({lf8/dc:.3f})")
