from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

import database
import local_store
from auth import verify_token
from models.sample import SampleCreate, SampleUpdate, sample_document
from services.dopant_ranker import rank_dopant_recommendations
from services.experiment_brief import generate_experiment_brief

router = APIRouter(prefix="/api/samples", tags=["samples"])


def _serialize(doc: dict) -> dict:
    if not database.DB_AVAILABLE:
        return local_store._serialize(doc)  # noqa: SLF001

    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for key in ("createdAt", "updatedAt"):
        if key in doc and doc[key]:
            doc[key] = doc[key].isoformat()
    if doc.get("aiRecommendations"):
        for rec in doc["aiRecommendations"]:
            if rec.get("generatedAt") and hasattr(rec["generatedAt"], "isoformat"):
                rec["generatedAt"] = rec["generatedAt"].isoformat()
    return doc


async def _get_owned_sample(sample_id: str, user_id: str) -> dict:
    if database.DB_AVAILABLE:
        if not ObjectId.is_valid(sample_id):
            raise HTTPException(400, "Invalid sample id")
        sample = await database.db.samples.find_one(
            {"_id": ObjectId(sample_id), "userId": user_id}
        )
        if not sample:
            raise HTTPException(404, "Sample not found")
        return sample

    sample = local_store.get_raw_sample(sample_id, user_id)
    if not sample:
        raise HTTPException(404, "Sample not found")
    return sample


async def _project_samples(user_id: str, project_name: str | None) -> list[dict]:
    if database.DB_AVAILABLE:
        query: dict = {"userId": user_id}
        if project_name:
            query["projectName"] = project_name
        return [doc async for doc in database.db.samples.find(query).sort("createdAt", -1)]

    return local_store.find_samples(user_id, project_name)


@router.post("")
async def create_sample(payload: SampleCreate, user=Depends(verify_token)):
    doc = sample_document(user["userId"], payload)
    if database.DB_AVAILABLE:
        result = await database.db.samples.insert_one(doc)
        created = await database.db.samples.find_one({"_id": result.inserted_id})
        return _serialize(created)
    return local_store.create_sample(user["userId"], doc)


@router.get("")
async def list_samples(user=Depends(verify_token)):
    if database.DB_AVAILABLE:
        cursor = database.db.samples.find({"userId": user["userId"]}).sort("createdAt", -1)
        return [_serialize(doc) async for doc in cursor]
    return local_store.list_samples(user["userId"])


@router.get("/{sample_id}")
async def get_sample(sample_id: str, user=Depends(verify_token)):
    if database.DB_AVAILABLE:
        sample = await _get_owned_sample(sample_id, user["userId"])
        xrd_records = [
            _serialize(doc)
            async for doc in database.db.xrd.find(
                {"userId": user["userId"], "sampleId": sample_id}
            ).sort("createdAt", -1)
        ]
        magnetic_records = [
            _serialize(doc)
            async for doc in database.db.magnetic.find(
                {"userId": user["userId"], "sampleId": sample_id}
            ).sort("createdAt", -1)
        ]
        payload = _serialize(sample)
        payload["xrdRecords"] = xrd_records
        payload["magneticRecords"] = magnetic_records
        return payload

    payload = local_store.get_sample(sample_id, user["userId"])
    if not payload:
        raise HTTPException(404, "Sample not found")
    return payload


@router.post("/{sample_id}/recommend")
async def recommend_experiments(sample_id: str, user=Depends(verify_token)):
    sample = await _get_owned_sample(sample_id, user["userId"])
    project_name = sample.get("projectName")
    family = sample.get("materialFamily", "mnal_tau")

    project_docs = await _project_samples(user["userId"], project_name)
    serialized = [_serialize(dict(d)) for d in project_docs]

    result = rank_dopant_recommendations(
        serialized,
        material_family=family,
        project_name=project_name,
        limit=3,
    )

    now = datetime.utcnow()
    recs_with_ts = [{**rec, "generatedAt": now} for rec in result["recommendations"]]

    if database.DB_AVAILABLE:
        await database.db.samples.update_one(
            {"_id": ObjectId(sample_id), "userId": user["userId"]},
            {"$set": {"aiRecommendations": recs_with_ts, "updatedAt": now}},
        )
    else:
        local_store.update_sample(
            sample_id, user["userId"], {"aiRecommendations": recs_with_ts}
        )

    return {
        "success": True,
        "sampleId": sample_id,
        "summary": result["summary"],
        "modelVersion": result["modelVersion"],
        "recommendations": result["recommendations"],
    }


@router.post("/{sample_id}/experiment-brief")
async def experiment_brief(sample_id: str, user=Depends(verify_token)):
    sample = await _get_owned_sample(sample_id, user["userId"])
    project_name = sample.get("projectName")
    project_docs = await _project_samples(user["userId"], project_name)

    recommendations = sample.get("aiRecommendations") or []
    if not recommendations:
        ranked = rank_dopant_recommendations(
            [_serialize(dict(d)) for d in project_docs],
            material_family=sample.get("materialFamily", "mnal_tau"),
            project_name=project_name,
            limit=3,
        )
        recommendations = ranked["recommendations"]

    brief = await generate_experiment_brief(sample, recommendations, project_docs)
    return {"success": True, **brief}


@router.patch("/{sample_id}")
async def update_sample(sample_id: str, payload: SampleUpdate, user=Depends(verify_token)):
    await _get_owned_sample(sample_id, user["userId"])

    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    field_map = {
        "material_family": "materialFamily",
        "project_name": "projectName",
        "outcome_label": "outcomeLabel",
    }
    mongo_updates = {}
    for key, value in updates.items():
        mongo_key = field_map.get(key, key)
        mongo_updates[mongo_key] = value

    mongo_updates["updatedAt"] = datetime.utcnow()

    if database.DB_AVAILABLE:
        await database.db.samples.update_one(
            {"_id": ObjectId(sample_id), "userId": user["userId"]},
            {"$set": mongo_updates},
        )
        updated = await database.db.samples.find_one({"_id": ObjectId(sample_id)})
        return _serialize(updated)

    updated = local_store.update_sample(sample_id, user["userId"], mongo_updates)
    return updated


@router.delete("/{sample_id}")
async def delete_sample(sample_id: str, user=Depends(verify_token)):
    await _get_owned_sample(sample_id, user["userId"])
    if database.DB_AVAILABLE:
        await database.db.samples.delete_one(
            {"_id": ObjectId(sample_id), "userId": user["userId"]}
        )
    else:
        local_store.delete_sample(sample_id, user["userId"])
    return {"success": True}
