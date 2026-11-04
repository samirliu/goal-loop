# One source of truth for status advice. Inputs: scores.rec, loop-log.md.
# A score is the AFTER measurement: delta(t) belongs to strategy(t).
# This is local observational evidence, never causal proof or gate authority.
function abs(x) { return x < 0 ? -x : x }
function numeric(x) { return x ~ /^-?[0-9]+(\.[0-9]+)?$/ }
FILENAME == ARGV[1] {
    line=$0; sub(/\r$/, "", line); split(line, a, "|")
    if (a[1] ~ /^[0-9]+$/) {
        it=a[1]+0
        # Latest invalid measurement breaks the chain, rather than reviving
        # an older numeric row for the same iteration.
        delete SC[it]
        if (numeric(a[2])) SC[it]=a[2]+0
    }
    next
}
{
    line=$0; sub(/\r$/, "", line)
    if (line ~ /^## iteration/) {
        num=line; sub(/^[^0-9]+/, "", num); num+=0
        if (!(cur>0 && ORD[cur]==num)) cur++
        STRAT[cur]="none"; TASK[cur]=""; ORD[cur]=num; blk=cur
        next
    }
    p=index(line, "=")
    if (p>1 && cur>0) {
        k=substr(line,1,p-1); v=substr(line,p+1)
        sub(/^ +/, "", v); sub(/ +$/, "", v)
        if (k=="strategy") STRAT[cur]=(v=="" ? "none" : v)
        if (k=="task") TASK[cur]=v
    }
}
END {
    for (k in SC) sn++
    if (!sn) advice="CTL: EFFICIENCY score-data: none recorded\n"
    for (i=1; i<=blk; i=j+1) {
        j=i
        while (j<blk && STRAT[j+1]==STRAT[i]) j++
        lab=STRAT[i]
        if (lab=="none") continue
        labeled=1
        if (!(lab in SEEN)) { SEEN[lab]=1; LABEL[++nl]=lab }
        # Most recent window supersedes an earlier success/failure of this
        # label. Within it, a missing measurement resets evidence as well.
        n=0; gain=0; start=0; finish=0
        for (q=i; q<=j; q++) {
            it=ORD[q]
            if (q>1 && ORD[q-1]==it-1 && (it in SC) && ((it-1) in SC)) {
                if (!n) { start=SC[it-1]; lo=start; hi=start }
                finish=SC[it]; gain+=finish-SC[it-1]; n++
                if (finish<lo) lo=finish
                if (finish>hi) hi=finish
            } else { n=0; gain=0; start=0; finish=0 }
        }
        ACT[lab]="unmeasured"; RATE[lab]=0
        if (n) {
            band=tol*(abs(start)>abs(finish) ? abs(start) : abs(finish))
            directed=(obj=="minimize" ? -gain : gain)
            RATE[lab]=directed/n
            if (directed>band) ACT[lab]="exploit"
            else if (directed < -band || (n>=3 && hi-lo<=band)) ACT[lab]="prune"
            else ACT[lab]="observe"
            if (uncertain+0) ACT[lab]="observe"
            adv=(ACT[lab]=="exploit" ? " -> exploit" : (ACT[lab]=="prune" ? " -> prune" : ""))
            if (uncertain+0) adv=" noise-unverified"
            if (ACT[lab]=="prune" && directed>=-band) adv=adv sprintf(" (flat %d iters)", n)
            advice=advice sprintf("CTL: EFFICIENCY strategy=%s %+.1f /%d iters%s\n", lab, gain/n, n, adv)
        } else advice=advice sprintf("CTL: EFFICIENCY strategy=%s n=0 unmeasured\n", lab)
    }
    prefer="none"; avoid="none"
    for (i=1; i<=nl; i++) {
        lab=LABEL[i]
        if (ACT[lab]=="exploit" && (prefer=="none" || RATE[lab]>best)) { prefer=lab; best=RATE[lab] }
        if (ACT[lab]=="prune") avoid=(avoid=="none" ? lab : avoid "," lab)
    }
    if (obj!="none" && labeled)
        printf "CTL: STRATEGY-PICK prefer=%s avoid=%s\n", prefer, avoid
    printf "%s", advice
    if (stalled+0) {
        # Only the latest THREE ADJACENT ledger rounds can establish flatness.
        if (obj!="none" && blk>=3) {
            ia=ORD[blk-2]; ib=ORD[blk-1]; ic=ORD[blk]
            if (ib==ia+1 && ic==ib+1 && (ia in SC) && (ib in SC) && (ic in SC)) {
                lo=SC[ia]; hi=lo
                if (SC[ib]<lo) lo=SC[ib]
                if (SC[ib]>hi) hi=SC[ib]
                if (SC[ic]<lo) lo=SC[ic]
                if (SC[ic]>hi) hi=SC[ic]
                if (hi-lo<=tol*(abs(lo)>abs(hi) ? abs(lo) : abs(hi)))
                    print "CTL: eval-gap: objective scores flat while stalled - inspect raw failures; dispatch goal-critic for candidate AC proposals into .goal/proposals/ (user-approved, not applied)"
            }
        }
        prev=""; run=0
        for (q=1; q<=blk; q++) {
            id=TASK[q]; sub(/\[.*/, "", id)
            if (id ~ /^T[0-9]+$/) {
                if (id==prev) run++; else { prev=id; run=1 }
                if (run==3) print "CTL: promote: " id " (3 consecutive waves) - consider a role-card promotion for this task domain"
            } else { prev=""; run=0 }
        }
    }
    if (obj!="none" && blk && !labeled)
        print "CTL: attribution-unused: no --strategy labels recorded - per-strategy attribution is empty"
}
