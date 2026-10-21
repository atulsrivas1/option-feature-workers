"""Consume pinned independent goldens in one real installed R26 cohort.

Requires a fresh external coordinator lease and reviewed artifact/manifest/provenance
anchors. Never generates numerical expectations, installs, builds, or admits itself.
"""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import inspect
import json
import os
from pathlib import Path
import platform
import sys
import sysconfig
import time
import traceback

APPROVED_ARTIFACT_SHA256 = "e0ab2065eaa62f3ac1b5442b0045f0e58a1c3c5a6ee45d20464f201a34316b51"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def file_digest(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(label)


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def peak_rss():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"bytes":int(counters.PeakWorkingSetSize), "method":"Windows GetProcessMemoryInfo.PeakWorkingSetSize"}
    import resource
    return {"bytes":int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
            "method":"Linux getrusage(RUSAGE_SELF).ru_maxrss KiB"}


def pinned_json(path, expected):
    require(path.is_file() and path.stat().st_size <= 33554432, "Pinned JSON must be a bounded actual file")
    require(file_digest(path) == expected, "Externally pinned file digest mismatch: " + path.name)
    return json.loads(path.read_bytes())


def run(args):
    require(sys.flags.isolated == 1 and sys.dont_write_bytecode, "Invoke prepared installed runtime with python -I -B")
    require(not os.environ.get("PYTHONPATH"), "PYTHONPATH is forbidden; installed imports only")
    require(args.artifact_sha256 == APPROVED_ARTIFACT_SHA256, "This consumer admits only the independently reviewed full artifact")
    require(bool(args.lease), "External coordinator lease identifier required")
    artifact = pinned_json(args.artifact, args.artifact_sha256)
    provenance = pinned_json(args.provenance, args.provenance_sha256)
    equal(artifact["schema"], "r26-independent-full-results1", "Independent artifact schema")
    output = args.output.absolute()
    require(not output.resolve().is_relative_to(Path(sys.prefix).resolve()), "Private output must be outside installed runtime")
    require(not any(parent.is_symlink() for parent in output.parents), "Output ancestors must not be links")
    output.mkdir(parents=False, exist_ok=False)
    started, cpu_started = time.perf_counter(), time.process_time()
    tool_sha = file_digest(Path(__file__))
    summary = {"schema":"r26-installed-integration-attempt1", "lease":args.lease, "passed":False,
               "full_release_accepted":False, "publication_authorized":False, "successes":[], "failures":[],
               "artifact_sha256":args.artifact_sha256, "provenance_sha256":args.provenance_sha256,
               "external_provenance":provenance, "tool_sha256_before":tool_sha,
               "command":sys.argv, "python":sys.version, "platform":platform.platform(),
               "profile":{"workers":1,"inflight":1,"io_slots":1,"backend_threads":1,
                          "logical_task_bytes":268435456,"limitation":"Logical admission reservation, not RSS/native allocation enforcement"},
               "limitations":["Single declared installed platform/artifact form only", "Fault seam simulation is not an OS crash/durability proof",
                              "Peak RSS is process-lifetime high-water, not per-case allocation or a memory bound",
                              "No speed claim, R25 regression, equity producer integration, browser inspection or release acceptance"]}
    sequence = 0
    def record(identity, category, action):
        nonlocal sequence
        index = sequence
        sequence += 1
        wall, cpu = time.perf_counter(), time.process_time()
        item = {"id":identity,"category":category}
        try:
            detail = action()
            item.update(passed=True, detail=detail)
            summary["successes"].append(item)
        except Exception as error:
            item.update(passed=False, exception_class=type(error).__name__, detail=str(error), traceback=traceback.format_exc())
            for key in ("code", "path", "cause_code", "cause_path"):
                if hasattr(error, key):item[key]=getattr(error,key)
            summary["failures"].append(item)
        item.update(wall_seconds=time.perf_counter()-wall, process_cpu_seconds=time.process_time()-cpu, peak_rss=peak_rss())
        write_new(output / f"case-{index:03d}.json", item)
        print(json.dumps({"case":identity,"category":category,"passed":item["passed"],"wall_seconds":item["wall_seconds"]}), flush=True)
        return item
    try:
        # Imports come only from this already prepared isolated interpreter.
        from option_flow_contracts import (
            FlowSnapshot, FlowValidationError, decode_flow_record, decode_flow_request, decode_flow_snapshot,
            decode_flow_checkpoint, encode_flow_record, encode_flow_request, encode_flow_snapshot,
            encode_flow_checkpoint, encode_flow_results, flow_canonical_bytes, flow_from_payload,
            flow_record_digest, flow_to_payload,
        )
        from option_flow_features import evaluate_flow, replay_flow, restore_flow, make_flow_checkpoint
        from option_flow_features.engine import merge_flow_history
        from option_flow_io import SyntheticFlowAdapter, FlowDuckDBSink, PublicationConflict, StorageIntegrityError, StorageSchemaError
        from option_flow_workers import (
            FlowArtifact, FlowCohort, FlowExecutionConfig, FlowQualificationManifest, FlowQualificationSource,
            FlowWorkerError, execute_flow, execute_flow_replay, execute_flow_restore,
            inspect_flow_resources, verify_flow_installed,
        )
        inputs = json.loads(args.inputs.read_bytes())
        manifest_payload = json.loads(args.manifest.read_bytes())
        manifest = FlowQualificationManifest(manifest_payload["manifest_version"], tuple(FlowQualificationSource(**item) for item in manifest_payload["artifacts"]))
        roles = {item["distribution"]:item["role"] for item in inputs}
        cohort = FlowCohort("option-flow-cohort1", platform.python_version(), sysconfig.get_platform(), tuple(
            FlowArtifact(item.distribution,item.version,item.source_commit,item.wheel_sha256,roles[item.distribution]) for item in manifest.artifacts))
        verified = verify_flow_installed(cohort, tuple(item["wheel_path"] for item in inputs),
            str(output / "installed-verification.json"), manifest, args.trusted_manifest_sha256)
        summary.update(verification=asdict(verified), cohort=asdict(cohort), inputs_sha256=file_digest(args.inputs),
                       manifest_file_sha256=file_digest(args.manifest), external_manifest_anchor=args.trusted_manifest_sha256)
        config = FlowExecutionConfig("batch",1,1,1,1,268435456,268435456)
        def snapshot(source):
            wire = source.get("snapshot_wire")
            if wire is None:
                wire = encode_flow_snapshot(flow_from_payload("flow_snapshot",source["snapshot"])).decode("utf-8")
            adapter = SyntheticFlowAdapter(wire.encode("utf-8"))
            value = adapter.load()
            equal(encode_flow_snapshot(value).decode("utf-8"),wire,"Strict snapshot adapter roundtrip")
            if "snapshot_record_sha256" in source:
                equal(flow_record_digest("flow_snapshot",value),source["snapshot_record_sha256"],"Snapshot record identity")
            return value, asdict(adapter.receipt)
        def request(source):
            if "request_wire" in source:
                value = decode_flow_request(source["request_wire"].encode("utf-8"))
                equal(encode_flow_request(value).decode("utf-8"),source["request_wire"],"Strict request roundtrip")
            else:
                value = flow_from_payload("flow_request",source["request"])
                value = decode_flow_request(encode_flow_request(value))
            if "request_record_sha256" in source:
                equal(flow_record_digest("flow_request",value),source["request_record_sha256"],"Request record identity")
            return value
        def suffix(payload):
            names = {"bindings":"flow_binding","references":"flow_reference","executions":"flow_execution",
                     "quotes":"flow_quote","groups":"flow_group","populations":"flow_population",
                     "context_certificates":"flow_context_certificate","baselines":"flow_baseline","cursors":"flow_cursor"}
            # Local strict record wires; retained references resolve only in real merge.
            return FlowSnapshot(payload["schema_version"], **{name:tuple(
                decode_flow_record(kind,encode_flow_record(kind,flow_from_payload(kind,item))) for item in payload[name]) for name,kind in names.items()})
        def prepare(source):
            req = request(source)
            operation = source.get("operation","evaluate")
            if operation == "restore":
                cp = flow_from_payload("flow_checkpoint",source["checkpoint"])
                cp = decode_flow_checkpoint(encode_flow_checkpoint(cp))
                tail = suffix(source["snapshot"])
                merged = merge_flow_history(cp,tail,req)
                merged_adapter = SyntheticFlowAdapter(encode_flow_snapshot(merged))
                equal(flow_canonical_bytes(merged_adapter.load()),flow_canonical_bytes(merged),"Merged restore strict adapter")
                cp_hash = flow_record_digest("flow_checkpoint",cp)
                if "input_checkpoint_sha256" in source:equal(cp_hash,source["input_checkpoint_sha256"],"Input checkpoint identity")
                direct = evaluate_flow(merged,req,input_checkpoint_sha256=cp_hash)
                restored, checkpoint_out = restore_flow(cp,tail,req)
                equal(encode_flow_results(restored),encode_flow_results(direct),"Real restore/direct bytes")
                return operation,[(direct,merged,req,cp_hash)],(cp,tail),[asdict(merged_adapter.receipt)]
            value, adapter = snapshot(source)
            if operation == "replay":
                requests = tuple(decode_flow_request(encode_flow_request(flow_from_payload("flow_request",item))) for item in source["requests"])
                cuts = replay_flow(value,requests)
                direct = tuple(evaluate_flow(value,cut) for cut in requests)
                equal(tuple(encode_flow_results(rows) for rows in cuts),tuple(encode_flow_results(rows) for rows in direct),"Real replay/direct bytes")
                return operation,list((rows,value,cut,None) for rows,cut in zip(direct,requests)),None,[adapter]
            equal(operation,"evaluate","Fixture operation")
            return operation,[(evaluate_flow(value,req),value,req,None)],None,[adapter]
        def compare(rows,value,req,checkpoint_hash,expected):
            for key, actual in (("snapshot_record_sha256",flow_record_digest("flow_snapshot",value)),
                                ("request_record_sha256",flow_record_digest("flow_request",req)),("input_checkpoint_sha256",checkpoint_hash)):
                if key in expected:equal(actual,expected[key],"Expected invocation "+key)
            equal(flow_to_payload(rows),expected["expected_results"],"All independent typed result fields")
            equal(flow_canonical_bytes(rows),canonical(expected["expected_results"]),"All independent canonical result bytes")
            equal(flow_record_digest("flow_results",rows),expected["expected_results_record_sha256"],"Independent complete results digest")
            equal(encode_flow_results(rows).decode("utf-8"),expected["expected_results_wire"],"Independent complete results wire")
        databases = output / "databases"
        databases.mkdir()
        seed = None
        full_cases = artifact["full_result_cases"]
        controls = [case for family in ("independent_baseline_status_controls","independent_observed_side_clock_controls") for case in artifact[family]]
        equal((len(full_cases),len(controls),len(artifact["input_error_cases"])),(66,5,19),"Frozen fixture census")
        equal(sum(len(case["invocations"]) for case in full_cases),68,"Frozen full invocation census")
        equal(sum(len(inv["expected_results"]) for case in full_cases for inv in case["invocations"]) + sum(len(case["expected_results"]) for case in controls),433,"Frozen complete row census")
        counters={"full_groups":0,"full_invocations":0,"controls":0,"complete_rows":0,"input_errors":0}
        def valid_case(case,index,control=False):
            nonlocal seed
            source=case["source_input"]
            expected_invocations=[case] if control else case["invocations"]
            operation, invocations, restoration, adapters=prepare(source)
            equal(len(invocations),len(expected_invocations),"Actual independent invocation census")
            keys=tuple(f"case{index:03d}-cut{cut}" for cut in range(len(invocations)))
            db=databases / f"case-{index:03d}.duckdb"
            with FlowDuckDBSink(str(db)) as sink:
                def dispatch():
                    if operation=="replay":
                        return execute_flow_replay(invocations[0][1],tuple(item[2] for item in invocations),run_keys=keys,
                            config=replace(config,mode="chronological_cut_replay"),verified_cohort=cohort,sink=sink)
                    if operation=="restore":
                        cp,tail=restoration
                        return (execute_flow_restore(cp,tail,invocations[0][2],run_key=keys[0],config=replace(config,mode="checkpoint_restore"),verified_cohort=cohort,sink=sink),)
                    return (execute_flow(invocations[0][1],invocations[0][2],run_key=keys[0],config=config,verified_cohort=cohort,sink=sink),)
                receipts=dispatch()
                retries=dispatch()
                equal(len(receipts),len(invocations),"Worker invocation census")
                equal(len(retries),len(invocations),"Retry invocation census")
                details=[]
                for ordinal,(invocation,expected,actual,retry) in enumerate(zip(invocations,expected_invocations,receipts,retries)):
                    rows,value,req,cp_hash=invocation
                    compare(rows,value,req,cp_hash,expected)
                    equal(actual.outcome,"committed","Real publication outcome")
                    equal(retry.outcome,"already_committed","Exact real retry outcome")
                    compare(actual.results,value,req,cp_hash,expected)
                    try:
                        direct_checkpoint=make_flow_checkpoint(value,req)
                    except FlowValidationError as error:
                        if error.code!="checkpoint_cut_mismatch":raise
                        direct_checkpoint=None
                    if direct_checkpoint is None:
                        equal(actual.output_checkpoint,None,"Direct/worker no output checkpoint")
                    else:
                        equal(flow_canonical_bytes(actual.output_checkpoint),flow_canonical_bytes(direct_checkpoint),"Direct/worker complete checkpoint parity")
                    equal(encode_flow_results(retry.results),encode_flow_results(rows),"Retry complete bytes")
                    stored=sink.read(keys[ordinal])
                    require(stored is not None,"Stored generation exists")
                    equal(encode_flow_results(stored.results),encode_flow_results(rows),"Stored complete result bytes")
                    equal(flow_canonical_bytes(stored.output_checkpoint),flow_canonical_bytes(actual.output_checkpoint),"Stored complete output checkpoint") if actual.output_checkpoint is not None else equal(stored.output_checkpoint,None,"No output checkpoint")
                    compare(stored.results,value,req,cp_hash,expected)
                    admission=inspect_flow_resources(value,req,config,restoration[0] if restoration else None)
                    details.append({"receipt":asdict(actual.commit_receipt),"retry":asdict(retry.commit_receipt),
                                    "logical_admission":asdict(admission),"wire_result_bytes":len(encode_flow_results(rows)),
                                    "publication_sha256":flow_record_digest("flow_publication",stored),"result_rows":len(rows)})
                    if seed is None and operation=="evaluate" and rows and actual.output_checkpoint is not None:
                        seed=(value,req,rows,expected)
                publications=tuple(flow_canonical_bytes(sink.read(key)) for key in keys)
            with FlowDuckDBSink(str(db)) as reopened:
                equal(tuple(flow_canonical_bytes(reopened.read(key)) for key in keys),publications,"Reopened complete generation parity")
            if control:counters["controls"]+=1
            else:
                counters["full_groups"]+=1
                counters["full_invocations"]+=len(invocations)
            counters["complete_rows"]+=sum(len(item[0]) for item in invocations)
            return {"operation":operation,"adapter_receipts":adapters,"invocations":details,"database":str(db)}
        for index,case in enumerate(full_cases):
            record(case["id"],"full_result",lambda case=case,index=index:valid_case(case,index))
        for index,case in enumerate(controls,start=len(full_cases)):
            record(case["source_input"]["id"],"control",lambda case=case,index=index:valid_case(case,index,True))
        originals={case["id"]:case for case in artifact["source_materialization"]["cases"]}
        def invalid_case(case):
            expected=case["expected_error"]
            try:
                prepare(originals[case["id"]])
            except FlowValidationError as error:
                equal(error.code,expected["code"],"Independent boundary code")
                if "path" in expected:equal(error.path,expected["path"],"Independent boundary pointer")
                if "exception_class" in expected:equal(type(error).__name__,expected["exception_class"],"Independent boundary class")
                # Repeat through a real worker where closed wire admission permits
                # constructing inputs. Invalid closed wires stop before dispatch.
                source=originals[case["id"]]
                worker_route=None
                try:
                    invalid_request=request(source)
                    if source.get("operation")=="restore":
                        cp=flow_from_payload("flow_checkpoint",source["checkpoint"])
                        cp=decode_flow_checkpoint(encode_flow_checkpoint(cp))
                        tail=suffix(source["snapshot"])
                        execute_flow_restore(cp,tail,invalid_request,run_key="invalid",config=replace(config,mode="checkpoint_restore"),verified_cohort=cohort)
                    else:
                        invalid_snapshot,_=snapshot(source)
                        execute_flow(invalid_snapshot,invalid_request,run_key="invalid",config=config,verified_cohort=cohort)
                except FlowValidationError as admission_error:
                    equal(admission_error.code,expected["code"],"Repeated strict wire boundary code")
                    if "path" in expected:equal(admission_error.path,expected["path"],"Repeated strict wire pointer")
                    worker_route={"stage":"strict_wire_before_dispatch","code":admission_error.code,"path":admission_error.path}
                except FlowWorkerError as worker_error:
                    actual_code=worker_error.cause_code or worker_error.code
                    equal(actual_code,expected["code"],"Real worker structured boundary cause")
                    if "path" in expected:equal(worker_error.cause_path,expected["path"],"Real worker structured boundary pointer")
                    worker_route={"stage":"actual_worker_dispatch","code":worker_error.code,
                                  "cause_code":worker_error.cause_code,"cause_path":worker_error.cause_path}
                else:
                    raise AssertionError("Invalid independent input returned successful worker receipt")
                counters["input_errors"]+=1
                return {"code":error.code,"path":error.path,"route":worker_route}
            raise AssertionError("Independent boundary exception absent")
        for case in artifact["input_error_cases"]:
            record(case["id"],"input_error",lambda case=case:invalid_case(case))
        require(seed is not None,"A complete original synthetic seed is required for fault qualification")
        value,req,rows,expected=seed
        class Token:
            def __init__(self,phase):
                self.phase,self.calls,self.observed=phase,0,[]
            def is_cancelled(self):
                self.calls+=1
                if self.phase is True:return True
                frame=inspect.currentframe().f_back
                try:
                    while frame:
                        if frame.f_code.co_name=="_run" and frame.f_globals.get("__name__")=="option_flow_workers.executor":
                            if self.phase=="mid" and "steps" in frame.f_locals and inspect.getgeneratorstate(frame.f_locals["steps"])==inspect.GEN_SUSPENDED:
                                self.observed.append("evaluation_generator_suspended")
                                return True
                            if self.phase=="precommit" and "publication" in frame.f_locals:
                                self.observed.append("publication_prepared_before_transaction")
                                return True
                        frame=frame.f_back
                finally:
                    del frame
                return False
        class InjectedFault(RuntimeError):pass
        class FaultSink(FlowDuckDBSink):
            def __init__(self,path,behavior,token=None):
                self.behavior,self.token,self.fired=behavior,token,False
                super().__init__(str(path))
            def _commit_transaction(self):
                if self.fired:return super()._commit_transaction()
                self.fired=True
                if self.behavior=="before_commit":raise InjectedFault("Simulated failure before actual COMMIT")
                super()._commit_transaction()
                if self.behavior=="lost_ack":raise InjectedFault("Simulated acknowledgement loss after actual COMMIT")
                if self.behavior=="postcommit":self.token.phase=True
        def cancellation_case(phase):
            token=Token(phase)
            db=databases / ("cancel-"+str(phase)+".duckdb")
            with FlowDuckDBSink(str(db)) as sink:
                receipt=execute_flow(value,req,run_key="cancel",config=config,verified_cohort=cohort,sink=sink,cancellation=token)
                equal((receipt.outcome,receipt.results,receipt.output_checkpoint,receipt.commit_receipt),("cancelled",(),None,None),"Cancelled execution has no outputs")
                equal(sink.read("cancel"),None,"Cancellation writes no generation")
                if phase in ("mid","precommit"):require(bool(token.observed),"Deterministic observed cancellation phase witness")
            return {"calls":token.calls,"observed":token.observed,"receipt":asdict(receipt)}
        for phase in (True,"mid","precommit"):
            record("cancellation-"+str(phase),"fault",lambda phase=phase:cancellation_case(phase))
        def commit_fault(behavior):
            token=Token(False)
            db=databases / ("fault-"+behavior+".duckdb")
            with FaultSink(db,behavior,token) as sink:
                if behavior=="before_commit":
                    try:execute_flow(value,req,run_key="fault",config=config,verified_cohort=cohort,sink=sink)
                    except FlowWorkerError as error:equal(error.code,"execution_failed","Real failed commit outcome")
                    else:raise AssertionError("Failed commit incorrectly returned success")
                    equal(sink.read("fault"),None,"Failed transaction rolled back all generations")
                receipt=execute_flow(value,req,run_key="fault",config=config,verified_cohort=cohort,sink=sink,cancellation=token)
                equal(receipt.outcome,"committed","Recovered/retried actual commit outcome")
                compare(receipt.results,value,req,None,expected)
                if behavior=="postcommit":require(receipt.cancellation_observed,"Postcommit cancellation retained successful generation")
                token.phase=False
                retry=execute_flow(value,req,run_key="fault",config=config,verified_cohort=cohort,sink=sink)
                equal(retry.outcome,"already_committed","Fault exact retry retained generation")
                publication=sink.read("fault")
                require(publication is not None,"Fault publication complete readback")
                equal(encode_flow_results(publication.results),encode_flow_results(rows),"Fault readback independent rows")
            with FlowDuckDBSink(str(db)) as reopened:
                equal(flow_canonical_bytes(reopened.read("fault")),flow_canonical_bytes(publication),"Fault reopened complete generation")
            return {"behavior":behavior,"fault_fired":sink.fired,"receipt":asdict(receipt.commit_receipt),"retry":asdict(retry.commit_receipt)}
        for behavior in ("before_commit","lost_ack","postcommit"):
            record(behavior,"fault",lambda behavior=behavior:commit_fault(behavior))
        def conflict_case():
            db=databases / "retry-conflict.duckdb"
            with FlowDuckDBSink(str(db)) as sink:
                execute_flow(value,req,run_key="same",config=config,verified_cohort=cohort,sink=sink)
                original=flow_canonical_bytes(sink.read("same"))
                changed=replace(req,limits=replace(req.limits,max_wire_bytes=req.limits.max_wire_bytes-1))
                try:execute_flow(value,changed,run_key="same",config=config,verified_cohort=cohort,sink=sink)
                except FlowWorkerError as error:equal(error.code,"publication_conflict","Changed invocation under same key conflicts")
                else:raise AssertionError("Changed invocation overwritten existing generation")
                equal(flow_canonical_bytes(sink.read("same")),original,"Conflict preserved original complete publication")
            return {"original_publication_sha256":sha256(original).hexdigest()}
        record("changed-invocation-conflict","fault",conflict_case)
        import duckdb
        def corruption_case(kind):
            db=databases / ("corruption-"+kind+".duckdb")
            with FlowDuckDBSink(str(db)) as sink:
                execute_flow(value,req,run_key="corrupt",config=config,verified_cohort=cohort,sink=sink)
            # Deliberate mutation is confined to this newly owned synthetic DB.
            connection=duckdb.connect(str(db),config={"threads":"1"})
            try:
                if kind=="missing_result":connection.execute("DELETE FROM flow_result_rows WHERE run_key=? AND ordinal=0",["corrupt"])
                elif kind=="metadata":connection.execute("UPDATE flow_generations SET state='broken' WHERE run_key=?",["corrupt"])
                elif kind=="binding":connection.execute("UPDATE flow_bindings SET canonical_json='{}' WHERE run_key=?",["corrupt"])
                elif kind=="schema":connection.execute("ALTER TABLE flow_generations ADD COLUMN unexpected VARCHAR")
                else:raise AssertionError("Unknown fixed corruption case")
            finally:connection.close()
            try:
                with FlowDuckDBSink(str(db)) as sink:sink.read("corrupt")
            except (StorageIntegrityError,StorageSchemaError) as error:
                return {"kind":kind,"actual_exception":type(error).__name__,"database":str(db)}
            raise AssertionError("Corrupt actual storage escaped readback checks")
        for kind in ("missing_result","metadata","binding","schema"):
            record("corruption-"+kind,"corruption",lambda kind=kind:corruption_case(kind))
        summary["counters"]=counters
        equal(counters,{"full_groups":66,"full_invocations":68,"controls":5,"complete_rows":433,"input_errors":19},"Completed independent census")
        verify_flow_installed(cohort,tuple(item["wheel_path"] for item in inputs),str(output/"installed-verification-final.json"),manifest,args.trusted_manifest_sha256)
        equal(file_digest(Path(__file__)),tool_sha,"Qualification tool unchanged")
        summary["passed"]=not summary["failures"]
    except BaseException as error:
        summary["fatal"]={"exception_class":type(error).__name__,"detail":str(error),"traceback":traceback.format_exc()}
        raise
    finally:
        summary.update(wall_seconds=time.perf_counter()-started,process_cpu_seconds=time.process_time()-cpu_started,
                       peak_rss=peak_rss(),tool_sha256_after=file_digest(Path(__file__)))
        write_new(output/"integration-attempt.json",summary)
    return summary["passed"]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("artifact","inputs","manifest","provenance","output"):
        parser.add_argument("--"+name,required=True,type=Path)
    for name in ("artifact-sha256","trusted-manifest-sha256","provenance-sha256","lease"):
        parser.add_argument("--"+name,required=True)
    raise SystemExit(0 if run(parser.parse_args()) else 1)

if __name__=="__main__":main()
