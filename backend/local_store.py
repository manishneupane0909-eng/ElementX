"""In-memory sample store when MongoDB is unavailable (local demos)."""

from copy import deepcopy
from datetime import datetime
from uuid import uuid4

_SAMPLES: dict[str, dict] = {}
_XRD: dict[str, dict] = {}
_MAGNETIC: dict[str, dict] = {}
_LOCAL_USERS_BY_EMAIL: dict[str, dict] = {}


def upsert_local_user(email: str, doc: dict) -> str:
    _LOCAL_USERS_BY_EMAIL[email] = doc
    return str(doc["_id"])


def get_local_user(email: str) -> dict | None:
    return _LOCAL_USERS_BY_EMAIL.get(email)


def _now():
    return datetime.utcnow()


def _serialize(doc: dict) -> dict:
    out = deepcopy(doc)
    oid = out.pop("_id", out.get("id"))
    out["id"] = str(oid)
    for key in ("createdAt", "updatedAt"):
        if key in out and out[key] and hasattr(out[key], "isoformat"):
            out[key] = out[key].isoformat()
    if out.get("aiRecommendations"):
        for rec in out["aiRecommendations"]:
            if rec.get("generatedAt") and hasattr(rec["generatedAt"], "isoformat"):
                rec["generatedAt"] = rec["generatedAt"].isoformat()
    return out


def list_samples(user_id: str) -> list[dict]:
    items = [s for s in _SAMPLES.values() if s.get("userId") == user_id]
    items.sort(key=lambda x: x.get("createdAt") or _now(), reverse=True)
    return [_serialize(s) for s in items]


def get_sample(sample_id: str, user_id: str) -> dict | None:
    doc = _SAMPLES.get(sample_id)
    if not doc or doc.get("userId") != user_id:
        return None
    payload = _serialize(doc)
    payload["xrdRecords"] = [
        _serialize(x)
        for x in _XRD.values()
        if x.get("userId") == user_id and x.get("sampleId") == sample_id
    ]
    payload["magneticRecords"] = [
        _serialize(m)
        for m in _MAGNETIC.values()
        if m.get("userId") == user_id and m.get("sampleId") == sample_id
    ]
    return payload


def create_sample(user_id: str, doc: dict) -> dict:
    sid = str(uuid4())
    stored = deepcopy(doc)
    stored["_id"] = sid
    stored["userId"] = user_id
    _SAMPLES[sid] = stored
    return _serialize(stored)


def update_sample(sample_id: str, user_id: str, updates: dict) -> dict | None:
    doc = _SAMPLES.get(sample_id)
    if not doc or doc.get("userId") != user_id:
        return None
    doc.update(updates)
    doc["updatedAt"] = _now()
    return _serialize(doc)


def delete_sample(sample_id: str, user_id: str) -> bool:
    doc = _SAMPLES.pop(sample_id, None)
    if not doc or doc.get("userId") != user_id:
        return False
    for store in (_XRD, _MAGNETIC):
        for key in list(store.keys()):
            if store[key].get("sampleId") == sample_id:
                del store[key]
    return True


def insert_xrd(user_id: str, sample_id: str | None, record: dict) -> str:
    rid = str(uuid4())
    stored = deepcopy(record)
    stored["_id"] = rid
    stored["userId"] = user_id
    stored["sampleId"] = sample_id
    _XRD[rid] = stored
    return rid


def insert_magnetic(user_id: str, sample_id: str | None, record: dict) -> str:
    rid = str(uuid4())
    stored = deepcopy(record)
    stored["_id"] = rid
    stored["userId"] = user_id
    stored["sampleId"] = sample_id
    _MAGNETIC[rid] = stored
    return rid


def find_samples(user_id: str, project_name: str | None = None) -> list[dict]:
    items = [s for s in _SAMPLES.values() if s.get("userId") == user_id]
    if project_name:
        items = [s for s in items if s.get("projectName") == project_name]
    items.sort(key=lambda x: x.get("createdAt") or _now(), reverse=True)
    return [deepcopy(s) for s in items]


def count_samples(user_id: str, project_name: str) -> int:
    return sum(
        1
        for s in _SAMPLES.values()
        if s.get("userId") == user_id and s.get("projectName") == project_name
    )


def delete_project_samples(user_id: str, project_name: str) -> list[str]:
    ids = [
        sid
        for sid, s in _SAMPLES.items()
        if s.get("userId") == user_id and s.get("projectName") == project_name
    ]
    for sid in ids:
        delete_sample(sid, user_id)
    return ids


def get_raw_sample(sample_id: str, user_id: str) -> dict | None:
    doc = _SAMPLES.get(sample_id)
    if not doc or doc.get("userId") != user_id:
        return None
    return doc
