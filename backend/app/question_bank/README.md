# AIR4 Question Bank v0.2 (CORE)

This module turns "questions" into a runtime sensing system:
- decay (old answers expire)
- load bank (core.yaml)
- resolve collisions (collisions.yaml)
- pick state (states.yaml)
- select next questions (policy.py)

Inputs:
- current_answers: Dict[signal -> answer] (answers are strings like "yes"/"no"/"low"/"mid"/"high")

Outputs:
- state decision: mode + ask_budget + forbids
- next questions: list of Question objects
- expired signals: list[signal, age_sec]

Onboarding:
- GET /qb/onboarding returns packs
- POST /qb/onboarding/start returns questions by pack signals

Design principles:
- ask minimum
- stop authority (user can stop)
- action locks questions (execution_window => no more questions)
