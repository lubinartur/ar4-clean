#!/usr/bin/env python3
"""
AIR4 Question Bank Audit Script
Audits QB to determine Phase N readiness (30-50 questions, 6+ domains).
"""

from pathlib import Path
import sys
import os
import re
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional

def parse_yaml_questions(content: str) -> List[Dict]:
    """Simple YAML parser for questions list (no external deps)."""
    questions = []
    current_q = {}
    current_field = None
    current_value = []
    in_answers_list = False
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        
        # Start of question
        if line.startswith('  - id:'):
            # Save previous question
            if current_q and 'id' in current_q:
                # Save last field
                if current_field and current_value:
                    if current_field == 'answers':
                        # Parse answers list - extract quoted strings
                        answers_str = ' '.join(current_value)
                        # Match quoted strings or unquoted words
                        answers = re.findall(r'["\']([^"\']+)["\']|(\w+)', answers_str)
                        current_q[current_field] = [a[0] if a[0] else a[1] for a in answers if a[0] or a[1]]
                    else:
                        current_q[current_field] = ' '.join(current_value).strip().strip('"\'')
                questions.append(current_q)
            
            # Start new question
            current_q = {}
            current_field = None
            current_value = []
            in_answers_list = False
            
            # Extract ID
            match = re.search(r'id:\s*(.+)', line)
            if match:
                current_q['id'] = match.group(1).strip().strip('"\'')
        elif line.strip() and not line.startswith('#'):
            # Field: value
            match = re.match(r'^\s{4}(\w+):\s*(.+)', line)
            if match:
                # Save previous field
                if current_field and current_value:
                    if current_field == 'answers':
                        answers_str = ' '.join(current_value)
                        answers = re.findall(r'["\']([^"\']+)["\']|(\w+)', answers_str)
                        current_q[current_field] = [a[0] if a[0] else a[1] for a in answers if a[0] or a[1]]
                    else:
                        current_q[current_field] = ' '.join(current_value).strip().strip('"\'')
                
                current_field = match.group(1)
                val = match.group(2).strip()
                
                if current_field == 'answers' and val.startswith('['):
                    # Answers list on same line
                    in_answers_list = True
                    current_value = [val]
                    # Check if list closes on same line
                    if ']' in val:
                        in_answers_list = False
                elif val:
                    current_value = [val]
            elif in_answers_list:
                # Continuation of answers list
                current_value.append(line.strip())
                if ']' in line:
                    in_answers_list = False
            elif current_field:
                # Continuation of field value
                current_value.append(line.strip())
        i += 1
    
    # Add last question
    if current_q and 'id' in current_q:
        if current_field and current_value:
            if current_field == 'answers':
                answers_str = ' '.join(current_value)
                answers = re.findall(r'["\']([^"\']+)["\']|(\w+)', answers_str)
                current_q[current_field] = [a[0] if a[0] else a[1] for a in answers if a[0] or a[1]]
            else:
                current_q[current_field] = ' '.join(current_value).strip().strip('"\'')
        questions.append(current_q)
    
    return questions

def load_questions_from_file(path: Path) -> List[Dict]:
    """Load questions from YAML file."""
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    return parse_yaml_questions(content)

def is_squeeze_answer(answers: List[str]) -> bool:
    """Check if answers are squeeze (yes/no or choice like low/mid/high)."""
    if not answers:
        return False
    # Check for yes/no
    if set(answers) == {"yes", "no"}:
        return True
    # Check for tri-level
    if set(answers) == {"low", "mid", "high"}:
        return True
    # Check for other common squeeze patterns
    squeeze_patterns = [
        {"yes", "no"},
        {"low", "mid", "high"},
        {"low", "high"},
        {"yes", "no", "maybe"},
    ]
    answer_set = set(str(a).lower() for a in answers)
    return any(answer_set == pattern for pattern in squeeze_patterns)

def is_short_question(question: str) -> bool:
    """Check if question is short (reasonable length)."""
    # Consider questions under 100 characters as short
    return len(question) <= 100

