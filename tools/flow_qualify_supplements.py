"""Consume externally pinned supplemental goldens through installed worker/storage.

Caller must supply a reviewed closed five-distribution manifest and active scoped
resource lease. No source path insertion, fixture generation, builds or installs.
The original 433-row integration consumer is separate and unchanged.
"""
import argparse
from dataclasses import asdict,replace
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import sys
import sysconfig
import time
import traceback


FAMILIES=(("definition","r26-independent-definition-partition-fixtures1",8,78),("clock","r26-independent-selection-clock-fixtures1",12,48))


def require(value,detail):
    if not value:raise RuntimeError(detail)


def digest(path):return sha256(path.read_bytes()).hexdigest()


def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")


def write_new(path,value):
    with path.open("xb") as stream:stream.write(canonical(value)+b"\n")


def run(args):
    require(sys.flags.isolated==1 and sys.dont_write_bytecode and not os.environ.get("PYTHONPATH"),"Use installed python -I -B without PYTHONPATH")
    require(sys.version_info[:2]==(3,12),"Selected R26 runtime requires Python3.12")
    script=Path(__file__).resolve()
    pins={script:args.consumer_sha256,args.inputs.absolute():args.inputs_sha256,args.manifest.absolute():args.manifest_file_sha256,args.lease_file.absolute():args.lease_sha256}
    packets={}
    for family,schema,count,rows in FAMILIES:
        path=getattr(args,family+"_fixture").absolute();anchor=getattr(args,family+"_fixture_sha256")
        pins[path]=anchor
        require(digest(path)==anchor,"Externally approved supplemental artifact changed")
        packet=json.loads(path.read_bytes());require(packet.get("schema")==schema,"Wrong closed supplemental schema")
        require(type(packet["cases"]) is list and len(packet["cases"])==count and len({case["id"] for case in packet["cases"]})==count,"Closed supplemental case census differs")
        require(sum(len(case["expected_results"]) for case in packet["cases"])==rows,"Closed supplemental full-row census differs")
        packets[family]=packet
    for path,anchor in pins.items():
        require(re.fullmatch("[0-9a-f]{64}",anchor) is not None and digest(path)==anchor,"Externally pinned input/tool/grant differs")
    require(re.fullmatch("[0-9a-f]{64}",args.trusted_manifest_sha256) is not None,"External independent manifest domain anchor required")
    lease=json.loads(args.lease_file.read_bytes());require(lease.get("state")=="active" and lease.get("lease")==args.lease,"Active externally scoped resource grant required")
    require(lease.get("active_jobs")==lease.get("inflight")==lease.get("io_slots")==lease.get("configured_backend_threads")==1 and lease.get("logical_memory_reservation_bytes")==268435456,"External grant must authorize the reviewed bounded profile")
    output=args.output.absolute()
    require(not output.resolve().is_relative_to(Path(sys.prefix).resolve()),"Private outputs must be outside installed runtime")
    require(not output.resolve().is_relative_to(script.parents[1]),"Synthetic database outputs must be outside tool repository")
    require(not any(p.is_symlink() for p in output.parents),"Output parent is a link")
    output.mkdir(exist_ok=False,parents=False);(output/"databases").mkdir()
    report={"schema":"r26-installed-supplemental-integration1","passed":False,"release_accepted":False,"original_full_consumer":"Separate tool, not executed or modified by this consumer",
        "lease":args.lease,"python":sys.version,"platform":platform.platform(),"executable":sys.executable,
        "external_pins":{str(k):v for k,v in pins.items()},"external_manifest_domain_sha256":args.trusted_manifest_sha256,"cases":[],
        "profile":{"workers":1,"inflight":1,"io_slots":1,"backend_threads":1,"logical_task_bytes":268435456},
        "limitations":["Only supplemental20-case126-row adapter/worker/storage conformance; separate original433 and remaining release gates still required", "Logical256MiB reservation is not an RSS/native allocation bound", "Two representative replay controls use one literal request each, not multi-cut replay coverage", "No supplemental checkpoint-restore golden is claimed; independently bound checkpoint identities are still required", "No new math oracle, fault simulation, performance or release claim"]}
    started=time.perf_counter();cpu=time.process_time()
    try:
        from option_flow_contracts import (FlowValidationError,decode_flow_snapshot,decode_flow_request,encode_flow_snapshot,encode_flow_request,encode_flow_results,flow_canonical_bytes,flow_to_payload,flow_record_digest)
        from option_flow_features import evaluate_flow,make_flow_checkpoint
        from option_flow_io import SyntheticFlowAdapter,FlowDuckDBSink
        from option_flow_workers import (FlowArtifact,FlowCohort,FlowExecutionConfig,FlowQualificationManifest,FlowQualificationSource,execute_flow,execute_flow_replay,inspect_flow_resources,verify_flow_installed)
        inputs=json.loads(args.inputs.read_bytes());payload=json.loads(args.manifest.read_bytes())
        manifest=FlowQualificationManifest(payload["manifest_version"],tuple(FlowQualificationSource(**item) for item in payload["artifacts"]))
        roles={item["distribution"]:item["role"] for item in inputs}
        cohort=FlowCohort("option-flow-cohort1",platform.python_version(),sysconfig.get_platform(),tuple(FlowArtifact(item.distribution,item.version,item.source_commit,item.wheel_sha256,roles[item.distribution]) for item in manifest.artifacts))
        wheels=tuple(item["wheel_path"] for item in inputs)
        verification=verify_flow_installed(cohort,wheels,str(output/"installed-before.json"),manifest,args.trusted_manifest_sha256)
        report["verification_before"]=asdict(verification)
        config=FlowExecutionConfig("batch",1,1,1,1,268435456,268435456)
        def compare(rows,case):
            require(flow_to_payload(rows)==case["expected_results"],"All literal value/status/evidence/identity result fields differ")
            require(flow_canonical_bytes(rows)==canonical(case["expected_results"]),"Complete literal canonical result bytes differ")
            require(flow_record_digest("flow_results",rows)==case["expected_results_record_sha256"],"Complete literal results digest differs")
            require(encode_flow_results(rows).decode("utf-8")==case["expected_results_wire"],"Complete literal result envelope differs")
        def checkpoint_bytes(value):return None if value is None else flow_canonical_bytes(value)
        total_rows=0;replay_rows=0;replay_cases=0
        for family,_,count,expected_rows in FAMILIES:
            family_rows=0
            for index,case in enumerate(packets[family]["cases"]):
                step_started=time.perf_counter()
                snapshot_wire=case["snapshot_wire"].encode("utf-8");request_wire=case["request_wire"].encode("utf-8")
                strict=decode_flow_snapshot(snapshot_wire);adapter=SyntheticFlowAdapter(snapshot_wire);snapshot=adapter.load();request=decode_flow_request(request_wire)
                require(encode_flow_snapshot(strict)==snapshot_wire and encode_flow_snapshot(snapshot)==snapshot_wire and encode_flow_request(request)==request_wire,"Strict adapter/decoder canonical input roundtrip differs")
                require(flow_record_digest("flow_snapshot",snapshot)==case["snapshot_record_sha256"] and flow_record_digest("flow_request",request)==case["request_record_sha256"],"Externally fixed input identities differ")
                direct=evaluate_flow(snapshot,request);compare(direct,case)
                try:checkpoint=make_flow_checkpoint(snapshot,request)
                except FlowValidationError as error:
                    if error.code!="checkpoint_cut_mismatch":raise
                    checkpoint=None
                name=family+"-"+str(index).zfill(2);db=output/"databases"/(name+".duckdb");key=name+"-batch"
                with FlowDuckDBSink(str(db)) as sink:
                    actual=execute_flow(snapshot,request,run_key=key,config=config,verified_cohort=cohort,sink=sink)
                    retry=execute_flow(snapshot,request,run_key=key,config=config,verified_cohort=cohort,sink=sink)
                    require(actual.outcome=="committed" and retry.outcome=="already_committed","Real commit/retry outcomes differ")
                    compare(actual.results,case);compare(retry.results,case)
                    require(checkpoint_bytes(actual.output_checkpoint)==checkpoint_bytes(checkpoint),"Pure/worker complete checkpoint parity differs")
                    stored=sink.read(key);require(stored is not None,"Stored generation missing")
                    compare(stored.results,case)
                    require(stored.snapshot_sha256==case["snapshot_record_sha256"] and stored.request_sha256==case["request_record_sha256"] and stored.input_checkpoint_sha256 is None and encode_flow_request(stored.request)==request_wire,"Stored invocation identity differs")
                    require(stored.work_sha256==actual.work_sha256==retry.work_sha256 and stored.run_key==actual.run_key==retry.run_key==key,"Stored/worker/retry work and run identities differ")
                    require(checkpoint_bytes(stored.output_checkpoint)==checkpoint_bytes(actual.output_checkpoint),"Stored complete output checkpoint differs")
                    require(actual.commit_receipt.run_key==retry.commit_receipt.run_key==key and actual.commit_receipt.work_sha256==retry.commit_receipt.work_sha256==actual.work_sha256 and actual.commit_receipt.result_count==retry.commit_receipt.result_count==len(actual.results),"Actual commit/retry receipt identity/census differs")
                    require(actual.commit_receipt.verified_readback and retry.commit_receipt.verified_readback,"Real commit/retry verified readback missing")
                    require(actual.commit_receipt.results_sha256==case["expected_results_record_sha256"] and retry.commit_receipt.results_sha256==case["expected_results_record_sha256"],"Real receipt result identity differs")
                    publication_bytes=flow_canonical_bytes(stored);publication_hash=flow_record_digest("flow_publication",stored)
                    require(actual.commit_receipt.publication_sha256==publication_hash and retry.commit_receipt.publication_sha256==publication_hash,"Actual receipt publication identity differs")
                    replay_detail=None
                    if index==0:
                        # This exact snapshot/request invocation has a literal
                        # independent golden already: replay introduces no new
                        # checkpoint input or producer-derived expected identity.
                        replay_key=name+"-replay";replay_config=replace(config,mode="chronological_cut_replay")
                        replay=execute_flow_replay(snapshot,(request,),run_keys=(replay_key,),config=replay_config,verified_cohort=cohort,sink=sink)
                        replay_retry=execute_flow_replay(snapshot,(request,),run_keys=(replay_key,),config=replay_config,verified_cohort=cohort,sink=sink)
                        require(len(replay)==len(replay_retry)==1 and replay[0].outcome=="committed" and replay_retry[0].outcome=="already_committed","Actual singleton replay/retry outcome differs")
                        compare(replay[0].results,case);compare(replay_retry[0].results,case)
                        replay_stored=sink.read(replay_key);require(replay_stored is not None,"Replay publication missing");compare(replay_stored.results,case)
                        replay_bytes=flow_canonical_bytes(replay_stored)
                        replay_detail={"run_key":replay_key,"receipt":asdict(replay[0].commit_receipt),"retry":asdict(replay_retry[0].commit_receipt),"literal_rows":len(replay[0].results),"publication_sha256":flow_record_digest("flow_publication",replay_stored)}
                        replay_rows+=len(replay[0].results);replay_cases+=1
                with FlowDuckDBSink(str(db)) as reopened:
                    reopened_stored=reopened.read(key);require(reopened_stored is not None and flow_canonical_bytes(reopened_stored)==publication_bytes,"Reopened complete generation bytes differ");compare(reopened_stored.results,case)
                    reopened_retry=execute_flow(snapshot,request,run_key=key,config=config,verified_cohort=cohort,sink=reopened)
                    require(reopened_retry.outcome=="already_committed","Retry after reopen differs");compare(reopened_retry.results,case)
                    if replay_detail is not None:
                        reopened_replay=reopened.read(replay_detail["run_key"])
                        require(reopened_replay is not None and flow_canonical_bytes(reopened_replay)==replay_bytes,"Reopened complete replay generation differs");compare(reopened_replay.results,case)
                entry={"family":family,"id":case["id"],"passed":True,"rows":len(actual.results),"database":str(db),"adapter_receipt":asdict(adapter.receipt),"logical_admission":asdict(inspect_flow_resources(snapshot,request,config)),"wire_result_bytes":len(encode_flow_results(actual.results)),"receipt":asdict(actual.commit_receipt),"retry_receipt":asdict(retry.commit_receipt),"reopen_retry_receipt":asdict(reopened_retry.commit_receipt),"publication_sha256":publication_hash,"snapshot_record_sha256":case["snapshot_record_sha256"],"request_record_sha256":case["request_record_sha256"],"results_record_sha256":case["expected_results_record_sha256"],"singleton_replay":replay_detail,"wall_seconds":time.perf_counter()-step_started}
                write_new(output/(name+".json"),entry);report["cases"].append(entry);family_rows+=len(actual.results)
                print(json.dumps({"family":family,"case":case["id"],"passed":True,"rows":len(actual.results)}),flush=True)
            require(family_rows==expected_rows and len(packets[family]["cases"])==count,"Actual supplemental family full-row census differs")
            total_rows+=family_rows
        verification_after=verify_flow_installed(cohort,wheels,str(output/"installed-after.json"),manifest,args.trusted_manifest_sha256)
        report["verification_after"]=asdict(verification_after)
        for path,anchor in pins.items():require(digest(path)==anchor,"Externally pinned input/tool/grant changed during qualification")
        require(total_rows==126 and len(report["cases"])==20 and replay_cases==2,"Actual supplemental integration census differs")
        report.update(passed=True,complete_rows=126,case_count=20,singleton_replay_cases=replay_cases,singleton_replay_literal_rows=replay_rows)
    except BaseException as error:report["failure"]={"class":type(error).__name__,"detail":str(error),"traceback":traceback.format_exc()}
    finally:
        report.update(wall_seconds=time.perf_counter()-started,process_cpu_seconds=time.process_time()-cpu)
        write_new(output/"supplement-integration-attempt.json",report)
    return 0 if report["passed"] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("definition-fixture","clock-fixture","inputs","manifest","lease-file","output"):parser.add_argument("--"+name,type=Path,required=True)
    for name in ("definition-fixture-sha256","clock-fixture-sha256","inputs-sha256","manifest-file-sha256","trusted-manifest-sha256","lease-sha256","lease","consumer-sha256"):parser.add_argument("--"+name,required=True)
    return run(parser.parse_args())

if __name__=="__main__":raise SystemExit(main())
