"""Supervised Machine Learning Query Intent Classifier for Multi-Hop GraphRAG (RP-27).

Implements a custom, self-contained NLP classification pipeline from first mathematical
principles (zero external cloud dependencies, 100% local execution):
  1. Sublinear TF-IDF Vectorizer over word n-grams (1..2) and character n-grams (3..4)
     with L2 unit-norm normalization.
  2. Ensemble of L2-Regularized Multinomial Logistic Regression (Softmax Cross-Entropy
     trained via Gradient Descent) and Laplace-Smoothed Multinomial Naive Bayes.
  3. Stratified 80/20 Train/Test Evaluation + 5-Fold Stratified Cross-Validation producing
     Accuracy, Macro Precision, Macro Recall, Macro F1-Score, Per-Class metrics, and a
     6x6 Confusion Matrix.
"""

from __future__ import annotations

import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from graphrag.models import QueryIntent

INTENT_CLASSES: List[QueryIntent] = [
    "blocker_chain",
    "deadline_schedule",
    "task_status",
    "meeting_summary",
    "person_context",
    "general",
]

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL_DIR = Path(__file__).resolve().parent / "models_store"
DATASET_PATH = DATA_DIR / "intent_training_dataset.json"
MODEL_WEIGHTS_PATH = MODEL_DIR / "intent_model.json"
METRICS_PATH = MODEL_DIR / "evaluation_metrics.json"


