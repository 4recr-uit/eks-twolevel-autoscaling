SCENARIO = 'E4'
"""Tóm tắt first-job và vòng đời worker từ dữ liệu E4 đã thu."""
import argparse, datetime as dt, json, math, pathlib, sys

def stamp(s): return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
def rows(path): return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()] if path.exists() else []
def delta(values, start, end):
    pts=sorted((float(t),float(v)) for t,v in values if start <= float(t) <= end and math.isfinite(float(v)))
    if len(pts)<2:return None
    return sum(b if b<a else b-a for (_,a),(_,b) in zip(pts,pts[1:]))
def counts(directory,name,label,start,end):
    path=directory/"metrics"/("collect-prometheus-"+name+".json")
    if not path.exists():return {}
    matrix=json.loads(path.read_text(encoding="utf-8-sig")); out={}
    for x in matrix.get("data",{}).get("result",[]):
        n=delta(x.get("values",[]),start,end)
        if n is not None:
            k=x.get("metric",{}).get(label,"unknown");out[k]=out.get(k,0)+n
    return out

def quantile(buckets,q):
    total=buckets.get("+Inf")
    if not total:return None
    target=total*q; last_b=last_c=0.0
    for bound,count in sorted((float(k),v) for k,v in buckets.items() if k!="+Inf"):
        if count<last_c:return None
        if count>=target:
            return round(bound if count==last_c else last_b+(bound-last_b)*(target-last_c)/(count-last_c),3)
        last_b,last_c=bound,count
    return None

def idle_pod_minutes(workers,start,end,max_gap):
    points=sorted((stamp(x["observed_at_utc"]),x["data"]["ready"]) for x in workers)
    before=[v for t,v in points if t<=start]
    if not before:return None
    current=before[-1];last=start;area=0.0
    for t,v in points:
        if start<t<=end:
            if t-last>max_gap:return None
            area+=current*(t-last);last=t;current=v
    if end-last>max_gap:return None
    return round((area+current*(end-last))/60,3)

