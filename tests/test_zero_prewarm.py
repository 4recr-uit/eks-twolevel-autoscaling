"""E4/E5 cold/prewarm tests use only temporary files and mocks."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
def module(scenario,name):
    path=ROOT/"experiments"/scenario/(name+".py")
    spec=importlib.util.spec_from_file_location(scenario+"_"+name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

class ZeroPrewarmTests(unittest.TestCase):
    def test_init_variants_and_no_overwrite(self):
        for scenario,variant in (("E4","pod-zero"),("E4","node-zero"),("E5","cold"),("E5","warm-1"),("E5","warm-2")):
            with self.subTest(scenario=scenario,variant=variant), tempfile.TemporaryDirectory() as root:
                run=module(scenario,"run");args=run.parser().parse_args(["init","--variant",variant,"--profile","idle","--attempt","1","--results-dir",root])
                with mock.patch.object(run,"git_snapshot",return_value={}): directory=run.init_run(args)
                data=json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
                self.assertEqual((data["scenario"],data["variant"]),(scenario,variant))
                with self.assertRaises(ValueError):run.init_run(args)

    def test_preflight_handles_zero_pods_and_cron(self):
        for scenario,variant,replicas in (("E4","pod-zero",0),("E4","node-zero",0),("E5","cold",0),("E5","warm-1",1),("E5","warm-2",2)):
            with self.subTest(scenario=scenario,variant=variant):
                c=module(scenario,"collect"); lo=scenario.lower()
                class Source:
                    target={"namespace":"retailstore","deployment":"orders-worker","queue_name":"orders-queue","aws_region":"us-east-1"}
                    queue_urls={}
                    def worker(self):return {"desired":replicas,"ready":replicas,"node_selector":{"karpenter.sh/nodepool":lo+"-orders"},"pods":[{"containers":[{"ready":True,"imageID":"sha256:a"}]} for i in range(replicas)]}
                    def controllers(self):return ["scaledobjects.keda.sh/"+lo+"-orders-sqs"]
                    def queue(self,name):self.queue_urls[name]="https://example/queue";return {"counts":dict.fromkeys(c.COUNTS,0),"redrive_policy":None}
                    def nodes(self):return [] if variant=="node-zero" else [{"labels":{"karpenter.sh/nodepool":lo+"-orders"},"conditions":[{"type":"Ready","status":"True"}]}]
                    def prom(self,*args,**kwargs):return {"data":{"result":[{"value":[1,"1"]} for i in range(replicas)]}}
                    def kube(self,*args):
                        if "deployment" in args:return {"spec":{"template":{"spec":{"containers":[{"name":"orders-worker","env":[{"name":"SQS_QUEUE_URL","value":"https://example/queue"}]}]}}}}
                        sqs={"type":"aws-sqs-queue","metadata":{"queueLength":"10","queueURLFromEnv":"SQS_QUEUE_URL","awsRegion":"us-east-1"}}
                        triggers=[sqs]+([{"type":"cron","metadata":{"desiredReplicas":str(replicas)}}] if scenario=="E5" and replicas else [])
                        return {"metadata":{"uid":"id","labels":{"experiments.retailstore.dev/owner":lo}},"spec":{"minReplicaCount":0,"maxReplicaCount":10,"triggers":triggers},"status":{"conditions":[{"type":"Ready","status":"True"}]}}
                self.assertEqual(c.preflight(Source(),variant)["variant"],variant)
                if variant == "node-zero":
                    src = Source(); original_kube = src.kube
                    def kube_with_claim(*args):
                        if "nodeclaims" in args:
                            return {"items": [{"metadata": {"labels": {"karpenter.sh/nodepool": lo + "-orders"}}}]}
                        return original_kube(*args)
                    src.kube = kube_with_claim
                    with self.assertRaisesRegex(ValueError, "NodeClaim"):
                        c.preflight(src, variant)
                src=Source();src.controllers=lambda:["hpa/unrelated"]
                with self.assertRaisesRegex(ValueError,"Autoscaler"):c.preflight(src,variant)

    def test_report_first_job_id_and_zero_pods(self):
        for scenario,variant in (("E4","pod-zero"),("E5","cold")):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as root:
                p=Path(root);r=module(scenario,"report")
                for folder in ("raw","events","metrics","logs"): (p/folder).mkdir()
                def save(name,value):(p/name).write_text(json.dumps(value),encoding="utf-8")
                save("metadata.json",{"scenario":scenario,"variant":variant,"profile":"idle","run_id":"a","target":{}})
                save("collection.json",{"status":"finished","started_at_utc":"1970-01-01T00:00:00Z","ended_at_utc":"1970-01-01T00:03:00Z","requested_interval_seconds":5})
                save("raw/first-job.json",{"state":"accepted","job_ids":["job1"],"enqueued_at_unix_ms":100000,"sent_at_utc":"1970-01-01T00:01:40Z","response_at_utc":"1970-01-01T00:01:41Z","work_units":100,"db_mode":"light"})
                save("events/collect-before.json",{"worker":{"node_selector":{},"containers":[]}})
                (p/"logs/collect-first-job.jsonl").write_text(json.dumps({"pod":"worker","job":{"jobId":"job1","completedAt":104000,"status":"success"}})+"\n",encoding="utf-8")
                with (p/"events/collect-worker-samples.jsonl").open("w",encoding="utf-8") as f:
                    for t in range(35,181,5):
                        ready=1 if 105<=t<125 else 0
                        pod={"name":"worker","conditions":[{"type":"Ready","status":"True","lastTransitionTime":"1970-01-01T00:01:43Z"}]}
                        f.write(json.dumps({"observed_at_utc":f"1970-01-01T00:{t//60:02d}:{t%60:02d}Z","data":{"ready":ready,"desired":ready,"pods":[pod] if ready else []}})+"\n")
                with (p/"metrics/collect-sqs-samples.jsonl").open("w",encoding="utf-8") as f:
                    for t in (105,110,115):f.write(json.dumps({"observed_at_utc":f"1970-01-01T00:{t//60:02d}:{t%60:02d}Z","data":{"main":{"counts":{"ApproximateNumberOfMessages":0,"ApproximateNumberOfMessagesNotVisible":0,"ApproximateNumberOfMessagesDelayed":0}}}})+"\n")
                result=r.summarize(p)
                self.assertEqual(result["job_id"],"job1")
                self.assertEqual(result["first_job_completion_seconds"],4)
                self.assertEqual(result["pod_ready_from_enqueue_seconds"],3)
                self.assertEqual(result["worker_zero_observed_after_completion_seconds"],21)
                self.assertEqual(result["ready_pod_minutes_idle_approx"],0)
                self.assertEqual(result["drain_confirmation_seconds_approx"],14)
                self.assertEqual(result["worker_zero_observed_after_drain_seconds"],10)
                # A zero after the first job is not a zero after a later workload.
                save("raw/k6-summary.json", {"metrics": {"workload_finished_at_unix_ms": {"value": 140000}}})
                with (p/"metrics/collect-sqs-samples.jsonl").open("a",encoding="utf-8") as f:
                    for t in (145,150,155):f.write(json.dumps({"observed_at_utc":f"1970-01-01T00:{t//60:02d}:{t%60:02d}Z","data":{"main":{"counts":{"ApproximateNumberOfMessages":0,"ApproximateNumberOfMessagesNotVisible":0,"ApproximateNumberOfMessagesDelayed":0}}}})+"\n")
                result=r.summarize(p)
                self.assertEqual(result["worker_zero_observed_after_drain_seconds"],0)
                (p/"logs/collect-first-job.jsonl").unlink()
                self.assertIsNone(r.summarize(p)["first_job_completion_seconds"])

    def test_first_job_is_sent_once_and_recorded(self):
        for scenario, variant in (("E4", "pod-zero"), ("E5", "warm-1")):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as root:
                p=Path(root); (p/"raw").mkdir()
                (p/"metadata.json").write_text(json.dumps({"scenario":scenario,"variant":variant}),encoding="utf-8")
                (p/"collection.json").write_text(json.dumps({"status":"collecting"}),encoding="utf-8")
                class Reply:
                    status=200
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def read(self):return json.dumps({"status":"published","jobIds":["id-1"],"enqueuedAt":1234}).encode()
                script=module(scenario,"first_job")
                with mock.patch.object(sys,"argv",["first_job.py","--run-dir",root]), mock.patch.object(script.urllib.request,"urlopen",return_value=Reply()) as call, mock.patch("builtins.print"):
                    self.assertEqual(script.main(),0)
                    self.assertEqual(json.loads((p/"raw/first-job.json").read_text(encoding="utf-8"))["job_ids"],["id-1"])
                    with self.assertRaises(FileExistsError):script.main()
                    self.assertEqual(call.call_count,1)

if __name__=="__main__":unittest.main()