def _build_curated_dataset() -> List[Dict[str, str]]:
    """Generate a balanced 360-sample labeled dataset (60 samples per intent class)
    covering explicit, implicit, and multi-hop conversational voice queries.
    """
    samples: Dict[QueryIntent, List[str]] = {
        "blocker_chain": [
            "What is blocking the benchmark task?",
            "Are there any issues or obstacles on whisper transcription?",
            "Why is the payment flow task stuck?",
            "What is preventing Sarah Chen from finishing WhisperX optimization?",
            "Which critical bug is holding up the mobile release?",
            "What is blocking Kavindu's SQLite voice cache task and how is it resolved?",
            "Show me all current blockers and impediments in the project",
            "Why can't we deploy the voice gateway cluster yet?",
            "What problem did David Miller raise about memory consumption?",
            "Which issue is causing the CUDA out of memory crash on 8GB VRAM?",
            "How was the Whisper memory limit exceeded issue resolved?",
            "What decision resolves the Android Keystore biometric timeout crash?",
            "Is anything blocking the local SQLite encryption task?",
            "Why is the audio pipeline optimization task delayed or blocked?",
            "Tell me the root cause issue behind the failing transcription task",
            "What obstacles are stopping the team from completing the sprint?",
            "Which tasks are currently blocked by open issues?",
            "What bug did Sarah report during the architecture sync?",
            "Why is the backend integration failing right now?",
            "What is the bottleneck in the Ollama 8B inference pipeline?",
            "Identify the blocker chain for the mobile app release",
            "Which high severity issues are still unresolved?",
            "What fix or decision addresses the GPU memory overflow bug?",
            "Why is the Whisper FP16 task marked as blocked?",
            "What technical problem is holding back the security patch?",
            "Are there any critical bugs preventing deployment?",
            "Who raised the payment API unavailability issue and what blocks it?",
            "What is the main impediment to finishing the benchmark?",
            "Explain why the encryption task cannot proceed",
            "Which issue blocks the voice cache task and how did we solve it?",
            "What trouble are we having with the upstream library?",
            "List the bugs and blockers raised in recent conversations",
            "Why did the Whisper transcription crash on 8GB machines?",
            "What is stopping David from completing his assigned task?",
            "Show the resolution path for the memory fragmentation blocker",
            "Which open issues are impacting our urgent tasks?",
            "What obstacle did the engineering team encounter with Docker?",
            "How are we resolving the critical blocker on the payment flow?",
            "What is causing the bottleneck in embedding computation?",
            "Are any tasks stuck waiting on an unresolved bug?",
            "What issue is blocking zz test Audio pipeline optimization?",
            "Why is the release candidate blocked right now?",
            "What problem is preventing the QA team from testing?",
            "Which decision fixes the blocker on Sarah's task?",
            "Tell me what is holding up the database migration work",
            "What bugs were raised that still need a resolution?",
            "Why is the voice assistant response latency task blocked?",
            "What is the blocker on Test payment flow?",
            "Which issue is obstructing the authentication module?",
            "How did the team resolve the CUDA memory crash?",
            "What is blocking the WhisperX GPU memory task?",
            "Are there any severe issues blocking our current work items?",
            "Why is the security review task stuck in blocked state?",
            "What technical hurdle is delaying the API integration?",
            "Which blocker was raised by David Miller?",
            "What issue prevents the mobile client from syncing?",
            "Show me the chain of blockers and their resolutions",
            "Why are we unable to close the benchmark task?",
            "What bug is blocking the sprint deliverable?",
            "Which critical issue is holding up the release?",
        ],
        "deadline_schedule": [
            "When is the deployment deadline?",
            "What is on the calendar schedule for Friday?",
            "When is the benchmark task due?",
            "What is the target date for the mobile app release?",
            "By when does Sarah need to finish optimizing WhisperX?",
            "What are the upcoming deadlines for this sprint?",
            "When is the due date for encrypting the local SQLite voice cache?",
            "What is the timeline for the cloud migration project?",
            "When is the release cutoff scheduled?",
            "Show me all tasks that are due on 2026-10-25",
            "What is the ETA for the voice gateway Docker cluster?",
            "When must the urgent security patch be completed?",
            "Did the deadline for WhisperX optimization change?",
            "What is the new target date after rescheduling?",
            "When is the Friday security cutoff date?",
            "List all upcoming due dates and milestones on the calendar",
            "By what date does Tharindu have to finish the Docker deployment?",
            "When is the surprise party event scheduled to happen?",
            "What deadlines do we have coming up in October?",
            "When is the final submission date for the architecture deliverable?",
            "What is the scheduled date for the beta release demo?",
            "When does the payment flow testing need to be done by?",
            "Tell me the due date for David Miller's benchmark task",
            "What is our schedule timeline for next week?",
            "When is the deadline for fixing the memory leak?",
            "Which tasks have a deadline this Friday?",
            "When is the target milestone for sub-500ms latency?",
            "What date is the Dilini surprise party planned for?",
            "By when should the design file be shared?",
            "What is the cutoff date for the sprint 15 deliverables?",
            "When is the due date for the QA extension task?",
            "Show the calendar schedule and target dates for all tasks",
            "When is the deadline for the SQLite encryption work item?",
            "What date was set as the deadline for the benchmark?",
            "How much time do we have until the release deadline?",
            "When is the scheduled date for the product launch?",
            "What is the due date assigned to Kavindu's task?",
            "When are the project deliverables due?",
            "Tell me the exact deadline date for the WhisperX task",
            "What is on the schedule for 2026-11-05?",
            "When is the target completion date for the security review?",
            "Which deadline applies to the Ollama 8B benchmark?",
            "When do we need to finish the cake and balloons task?",
            "What is the updated due date for the GPU memory optimization?",
            "Show me the timeline and due dates for open tasks",
            "By when is the team expected to deliver the prototype?",
            "When is the next milestone deadline on our roadmap?",
            "What is the exact date for the release cutoff?",
            "When is the due date for the tasks assigned to Sarah?",
            "Check the calendar for any deadlines due this week",
            "When is the target date for completing the voice pipeline?",
            "What date is the task due on?",
            "When is the scheduled deadline for the deployment?",
            "By what day must the critical patch be delivered?",
            "What are the due dates for our high priority tasks?",
            "When is the planned date for the Kandy trip event?",
            "Tell me when the sprint tasks are due",
            "What is the deadline for the payment integration?",
            "When is the cutoff schedule for the current sprint?",
            "What date is the deadline for this task?",
        ],
        "task_status": [
            "What is David working on?",
            "Show me all in progress tasks and action items",
            "Who is assigned to the Test payment flow task?",
            "What is the current status of the Ollama 8B benchmark task?",
            "Which tasks are assigned to Sarah Chen?",
            "What work items are currently open in the backlog?",
            "Who is responsible for encrypting the local SQLite voice cache?",
            "What is the priority and status of the Docker cluster task?",
            "List all action items assigned to Ruwan Fernando",
            "What deliverables is the Core AI Pipeline Team working on?",
            "Is the benchmark task done or still in progress?",
            "Who is working on the local voice AI assistant project?",
            "What tasks does Kavindu Jayasinghe have assigned to him?",
            "Show the progress and status of all urgent tasks",
            "Who requested the WhisperX GPU memory optimization task?",
            "What todo items are left for the mobile app release?",
            "Which action items are marked as high priority?",
            "What is Tharindu Bandara currently working on?",
            "Who is assigned to buy cake and balloons?",
            "Give me a status update on the pending tasks",
            "Which tasks are in progress versus open?",
            "Who is handling the QA time extension task?",
            "What work item is assigned to zz test Alice?",
            "Check the status of the design file sharing task",
            "What are the active tasks and their assignees?",
            "Who is responsible for the urgent security patch?",
            "What is the progress on the audio pipeline optimization task?",
            "Which tasks belong to the Local Voice AI Assistant project?",
            "Show me the todo list and assigned owners",
            "What action items were created for David Miller?",
            "Is the payment flow task completed or still open?",
            "What is the priority level of the SQLite voice cache task?",
            "Who is assigned to fix the memory leak task?",
            "List all deliverables and their current lifecycle status",
            "What work is Nimal doing on the mobile release?",
            "Which tasks are currently in the doing or wip state?",
            "Who owns the task to deploy the Docker cluster?",
            "What is the status of the tasks in our current sprint?",
            "Show me the action items that are still pending",
            "What task is assigned to Tharindu and what is its status?",
            "Who is working on the benchmark core deliverable?",
            "Are there any urgent tasks assigned to Sarah?",
            "What is the current progress of our engineering tasks?",
            "Which work items have been completed so far?",
            "Tell me the status and priority of the WhisperX task",
            "Who is assigned to zz test Implement feature?",
            "What tasks are open in the knowledge graph?",
            "Show the assignee and status for the encryption task",
            "What is Priya working on right now?",
            "Which todo items need immediate attention?",
            "What task is Kavindu working on?",
            "Who is assigned to the benchmark task?",
            "What is the status of all assigned action items?",
            "List the open tasks and who is working on them",
            "What high priority deliverables are in progress?",
            "Who is responsible for the voice gateway deployment task?",
            "What tasks are currently active in the project?",
            "Tell me what work items David is assigned to",
            "What is the status of the party planning task?",
            "Which tasks are assigned and in progress?",
        ],
        "meeting_summary": [
            "Summarize the Sprint 14 Architecture Sync meeting",
            "Who attended the discussion call yesterday?",
            "When is the Weekly sync meeting and who was absent?",
            "What was discussed in the Sprint 15 Architecture Sync?",
            "Who was absent from the weekly sync call?",
            "When is the Security Architecture Standup meeting?",
            "What decisions were made during the architecture sync meeting?",
            "Who attended the Infrastructure Review Call?",
            "Where was the architecture sync meeting located?",
            "Give me the minutes and notes from the standup call",
            "Was Kamal absent from the Weekly sync meeting?",
            "What agenda topics were discussed in the conference call?",
            "Who led the Sprint 14 Architecture Sync meeting?",
            "When did the Security Architecture Standup take place?",
            "Which decisions originated in the architecture sync meeting?",
            "Tell me who attended and who missed the weekly sync",
            "What was the duration and date of the Sprint 15 Architecture Sync?",
            "Summarize the key takeaways from the standup discussion",
            "Did David Miller attend the Sprint 15 Architecture Sync?",
            "When is the Infrastructure Review Call scheduled and who attended?",
            "What notes were recorded during the retrospective meeting?",
            "Which meeting discussed Ollama memory consumption?",
            "Who participated in the morning standup call?",
            "What was decided in the security standup meeting?",
            "When was the weekly engineering alignment meeting held?",
            "Show me the attendance list for the architecture sync",
            "Who missed the weekly sync call on 2026-03-29?",
            "What topics were covered in the design discussion?",
            "Did Kavindu attend the Security Architecture Standup?",
            "Give me a summary of the recent voice sync session",
            "What time and date is the Security Architecture Standup?",
            "Which meeting created the decision to use background key caching?",
            "Who was present at the infrastructure review meeting?",
            "Were there any absentees from the sprint sync call?",
            "What did the team discuss during the standup?",
            "Tell me the details of the Weekly sync meeting",
            "Which conference room was the meeting located at?",
            "Summarize the decisions and discussions from the sync call",
            "Who attended the party planning discussion?",
            "When is the next standup or sync meeting?",
            "What happened in the Sprint 15 Architecture Sync?",
            "Who attended the meeting on 2026-10-20?",
            "Give me the meeting minutes for the architecture call",
            "Which people attended the review call?",
            "Who was absent from the meeting?",
            "What time is the standup meeting scheduled?",
            "Did Tharindu attend the Infrastructure Review Call?",
            "What was agreed upon in the architecture sync meeting?",
            "Show me the summary and attendees of the sync meeting",
            "When was the Sprint 15 Architecture Sync held?",
            "Who attended the Security Architecture Standup?",
            "What topics were discussed in the meeting?",
            "Tell me when the Weekly sync meeting happened",
            "Who was present and who was absent at the meeting?",
            "What decisions came out of the standup call?",
            "Summarize the meeting attendance and agenda",
            "When is the meeting and who attended it?",
            "What call did Tharindu Bandara attend?",
            "Which meeting did David Miller attend?",
            "Give me the date and attendees of the sync meeting",
        ],
        "person_context": [
            "Who is Sarah Chen?",
            "Where does Elena live and who are her friends?",
            "Who is friend of Kamal?",
            "Where does Tharindu work and where does he live?",
            "Who are Kamal Perera's friends?",
            "What organization does Ruwan work at?",
            "Tell me about David Miller and his role",
            "Who is in Kamal's family?",
            "Where does Sarah live and what team is she a member of?",
            "What is Kavindu Jayasinghe's job title?",
            "Who does David report to in the organization?",
            "Which company does Kamal work at?",
            "Who are the members of the Mobile Team?",
            "What food does Kamal like or dislike?",
            "Where does Ruwan live and who is his family?",
            "Who collaborates with Sarah Chen on the AI team?",
            "Tell me the profile and contact details for Sarah",
            "Who is Dilini and how is she related to Ruwan?",
            "What is Tharindu Bandara's title at Dialog Axiata?",
            "Which city does Tharindu live in?",
            "Who are the coworkers working at ABC Software?",
            "What are Kamal's personal preferences and hobbies?",
            "Who is Dr. Chen and what is her role?",
            "Tell me about Ruwan Fernando and his friends",
            "Which team is Kamal a member of?",
            "Who is the Staff AI Engineer on the team?",
            "Where does Priya work?",
            "How is Kamal Perera connected to Ruwan Silva?",
            "Who are the colleagues in the Core AI Pipeline Team?",
            "What does Kamal dislike eating?",
            "Who likes cricket in the personal graph?",
            "Tell me about Kavindu and his engineering role",
            "Who is Nimal and where does he work?",
            "What organization employs Tharindu Bandara?",
            "Who is the Senior Backend Engineer?",
            "Where does Kamal's friend work?",
            "Who is the DevOps Lead living in Galle?",
            "Tell me about the people working at ABC Software",
            "Who is Ruwan's friend and family member?",
            "What is Sarah Chen's title and alias?",
            "Who are the friends of Kamal in the knowledge graph?",
            "Where does the Mobile Security Engineer work?",
            "Tell me about Elena Rostova",
            "Who is connected to Kamal via friendship or family?",
            "Which people belong to the engineering team?",
            "What do we know about Ruwan Silva?",
            "Where does Kamal work and what team is he in?",
            "Who is the person with alias Sarah?",
            "Tell me about Tharindu's workplace and hometown",
            "Who are the coworkers and friends of Kamal?",
            "Who is friend of Kamal and where do they work?",
            "Who is Kavindu Jayasinghe?",
            "Where does Ruwan work?",
            "Who lives in Colombo and works at ABC Software?",
            "Tell me about Sarah's background and team",
            "Who are Kamal's friends?",
            "What is David Miller's title?",
            "How are Ruwan and Dilini related?",
            "Where does Tharindu Bandara live?",
            "Who is the person working at Dialog Axiata?",
        ],
        "general": [
            "Ollama quantization details",
            "Tell me about Neo4j 5 graph database architecture",
            "What tools are used by the AI Core Team?",
            "Explain the 4-bit quantization rationale for LLaMA 3",
            "What is the Cloud GPU Invoice #402 value?",
            "Describe the RFC-204 Local Graph Storage Architecture document",
            "What metrics are tracked for P99 response latency?",
            "How does SQLite acoustic embedding caching work?",
            "What is the goal for sub-500ms voice response latency?",
            "Show me details about the Kandy hill country venue",
            "What is Docker Desktop used for in this project?",
            "Explain the zero-knowledge proofs concept",
            "What is the rationale behind adopting Ollama 8B?",
            "Tell me about the Sony WH-1000XM5 headphones item",
            "What software tools does the project rely on?",
            "Describe the memory optimization and quantization topic",
            "What is the resident memory footprint of the 4-bit model?",
            "Show information about the Local Voice AI Assistant project",
            "What documents or specifications are referenced?",
            "How much VRAM does INT8 quantization save?",
            "What is the description of Dialog Axiata?",
            "Tell me about the Southern Province location Galle",
            "What is the AES-256 encryption specification?",
            "Show me the details of the Cloud GPU Invoice payment",
            "What tools are linked to the zz test AI Core Team?",
            "Explain the background session key caching decision rationale",
            "What is the target metric for inference latency?",
            "Describe the architecture of the local voice pipeline",
            "What items or hardware devices are mentioned in the graph?",
            "Tell me about the design file document",
            "What is PyTorch used for in the pipeline?",
            "Give me an overview of the Neo4j Engine tool",
            "What is the rationale for adopting Neo4j 5 as single source of truth?",
            "Show details about the MacBook Pro item",
            "What concepts are stored in the knowledge graph?",
            "Explain the quantization parameters and memory savings",
            "What is the unit and value of Invoice #402?",
            "Tell me about the hill country venue in Kandy",
            "What strategic goals does the project support?",
            "Describe the technical stack and tools in the graph",
            "What is the WhisperX model architecture?",
            "Show me the general notes and ideas in memory",
            "What ideas were proposed for caching embeddings?",
            "Tell me about the Oat milk grocery item",
            "What is the rationale for INT8 quantization?",
            "Describe the Telecom Enterprise Partner organization",
            "What is the target VRAM usage for local inference?",
            "Show me the details of the architecture RFC document",
            "What general topics are stored in the database?",
            "Tell me about the system tools and benchmarks",
            "What is the memory footprint of Ollama 8B?",
            "Show the technical details of the quantization decision",
            "What tools and frameworks are in the graph?",
            "Tell me about the payment invoice details",
            "What is the rationale for the database decision?",
            "Explain the general concept of graph memory",
            "What hardware and software items are recorded?",
            "Show the benchmark metric values and units",
            "What is the description of the Kandy location?",
            "Tell me about the technical concepts in the graph",
        ],
    }

    flat_dataset: List[Dict[str, str]] = []
    for intent_label, queries in samples.items():
        for q in queries:
            flat_dataset.append({"query": q, "intent": intent_label})
    return flat_dataset


