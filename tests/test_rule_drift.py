import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('rule_drift',Path(__file__).resolve().parents[1]/'tools/rule_drift.py')
drift=importlib.util.module_from_spec(spec);spec.loader.exec_module(drift)


def test_old_restrictions_are_review_flags_not_permissions():
    flags=drift.assess('You must use only 5 degree steps in the 85–95 range.')
    assert 'possible-reference-workflow-promoted-to-restriction' in flags
    assert 'request-origin-not-visible-in-nearby-text' in flags


def test_origin_is_evidence_not_automatic_approval():
    flags=drift.assess('Only slow movement is allowed.','Instructor confirmed this example.')
    assert 'request-origin-not-visible-in-nearby-text' not in flags
    assert 'possible-reference-workflow-promoted-to-restriction' in flags


def test_code_fact_conflict_is_explicit():
    assert drift.assess('SDA=GPIO3',assignments={'SDA':'s3.GPIO2'})==['documented-SDA-assignment-differs-from-current-firmware:s3.GPIO2']
    assert drift.assess('SDA=GPIO2',assignments={'SDA':'s3.GPIO2'})==[]


def test_reference_exercise_not_automatically_a_restriction():
    assert drift.assess('An earlier experiment moved 5 degrees.')==[]
    assert 'possible-reference-deliverable-as-project-ceiling' in drift.assess('The goal is two tricks.')


def test_historical_wiring_record_prerequisite_is_detected():
    text="Before firmware upload/debug, ask the student to complete the canonical guide's"
    flags=drift.assess(text,text+'\n[final wiring checks] and paste evidence')
    assert 'possible-reference-workflow-promoted-to-restriction' in flags
    assert drift.assess('CAD/topology PASS was never a physical measurement.')==[]
