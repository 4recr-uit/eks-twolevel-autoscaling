"""Test isolated E2/E3 controller preflight and observed timeline using fixtures."""
import importlib.util
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
def load(scenario, name):
    spec=importlib.util.spec_from_file_location(f"{scenario}_{name}", ROOT/"experiments"/scenario/(name+".py"))
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
E2=load("E2","collect");E3=load("E3","collect");timeline=load("E2","timeline");report=load("E2","report")

class Source:
    def __init__(self, scenario, variant, replicas=1):
        self.scenario=scenario;self.variant=variant;self.replicas=replicas
        self.target={"namespace":"retailstore","deployment":"orders-worker","queue_name":"orders-queue","aws_region":"us-east-1"}
        self.queue_urls={}
    def worker(self):
        return {"desired":self.replicas,"ready":self.replicas,"node_selector":{"karpenter.sh/nodepool":f"{self.scenario}-orders"},
                "pods":[{"containers":[{"ready":True,"imageID":"sha256:x"}]} for _ in range(self.replicas)]}
    def controllers(self):
        return [f"hpa/{self.scenario}-orders-cpu"] if self.variant=="hpa" else [f"hpa/{self.scenario}-orders-keda-hpa",f"scaledobjects.keda.sh/{self.scenario}-orders-sqs"]
    def nodes(self): return [{"name":"n","labels":{"karpenter.sh/nodepool":f"{self.scenario}-orders"},"annotations":{"karpenter.sh/do-not-disrupt":"true"},"conditions":[{"type":"Ready","status":"True"}]}]
    def queue(self,name):
        self.queue_urls[name]="https://example/queue"
        return {"counts":dict.fromkeys(E2.COUNTS,0),"redrive_policy":None}
    def prom(self,endpoint,**kw):
        if not self.replicas: assert kw["query"]=="vector(1)"
        return {"data":{"result":[{"value":[1,"1"]}]}}
    def kube(self,*args):
        if args[-2]=="deployment": return {"spec":{"template":{"spec":{"containers":[{"name":"orders-worker","env":[{"name":"SQS_QUEUE_URL","value":"https://example/queue"}]}]}}}}
        if args[-2]=="scaledobject":
            return {"metadata":{"uid":"s","labels":{"experiments.retailstore.dev/owner":self.scenario}},"status":{"conditions":[{"type":"Ready","status":"True"}]},
                    "spec":{"minReplicaCount":0 if self.scenario=="e2" else 1,"maxReplicaCount":10,**({"pollingInterval":5,"cooldownPeriod":150} if self.scenario=="e2" else {}),"triggers":[{"type":"aws-sqs-queue","metadata":{"queueLength":"10","queueURLFromEnv":"SQS_QUEUE_URL","awsRegion":"us-east-1"}}]}}
        if self.variant=="hpa":
            return {"metadata":{"labels":{"experiments.retailstore.dev/owner":self.scenario}},"spec":{"minReplicas":1,"maxReplicas":10,"metrics":[{"type":"Resource","resource":{"name":"cpu","target":{"type":"Utilization","averageUtilization":60}}}]},"status":{"conditions":[{"type":"AbleToScale","status":"True"},{"type":"ScalingActive","status":"True"}]}}
        return {"metadata":{"ownerReferences":[{"uid":"s","kind":"ScaledObject"}]},"spec":{"minReplicas":1,"maxReplicas":10},"status":{"conditions":[{"type":"AbleToScale","status":"True"},{"type":"ScalingActive","status":"True"}]}}

