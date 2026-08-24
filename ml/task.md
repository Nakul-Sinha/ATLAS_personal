# ATLAS ML Pipeline - Implementation Tasks

**Last Updated:** 2026-02-10 04:08 IST

---

## Phase 1: Model Integration ✅ COMPLETE (VERIFIED)

| Item | Status | Verification |
|------|--------|--------------|
| Project structure | ✅ | `ml/` with 7 subdirectories |
| `config/settings.py` | ✅ | Pydantic models for all config |
| `models/ocr_model.py` | ✅ | EasyOCR wrapper (updated) |
| `models/vlm_model.py` | ✅ | 253 lines, LLaVA wrapper (Ollama backend) |
| `models/llm_model.py` | ✅ | 404 lines, Ollama + llama-cpp dual backend |
| `perception/` | ✅ | screen_capture, bbox_fusion, engine |
| `actions/` | ✅ | actions.py, executor.py |
| `agent/` | ✅ | agent_loop, state, verification |
| `memory/` | ✅ | memory.py (SQLite) — **implemented but not wired into agent loop** |
| Dependencies installed | ✅ | All core packages working |

---

## Phase 2: Model Testing & Validation ✅ COMPLETE (VERIFIED)

| Item | Status | Verification |
|------|--------|--------------|
| **OCR (EasyOCR)** | ✅ | 196-226 text regions detected |
| **Screen capture (mss)** | ✅ | 1920x1080 captured |
| **PyAutoGUI** | ✅ | Mouse position + screen size working |
| **llama-cpp-python** | ✅ | Import + model load + inference working |
| **GGUF model downloaded** | ✅ | TinyLlama 1.1B (668MB) — fallback only |
| **VLM (LLaVA via Ollama)** | ✅ | Working via Ollama backend |

---

## Phase 3: Perception Pipeline ✅ COMPLETE (VERIFIED)

| Item | Status | Verification |
|------|--------|--------------|
| **Update OCR to EasyOCR** | ✅ | `ocr_model.py` rewritten |
| **Screen capture** | ✅ | 1920x1080, DPI scale: 1.0 |
| **Coordinate normalization** | ✅ | to_absolute/to_normalized working |
| **DPI detection** | ✅ | Windows API detection implemented |
| **BBox fusion** | ✅ | 198-207 elements, 0.05s |
| **Perception engine** | ✅ | quick_perceive() works without VLM |
| **Element search** | ✅ | get_element_by_text() found "File" |
| **Full pipeline benchmark** | ✅ | ~19s (OCR is ~30s on CPU) |

### Phase 3 Notes:
- VLM is **optional** - perception engine works with OCR only
- OCR running on CPU (GPU enabled in config, but PyTorch is CPU-only)
- Full pipeline: capture (0.1s) → OCR (~30s) → fusion (0.05s)

---

## Phase 4: Action Execution ✅ COMPLETE (VERIFIED)

| Item | Status | Verification |
|------|--------|--------------|
| **PyAutoGUI executor** | ✅ | Mouse movement precise (0px error) |
| **Direct actions** | ✅ | Click, Type, Key, Scroll, Wait implemented |
| **Coordinate conversion** | ✅ | Normalized ↔ Absolute round-trip verified |
| **Screen resolution** | ✅ | 1920x1080 detected correctly |
| **Safety mechanisms** | ✅ | FAILSAFE=True, PAUSE=0.1s enabled |
| **Action logging** | ✅ | Last action tracked successfully |

---

## Phase 5: Visual Verification ✅ COMPLETE (VERIFIED)
| Item | Status | Verification |
|------|--------|--------------|
| **Visual Diff Logic** | ✅ | OpenCV MSE + pixel-change % implemented |
| **Change Detection** | ✅ | >1% pixel change detected (Win key) |
| **Noise Filtering** | ✅ | <1% changes classified as "minor" |
| **Verification Logic** | ✅ | Integrated into `verification.py` |

---

## Phase 6: Agent Loop Integration ✅ COMPLETE (VERIFIED)
| Item | Status | Verification |
|------|--------|--------------|
| **Pipeline Wiring** | ✅ | PERCEIVE → PLAN → ACT → VERIFY loop works |
| **Step Logic** | ✅ | Step execution and advancement verified |
| **Task Completion** | ✅ | Detects end of plan and exits |
| **Error Handling** | ⚠️ | Basic retry only — `LLMModel.handle_error()` exists but NOT wired in |

### Phase 6 Known Gaps (pre-Phase 8):
- `Memory` module implemented but **never called** from `AgentLoop`
- `LLMModel.handle_error()` (LLM-guided recovery) is **dead code** — agent only does blind retries
- `LLMModel.rank_candidates()` is **dead code** — never called from fusion or agent
- `quick_perceive()` (OCR-only) always used — VLM never runs even when `config.vlm.use_vlm=True`

---

## Phase 7: End-to-End Testing ✅ COMPLETE
| Item | Status | Details |
|------|--------|---------|
| **LLM Backend** | ✅ | Ollama (`llama3.2`) |
| **VLM Backend** | ✅ | Ollama (`llava`) |
| **Simple Task** | ✅ | "Open Notepad" works |
| **Multi-step** | ✅ | "Open Notepad & Type Hello" works |