def summarize(directory):
    read=lambda x:json.loads((directory/x).read_text(encoding="utf-8-sig"))
    metadata=read("metadata.json"); collection=read("collection.json"); first=read("raw/first-job.json")
    if metadata.get("scenario") != SCENARIO or collection.get("status") not in ("finished","partial"):
        raise ValueError("Sai kịch bản hoặc collector chưa hoàn tất")
    if first.get("state") != "accepted" or len(first.get("job_ids") or [])!=1: raise ValueError("First job chưa được xác nhận accepted")
    job_id=first["job_ids"][0]; origin=first.get("enqueued_at_unix_ms"); start=origin/1000 if isinstance(origin,(int,float)) else stamp(first["sent_at_utc"])
    end=stamp(collection["ended_at_utc"]); workers=rows(directory/"events/collect-worker-samples.jsonl"); queue=rows(directory/"metrics/collect-sqs-samples.jsonl")
    matches=[x for x in rows(directory/"logs/collect-first-job.jsonl") if x.get("job",{}).get("jobId")==job_id]
    matches.sort(key=lambda x: x["job"].get("completedAt") or 0)
    match=matches[0] if matches else None
    completed=(match or {}).get("job",{}).get("completedAt"); completed=completed/1000 if isinstance(completed,(int,float)) else None
    pod=(match or {}).get("pod"); ready_at=None
    if pod:
        for sample in workers:
            for p in sample.get("data",{}).get("pods",[]):
                if p.get("name")!=pod:continue
                for c in p.get("conditions",[]):
                    if c.get("type")=="Ready" and c.get("status")=="True" and c.get("lastTransitionTime"):
                        t=stamp(c["lastTransitionTime"]);ready_at=t if ready_at is None else min(t,ready_at)
    desired_next=next((stamp(x["observed_at_utc"]) for x in workers if stamp(x["observed_at_utc"])>=start and x["data"].get("desired",0)>0),None)
    zero_after=next((stamp(x["observed_at_utc"]) for x in workers if completed is not None and stamp(x["observed_at_utc"])>=completed and x["data"].get("desired")==0 and x["data"].get("ready")==0),None)
    counts_rows=[x["data"]["main"]["counts"] for x in queue if start<=stamp(x["observed_at_utc"])<=end]
    peak=max((x["ApproximateNumberOfMessages"]+x["ApproximateNumberOfMessagesNotVisible"] for x in counts_rows),default=None)
    early_end=min(start+120,end)
    b=counts(directory,"worker_job_e2e_latency_seconds_bucket","le",start,early_end)
    statuses=counts(directory,"worker_tasks_processed_total","status",start,end)
    cpu=counts(directory,"worker_cpu_counter","pod",start,end)
    load_file=directory/"raw/k6-summary.json"
    load_end=None
    workload_config=None
    if load_file.exists():
        km=json.loads(load_file.read_text(encoding="utf-8-sig")).get("metrics",{})
        workload_config={k:km.get("workload_"+k,{}).get("value") for k in ("model_version", "low_rate", "high_rate", "batch_size", "work_units", "db_mode_code")}
        load_end=km.get("workload_finished_at_unix_ms",{}).get("value")
        if isinstance(load_end,(int,float)):load_end/=1000
        else:load_end=None
    stop=load_end if load_end is not None else stamp(first["response_at_utc"])
    zeros=[];drain=None;gap=3*float(collection.get("requested_interval_seconds",5))+10
    for sample in queue:
        t=stamp(sample["observed_at_utc"])
        if t<stop:continue
        c=sample["data"]["main"]["counts"]
        if any(c.values()) or (zeros and t-zeros[-1]>gap):zeros=[]
        if not any(c.values()):zeros.append(t)
        if len(zeros)>=3:drain=round(t-stop,3);break
    # A zero observed after the first job may precede the optional k6 load.
    # Only call it post-drain when both completion and a later drain are observed.
    zero_after_drain=None
    if completed is not None and drain is not None:
        drained_at=stop+drain
        zero_time=next((stamp(x["observed_at_utc"]) for x in workers
                        if stamp(x["observed_at_utc"])>=max(completed,drained_at)
                        and x["data"].get("desired")==0 and x["data"].get("ready")==0),None)
        if zero_time is not None:zero_after_drain=round(zero_time-drained_at,3)
    topology=rows(directory/"events/collect-topology-samples.jsonl")
    pool=SCENARIO.lower()+"-orders"
    claims=[]; node_ready=[]; active=[]
    for sample in topology:
        observed=stamp(sample["observed_at_utc"])
        if observed >= start:
            for condition in sample.get("data",{}).get("scaledobject_status",{}).get("conditions",[]):
                if condition.get("type")=="Active" and condition.get("status")=="True":
                    transition=stamp(condition["lastTransitionTime"]) if condition.get("lastTransitionTime") else observed
                    active.append((transition,"condition transition") if transition>=start else (observed,"observation proxy"))
        for claim in sample.get("data",{}).get("nodeclaims",[]):
            if claim.get("labels",{}).get("karpenter.sh/nodepool")==pool and claim.get("created"):
                t=stamp(claim["created"])
                if t>=start:claims.append(t)
        for node in sample.get("data",{}).get("nodes",[]):
            if node.get("labels",{}).get("karpenter.sh/nodepool")!=pool:continue
            for condition in node.get("conditions",[]):
                if condition.get("type")=="Ready" and condition.get("status")=="True" and condition.get("lastTransitionTime"):
                    t=stamp(condition["lastTransitionTime"])
                    if t>=start:node_ready.append(t)
    final_nodes=None
    if topology:
        final_nodes=sum(n.get("labels",{}).get("karpenter.sh/nodepool")==pool for n in topology[-1].get("data",{}).get("nodes",[]))
    samples_interval=float(collection.get("requested_interval_seconds",5)); idle=idle_pod_minutes(workers,start-60,start,3*samples_interval+10)
    warnings=list(collection.get("warnings",[]))
    if not origin:warnings.append("t0_uses_request_sent_proxy")
    if not match:warnings.append("first_job_completion_unobserved")
    if not workers:warnings.append("worker_samples_missing")
    if not b:warnings.append("latency_histogram_missing")
    if metadata.get("profile") != "idle" and workload_config is None:warnings.append("workload_summary_missing")
    if not counts_rows:warnings.append("sqs_samples_missing")
    if idle is None:warnings.append("idle_samples_incomplete")
    if drain is None:warnings.append("drain_not_confirmed")
    if completed is not None and completed<start: warnings.append("clock_order_inconsistent")
    baseline=read("events/collect-before.json")
    c=baseline.get("worker",{})
    trigger_list=baseline.get("scaledobject_spec",{}).get("triggers",[])
    sqs_metadata=next((x.get("metadata",{}) for x in trigger_list if x.get("type")=="aws-sqs-queue"),None)
    cron_metadata=next((x.get("metadata",{}) for x in trigger_list if x.get("type")=="cron"),None)
    cron_schedule={k:cron_metadata.get(k) for k in ("timezone","start","end")} if cron_metadata else None
    image_ids=sorted({container.get("imageID") for sample in workers for pod in sample.get("data",{}).get("pods",[]) for container in pod.get("containers",[]) if container.get("imageID")})
    if not image_ids:warnings.append("worker_image_digest_unobserved")
    config={"queue_name":metadata.get("target",{}).get("queue_name"),"region":metadata.get("target",{}).get("aws_region"),"containers":c.get("containers"),"node_selector":c.get("node_selector"),"work_units":first.get("work_units"),"db_mode":first.get("db_mode"),"sqs_trigger":sqs_metadata,"image_ids":image_ids,"workload":workload_config}
    return {"scenario":SCENARIO,"run_id":metadata.get("run_id"),"variant":metadata.get("variant"),"profile":metadata.get("profile"),"configuration":config,"cron_schedule":cron_schedule,
            "job_id":job_id,"t0_unix_seconds":start,"t0_source":"enqueue API" if origin else "request sent proxy", "worker_pod":pod,
            "first_job_status":(match or {}).get("job",{}).get("status"),"first_job_completion_seconds":round(completed-start,3) if completed is not None and completed>=start else None,
            "pod_ready_from_enqueue_seconds":round(ready_at-start,3) if ready_at is not None else None,
            "desired_nonzero_observed_from_enqueue_seconds":round(desired_next-start,3) if desired_next is not None else None,
            "worker_zero_observed_after_completion_seconds":round(zero_after-completed,3) if zero_after is not None and completed is not None else None,
            "worker_zero_observed_after_drain_seconds":zero_after_drain,
            "peak_visible_plus_inflight_approx":peak,"completed_by_status_approx":statuses or None,
            "success_per_second_through_observation_approx":round(statuses.get("success",0)/(end-start),3) if "success" in statuses and end>start else None,
            "mean_worker_cpu_millicores_approx":round(sum(cpu.values())/(end-start)*1000,1) if cpu and end>start else None,
            "drain_confirmation_seconds_approx":drain,"drain_start_source":"k6 end" if load_end is not None else "first-job response",
            "trigger_active_from_enqueue_seconds":round(min(active)[0]-start,3) if active else None,
            "trigger_active_source":min(active)[1] if active else None,
            "nodeclaim_created_from_enqueue_seconds":round(min(claims)-start,3) if claims else None,
            "node_ready_from_enqueue_seconds":round(min(node_ready)-start,3) if node_ready else None,
            "worker_nodes_last_sample":final_nodes,
            "e2e_latency_seconds_approx_all_statuses":{"p95":quantile(b,.95),"p99":quantile(b,.99)}, "latency_window_seconds":round(early_end-start,3),
            "idle_window_seconds":60,"ready_pod_minutes_idle_approx":idle,"k6_summary_present":(directory/"raw/k6-summary.json").is_file(),
            "warnings":sorted(set(warnings)),"validity":"not_assessed","notes":"Kubernetes/SQS samples and Prometheus counters are approximate. Pod Ready and desired use observed data. Histogram covers at most 120 seconds and includes error/duplicate; first-job log may be missing if pod disappeared. NodeClaim/Ready times are candidates, not proven links to the job; confirm node/Pod/event/queue evidence and drain manually."}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run-dir",required=True,type=pathlib.Path);a=p.parse_args()
    result=summarize(a.run_dir)
    with (a.run_dir/"report.json").open("x",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write("\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:main()
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:print(f"Không tạo được report: {exc}",file=sys.stderr);sys.exit(1)