class ScenarioTests(unittest.TestCase):
    def test_e2_can_preflight_without_a_worker_target(self):
        result=E2.preflight(Source("e2","elastic",0),"elastic")
        self.assertEqual(result["worker"]["ready"],0)
    def test_e2_rejects_old_or_missing_keda_intervals(self):
        for changes in ({"pollingInterval":30}, {"cooldownPeriod":300}, {"pollingInterval":None}, {"cooldownPeriod":None}):
            with self.subTest(changes=changes):
                src=Source("e2","elastic",0); original=src.kube
                def kube(*args):
                    obj=original(*args)
                    if args[-2]=="scaledobject": obj["spec"].update(changes)
                    return obj
                src.kube=kube
                with self.assertRaisesRegex(ValueError,"polling=5s, cooldown=150s"): E2.preflight(src,"elastic")
    def test_e2_rejects_wrong_worker_nodepool(self):
        src=Source("e2","elastic",0)
        src.worker=lambda: {"desired":0,"ready":0,"pods":[],"node_selector":{}}
        with self.assertRaisesRegex(ValueError,"NodePool"): E2.preflight(src,"elastic")
    def test_e2_requires_zero_workers_and_one_protected_ready_node(self):
        with self.assertRaisesRegex(ValueError,"0 worker"): E2.preflight(Source("e2","elastic",1),"elastic")
        for nodes in ([], [{"labels":{"karpenter.sh/nodepool":"e2-orders"},"conditions":[{"type":"Ready","status":"True"}]}],
                      [{"labels":{"karpenter.sh/nodepool":"e2-orders"},"annotations":{"karpenter.sh/do-not-disrupt":"true"},"conditions":[]}]):
            src=Source("e2","elastic",0); src.nodes=lambda: nodes
            with self.assertRaisesRegex(ValueError,"một node"): E2.preflight(src,"elastic")
    def test_e2_detects_image_change_after_zero_worker_baseline(self):
        collector=E2.Collector(None,None,None,None)
        collector.before={"worker":{"uid":"deployment","containers":[],"pods":[]}}
        for image_id in ("sha256:first", "sha256:second"):
            collector.observe_worker({"uid":"deployment","containers":[],"pods":[{"containers":[{"imageID":image_id,"restartCount":0}]}]})
        self.assertIn("worker_image_changed",collector.warnings)
    def test_e2_report_records_image_seen_after_zero_worker_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name in ("events","raw","metrics"): (p/name).mkdir()
            def save(name, obj): (p/name).write_text(json.dumps(obj),encoding="utf-8")
            save("metadata.json",{"scenario":"E2","variant":"elastic","profile":"burst","run_id":"r","target":{}})
            save("collection.json",{"status":"finished","started_at_utc":"1970-01-01T00:00:00Z","ended_at_utc":"1970-01-01T00:05:00Z"})
            save("events/collect-before.json",{"worker":{"pods":[]}})
            metrics={key:{"value":value} for key,value in {"workload_profile_code":2,"workload_model_version":5,"workload_vus":100,"workload_low_rate":5,"workload_high_rate":40,"workload_batch_size":1,"workload_work_units":100,"workload_db_mode_code":1,"workload_started_at_unix_ms":100000,"workload_finished_at_unix_ms":200000}.items()}
            save("raw/k6-summary.json",{"metrics":metrics})
            (p/"events/collect-worker-samples.jsonl").write_text(json.dumps({"data":{"pods":[{"containers":[{"imageID":"sha256:seen"}]}]}})+"\n",encoding="utf-8")
            (p/"metrics/collect-sqs-samples.jsonl").write_text("",encoding="utf-8")
            result=report.summarize(p)
            self.assertEqual(result["configuration"]["image_ids"],["sha256:seen"])
            self.assertEqual(result["workload"]["high_phase_duration_seconds"],90)
            self.assertEqual(result["workload"]["load_generator_max_vus"],100)
    def test_e3_requires_controller_and_exactly_one_node(self):
        for branch in ("hpa","keda"):
            self.assertEqual(E3.preflight(Source("e3",branch),branch)["variant"],branch)
        src=Source("e3","hpa");src.nodes=lambda: []
        with self.assertRaisesRegex(ValueError,"một node"): E3.preflight(src,"hpa")
        with self.assertRaises(ValueError): E3.preflight(Source("e3","hpa"),"fixed")
    def test_timeline_keeps_candidates_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name in ("events","raw"): (p/name).mkdir()
            (p/"metadata.json").write_text(json.dumps({"scenario":"E2","variant":"elastic","run_id":"r"}))
            (p/"raw/k6-summary.json").write_text(json.dumps({"metrics":{"workload_started_at_unix_ms":{"value":100000}}}))
            def save(name, lines): (p/name).write_text("".join(json.dumps(x)+"\n" for x in lines),encoding="utf-8")
            save("events/collect-topology-samples.jsonl",[{"observed_at_utc":"1970-01-01T00:01:45Z","data":{"nodeclaims":[{"uid":"c","name":"claim","labels":{"karpenter.sh/nodepool":"e2-orders"},"status":{"providerID":"aws://id"}}],"nodes":[{"uid":"n","name":"node","provider_id":"aws://id","labels":{"karpenter.sh/nodepool":"e2-orders"},"conditions":[{"type":"Ready","status":"True"}]}]}}])
            save("events/collect-worker-samples.jsonl",[{"observed_at_utc":"1970-01-01T00:01:43Z","data":{"pods":[{"uid":"p","name":"worker","conditions":[{"type":"PodScheduled","status":"False","reason":"Unschedulable"}]}]}}, {"observed_at_utc":"1970-01-01T00:01:50Z","data":{"pods":[{"uid":"p","name":"worker","node":"node","containers":[{"ready":True}]}]}}])
            out=timeline.analyze(p)
            self.assertEqual(out["unschedulable_pods"][0]["uid"],"p")
            self.assertEqual(out["new_nodeclaims"][0]["provider_id"],out["new_ready_nodes"][0]["provider_id"])
            self.assertEqual(out["candidate_links"][0]["pending_to_pod_ready_seconds_approx"],7)
            self.assertIn("ứng viên",out["note"])
            self.assertIsNone(out["timeline_utc"]["T2"])
            self.assertIsNone(out["timeline_utc"]["T3"])
    def test_e2_timeline_tracks_cold_start_provisioning_and_scale_to_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name in ("events","raw","metrics"): (p/name).mkdir()
            def stamp(seconds): return dt.datetime.fromtimestamp(seconds,dt.timezone.utc).isoformat()
            def save(name, obj): (p/name).write_text(json.dumps(obj),encoding="utf-8")
            def lines(name, items): (p/name).write_text("".join(json.dumps(item)+"\n" for item in items),encoding="utf-8")
            def sample(t, data): return {"observed_at_utc":stamp(t),"data":data}
            def pod(uid,node=None,ready=False,condition=None):
                return {"uid":uid,"name":uid,"node":node,"containers":[{"ready":ready}],"conditions":[condition] if condition else []}
            save("metadata.json",{"scenario":"E2","variant":"elastic","profile":"burst","run_id":"r"})
            save("collection.json",{"requested_interval_seconds":5})
            save("raw/k6-summary.json",{"metrics":{"workload_started_at_unix_ms":{"value":100000},"workload_finished_at_unix_ms":{"value":200000},"workload_model_version":{"value":5}}})
            save("events/collect-before.json",{"nodes":[{"name":"initial","labels":{"karpenter.sh/nodepool":"e2-orders"}}],"dlq":{"queue_name":"dlq"}})
            unscheduled={"type":"PodScheduled","status":"False","reason":"Unschedulable","message":"0/2 nodes are available: 1 Insufficient cpu"}
            lines("events/collect-worker-samples.jsonl",[sample(103,{"desired":1,"ready":1,"pods":[pod("p0","initial",True)]}),
                sample(110,{"desired":2,"ready":1,"pods":[pod("p0","initial",True),pod("p1",condition=unscheduled)]}),
                sample(135,{"desired":2,"ready":2,"pods":[pod("p0","initial",True),pod("p1","new",True)]}),
                sample(230,{"desired":0,"ready":0,"pods":[]})])
            lines("events/collect-topology-samples.jsonl",[sample(130,{"nodeclaims":[{"uid":"c","name":"claim","created":stamp(114),"labels":{"karpenter.sh/nodepool":"e2-orders"},"status":{"providerID":"aws://id","nodeName":"new"}}],
                "nodes":[{"uid":"n","name":"new","created_at":stamp(125),"provider_id":"aws://id","labels":{"karpenter.sh/nodepool":"e2-orders"},"conditions":[{"type":"Ready","status":"True"}]}]})])
            def counts(visible): return {"ApproximateNumberOfMessages":visible,"ApproximateNumberOfMessagesNotVisible":0,"ApproximateNumberOfMessagesDelayed":0}
            def queue(count,dlq=0): return {"main":{"counts":counts(count)},"dlq":{"counts":counts(dlq)}}
            lines("metrics/collect-sqs-samples.jsonl",[sample(205,queue(2)),sample(210,queue(0)),sample(215,queue(0)),sample(220,queue(0,1)),sample(225,queue(0)),sample(230,queue(0)),sample(235,queue(0))])
            out=timeline.analyze(p)
            self.assertEqual([out["timeline_utc"][f"T{i}"] for i in range(9)], [stamp(n) for n in (100,103,110,114,130,135,200,235,230)])
            self.assertEqual(out["intervals_seconds_approx"],{"cold_start_pod":3,"node_provisioning":16,"pod_startup_on_new_node":5,"queue_drain_after_workload":35,"scale_to_zero_after_workload":30})
            self.assertEqual(out["high_rate_started_utc"],stamp(160))
    @unittest.skipUnless(shutil.which("k6"),"k6 is required")
    def test_e2_burst_holds_high_rate_for_90_seconds(self):
        result=subprocess.run([shutil.which("k6"),"inspect",str(ROOT/"experiments/E2/burst.js")],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(result.returncode,0,result.stderr)
        scenario=json.loads(result.stdout)["scenarios"]["jobs"]
        self.assertEqual(scenario["startRate"],5)
        self.assertEqual(scenario["maxVUs"],100)
        self.assertEqual([(s["target"],s["duration"]) for s in scenario["stages"] if s["duration"]!="0s"],[(5,"1m0s"),(40,"1m30s"),(5,"1m0s")])

if __name__=="__main__":unittest.main()