SEMANTIC_CLUSTERS: Dict[str, List[str]] = {
    "sem_blocker": [
        "block", "blocked", "blocker", "blockers", "blocking", "issue", "issues",
        "obstacle", "obstacles", "impediment", "impediments", "stuck", "trouble",
        "bug", "bugs", "problem", "problems", "failing", "preventing", "bottleneck",
        "bottlenecks", "crash", "delay", "delayed", "hold", "holding", "obstructing",
        "hurdle", "unable", "resolves", "resolved", "resolve", "fix", "fixes",
    ],
    "sem_deadline": [
        "deadline", "deadlines", "due", "schedule", "schedules", "scheduled",
        "calendar", "timeline", "target", "eta", "cutoff", "milestone", "milestones",
        "date", "dates", "friday", "october", "rescheduling", "by_when", "when_is",
    ],
    "sem_task": [
        "task", "tasks", "status", "progress", "assigned", "todo", "todos",
        "backlog", "doing", "wip", "working", "work", "action", "deliverable",
        "deliverables", "responsible", "owns", "handling", "pending", "open", "active",
    ],
    "sem_meeting": [
        "meeting", "meetings", "sync", "syncs", "standup", "standups", "discussion",
        "discussions", "discuss", "discussed", "attended", "attend", "absent",
        "absentees", "agenda", "call", "calls", "minutes", "conference", "retrospective",
        "takeaways", "participated", "present", "missed",
    ],
    "sem_person": [
        "who_is", "who_are", "person", "people", "colleague", "colleagues", "coworker",
        "coworkers", "friend", "friends", "family", "lives", "live", "member",
        "role", "title", "contact", "profile", "employ", "employs", "hometown",
        "workplace", "related", "connected", "likes", "dislikes", "report",
    ],
    "sem_general": [
        "quantization", "architecture", "rationale", "invoice", "document", "rfc",
        "metric", "metrics", "footprint", "vram", "specification", "overview",
        "concept", "concepts", "grocery", "headphones", "macbook", "describe", "explain",
    ],
}