def audit_question_bank() -> Dict:
    """Main audit function."""
    # Load questions from YAML files
    project_root = Path(__file__).parent.parent
    core_path = project_root / "question_bank" / "core.yaml"
    deep_path = project_root / "question_bank" / "deep.yaml"
    optional_path = project_root / "question_bank" / "optional.yaml"
    
    core_questions = load_questions_from_file(core_path)
    deep_questions = load_questions_from_file(deep_path)
    optional_questions = load_questions_from_file(optional_path)
    
    all_questions = core_questions + deep_questions + optional_questions
    
    # Track statistics
    total_questions = len(all_questions)
    domain_counts = defaultdict(int)
    question_ids: List[str] = []
    signals: List[str] = []
    duplicate_ids: List[str] = []
    duplicate_signals: List[str] = []
    invalid_structure: List[Dict] = []
    non_squeeze_answers: List[Dict] = []
    long_questions: List[Dict] = []
    domain_examples: Dict[str, List[str]] = defaultdict(list)
    
    # Process each question
    for q in all_questions:
        # Check structure
        required_fields = ["id", "domain", "signal", "question", "answers"]
        missing_fields = [f for f in required_fields if f not in q]
        if missing_fields:
            invalid_structure.append({
                "question": q.get("id", "unknown"),
                "missing": missing_fields
            })
            continue
        
        qid = q["id"]
        domain = q["domain"]
        signal = q["signal"]
        question_text = q["question"]
        answers = q["answers"]
        
        # Track IDs and signals
        question_ids.append(qid)
        signals.append(signal)
        
        # Count domains
        domain_counts[domain] += 1
        
        # Collect example IDs per domain (first 3)
        if len(domain_examples[domain]) < 3:
            domain_examples[domain].append(qid)
        
        # Check answer format
        if not is_squeeze_answer(answers):
            non_squeeze_answers.append({
                "id": qid,
                "domain": domain,
                "answers": answers
            })
        
        # Check question length
        if not is_short_question(question_text):
            long_questions.append({
                "id": qid,
                "domain": domain,
                "length": len(question_text),
                "question": question_text[:50] + "..."
            })
    
    # Find duplicates
    id_counter = Counter(question_ids)
    duplicate_ids = [qid for qid, count in id_counter.items() if count > 1]
    
    signal_counter = Counter(signals)
    duplicate_signals = [sig for sig, count in signal_counter.items() if count > 1]
    
    # Determine Phase N status
    # Phase N requirement: >= 30 questions, >= 6 domains, valid structure
    total_domains = len(domain_counts)
    phase_n_done = (
        total_questions >= 30 and
        total_domains >= 6 and
        len(duplicate_ids) == 0 and
        len(duplicate_signals) == 0 and
        len(invalid_structure) == 0
    )
    
    return {
        "total_questions": total_questions,
        "total_domains": total_domains,
        "domain_counts": dict(domain_counts),
        "domain_examples": dict(domain_examples),
        "duplicate_ids": duplicate_ids,
        "duplicate_signals": duplicate_signals,
        "invalid_structure": invalid_structure,
        "non_squeeze_answers": non_squeeze_answers,
        "long_questions": long_questions,
        "phase_n_done": phase_n_done,
        "phase_n_status": "DONE" if phase_n_done else "NOT DONE",
    }

