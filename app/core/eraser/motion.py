from __future__ import annotations

import cv2
import numpy as np

from .temporal_qa import ring_mae_robust


def complete_flow(flow: np.ndarray, mask: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    hard = (mask > 0).astype(np.uint8) * 255
    completed = flow.astype(np.float32).copy()
    if not np.any(hard):
        return completed
    for channel in range(2):
        values = completed[..., channel].copy()
        values[hard > 0] = 0.0
        values = cv2.inpaint(values, hard, 3.0, cv2.INPAINT_TELEA)
        if sigma > 0:
            values = cv2.GaussianBlur(values, (0, 0), sigmaX=sigma, sigmaY=sigma)
        completed[..., channel] = values
    return completed


def _gray(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def estimate_homography(reference: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    orb = cv2.ORB_create(nfeatures=900)
    valid = cv2.bitwise_not((mask > 0).astype(np.uint8) * 255)
    kp_ref, des_ref = orb.detectAndCompute(_gray(reference), valid)
    kp_target, des_target = orb.detectAndCompute(_gray(target), valid)
    if des_ref is None or des_target is None or len(kp_ref) < 8 or len(kp_target) < 8:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(des_ref, des_target, k=2)
    good = [m for m, n in pairs if m.distance < 0.75 * n.distance]
    if len(good) < 6:
        return None
    src = np.float32([kp_ref[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_target[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, _ = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    return matrix


def _warp_homography(reference: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray:
    matrix = estimate_homography(reference, target, mask)
    if matrix is None:
        return reference.copy()
    h, w = target.shape[:2]
    return cv2.warpPerspective(reference, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _dense_refine(reference_aligned: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray:
    target_gray = _gray(target)
    reference_gray = _gray(reference_aligned)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    dis.setUseSpatialPropagation(True)
    flow = dis.calc(target_gray, reference_gray, None)
    flow = complete_flow(flow, cv2.dilate((mask > 0).astype(np.uint8) * 255, np.ones((5, 5), np.uint8)), sigma=2.0)
    h, w = target.shape[:2]
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    map_x = xx + flow[..., 0]
    map_y = yy + flow[..., 1]
    return cv2.remap(reference_aligned, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def align_reference(reference: np.ndarray, target: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float, str]:
    identity = reference.copy()
    global_warp = _warp_homography(reference, target, mask)
    dense = _dense_refine(global_warp, target, mask)
    candidates = ((identity, "identity"), (global_warp, "homography"), (dense, "dense"))
    scored = [(ring_mae_robust(image, target, mask), name, image) for image, name in candidates]
    scored.sort(key=lambda item: item[0])
    score, name, image = scored[0]
    return image, float(score), name
