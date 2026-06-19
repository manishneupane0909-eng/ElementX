from datetime import datetime

import numpy as np
from bson import ObjectId
from scipy.signal import find_peaks

import database
from models.sample import sample_document
from models.sample import SampleCreate, Dopant, Synthesis
from services.demo_data import DEMO_PROJECT, DEMO_SAMPLES
from services.dopant_ranker import rank_dopant_recommendations
from services.demo_data import synthetic_xrd_pattern, synthetic_mh_loop
from services.phase_detector import detect_tau_mnal


def _serialize_id(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return d


async def seed_demo_lab(user_id: str, *, force: bool = False) -> dict:
    if not database.DB_AVAILABLE:
        raise RuntimeError("MongoDB required for demo data")

    existing = await database.db.samples.count_documents(
        {"userId": user_id, "projectName": DEMO_PROJECT}
    )
    if existing >= len(DEMO_SAMPLES) and not force:
        cursor = database.db.samples.find(
            {"userId": user_id, "projectName": DEMO_PROJECT}
        ).sort("createdAt", 1)
        ids = [str(doc["_id"]) async for doc in cursor]
        return {
            "success": True,
            "alreadyLoaded": True,
            "message": "Demo lab already loaded — check Sample Database or Lab chat.",
            "sampleIds": ids,
            "projectName": DEMO_PROJECT,
        }

    if force and existing:
        sample_ids_old = [
            str(doc["_id"])
            async for doc in database.db.samples.find(
                {"userId": user_id, "projectName": DEMO_PROJECT}, {"_id": 1}
            )
        ]
        if sample_ids_old:
            await database.db.xrd.delete_many(
                {"userId": user_id, "sampleId": {"$in": sample_ids_old}}
            )
            await database.db.magnetic.delete_many(
                {"userId": user_id, "sampleId": {"$in": sample_ids_old}}
            )
        await database.db.samples.delete_many(
            {"userId": user_id, "projectName": DEMO_PROJECT}
        )

    created_ids: list[str] = []

    for spec in DEMO_SAMPLES:
        payload = SampleCreate(
            name=spec["name"],
            formula=spec["formula"],
            material_family=spec["material_family"],
            dopants=[Dopant(**d) for d in spec["dopants"]],
            synthesis=Synthesis(**spec["synthesis"]),
            status=spec["status"],
            project_name=DEMO_PROJECT,
        )
        doc = sample_document(user_id, payload)
        doc["outcomeLabel"] = spec["outcome_label"]
        doc["projectName"] = DEMO_PROJECT

        result = await database.db.samples.insert_one(doc)
        sample_id = str(result.inserted_id)
        created_ids.append(sample_id)

        xrd_points = synthetic_xrd_pattern(spec["xrd_peaks"])
        angles = np.array([p[0] for p in xrd_points])
        intensities = np.array([p[1] for p in xrd_points])
        peaks_idx, _ = find_peaks(
            intensities, prominence=0.02 * intensities.max(), distance=10
        )
        peak_list = [
            {"angle": float(angles[i]), "intensity": float(intensities[i])}
            for i in peaks_idx
        ]

        xrd_result = await database.db.xrd.insert_one(
            {
                "userId": user_id,
                "sampleId": sample_id,
                "filename": f"{spec['name'].replace(' ', '_')}.txt",
                "data": [{"angle": p[0], "intensity": p[1]} for p in xrd_points],
                "peaks": peak_list,
                "notes": "ElementX demo dataset",
                "createdAt": datetime.utcnow(),
            }
        )

        phase_analysis = detect_tau_mnal(peak_list)
        xrd_summary = {
            "id": str(xrd_result.inserted_id),
            "filename": f"{spec['name'].replace(' ', '_')}.txt",
            "peaks": peak_list,
            "pointCount": len(xrd_points),
            "uploadedAt": datetime.utcnow().isoformat(),
        }

        mh_points = synthetic_mh_loop(ms=spec["magnetic_ms"])
        x_vals = np.array([p[0] for p in mh_points])
        y_vals = np.array([p[1] for p in mh_points])
        props = {
            "Ms": float(np.max(np.abs(y_vals))),
            "Mr": float(np.abs(np.interp(0, x_vals, y_vals)))
            if np.any(np.diff(np.sign(x_vals)))
            else 0.0,
            "Hc": float(np.abs(np.interp(0, y_vals, x_vals)))
            if np.any(np.diff(np.sign(y_vals)))
            else 0.0,
        }

        mag_result = await database.db.magnetic.insert_one(
            {
                "userId": user_id,
                "sampleId": sample_id,
                "filename": f"{spec['name'].replace(' ', '_')}_MH.txt",
                "measurementType": "M-H",
                "data": [{"x": p[0], "y": p[1]} for p in mh_points],
                "properties": props,
                "notes": "ElementX demo dataset",
                "createdAt": datetime.utcnow(),
            }
        )

        mag_summary = {
            "id": str(mag_result.inserted_id),
            "filename": f"{spec['name'].replace(' ', '_')}_MH.txt",
            "measurementType": "M-H",
            "properties": props,
            "uploadedAt": datetime.utcnow().isoformat(),
        }

        await database.db.samples.update_one(
            {"_id": ObjectId(sample_id)},
            {
                "$set": {
                    "characterization": {"xrd": xrd_summary, "magnetic": mag_summary},
                    "phaseAnalysis": phase_analysis,
                    "status": "characterized",
                    "updatedAt": datetime.utcnow(),
                }
            },
        )

    all_docs = [
        _serialize_id(doc)
        async for doc in database.db.samples.find(
            {"userId": user_id, "projectName": DEMO_PROJECT}
        )
    ]
    for doc in all_docs:
        if not doc.get("phaseAnalysis") and doc.get("characterization", {}).get("xrd"):
            doc["phaseAnalysis"] = detect_tau_mnal(
                doc["characterization"]["xrd"].get("peaks") or []
            )

    ranked = rank_dopant_recommendations(
        all_docs,
        material_family="mnal_tau",
        project_name=DEMO_PROJECT,
        limit=3,
    )
    now = datetime.utcnow()
    if created_ids:
        await database.db.samples.update_one(
            {"_id": ObjectId(created_ids[0])},
            {
                "$set": {
                    "aiRecommendations": [
                        {**rec, "generatedAt": now} for rec in ranked["recommendations"]
                    ],
                    "updatedAt": now,
                }
            },
        )

    tau_count = sum(
        1
        for d in all_docs
        if (d.get("phaseAnalysis") or {}).get("tauDetected")
        or detect_tau_mnal(
            (d.get("characterization") or {}).get("xrd", {}).get("peaks") or []
        ).get("tauDetected")
    )

    return {
        "success": True,
        "alreadyLoaded": False,
        "message": f"Loaded {len(created_ids)} demo samples with XRD, VSM, and sample suggestions.",
        "sampleIds": created_ids,
        "projectName": DEMO_PROJECT,
        "stats": {
            "samples": len(created_ids),
            "tauPhaseDetected": tau_count,
            "recommendationsReady": True,
        },
        "recommendations": ranked["recommendations"],
        "pitchHint": "Open Lab chat or Sample Database and try DEMO MnAl-C 5%.",
    }