def print_report(audit_result: Dict):
    """Print formatted audit report."""
    print("=" * 70)
    print("AIR4 Question Bank Audit Report")
    print("=" * 70)
    print()
    
    # Phase N status
    status = audit_result["phase_n_status"]
    print(f"Phase N Status: {status}")
    print()
    
    # Summary
    print("Summary:")
    print(f"  Total questions: {audit_result['total_questions']}")
    print(f"  Total domains: {audit_result['total_domains']}")
    print(f"  Required: >= 30 questions, >= 6 domains")
    print()
    
    # Domain breakdown
    print("Domain Breakdown:")
    print(f"{'Domain':<30} {'Count':<10} {'Example IDs'}")
    print("-" * 70)
    domain_counts = audit_result["domain_counts"]
    domain_examples = audit_result["domain_examples"]
    for domain in sorted(domain_counts.keys()):
        count = domain_counts[domain]
        examples = ", ".join(domain_examples.get(domain, [])[:3])
        print(f"{domain:<30} {count:<10} {examples}")
    print()
    
    # Conflicts
    conflicts = []
    if audit_result["duplicate_ids"]:
        conflicts.append(f"Duplicate IDs: {', '.join(audit_result['duplicate_ids'])}")
    if audit_result["duplicate_signals"]:
        conflicts.append(f"Duplicate signals: {', '.join(audit_result['duplicate_signals'])}")
    if audit_result["invalid_structure"]:
        conflicts.append(f"Invalid structure: {len(audit_result['invalid_structure'])} questions")
    if audit_result["non_squeeze_answers"]:
        conflicts.append(f"Non-squeeze answers: {len(audit_result['non_squeeze_answers'])} questions")
    if audit_result["long_questions"]:
        conflicts.append(f"Long questions (>100 chars): {len(audit_result['long_questions'])} questions")
    
    if conflicts:
        print("Conflicts/Issues:")
        for conflict in conflicts:
            print(f"  ⚠️  {conflict}")
        print()
    else:
        print("Conflicts: None")
        print()
    
    # Detailed issues (if any)
    if audit_result["non_squeeze_answers"]:
        print("Non-squeeze answers:")
        for item in audit_result["non_squeeze_answers"][:5]:  # Show first 5
            print(f"  - {item['id']} ({item['domain']}): {item['answers']}")
        if len(audit_result["non_squeeze_answers"]) > 5:
            print(f"  ... and {len(audit_result['non_squeeze_answers']) - 5} more")
        print()
    
    if audit_result["long_questions"]:
        print("Long questions (>100 chars):")
        for item in audit_result["long_questions"][:5]:  # Show first 5
            print(f"  - {item['id']} ({item['domain']}): {item['length']} chars - {item['question']}")
        if len(audit_result["long_questions"]) > 5:
            print(f"  ... and {len(audit_result['long_questions']) - 5} more")
        print()
    
    # Phase N requirements check
    print("Phase N Requirements Check:")
    total = audit_result["total_questions"]
    domains = audit_result["total_domains"]
    print(f"  ✓ Questions: {total} (required: >= 30) {'✓' if total >= 30 else '✗'}")
    print(f"  ✓ Domains: {domains} (required: >= 6) {'✓' if domains >= 6 else '✗'}")
    print(f"  ✓ No duplicate IDs: {'✓' if not audit_result['duplicate_ids'] else '✗'}")
    print(f"  ✓ No duplicate signals: {'✓' if not audit_result['duplicate_signals'] else '✗'}")
    print(f"  ✓ Valid structure: {'✓' if not audit_result['invalid_structure'] else '✗'}")
    print()
    
    # What's missing
    if not audit_result["phase_n_done"]:
        print("What's Missing:")
        if total < 30:
            print(f"  - Need {30 - total} more questions (currently {total})")
        if domains < 6:
            print(f"  - Need {6 - domains} more domains (currently {domains})")
        if audit_result["duplicate_ids"]:
            print(f"  - Fix {len(audit_result['duplicate_ids'])} duplicate IDs")
        if audit_result["duplicate_signals"]:
            print(f"  - Fix {len(audit_result['duplicate_signals'])} duplicate signals")
        if audit_result["invalid_structure"]:
            print(f"  - Fix {len(audit_result['invalid_structure'])} questions with invalid structure")
        print()
    
    print("=" * 70)

if __name__ == "__main__":
    # Change to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    audit_result = audit_question_bank()
    print_report(audit_result)
    
    # Exit with appropriate code
    sys.exit(0 if audit_result["phase_n_done"] else 1)