def _extract_ngrams(text: str) -> Counter:
    """Extract word unigrams, word bigrams, semantic cluster signals, and char n-grams."""
    clean = re.sub(r"[^\w\s']", " ", text.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    tokens = clean.split()

    feats: Counter = Counter()
    # 1. Word unigrams
    for tok in tokens:
        feats[f"w1:{tok}"] += 1.2

    # 2. Word bigrams
    bigrams: List[str] = []
    for i in range(len(tokens) - 1):
        bg = f"{tokens[i]}_{tokens[i + 1]}"
        bigrams.append(bg)
        feats[f"w2:{bg}"] += 1.5

    # 3. Semantic cluster signals
    token_set = set(tokens) | set(bigrams)
    for cluster_name, kw_list in SEMANTIC_CLUSTERS.items():
        hits = sum(1 for kw in kw_list if kw in token_set)
        if hits > 0:
            feats[f"cls:{cluster_name}"] += 2.2 * hits

    # 4. Character boundary 3-grams and 4-grams for morphological robustness
    for tok in tokens:
        if len(tok) >= 4:
            padded = f"<{tok}>"
            for n in (3, 4):
                for i in range(len(padded) - n + 1):
                    feats[f"c{n}:{padded[i : i + n]}"] += 0.30

    return feats


class TrainedIntentClassifier:
    """Supervised NLP Intent Classifier (TF-IDF + L2 Softmax Logistic Regression & MNB Ensemble)."""

    def __init__(self) -> None:
        self.classes: List[str] = list(INTENT_CLASSES)
        self.idf: Dict[str, float] = {}
        self.weights: Dict[str, Dict[str, float]] = {c: {} for c in self.classes}
        self.biases: Dict[str, float] = {c: 0.0 for c in self.classes}
        self.nb_log_prob: Dict[str, Dict[str, float]] = {c: {} for c in self.classes}
        self.nb_default_log_prob: Dict[str, float] = {c: -10.0 for c in self.classes}
        self.is_trained: bool = False
        self.metrics: Dict[str, Any] = {}

    def _vectorize(self, text: str) -> Dict[str, float]:
        """Convert raw query text into an L2-normalized sublinear TF-IDF feature vector."""
        raw_counts = _extract_ngrams(text)
        vec: Dict[str, float] = {}
        norm_sq = 0.0
        for feat, count in raw_counts.items():
            if feat in self.idf and count > 0:
                val = math.log1p(count) * self.idf[feat]
                vec[feat] = val
                norm_sq += val * val
        if norm_sq > 0.0:
            inv_norm = 1.0 / math.sqrt(norm_sq)
            for feat in vec:
                vec[feat] *= inv_norm
        return vec

    def fit_parameters(
        self,
        train_data: List[Dict[str, str]],
        epochs: int = 35,
        learning_rate: float = 2.0,
        l2_reg: float = 0.0003,
        seed: int = 42,
    ) -> None:
        """Fit TF-IDF vocabulary, Multinomial Naive Bayes log-likelihoods, and Softmax Logistic Regression weights."""
        n_docs = len(train_data)
        df_counts: Counter = Counter()
        doc_raw_feats: List[Tuple[Counter, str]] = []

        for item in train_data:
            feats = _extract_ngrams(item["query"])
            label = item["intent"]
            doc_raw_feats.append((feats, label))
            for f in feats.keys():
                df_counts[f] += 1

        # Keep word/semantic features (df >= 1) and character n-grams with df >= 2
        self.idf = {
            f: math.log((1.0 + n_docs) / (1.0 + df)) + 1.0
            for f, df in df_counts.items()
            if (not f.startswith("c")) or df >= 2
        }

        # Vectorize training set
        vectorized_docs: List[Tuple[Dict[str, float], str]] = []
        for item in train_data:
            vectorized_docs.append((self._vectorize(item["query"]), item["intent"]))

        # 1. Fit Laplace-Smoothed Multinomial Naive Bayes on TF-IDF features
        vocab_size = max(1, len(self.idf))
        alpha = 0.25
        class_feat_sums: Dict[str, Counter] = {c: Counter() for c in self.classes}
        class_totals: Dict[str, float] = {c: 0.0 for c in self.classes}

        for vec, label in vectorized_docs:
            for f, val in vec.items():
                class_feat_sums[label][f] += val
                class_totals[label] += val

        self.nb_log_prob = {}
        self.nb_default_log_prob = {}
        for c in self.classes:
            denom = class_totals[c] + alpha * vocab_size
            self.nb_default_log_prob[c] = math.log(alpha / denom)
            self.nb_log_prob[c] = {
                f: math.log((val + alpha) / denom)
                for f, val in class_feat_sums[c].items()
            }

        # 2. Fit L2-Regularized Softmax Multinomial Logistic Regression via SGD
        self.weights = {c: defaultdict(float) for c in self.classes}
        self.biases = {c: 0.0 for c in self.classes}
        rng = random.Random(seed)
        indices = list(range(n_docs))

        for epoch in range(epochs):
            rng.shuffle(indices)
            lr = learning_rate * (0.96 ** epoch)
            for idx in indices:
                vec, true_label = vectorized_docs[idx]
                # Compute logits
                logits: Dict[str, float] = {}
                for c in self.classes:
                    w_c = self.weights[c]
                    s = self.biases[c]
                    for f, val in vec.items():
                        if f in w_c:
                            s += w_c[f] * val
                    logits[c] = s

                max_logit = max(logits.values())
                exps = {c: math.exp(logits[c] - max_logit) for c in self.classes}
                sum_exp = sum(exps.values())
                probs = {c: exps[c] / sum_exp for c in self.classes}

                # Gradient update
                for c in self.classes:
                    target = 1.0 if c == true_label else 0.0
                    err = probs[c] - target
                    self.biases[c] -= lr * err * 0.1
                    w_c = self.weights[c]
                    for f, val in vec.items():
                        w_c[f] = w_c[f] * (1.0 - lr * l2_reg) - lr * err * val

        # Convert defaultdicts to regular dicts and prune near-zero weights
        self.weights = {
            c: {f: round(w, 6) for f, w in self.weights[c].items() if abs(w) > 1e-4}
            for c in self.classes
        }
        self.biases = {c: round(b, 6) for c, b in self.biases.items()}
        self.is_trained = True

    def predict_proba(self, query: str) -> Dict[str, float]:
        """Predict calibrated class probability distribution over the 6 GraphRAG intents."""
        if not self.is_trained:
            self.load_or_train()

        vec = self._vectorize(query)
        if not vec:
            return {c: (1.0 if c == "general" else 0.0) for c in self.classes}

        # Softmax Logistic Regression probabilities (temperature-scaled for crisp calibration)
        lr_logits: Dict[str, float] = {}
        for c in self.classes:
            w_c = self.weights.get(c, {})
            s = self.biases.get(c, 0.0)
            for f, val in vec.items():
                if f in w_c:
                    s += w_c[f] * val
            lr_logits[c] = s * 2.2

        max_lr = max(lr_logits.values())
        lr_exps = {c: math.exp(lr_logits[c] - max_lr) for c in self.classes}
        lr_sum = sum(lr_exps.values())
        lr_probs = {c: lr_exps[c] / lr_sum for c in self.classes}

        # Multinomial Naive Bayes probabilities
        nb_scores: Dict[str, float] = {}
        for c in self.classes:
            nb_c = self.nb_log_prob.get(c, {})
            default_lp = self.nb_default_log_prob.get(c, -10.0)
            s = 0.0
            for f, val in vec.items():
                s += val * nb_c.get(f, default_lp)
            nb_scores[c] = s * 1.5

        max_nb = max(nb_scores.values())
        nb_exps = {c: math.exp(nb_scores[c] - max_nb) for c in self.classes}
        nb_sum = sum(nb_exps.values())
        nb_probs = {c: nb_exps[c] / nb_sum for c in self.classes}

        # Ensemble blend: 0.70 Softmax Logistic Regression + 0.30 Multinomial Naive Bayes
        combined = {c: 0.70 * lr_probs[c] + 0.30 * nb_probs[c] for c in self.classes}
        total = sum(combined.values())
        return {c: round(combined[c] / total, 4) for c in self.classes}

    def predict(self, query: str) -> Tuple[QueryIntent, float, Dict[str, float]]:
        """Return (predicted_intent, confidence, probabilities_dict)."""
        probs = self.predict_proba(query)
        best_intent = max(probs.items(), key=lambda kv: kv[1])[0]
        return best_intent, round(probs[best_intent], 4), probs  # type: ignore[return-value]

    @staticmethod
    def _compute_classification_metrics(
        y_true: List[str],
        y_pred: List[str],
        classes: List[str],
    ) -> Dict[str, Any]:
        """Compute Accuracy, Per-Class Precision/Recall/F1, Macro averages, and Confusion Matrix."""
        n = max(1, len(y_true))
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
        accuracy = round(correct / n, 4)

        # Confusion matrix: rows = true class, cols = predicted class
        matrix: List[List[int]] = [[0 for _ in classes] for _ in classes]
        class_to_idx = {c: i for i, c in enumerate(classes)}
        for t, p in zip(y_true, y_pred):
            matrix[class_to_idx[t]][class_to_idx[p]] += 1

        per_class: Dict[str, Dict[str, float]] = {}
        precisions: List[float] = []
        recalls: List[float] = []
        f1s: List[float] = []

        for i, c in enumerate(classes):
            tp = matrix[i][i]
            fp = sum(matrix[r][i] for r in range(len(classes)) if r != i)
            fn = sum(matrix[i][col] for col in range(len(classes)) if col != i)
            support = sum(matrix[i])

            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

            precisions.append(prec)
            recalls.append(rec)
            f1s.append(f1)

            per_class[c] = {
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1_score": round(f1, 4),
                "support": support,
            }

        macro_precision = round(sum(precisions) / len(classes), 4)
        macro_recall = round(sum(recalls) / len(classes), 4)
        macro_f1 = round(sum(f1s) / len(classes), 4)

        return {
            "accuracy": accuracy,
            "macro_precision": macro_precision,
            "macro_recall": macro_recall,
            "macro_f1": macro_f1,
            "per_class": per_class,
            "confusion_matrix": matrix,
            "classes": classes,
            "sample_count": len(y_true),
        }

    def train_and_evaluate(self) -> Dict[str, Any]:
        """Train the model on the curated dataset, run 80/20 split + 5-Fold Stratified CV,
        and save both the trained model weights and evaluation metrics to disk.
        """
        start_ts = time.perf_counter()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        dataset = _build_curated_dataset()
        with open(DATASET_PATH, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2)

        # Group by class for stratified splitting
        by_class: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for item in dataset:
            by_class[item["intent"]].append(item)

        rng = random.Random(42)
        for c in by_class:
            rng.shuffle(by_class[c])

        # 1. 5-Fold Stratified Cross-Validation
        k_folds = 5
        fold_accuracies: List[float] = []
        fold_f1s: List[float] = []
        cv_y_true: List[str] = []
        cv_y_pred: List[str] = []

        for fold in range(k_folds):
            train_fold: List[Dict[str, str]] = []
            val_fold: List[Dict[str, str]] = []
            for c, items in by_class.items():
                fold_size = len(items) // k_folds
                start_i = fold * fold_size
                end_i = start_i + fold_size if fold < k_folds - 1 else len(items)
                val_fold.extend(items[start_i:end_i])
                train_fold.extend(items[:start_i] + items[end_i:])

            fold_clf = TrainedIntentClassifier()
            fold_clf.fit_parameters(train_fold, seed=42 + fold)
            f_true = [x["intent"] for x in val_fold]
            f_pred = [fold_clf.predict(x["query"])[0] for x in val_fold]
            cv_y_true.extend(f_true)
            cv_y_pred.extend(f_pred)

            f_metrics = self._compute_classification_metrics(f_true, f_pred, self.classes)
            fold_accuracies.append(f_metrics["accuracy"])
            fold_f1s.append(f_metrics["macro_f1"])

        cv_overall = self._compute_classification_metrics(cv_y_true, cv_y_pred, self.classes)

        # 2. Stratified 80/20 Train/Test Split Evaluation
        train_split: List[Dict[str, str]] = []
        test_split: List[Dict[str, str]] = []
        for c, items in by_class.items():
            split_idx = int(len(items) * 0.8)
            train_split.extend(items[:split_idx])
            test_split.extend(items[split_idx:])

        split_clf = TrainedIntentClassifier()
        split_clf.fit_parameters(train_split, seed=42)
        test_true = [x["intent"] for x in test_split]
        test_pred = [split_clf.predict(x["query"])[0] for x in test_split]
        test_metrics = self._compute_classification_metrics(test_true, test_pred, self.classes)

        # 3. Fit final production model on full dataset
        self.fit_parameters(dataset, seed=42)
        elapsed_ms = round((time.perf_counter() - start_ts) * 1000.0, 2)

        self.metrics = {
            "model_name": "Hybrid TF-IDF N-Gram + L2 Softmax Logistic Regression & MNB Ensemble",
            "task": "GraphRAG Query Intent Classification (6 Classes)",
            "dataset_size": len(dataset),
            "classes_count": len(self.classes),
            "samples_per_class": len(dataset) // len(self.classes),
            "vocabulary_size": len(self.idf),
            "training_time_ms": elapsed_ms,
            "test_split_80_20": test_metrics,
            "cross_validation_5fold": {
                "mean_accuracy": round(sum(fold_accuracies) / k_folds, 4),
                "mean_macro_f1": round(sum(fold_f1s) / k_folds, 4),
                "fold_accuracies": fold_accuracies,
                "fold_macro_f1s": fold_f1s,
                "overall_cv_metrics": cv_overall,
            },
        }

        # Save artifacts to disk
        with open(MODEL_WEIGHTS_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "classes": self.classes,
                    "idf": self.idf,
                    "weights": self.weights,
                    "biases": self.biases,
                    "nb_log_prob": self.nb_log_prob,
                    "nb_default_log_prob": self.nb_default_log_prob,
                },
                f,
            )

        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, indent=2)

        return self.metrics

    def load_or_train(self) -> None:
        """Load saved model weights and metrics from disk, or train immediately if missing."""
        if MODEL_WEIGHTS_PATH.exists() and METRICS_PATH.exists():
            try:
                with open(MODEL_WEIGHTS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.classes = data["classes"]
                self.idf = data["idf"]
                self.weights = data["weights"]
                self.biases = data["biases"]
                self.nb_log_prob = data["nb_log_prob"]
                self.nb_default_log_prob = data["nb_default_log_prob"]
                with open(METRICS_PATH, "r", encoding="utf-8") as mf:
                    self.metrics = json.load(mf)
                self.is_trained = True
                return
            except Exception:
                pass
        self.train_and_evaluate()


# Singleton model instance
_CLASSIFIER_INSTANCE: Optional[TrainedIntentClassifier] = None


def get_intent_classifier() -> TrainedIntentClassifier:
    """Return the singleton trained intent classifier, loading or training if needed."""
    global _CLASSIFIER_INSTANCE
    if _CLASSIFIER_INSTANCE is None:
        _CLASSIFIER_INSTANCE = TrainedIntentClassifier()
        _CLASSIFIER_INSTANCE.load_or_train()
    return _CLASSIFIER_INSTANCE
