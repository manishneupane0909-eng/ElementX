from datetime import datetime

import numpy as np
from scipy.signal import find_peaks

import database
import local_store
from models.sample import SampleCreate, sample_document
from services.demo_data import DEMO_PROJECT, DEMO_SAMPLES, DEMO_NAME, DEMO_EMAIL
from services.dopant_ranker import rank_dopant_recommendations
from services.demo_data import synthetic_xrd_pattern, synthetic_mh_loop
from services.phase_detector import detect_tau_mnal


def _serialize_id(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.get("_id", d.get("id", "")))
    if "_id" in d:
        d.pop("_id", None)
    return d


async def _seed_into_local(user_id: str, force: bool) -> dict:
    existing = local_store.count_samples(user_id, DEMO_PROJECT)
    if existing >= len(DEMO_SAMPLES) and not force:
        samples = local_store.find_samples(user_id, DEMO_PROJECT)
        return {
            "success": True,
            "alreadyLoaded": True,
            "message": "Demo lab already loaded — open Sample Database or AI Discovery.",
            "sampleIds": [str(s["_id"]) for s in samples],
            "projectName": DEMO_PROJECT,
            "localMode": True,
        }

    if force and existing:
        local_store.delete_project_samples(user_id, DEMO_PROJECT)

    created_ids: list[str] = []

    for spec in DEMO_SAMPLES:
        payload = SampleCreate(
            name=spec["name"],
            formula=spec["formula"],
            material_family=spec["material_family"],
            dopants=spec["dopants"],
            synthesis=spec["synthesis"],
            status=spec["status"],
            project_name=DEMO_PROJECT,
        )
        doc = sample_document(user_id, payload)
        doc["outcomeLabel"] = spec["outcome_label"]
        doc["projectName"] = DEMO_PROJECT
        created = local_store.create_sample(user_id, doc)
        sample_id = created["id"]
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
        phase_analysis = detect_tau_mnal(peak_list)

        xrd_id = local_store.insert_xrd(
            user_id,
            sample_id,
            {
                "filename": f"{spec['name'].replace(' ', '_')}.txt",
                "data": [{"angle": p[0], "intensity": p[1]} for p in xrd_points],
                "peaks": peak_list,
                "notes": "ElementX demo dataset",
                "createdAt": datetime.utcnow(),
            },
        )

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

        mag_id = local_store.insert_magnetic(
            user_id,
            sample_id,
            {
                "filename": f"{spec['name'].replace(' ', '_')}_MH.txt",
                "measurementType": "M-H",
                "data": [{"x": p[0], "y": p[1]} for p in mh_points],
                "properties": props,
                "notes": "ElementX demo dataset",
                "createdAt": datetime.utcnow(),
            },
        )

        local_store.update_sample(
            sample_id,
            user_id,
            {
                "characterization": {
                    "xrd": {
                        "id": xrd_id,
                        "filename": f"{spec['name'].replace(' ', '_')}.txt",
                        "peaks": peak_list,
                        "pointCount": len(xrd_points),
                        "uploadedAt": datetime.utcnow().isoformat(),
                    },
                    "magnetic": {
                        "id": mag_id,
                        "filename": f"{spec['name'].replace(' ', '_')}_MH.txt",
                        "measurementType": "M-H",
                        "properties": props,
                        "uploadedAt": datetime.utcnow().isoformat(),
                    },
                },
                "phaseAnalysis": phase_analysis,
                "status": "characterized",
            },
        )

    all_docs = [_serialize_id(s) for s in local_store.find_samples(user_id, DEMO_PROJECT)]
    ranked = rank_dopant_recommendations(
        all_docs, material_family="mnal_tau", project_name=DEMO_PROJECT, limit=3
    )
    now = datetime.utcnow()
    if created_ids:
        local_store.update_sample(
            created_ids[0],
            user_id,
            {
                "aiRecommendations": [
                    {**rec, "generatedAt": now} for rec in ranked["recommendations"]
                ],
            },
        )

    return {
        "success": True,
        "alreadyLoaded": False,
        "localMode": True,
        "message": f"Loaded {len(created_ids)} demo samples (local mode — no MongoDB).",
        "sampleIds": created_ids,
        "projectName": DEMO_PROJECT,
        "stats": {"samples": len(created_ids), "tauPhaseDetected": 1, "recommendationsReady": True},
        "recommendations": ranked["recommendations"],
        "pitchHint": "Open AI Discovery → ask copilot about τ-phase, or view DEMO MnAl-C 5% in Sample Database.",
    }


async def seed_demo_lab(user_id: str, *, force: bool = False) -> dict:
    if database.DB_AVAILABLE:
        from services.demo_seed import seed_demo_lab as _mongo_seed

        result = await _mongo_seed(user_id, force=force)
        result["localMode"] = False
        return result
    return await _seed_into_local(user_id, force)
