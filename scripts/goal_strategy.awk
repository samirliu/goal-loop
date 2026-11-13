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
        STRAT[cur]="none"; TASK[cur]=""; ART[cur]=""; CLAIM[cur]=0; ORD[cur]=num; blk=cur
        next
    }
    p=index(line, "=")
    if (p>1 && cur>0) {
        k=substr(line,1,p-1); v=substr(line,p+1)
        sub(/^ +/, "", v); sub(/ +$/, "", v)
        if (k=="strategy") STRAT[cur]=(v=="" ? "none" : v)
        if (k=="task") TASK[cur]=v
        if (k=="digest") ART[cur]=v
        if (k=="exit_signal") CLAIM[cur]=(v=="yes")
    }
}
END {
    last=""; versions=0; unchanged=0; restored=0; unknown=0; claims=0; artifact_stall=0; information=0; legacy=0
    for (q=1; q<=blk; q++) {
        claims+=CLAIM[q]
        d=ART[q]
        if (d=="") { unknown++; last=""; NEW[q]=0; continue }
        if (d !~ /^v2-[0-9a-f]{64}$/) legacy=1
        if (last==d) {
            unchanged++; artifact_stall++; NEW[q]=0
            if ((ORD[q] in SC) && (ORD[q-1] in SC) && SC[ORD[q]]!=SC[ORD[q-1]]) information++
        } else if (d in SEEN_ART && last!="") { restored++; artifact_stall++; NEW[q]=0 }
        else if (d in SEEN_ART) { unknown++; NEW[q]=0 }
        else { versions++; SEEN_ART[d]=1; artifact_stall=0; NEW[q]=1 }
        last=d
    }
    printf "CTL: EVENTS artifact-versions=%d acceptance-claims=%d unchanged-artifact-rounds=%d restorations=%d unknown-artifact-rounds=%d artifact-stagnation=%d measurement-revisions=%d digest-scope=%s\n", versions, claims, unchanged, restored, unknown, artifact_stall, information, (legacy ? "legacy-unverified" : (unknown ? "incomplete" : "content-v2"))
    # Event accounting is always useful; policy advice remains conditional.
    if (obj=="none" && !(stalled+0)) exit
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
            # No new artifact means no artifact-strategy credit. Score changes
            # can be new information; a restored artifact is recovery, not a
            # fresh policy win. Missing identities break attribution as well.
            if (q>1 && NEW[q] && ART[q-1]!="" && ORD[q-1]==it-1 && (it in SC) && ((it-1) in SC)) {
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
            if (NEW[blk-2] && NEW[blk-1] && NEW[blk] && ib==ia+1 && ic==ib+1 && (ia in SC) && (ib in SC) && (ic in SC)) {
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
            if (NEW[q] && id ~ /^T[0-9]+$/) {
                if (id==prev) run++; else { prev=id; run=1 }
                if (run==3) print "CTL: promote: " id " (3 consecutive waves) - consider a role-card promotion for this task domain"
            } else { prev=""; run=0 }
        }
    }
    if (obj!="none" && blk && !labeled)
        print "CTL: attribution-unused: no --strategy labels recorded - per-strategy attribution is empty"
}
