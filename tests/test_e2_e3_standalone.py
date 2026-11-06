"""Test isolated E2/E3 controller preflight and observed timeline using fixtures."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
def load(scenario, name):
    spec=importlib.util.spec_from_file_location(f"{scenario}_{name}", ROOT/"experiments"/scenario/(name+".py"))
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
E2=load("E2","collect");E3=load("E3","collect");timeline=load("E2","timeline")

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
    def nodes(self): return [{"name":"n","labels":{"karpenter.sh/nodepool":f"{self.scenario}-orders"},"conditions":[{"type":"Ready","status":"True"}]}]
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
                    "spec":{"minReplicaCount":0 if self.scenario=="e2" else 1,"maxReplicaCount":10,"triggers":[{"type":"aws-sqs-queue","metadata":{"queueLength":"10","queueURLFromEnv":"SQS_QUEUE_URL","awsRegion":"us-east-1"}}]}}
        if self.variant=="hpa":
            return {"metadata":{"labels":{"experiments.retailstore.dev/owner":self.scenario}},"spec":{"minReplicas":1,"maxReplicas":10,"metrics":[{"type":"Resource","resource":{"name":"cpu","target":{"type":"Utilization","averageUtilization":60}}}]},"status":{"conditions":[{"type":"AbleToScale","status":"True"},{"type":"ScalingActive","status":"True"}]}}
        return {"metadata":{"ownerReferences":[{"uid":"s","kind":"ScaledObject"}]},"spec":{"minReplicas":1,"maxReplicas":10},"status":{"conditions":[{"type":"AbleToScale","status":"True"},{"type":"ScalingActive","status":"True"}]}}

class ScenarioTests(unittest.TestCase):
    def test_e2_can_preflight_without_a_worker_target(self):
        result=E2.preflight(Source("e2","elastic",0),"elastic")
        self.assertEqual(result["worker"]["ready"],0)
    def test_e2_rejects_wrong_worker_nodepool(self):
        src=Source("e2","elastic",0)
        src.worker=lambda: {"desired":0,"ready":0,"pods":[],"node_selector":{}}
        with self.assertRaisesRegex(ValueError,"NodePool"): E2.preflight(src,"elastic")
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

if __name__=="__main__":unittest.main()