### Required Models (Ollama)
The user already has these installed. If not, run:
```bash
ollama pull llama3.2
ollama pull llava
```

---

## Phase 8: Optimization & Refinement DONE

| Item | Status | Details |
|------|--------|---------|
| **Memory Integration** | DONE | `Memory` wired into `AgentLoop` -- stores patterns on success, boosts confidence on lookup |
| **LLM Error Recovery** | DONE | `handle_error()` wired into retry logic -- LLM decides retry/skip/abort |
| **VLM in Agent Loop** | DONE | VLM available but OCR-only used by default (VLM bboxes unreliable, ~60s latency) |
| **rank_candidates Wiring** | DONE | LLM ranks candidates when multiple fuzzy matches found during action resolution |
| **App Navigation (Win+S)** | DONE | Task planner instructs Win+S search; deterministic override ensures key/type actions |
| **Deterministic Action Override** | DONE | Bypasses LLM for key press/type steps (LLM was hallucinating click targets) |
| **Latency Optimization** | PARTIAL | OCR-only path ~5s per step; VLM path ~60s (deferred) |

### Phase 8 Component Test Results (16/16 PASS)
- Config, Screen Capture, OCR, BBox Fusion, Perception Engine, Actions, Executor
- LLM Intent Extraction, Task Planning, Action Planning
- VLM Screen Description, UI Element Detection
- Verification, Memory, Agent State, Agent Loop import

### Phase 8 E2E Test Results
- **Task**: "Open Notepad" — **PASSED** in 94s
- Plan: Win+S → type "notepad" → Enter (3 steps, all verified)
- All actions executed via deterministic override (no LLM hallucination)

---

## Phase 9: Critical Issues (from errors.txt)
- [x] CRITICAL-001: DPI/Scaling handling. set_dpi_awareness() is called at agent
      init so captured pixels and click pixels share one space, and clicks now go
      through ScreenFrame.to_absolute() instead of bypassing it.
- [x] CRITICAL-002: Modal/Dialog detection. perception/modal_detection.py detects a
      centered blocking overlay; the agent loop checks it each step.
- [x] CRITICAL-003: App window state tracking. perception/window_state.py inspects
      and focuses the target window (best-effort, Windows) at task start.
- [x] CRITICAL-004: Multi-monitor support. ScreenFrame keeps the monitor offset and
      to_absolute() adds it, so clicks land correctly on non-primary monitors.

---

## Phase 10: Non-Critical Robustness (from errors.txt)
- [x] NON-CRIT-001: Error classification taxonomy. agent/error_taxonomy.py routes a
      failure to PERCEPTION / EXECUTION / STATE / TASK and the loop skips infeasible
      tasks instead of burning retries.
- [x] NON-CRIT-002: Typing and input buffering. Chunked, unicode-safe typing in the
      executor avoids dropped keystrokes.
- [x] NON-CRIT-003: Multi-app context switching. agent/app_context.py focuses the
      target app and relays copy/paste across apps.
- [x] NON-CRIT-004: VLM latency. A perceptual-hash cache reuses VLM results on static
      screens; cross-validation is opt-in via config.vlm.cross_validate.
- [x] NON-CRIT-005: Icon fallback. perception/icon_match.py detects text-free icons and
      feeds them into fusion.
- [x] NON-CRIT-006: Memory persistence (already wired).

---

## Dependencies Status

| Package | Version | Status | Notes |
|---------|---------|--------|-------|
| torch | 2.8.0 | ⚠️ | CPU version (CUDA install deferred) |
| easyocr | 1.7.2 | ✅ | **Primary OCR** |
| paddleocr | 2.8.1 | ⚠️ | Not used (oneDNN issues) |
| llama-cpp-python | 0.3.2 | ✅ | CPU version (fallback backend) |
| mss | - | ✅ | Screen capture |
| pyautogui | - | ✅ | Mouse/keyboard |
| transformers | - | ✅ | For VLM (deferred — using Ollama instead) |
| numpy | 2.2.6 | ✅ | |
| opencv-python | 4.10.0 | ✅ | |
| ollama | - | ✅ | **Core Backend for LLM + VLM** |

---

## Model Files

| Model | Location | Size | Status |
|-------|----------|------|--------|
| TinyLlama-1.1B | `models/downloads/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf` | 668 MB | ✅ (Fallback only) |
| **Llama 3.2** | Local (Ollama) | 2.0 GB | ✅ ACTIVE |
| **LLaVA** | Local (Ollama) | 4.7 GB | ✅ ACTIVE |
| EasyOCR models | `~/.EasyOCR/` | ~100 MB | ✅ Auto-downloaded |

---

## Test Commands
```bash
cd ml
python test_components.py  # Individual component tests (16 tests)
python test_e2e.py         # End-to-End Test (Open Notepad via Win+S)
python test_phase7.py      # Legacy E2E Test
python test_phase3.py      # Perception pipeline (OCR + Fusion)
python test_phase4.py      # Action execution (Safe test)
```

---

## Current Focus
> **Phase 8 COMPLETE — All components tested, E2E pipeline working. Next: Phase 9 critical issues or more complex task testing.**
