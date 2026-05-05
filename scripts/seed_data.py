"""Seed questions (MNC packs + 7 new companies), jobs, and bootstrap users.

Run: python -m scripts.seed_data
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import Difficulty, Job, Question, QuestionCategory, User, UserRole
from app.db.session import SessionLocal


# ─────────────────────────── MNC Question Banks ──────────────────────────────

GOOGLE_QUESTIONS = [
    # Technical – DSA
    ("Explain how you would detect a cycle in a linked list. What are the time and space complexities?",
     QuestionCategory.technical, Difficulty.medium, "linked list, cycle, Floyd, tortoise, two pointers",
     "Use Floyd's Tortoise and Hare algorithm. Two pointers: slow moves 1 step, fast moves 2 steps. If they meet, there's a cycle. Time: O(n), Space: O(1). Alternative: hash set of visited nodes O(n) time, O(n) space."),

    ("Given an array of integers, find two numbers that sum to a target. What is the optimal solution?",
     QuestionCategory.technical, Difficulty.easy, "two sum, hash map, array, target",
     "Use a hash map: for each element, check if (target - element) exists in the map. If yes, return the pair. If no, store the element. Time: O(n), Space: O(n). Brute force is O(n²)."),

    ("How would you design a URL shortener like bit.ly? Discuss the system design.",
     QuestionCategory.technical, Difficulty.hard, "system design, URL shortener, hash, database, scalability",
     "Use a hash function (MD5/Base62 encoding) to generate a 6-7 character short key. Store mapping in a database (key → original URL). Use a CDN and caching layer (Redis) for fast redirects. For scale: horizontal sharding of DB, consistent hashing, load balancers. Handle collisions with retry or counter-based approach."),

    ("Explain the difference between BFS and DFS. When would you use each?",
     QuestionCategory.technical, Difficulty.easy, "BFS, DFS, graph, tree, traversal",
     "BFS uses a queue, explores level by level - ideal for shortest path in unweighted graphs. DFS uses a stack (or recursion), explores depth-first - ideal for cycle detection, topological sort, connected components. BFS: O(V+E) time, O(V) space for queue. DFS: O(V+E) time, O(V) space for recursion stack."),

    ("How does garbage collection work in languages like Java or Go?",
     QuestionCategory.technical, Difficulty.medium, "garbage collection, memory, JVM, GC, heap",
     "GC automatically reclaims memory from objects no longer reachable. Common algorithms: Mark-and-Sweep (marks reachable objects, sweeps rest), Reference Counting (tracks reference count), Generational GC (JVM: young/old generations, most objects die young). Go uses tri-color mark-and-sweep with concurrent execution to minimize STW pauses."),

    ("Design a rate limiter for a REST API. What algorithms would you use?",
     QuestionCategory.technical, Difficulty.hard, "rate limiter, token bucket, sliding window, API, throttling",
     "Common algorithms: Token Bucket (tokens refill at fixed rate, smooth bursting), Leaky Bucket (fixed output rate), Sliding Window Counter (more accurate), Fixed Window Counter (simple). Store state in Redis with atomic operations. For distributed systems: Redis cluster with Lua scripts for atomicity. Return 429 Too Many Requests with Retry-After header."),

    ("What is the CAP theorem and how does it apply to distributed databases?",
     QuestionCategory.technical, Difficulty.hard, "CAP theorem, consistency, availability, partition tolerance",
     "CAP: a distributed system can guarantee only 2 of 3: Consistency (all nodes see same data), Availability (every request gets a response), Partition Tolerance (system works despite network splits). Since partitions are inevitable, you choose CP (PostgreSQL, MongoDB) or AP (Cassandra, DynamoDB). In practice, you tune consistency levels per operation."),

    ("Implement LRU Cache. What data structures would you use?",
     QuestionCategory.technical, Difficulty.medium, "LRU cache, doubly linked list, hash map, O(1)",
     "Use a HashMap for O(1) lookup + Doubly Linked List for O(1) insertion/deletion. HashMap keys → list nodes. On get: move node to front. On put: add to front, if capacity exceeded remove from tail. Python: OrderedDict makes this trivial. Time: O(1) for both get and put."),

    ("Explain how indexes work in relational databases. When should you avoid them?",
     QuestionCategory.technical, Difficulty.medium, "database, index, B-tree, query optimization",
     "Indexes use B-Tree (or Hash) structures for O(log n) lookups instead of full table scans. Create on frequently queried/sorted/joined columns. Avoid on: small tables (full scan faster), low-cardinality columns (gender/boolean), columns with frequent writes (index must be updated), tables with heavy INSERT workloads."),

    ("How would you reverse a string in-place without using extra memory?",
     QuestionCategory.technical, Difficulty.easy, "string, reverse, two pointers, in-place",
     "Use two pointers: left at index 0, right at last index. Swap characters and move pointers toward center until they meet. Time: O(n), Space: O(1). In languages with immutable strings (Python/Java), convert to char array first, then reconstruct."),

    # Behavioral – Googleyness
    ("Tell me about a time you had to learn a new technology quickly under pressure. How did you approach it?",
     QuestionCategory.behavioral, Difficulty.medium, "learning, adaptability, pressure, technology, growth",
     "Structure with STAR: Situation (new tech needed for urgent project), Task (learn and implement in X days), Action (focused learning plan: docs, tutorials, small experiments, pair programming), Result (delivered feature, now proficient). Emphasize curiosity and systematic learning approach."),

    ("Describe a situation where you disagreed with your team's decision. What did you do?",
     QuestionCategory.behavioral, Difficulty.medium, "disagreement, conflict, communication, influence",
     "STAR method: Describe the disagreement clearly and respectfully. Explain how you gathered data/evidence to support your view, presented it constructively, listened to others' perspectives. If overruled, committed to the decision fully. If your approach was adopted, describe the outcome. Show ability to disagree and commit."),

    ("Tell me about the most complex technical problem you've solved. Walk me through your approach.",
     QuestionCategory.behavioral, Difficulty.hard, "problem solving, technical depth, debugging, complexity",
     "STAR: Complex problem (e.g., performance degradation, race condition, cascading failure). Task: diagnose and fix. Action: systematic debugging (logs, profiling, bisecting), hypothesis-driven approach, root cause analysis. Result: resolution + prevention. Show structured thinking and depth."),

    ("How do you balance quality and speed when delivering projects?",
     QuestionCategory.behavioral, Difficulty.medium, "quality, speed, trade-offs, prioritization, technical debt",
     "Discuss defining 'good enough' quality for the context, using automated tests to move fast safely, feature flags for gradual rollout, accepting technical debt consciously with a paydown plan. Give concrete example of a trade-off decision and its outcome."),

    ("Tell me about a time you improved a process or system significantly.",
     QuestionCategory.behavioral, Difficulty.medium, "process improvement, impact, initiative, optimization",
     "STAR: Identify a pain point (slow deployment, manual testing, repeated incidents). Research and propose solution. Implement with stakeholder buy-in. Quantify the result: 40% faster deploys, 60% fewer incidents. Demonstrates initiative and impact."),
]

AMAZON_QUESTIONS = [
    # Leadership Principles
    ("Tell me about a time you had to make a difficult decision with incomplete information. (Bias for Action)",
     QuestionCategory.behavioral, Difficulty.medium, "decision making, incomplete information, bias for action, calculated risk",
     "STAR with LP framing: Situation with ambiguity. Task: decision needed now. Action: gathered available data quickly, identified reversible vs irreversible decision, made calculated bet with contingency plan. Result: outcome + learning. Show you don't wait for perfect information."),

    ("Describe a time you dove deep into data to solve a problem. (Dive Deep)",
     QuestionCategory.behavioral, Difficulty.medium, "data analysis, root cause, metrics, deep dive",
     "STAR: Observed anomaly in metrics. Task: find root cause. Action: dug into logs, queried databases, cross-correlated signals, formed and tested hypotheses. Result: found unexpected root cause, implemented fix. Show comfort with going beyond surface-level and using data systematically."),

    ("Tell me about a project where you had to raise the bar significantly. (Insist on Highest Standards)",
     QuestionCategory.behavioral, Difficulty.hard, "quality standards, bar raising, excellence, push back",
     "STAR: Project with acceptable-but-poor quality. Task: raise standards without slowing delivery. Action: defined clear quality criteria, introduced code reviews, automated testing, refactored critical paths. Result: measurable improvement in reliability/performance. Show you don't settle for 'good enough'."),

    ("Describe a time you dealt with a very difficult customer or stakeholder. (Customer Obsession)",
     QuestionCategory.behavioral, Difficulty.medium, "customer obsession, stakeholder, empathy, problem resolution",
     "STAR: Difficult stakeholder with unrealistic demands or complaints. Task: understand and address their real need. Action: listened deeply, identified root concern vs stated complaint, proposed solutions, set realistic expectations, followed through. Result: resolved situation, maintained relationship. Always start from customer's perspective."),

    ("Tell me about a time you had to influence without authority to get something done. (Earn Trust)",
     QuestionCategory.behavioral, Difficulty.medium, "influence, persuasion, stakeholder alignment, leadership",
     "STAR: Needed cross-team collaboration without direct authority. Task: get buy-in. Action: understood each stakeholder's motivations, framed initiative in terms of their goals, used data to support arguments, built relationships, created win-win proposals. Result: achieved alignment and delivered. Show ability to lead through influence."),

    ("Describe a situation where you had to deliver more with fewer resources. (Frugality)",
     QuestionCategory.behavioral, Difficulty.medium, "frugality, constraints, resourcefulness, efficiency",
     "STAR: Budget/time/headcount reduced. Task: still deliver the goal. Action: prioritized ruthlessly, automated manual work, reused existing systems, made build-vs-buy decisions favoring reuse. Result: delivered equivalent or better outcome. Show creativity within constraints."),

    ("Tell me about a time you took on something outside your comfort zone. (Learn and Be Curious)",
     QuestionCategory.behavioral, Difficulty.easy, "learning, growth, curiosity, stretch assignment",
     "STAR: Volunteered or assigned to unfamiliar domain. Task: execute despite knowledge gap. Action: structured learning plan, found mentors, built prototypes to learn by doing, asked good questions. Result: delivered successfully and retained knowledge. Show genuine curiosity and growth mindset."),

    ("How do you handle a situation where you're blocked and your manager is unavailable?",
     QuestionCategory.behavioral, Difficulty.easy, "ownership, problem solving, initiative, escalation",
     "Show ownership: first exhaust self-help options (documentation, colleagues, adjacent teams). If truly blocked on a time-sensitive issue, escalate to skip-level or a decision-making colleague with clear context. Document what you tried and why you escalated. Never let a blocker sit silently."),

    # Technical – Amazon scale
    ("How would you design Amazon's shopping cart system? Discuss data model and scalability.",
     QuestionCategory.technical, Difficulty.hard, "system design, shopping cart, scalability, database, availability",
     "Data model: Cart table (cart_id, user_id, items JSON, TTL). Items: product_id, quantity, price_at_add. Use NoSQL (DynamoDB) for flexible schema and high write throughput. Guest carts: session-scoped with UUID. Persistence: merge on login. Scalability: partition by user_id, cache hot carts in Redis, eventual consistency acceptable for cart."),

    ("Explain the difference between SQS, SNS, and Kinesis. When would you use each?",
     QuestionCategory.technical, Difficulty.medium, "AWS, SQS, SNS, Kinesis, messaging, streaming",
     "SQS: message queue, point-to-point, guaranteed delivery, good for task queues (order processing). SNS: pub-sub, fan-out to multiple subscribers (email, SQS, Lambda), good for notifications. Kinesis: real-time streaming, ordered by shard, replay capability, good for analytics pipelines and log aggregation. Key: SQS=work queues, SNS=notifications, Kinesis=streaming analytics."),

    ("What is eventual consistency? Give a real-world example.",
     QuestionCategory.technical, Difficulty.medium, "eventual consistency, distributed systems, CAP, replication",
     "Eventual consistency: after an update, all replicas will eventually converge to the same value, but reads may temporarily return stale data. Example: DynamoDB with default settings - write to primary, propagate to replicas asynchronously. Read might see old value for milliseconds to seconds. Use cases: social media likes, shopping cart, DNS. Trade: higher availability for temporary inconsistency."),

    ("How do you handle database migrations with zero downtime?",
     QuestionCategory.technical, Difficulty.hard, "database migration, zero downtime, blue-green, schema change",
     "Expand-Contract pattern: 1) Add new column (nullable/default), 2) Deploy code writing to both old and new columns, 3) Backfill existing data, 4) Deploy code reading from new column, 5) Remove old column. Use feature flags. For large tables: online schema change tools (pt-online-schema-change, gh-ost). Blue-green deployments help isolate DB changes."),

    ("Describe how you'd implement idempotency in a payment API.",
     QuestionCategory.technical, Difficulty.hard, "idempotency, payment, API, distributed systems, retry",
     "Require client to send unique idempotency-key header. Server stores (idempotency_key, response) in database with TTL. On duplicate request: return stored response without reprocessing. Use distributed lock (Redis SETNX) to handle concurrent duplicates. Key considerations: key expiry, storage cost, handling partial failures mid-execution."),

    ("Explain how you'd architect a notification system for millions of users.",
     QuestionCategory.technical, Difficulty.hard, "notification system, push, email, scalability, fanout",
     "Architecture: Event bus (Kafka/Kinesis) receives notification events. Notification service fans out to channel-specific workers (Email: SES, Push: FCM/APNs, SMS: Twilio). Workers handle batch sending with rate limiting. Database stores notification history and user preferences. User preference service controls opt-out/opt-in. At scale: partition by user_id, dead-letter queues for failures."),

    # General Amazon
    ("Where do you see yourself in 5 years at Amazon?",
     QuestionCategory.general, Difficulty.easy, "career growth, goals, Amazon, leadership",
     "Show alignment with Amazon LP 'Learn and Be Curious'. Discuss growing technical depth in first 2 years, taking on broader ownership, mentoring others, contributing to high-impact projects. Show you've researched Amazon's career ladder (SDE tracks). Be specific but flexible."),
]

MICROSOFT_QUESTIONS = [
    # Technical – Design Thinking
    ("How would you redesign Windows Taskbar for better usability? Walk through your design process.",
     QuestionCategory.technical, Difficulty.hard, "design thinking, usability, product, UX, system design",
     "Start with empathy: who uses it, what are their pain points (too many items, poor discoverability, no context). Define: core jobs-to-be-done. Ideate: group related apps, smart suggestions, adaptive layout, keyboard shortcuts. Prototype: low-fi mockup. Test: A/B test with real users. Quantify: measure task completion time, error rate. Show human-centered design process."),

    ("Explain the difference between process and thread. How does this apply to Windows internals?",
     QuestionCategory.technical, Difficulty.medium, "process, thread, Windows, OS, concurrency",
     "Process: independent memory space, heavier to create, isolated. Thread: shares memory with parent process, lighter, faster context switch. Windows: each process has at least one thread. Thread scheduling uses preemptive multitasking. Windows-specific: fibers (cooperative, user-mode), job objects (group processes), UMS (user-mode scheduling). Context switch saves/restores CPU register state."),

    ("How does Git work internally? Explain the object model.",
     QuestionCategory.technical, Difficulty.medium, "git, version control, DAG, objects, blob, tree, commit",
     "Git stores everything as content-addressable objects (SHA-1 hash): Blob (file content), Tree (directory listing), Commit (tree + parent + metadata), Tag. Repository = DAG of commits. Branch = pointer to a commit. HEAD = pointer to current branch. Merge creates commit with two parents. Rebase replays commits. All operations are local until push/pull."),

    ("Describe how you would design Microsoft Teams' presence indicator (Online/Away/Busy) at scale.",
     QuestionCategory.technical, Difficulty.hard, "presence, real-time, WebSocket, scalability, distributed",
     "Presence service tracks user heartbeats. Client sends heartbeat every 30s over WebSocket or HTTP. Presence state stored in Redis (fast expiry). Subscription model: clients subscribe to presence of contacts. Fan-out: when status changes, notify all subscribers. Scale: partition by user_id, use consistent hashing. Staleness accepted: presence shown with ~60s delay. Challenge: mobile apps backgrounded."),

    ("Explain garbage collection in C# .NET. How does the GC decide what to collect?",
     QuestionCategory.technical, Difficulty.medium, "GC, .NET, C#, memory, generational",
     ".NET GC is generational: Gen 0 (short-lived, collected frequently), Gen 1 (survived one GC), Gen 2 (long-lived objects). GC triggers when Gen 0 fills up. Mark phase: traces object graph from GC roots (stack, statics). Sweep phase: reclaims unreachable objects. Compact phase: defragments heap. Large Object Heap (>85KB) not compacted by default. Finalization queue for objects with destructors."),

    ("How would you approach building an accessibility feature into a Microsoft product?",
     QuestionCategory.technical, Difficulty.medium, "accessibility, WCAG, screen reader, inclusive design, A11y",
     "Start with user research: talk to users with disabilities. Follow WCAG 2.1 guidelines (perceivable, operable, understandable, robust). Implement: semantic HTML/ARIA, keyboard navigation, screen reader compatibility (NVDA, JAWS, Narrator), sufficient color contrast, text scaling, focus indicators. Test with real assistive technology. Bake into design system, not afterthought."),

    # Behavioral – Growth Mindset
    ("Tell me about a time you received critical feedback. How did you respond?",
     QuestionCategory.behavioral, Difficulty.medium, "feedback, growth mindset, self-awareness, improvement",
     "STAR: Received specific critical feedback (code quality, communication style, missing requirements). Task: process and improve. Action: listened openly without defensiveness, asked clarifying questions, created actionable improvement plan, sought follow-up feedback. Result: measurable improvement, demonstrated growth. Show feedback is a gift, not a threat."),

    ("Describe a time when you failed. What did you learn?",
     QuestionCategory.behavioral, Difficulty.medium, "failure, learning, resilience, growth mindset",
     "STAR: Be honest about a real failure (missed deadline, bad production decision, poor communication). Task: deal with consequences. Action: took ownership, communicated transparently, fixed the immediate problem, conducted retrospective, implemented process change. Result: what changed as a result. Show failure is learning, not shame."),

    ("How do you approach mentoring junior engineers?",
     QuestionCategory.behavioral, Difficulty.medium, "mentoring, leadership, teaching, growth, empathy",
     "Show structured approach: regular 1-on-1s to understand goals and blockers, pair programming for knowledge transfer, code reviews as teaching moments (explain why not just what), giving stretch assignments with safety net, celebrating wins. Balance guidance with autonomy - help them think, don't just give answers."),

    ("Tell me about a time you had to adapt your communication style for a different audience.",
     QuestionCategory.behavioral, Difficulty.easy, "communication, adaptability, stakeholders, audience",
     "STAR: Presented technical topic to non-technical executives or vice versa. Action: researched audience background, translated technical concepts to business impact (for execs) or added technical depth (for engineers), used analogies, prepared for different questions. Result: effective communication, decision made. Show situational awareness."),

    ("Describe a time you built consensus across teams with competing priorities.",
     QuestionCategory.behavioral, Difficulty.hard, "consensus, cross-team, negotiation, alignment, stakeholder",
     "STAR: Cross-team dependency with misaligned timelines/goals. Task: align without authority. Action: mapped each team's actual goals, found common ground and shared wins, proposed phased approach that served everyone's near-term needs, documented agreement. Result: alignment achieved, delivered outcome. Show empathy and systems thinking."),

    # Microsoft Technical General
    ("What is the difference between Azure Blob Storage and Azure Table Storage?",
     QuestionCategory.technical, Difficulty.easy, "Azure, blob storage, table storage, cloud",
     "Blob: unstructured data (files, images, videos, backups). Massively scalable, up to 5TB per blob. Use for: media, log archives, ML datasets. Table: structured NoSQL key-value store, schemaless rows. Use for: metadata, user preferences, IoT telemetry. Table has partition/row key for fast lookup. Blob has containers and hierarchical namespace (ADLS Gen2)."),

    ("How would you implement authentication in a distributed microservices system?",
     QuestionCategory.technical, Difficulty.hard, "authentication, JWT, OAuth, microservices, security",
     "Use JWT with short expiry (15 min) + refresh tokens (7 days). API Gateway validates token on every request, passes user context downstream. Services trust Gateway, no per-service auth. Refresh tokens stored in Redis with revocation list. Azure AD / OAuth2 for enterprise SSO. For service-to-service: mutual TLS or service accounts. Never store passwords in plaintext, bcrypt with salt."),

    ("Explain async/await in C# and how it differs from threading.",
     QuestionCategory.technical, Difficulty.medium, "async await, C#, threading, Task, asynchronous",
     "async/await uses Task-based async pattern. await yields control back to the caller thread (no blocking). No new thread created by default - uses thread pool efficiently via state machine generated by compiler. Difference from threads: threads block waiting, async/await frees thread to do other work. Best for I/O-bound work. For CPU-bound: Task.Run() to offload to thread pool."),

    ("What are some common security vulnerabilities and how do you prevent them?",
     QuestionCategory.technical, Difficulty.medium, "security, OWASP, SQL injection, XSS, CSRF, vulnerabilities",
     "OWASP Top 10: SQL Injection (use parameterized queries), XSS (encode output, CSP headers), CSRF (CSRF tokens, SameSite cookies), Broken Authentication (MFA, secure sessions), Sensitive Data Exposure (encryption at rest/transit), Insecure Deserialization (validate input), Security Misconfiguration (principle of least privilege). Security by design, not afterthought."),

    ("How do you ensure code quality in a fast-moving team?",
     QuestionCategory.technical, Difficulty.medium, "code quality, code review, testing, CI/CD, technical debt",
     "Multi-layered approach: automated (linting, static analysis, unit/integration tests in CI), human (code reviews - focus on correctness + maintainability), process (definition of done includes tests, no merge without review), culture (psychological safety to raise concerns, celebrate refactoring). Track code coverage, cyclomatic complexity. Schedule tech debt sprints."),
]

# General/Behavioral fallback questions
GENERAL_QUESTIONS = [
    ("Tell me about yourself and why you're interested in this role.",
     QuestionCategory.general, Difficulty.easy, "introduction, motivation, career, goals",
     "Structure: 2-3 sentences on background, highlight most relevant experience, connect to role requirements, end with why this specific company/role. Keep to 90 seconds. Show genuine enthusiasm and preparation."),

    ("Where do you see yourself in 3-5 years?",
     QuestionCategory.general, Difficulty.easy, "career goals, growth, ambition, planning",
     "Show progression: technical depth → broader impact → leadership or specialization. Align with the company's growth opportunities. Be specific but adaptable. Show you've thought about it but aren't rigidly locked in."),

    ("What are your greatest strengths and how have you applied them?",
     QuestionCategory.general, Difficulty.easy, "strengths, self-awareness, examples",
     "Pick 2-3 genuine strengths relevant to the role (problem-solving, communication, ownership). Give concrete examples of each. Avoid generic answers like 'hard-working' without proof."),

    ("Describe a time when you went above and beyond what was required.",
     QuestionCategory.behavioral, Difficulty.medium, "initiative, ownership, above and beyond, impact",
     "STAR: Identify situation where baseline wasn't enough. Chose to do more without being asked. Describe specific additional actions. Quantify the additional impact. Show this is your default mode, not an exception."),

    ("How do you manage multiple competing priorities under tight deadlines?",
     QuestionCategory.behavioral, Difficulty.medium, "time management, prioritization, stress, multitasking",
     "Show systematic approach: break down into tasks, estimate effort, identify dependencies, communicate timeline risks early, ruthlessly prioritize by impact, use time-boxing. Give concrete example. Show you don't just work harder but smarter."),
]


# ─────────────────────────── TCS Questions ───────────────────────────────────

TCS_QUESTIONS = [
    ("Describe your experience working on a client-facing IT services project. How did you manage client expectations?",
     QuestionCategory.behavioral, Difficulty.medium, "client management, IT services, communication, expectations, TCS",
     "STAR: Client project with shifting requirements. Task: keep client satisfied while managing scope. Action: established weekly status calls, documented all changes with impact assessment, used change-request process, flagged risks early. Result: delivered on time with positive client feedback. Show proactive communication and ownership."),

    ("Walk me through how you would handle a production incident escalated by a client at 2 AM.",
     QuestionCategory.behavioral, Difficulty.hard, "incident management, escalation, client, production, SLA",
     "Immediate response: acknowledge to client within SLA window, form an incident bridge with SMEs, triage severity, assign ownership. Communication: send regular updates every 30 minutes even if no new information. Resolution: RCA within 24 hours, preventive action plan. Show calmness, process discipline, and client focus."),

    ("What is the Software Development Life Cycle (SDLC)? Which model does TCS commonly use for large enterprises?",
     QuestionCategory.technical, Difficulty.easy, "SDLC, waterfall, agile, iterative, process, TCS",
     "SDLC phases: Requirements → Design → Implementation → Testing → Deployment → Maintenance. TCS uses multiple models: Waterfall for fixed-scope government/banking projects, Agile/Scrum for product development, and their proprietary TCS BaNCS methodology for BFSI. The choice depends on client risk appetite and requirement stability."),

    ("How would you explain a technical issue to a non-technical client stakeholder?",
     QuestionCategory.behavioral, Difficulty.medium, "communication, non-technical, stakeholder, simplification, clarity",
     "Use business language: translate technical jargon to business impact ('The database slowdown means users wait 10 seconds instead of 1 second, reducing daily transactions by 30%'). Use analogies. Present: what happened, business impact, what we are doing, expected resolution time. Avoid blame. Practice empathy. Follow up in writing."),

    ("Describe a situation where you had to follow a defined process even when you believed a shortcut was better. What did you do?",
     QuestionCategory.behavioral, Difficulty.medium, "process compliance, discipline, judgment, improvement",
     "STAR: Defined process seemed inefficient for a specific case. Instead of bypassing it, followed the process and simultaneously documented the issue and proposed an improvement. Raised it in retrospective with data. Result: process was improved for everyone. Show compliance mindset + constructive improvement culture."),

    ("What is the difference between unit testing and integration testing? Why are both important in IT delivery?",
     QuestionCategory.technical, Difficulty.easy, "unit testing, integration testing, QA, testing, delivery",
     "Unit testing: tests a single function/class in isolation using mocks. Fast, deterministic, developer-owned. Integration testing: tests interactions between components (service + database, API + external service). Catches interface bugs unit tests miss. Both needed: unit tests give fast feedback, integration tests give confidence in system-level behavior. TCS uses both in their delivery assurance framework."),

    ("Tell me about a time you contributed to knowledge sharing or documentation in your team.",
     QuestionCategory.behavioral, Difficulty.easy, "knowledge sharing, documentation, teamwork, collaboration, TCS",
     "STAR: Noticed team was spending time re-solving known issues. Created a knowledge base (Confluence/SharePoint) documenting common issues, runbooks, and best practices. Conducted lunch-and-learn sessions. Result: reduced onboarding time for new members by X%, reduced repeat escalations. Show initiative and team orientation."),
]


# ─────────────────────────── Infosys Questions ───────────────────────────────

INFOSYS_QUESTIONS = [
    ("Tell me about a time you delivered a project using Agile methodology. What was your role?",
     QuestionCategory.behavioral, Difficulty.medium, "agile, scrum, sprint, delivery, teamwork, Infosys",
     "STAR: Agile project with 2-week sprints. Describe your role (developer/scrum master/BA). Action: participated in sprint planning, daily standups, retrospectives. Handled mid-sprint requirement changes by re-prioritizing with PO. Result: delivered working software incrementally, improved velocity by X%. Show understanding of Agile values: collaboration, working software, responding to change."),

    ("How do you ensure quality when working under tight delivery timelines?",
     QuestionCategory.behavioral, Difficulty.medium, "quality, timeline, testing, delivery, trade-off",
     "Proactive approach: define 'done' criteria upfront including tests. Automate regression tests so each build is validated instantly. Prioritize testing for highest-risk features. Be transparent about quality trade-offs with stakeholders. Don't skip testing - negotiate scope instead. Show quality is non-negotiable even under pressure."),

    ("Describe a technology transformation project you worked on. What challenges did you face?",
     QuestionCategory.technical, Difficulty.hard, "digital transformation, legacy, migration, modernization, Infosys",
     "STAR: Legacy system modernization (e.g., monolith to microservices, on-prem to cloud). Challenges: data migration with zero downtime, re-training users, maintaining parallel systems, managing resistance to change. Actions: phased rollout, feature flags, stakeholder change management, rigorous testing. Result: successful migration, measurable performance/cost improvement."),

    ("What are microservices and what are their advantages and disadvantages?",
     QuestionCategory.technical, Difficulty.medium, "microservices, architecture, distributed, containers, scalability",
     "Microservices: application as suite of small, independently deployable services. Advantages: independent scaling, technology diversity, fault isolation, faster deployments. Disadvantages: network latency, distributed system complexity, data consistency challenges, operational overhead (service discovery, distributed tracing). Infosys uses microservices for digital-native clients, monolithic modernization for legacy clients."),

    ("Tell me about a time you demonstrated leadership without holding a leadership title.",
     QuestionCategory.behavioral, Difficulty.medium, "leadership, initiative, influence, teamwork, Infosys",
     "STAR: Identified gap or problem without being asked to fix it. Took initiative to rally colleagues, propose a solution, coordinate effort. Maintained momentum through regular check-ins. Result: problem solved, recognized for initiative. Show that leadership is a behavior, not a title."),

    ("How do you manage a client who keeps adding requirements after the project scope is locked?",
     QuestionCategory.behavioral, Difficulty.hard, "scope creep, client management, negotiation, change management",
     "Acknowledge the client's business need first (don't just say no). Then: reference the signed scope document, quantify the impact (time + cost) of the addition, present options (defer to Phase 2, drop an existing feature, formal change request). Document everything. Escalate to account manager if needed. Show diplomatic firmness and solution orientation."),

    ("Explain the difference between REST and GraphQL. When would you recommend each?",
     QuestionCategory.technical, Difficulty.medium, "REST, GraphQL, API, web services, Infosys",
     "REST: resource-based URLs, multiple endpoints, over-fetching/under-fetching common. Simple and widely supported. GraphQL: single endpoint, client specifies exactly what data it needs, reduces over-fetching. Better for complex, nested data or mobile clients (bandwidth-sensitive). Use REST for simple CRUD APIs; GraphQL for complex data graphs or BFF (Backend for Frontend) patterns."),
]


# ─────────────────────────── Deloitte Questions ──────────────────────────────

DELOITTE_QUESTIONS = [
    ("Walk me through how you would structure and solve a case: 'Our client, a retail bank, is seeing declining profits despite growing revenue. What would you investigate?'",
     QuestionCategory.technical, Difficulty.hard, "case study, consulting, profitability, framework, Deloitte",
     "Profit = Revenue - Cost. Revenue growing → problem is costs. Break costs: fixed vs variable, by business line (retail, corporate, treasury). Investigate: rising credit losses (NPAs), increasing compliance/regulatory costs, technology investment costs, staff headcount growth, branch network costs. Also check revenue mix shift (lower-margin products growing faster). Prioritize by size of impact. Show MECE thinking."),

    ("Tell me about a time you used data to change someone's mind.",
     QuestionCategory.behavioral, Difficulty.medium, "data-driven, persuasion, analytics, decision making, Deloitte",
     "STAR: Stakeholder held assumption not supported by data. Task: change decision direction. Action: gathered relevant data, built clear visualizations, presented hypothesis vs data in a structured way, acknowledged counter-arguments. Result: decision changed, better outcome. Show analytical thinking + communication skill."),

    ("How do you prioritize when a client gives you three equally urgent deliverables with the same deadline?",
     QuestionCategory.behavioral, Difficulty.medium, "prioritization, client service, consulting, time management",
     "Clarify 'equally urgent' - ask the client which has higher strategic value or harder dependencies. If truly equal: assess effort required, do highest-ROI work first, communicate proactively about sequencing. If deadline is truly immovable for all three: escalate to engagement manager, consider bringing in additional resource. Show structured thinking and communication."),

    ("What is a SWOT analysis and when would you use it in consulting?",
     QuestionCategory.technical, Difficulty.easy, "SWOT, strategic analysis, consulting, framework, Deloitte",
     "SWOT: Strengths (internal positives), Weaknesses (internal negatives), Opportunities (external positives), Threats (external negatives). Use in strategy engagements: market entry decisions, competitive positioning, organizational assessments. Limitation: static snapshot, doesn't prioritize. Often followed by TOWS matrix to generate strategic options. Good starting point but needs deeper analysis."),

    ("Describe a situation where you identified a risk that others had overlooked. What did you do?",
     QuestionCategory.behavioral, Difficulty.medium, "risk identification, analytical thinking, proactive, consulting",
     "STAR: During project work noticed an assumption or dependency that could fail. Task: surface the risk. Action: documented the risk with probability/impact analysis, raised it in the right forum (risk register, project meeting), proposed mitigation options. Result: risk was addressed, project averted a problem. Show analytical vigilance and constructive approach."),

    ("How would you approach advising a client who wants to outsource their entire IT department?",
     QuestionCategory.technical, Difficulty.hard, "IT outsourcing, advisory, risk, strategy, Deloitte",
     "Structured approach: 1) Assess current state: IT costs, capabilities, strategic vs commodity functions. 2) Define what should stay in-house (competitive differentiators, data-sensitive systems). 3) Evaluate outsourcing models: full, selective, hybrid. 4) Risk assessment: vendor dependency, knowledge loss, transition costs, data security. 5) Business case: TCO comparison. 6) Vendor selection criteria. Show end-to-end advisory thinking."),

    ("Tell me about a time you worked with a diverse, cross-functional team to solve a problem.",
     QuestionCategory.behavioral, Difficulty.medium, "diversity, teamwork, cross-functional, collaboration, Deloitte",
     "STAR: Team with members from different functions (finance, IT, operations) and/or backgrounds. Challenge: different priorities and communication styles. Action: established shared goal, created common vocabulary, respected each perspective, leveraged diversity as a strength (finance spotted risks IT missed). Result: better solution than any single function could have produced. Show inclusion and collaboration."),
]


# ─────────────────────────── Accenture Questions ─────────────────────────────

ACCENTURE_QUESTIONS = [
    ("Describe a digital transformation initiative you contributed to. What technologies were involved?",
     QuestionCategory.technical, Difficulty.hard, "digital transformation, cloud, AI, automation, Accenture",
     "STAR: Organisation moving from manual/legacy to digital. Technologies: cloud migration (AWS/Azure), process automation (RPA, BPM), data analytics platform, customer-facing app modernization. Your role: architect design, change management, technical delivery, or testing. Result: measurable improvement (cost reduction, faster time-to-market, better customer NPS). Show breadth across technology + business impact."),

    ("How do you stay current with emerging technologies? Give an example of a technology you recently learned.",
     QuestionCategory.behavioral, Difficulty.easy, "learning, innovation, technology trends, curiosity, Accenture",
     "Show continuous learning: follow industry blogs, take online courses (Coursera, AWS certifications), participate in hackathons, experiment with side projects. Recent example: learned about LLMs/generative AI, built a small proof-of-concept, understood use cases and limitations. Show you don't just read but actually experiment."),

    ("Tell me about a time you brought an innovative idea to your team that was adopted.",
     QuestionCategory.behavioral, Difficulty.medium, "innovation, initiative, idea, adoption, Accenture",
     "STAR: Identified an opportunity for improvement or a new approach. Developed the idea into a concrete proposal with a small prototype or business case. Pitched to team/manager with evidence. Navigated skepticism with data. Result: idea adopted, measurable impact. Show you are a 'doer' not just a thinker."),

    ("What is cloud-native development and how does it differ from traditional application development?",
     QuestionCategory.technical, Difficulty.medium, "cloud-native, containers, microservices, DevOps, Accenture",
     "Cloud-native: design principles for applications that fully leverage cloud (elastic scaling, managed services, automation). Key pillars: microservices, containers (Docker), container orchestration (Kubernetes), CI/CD pipelines, infrastructure as code (Terraform). Traditional: monoliths deployed on physical/VM servers, manual scaling. Cloud-native enables faster release cycles, better resilience, lower operational cost."),

    ("Describe a time you had to deliver results as part of a large team where your individual contribution was not always visible.",
     QuestionCategory.behavioral, Difficulty.medium, "teamwork, collaboration, humility, large team, Accenture",
     "STAR: Large delivery team with many contributors. Your work was foundational (platform, tooling, process) rather than visible features. Action: focused on quality and enabling others to go faster, documented your work thoroughly, communicated contributions clearly in status updates. Result: team delivered successfully. Show ability to subordinate ego to team outcome."),

    ("How would you explain AI/machine learning to a business executive who has no technical background?",
     QuestionCategory.technical, Difficulty.medium, "AI, machine learning, communication, business, Accenture",
     "Use business language: 'AI learns patterns from historical data and uses them to predict or automate decisions, like how Netflix recommends shows.' Use their domain: 'Instead of your underwriters manually reviewing each loan application, AI can flag high-risk applications automatically.' Focus on business outcomes: cost saving, faster decisions, better customer experience. Acknowledge limitations: AI needs good data, requires oversight."),

    ("Tell me about a situation where a project you were part of failed to meet its goals. What happened and what did you learn?",
     QuestionCategory.behavioral, Difficulty.medium, "failure, learning, accountability, resilience, Accenture",
     "STAR: Project that underdelivered (missed deadline, scope cut, quality issues). Be honest about what went wrong. Take ownership of your part. Describe what you learned: earlier escalation, better requirements management, more realistic estimation. Result: applied lessons in subsequent projects with better outcome. Show maturity and growth mindset."),
]


# ─────────────────────────── Wipro Questions ─────────────────────────────────

WIPRO_QUESTIONS = [
    ("Tell me about a challenging IT delivery project. How did you overcome obstacles?",
     QuestionCategory.behavioral, Difficulty.medium, "IT delivery, problem solving, obstacles, teamwork, Wipro",
     "STAR: Project with significant technical or organizational obstacles (integration issues, resource constraints, unclear requirements). Action: broke down the problem, escalated blockers appropriately, found creative workarounds, collaborated across teams. Result: delivered despite challenges. Show resilience and resourcefulness."),

    ("Describe a time you had to quickly learn a new tool or programming language for a project.",
     QuestionCategory.behavioral, Difficulty.medium, "learning agility, new technology, adaptability, growth, Wipro",
     "STAR: New project requiring unfamiliar technology. Action: created structured learning plan (official docs first, then tutorials, then build something small), paired with experienced colleague, applied learning immediately to project tasks. Result: productive within X days, delivered quality work. Show systematic approach to learning under pressure."),

    ("What is the difference between functional and non-functional requirements? Give examples.",
     QuestionCategory.technical, Difficulty.easy, "requirements, functional, non-functional, QA, Wipro",
     "Functional requirements: what the system does (user can log in, system processes payment, report is generated). Non-functional requirements: how the system does it (performance: 99.9% uptime, latency < 200ms; security: data encrypted at rest; usability: mobile-responsive). Both must be captured and tested. Non-functional failures often cause production incidents."),

    ("How do you approach debugging a production issue you've never seen before?",
     QuestionCategory.technical, Difficulty.medium, "debugging, problem solving, production, systematic, Wipro",
     "Systematic approach: 1) Reproduce or characterize the issue (when did it start, what changed). 2) Gather evidence: logs, metrics, traces, error messages. 3) Narrow scope: is it one service, one region, one user type? 4) Form hypotheses ordered by likelihood. 5) Test each hypothesis without making multiple changes simultaneously. 6) Find root cause, not just symptom. 7) Fix + add monitoring to detect early next time."),

    ("Describe a situation where you had to work with a team member who was not contributing equally. How did you handle it?",
     QuestionCategory.behavioral, Difficulty.medium, "teamwork, conflict, accountability, communication, Wipro",
     "STAR: Team member consistently missing deadlines or delivering poor quality. Action: had a private, empathetic conversation to understand root cause (personal issue, unclear expectations, skill gap). Offered support. If issue persisted, involved team lead with documented evidence. Focused on impact to team, not personal criticism. Result: situation resolved or appropriately escalated."),

    ("What is version control and why is it important in software development?",
     QuestionCategory.technical, Difficulty.easy, "git, version control, collaboration, branching, Wipro",
     "Version control (Git) tracks all code changes with history. Enables: collaboration (multiple developers work simultaneously via branches), rollback (revert to any previous state), audit trail (who changed what and why), release management (tag versions). Best practices: feature branches, meaningful commit messages, pull requests with review, protect main branch."),

    ("Tell me about a time you showed initiative to improve a process or tool used by your team.",
     QuestionCategory.behavioral, Difficulty.medium, "initiative, process improvement, automation, impact, Wipro",
     "STAR: Identified inefficient manual process (e.g., manual test execution, manual deployment steps, repeated copy-paste work). Proposed automation or improvement, got buy-in, implemented it. Result: saved X hours per week, reduced errors. Show you look beyond your task to improve the team's working environment."),
]


# ─────────────────────────── EY Questions ────────────────────────────────────

EY_QUESTIONS = [
    ("Walk me through a DCF (Discounted Cash Flow) analysis. What are its key inputs and limitations?",
     QuestionCategory.technical, Difficulty.hard, "DCF, valuation, finance, analytical, EY",
     "DCF: value of a business = PV of all future free cash flows discounted at WACC. Key inputs: revenue growth forecast, operating margins, capital expenditure, working capital changes, terminal value (Gordon Growth Model), discount rate (WACC = cost of equity + cost of debt, weighted). Limitations: highly sensitive to assumptions (small WACC change = large value change), terminal value dominates, difficult to forecast long-term. Best used alongside comps and precedent transactions."),

    ("Tell me about a time you identified an error or inconsistency in a dataset or report. What did you do?",
     QuestionCategory.behavioral, Difficulty.medium, "attention to detail, analytical, accuracy, audit, EY",
     "STAR: Found discrepancy (numbers not reconciling, outlier data point, formula error in model). Action: verified independently, traced to root source, quantified impact, brought it to the right person's attention before it was used in a decision. Result: corrected before causing downstream error. Show rigour, attention to detail, and constructive communication."),

    ("What is the difference between assurance and advisory services in a Big 4 firm like EY?",
     QuestionCategory.general, Difficulty.easy, "assurance, advisory, consulting, audit, EY",
     "Assurance (Audit): independent verification that financial statements are free from material misstatement. Provides credibility to stakeholders. Governed by independence rules. Advisory/Consulting: helps clients improve performance, transform operations, manage risk, implement technology. No independence constraint. EY provides both but keeps them organizationally separate due to independence requirements."),

    ("Describe a time you had to explain complex financial information to a non-finance audience.",
     QuestionCategory.behavioral, Difficulty.medium, "communication, finance, simplification, client, EY",
     "STAR: Had to present financial analysis to non-financial stakeholders (operations team, board member). Action: used visuals (charts over tables), focused on business implications ('this means we break even in 18 months'), used analogies, avoided jargon, prepared clear executive summary. Result: decision-makers understood and acted on findings. Show bridge-building between technical and business."),

    ("What is EBITDA and why is it used as a proxy for operational performance?",
     QuestionCategory.technical, Difficulty.medium, "EBITDA, financial analysis, valuation, profitability, EY",
     "EBITDA = Earnings Before Interest, Tax, Depreciation and Amortisation. Useful because it strips out: financing decisions (interest), tax jurisdiction, and non-cash charges (D&A). Allows comparison of operating performance across companies with different capital structures or accounting policies. EV/EBITDA is a common valuation multiple. Limitation: not a cash flow measure (ignores capex, working capital)."),

    ("How do you prioritise tasks when deadlines overlap during a busy period like year-end close?",
     QuestionCategory.behavioral, Difficulty.medium, "prioritization, time management, deadline, professional skills, EY",
     "Systematic approach: triage by deadline and consequence of missing it (client-facing vs internal). Communicate proactively - tell stakeholders early if timelines are at risk. Break tasks into smaller pieces and timebox. Delegate where possible. Work late strategically (for highest-stakes deliverables). In Big 4, year-end is intense by design - show you understand this and can perform under pressure."),

    ("What key factors would you consider when advising a client on entering a new market?",
     QuestionCategory.technical, Difficulty.hard, "market entry, strategy, advisory, consulting, EY",
     "Framework: 1) Market attractiveness (size, growth rate, profitability). 2) Competitive landscape (Porter's 5 Forces). 3) Regulatory environment (licences, local content rules). 4) Client's competitive advantage in this market. 5) Entry mode (organic, acquisition, JV, licensing). 6) Financial projections (investment required, break-even). 7) Risk assessment. Structure your answer MECE, ask clarifying questions before diving in."),
]


# ─────────────────────────── KPMG Questions ──────────────────────────────────

KPMG_QUESTIONS = [
    ("What is risk-based auditing and how does it differ from a traditional audit approach?",
     QuestionCategory.technical, Difficulty.medium, "risk-based audit, internal controls, KPMG, assurance, risk",
     "Traditional audit: test all transactions or large samples uniformly. Risk-based audit: identify where risk of material misstatement is highest (complex transactions, judgement-heavy estimates, related-party transactions) and concentrate audit effort there. More efficient and effective. Requires understanding the client's business, industry risks, and internal control environment. KPMG's audit methodology is risk-based (KPMG Clara platform)."),

    ("Describe a time you used analytical skills to identify a trend or pattern others had missed.",
     QuestionCategory.behavioral, Difficulty.medium, "analytical, pattern recognition, data, insight, KPMG",
     "STAR: Data-heavy task (financial analysis, operational data review). Spotted anomaly or trend by going deeper than summary figures. Used visualization or cross-segmentation to confirm. Brought insight to team or client with supporting evidence. Result: informed better decision, prevented problem, or identified opportunity. Show natural analytical curiosity."),

    ("What are the key differences between IFRS and US GAAP?",
     QuestionCategory.technical, Difficulty.hard, "IFRS, GAAP, accounting standards, finance, KPMG",
     "Key differences: 1) LIFO inventory: allowed under US GAAP, prohibited under IFRS. 2) Revaluation of assets: allowed under IFRS, not under US GAAP. 3) Development costs: capitalized under IFRS if criteria met, expensed under US GAAP. 4) Lease accounting: similar post-ASC 842/IFRS 16, but differences remain. 5) Revenue recognition: largely converged post-ASC 606/IFRS 15. IFRS is principle-based (more judgement), US GAAP is rules-based (more prescriptive)."),

    ("Tell me about a time you worked under significant pressure to meet a non-negotiable deadline.",
     QuestionCategory.behavioral, Difficulty.medium, "pressure, deadline, resilience, professional skills, KPMG",
     "STAR: Hard deadline (regulatory filing, audit sign-off, board presentation). Task: complete quality work in compressed time. Action: stripped out non-essential tasks, worked extended hours strategically, communicated blockers immediately, asked for help where needed. Result: met deadline with acceptable quality. Show you can perform in the high-pressure environment typical of Big 4."),

    ("How would you explain internal controls over financial reporting to a new business owner?",
     QuestionCategory.technical, Difficulty.easy, "internal controls, ICFR, audit, risk, KPMG",
     "Use analogy: 'Internal controls are safeguards that reduce the chance of financial errors or fraud, like a lock on a cash register.' Examples: separation of duties (person who approves purchase cannot also pay it), reconciliation (monthly bank statement match), access controls (only authorized staff can modify financial records), management review (CFO reviews monthly financial statements). They provide reasonable assurance, not absolute certainty."),

    ("Describe a time you had to give difficult feedback to a colleague. How did you approach it?",
     QuestionCategory.behavioral, Difficulty.medium, "feedback, communication, professional development, empathy, KPMG",
     "STAR: Colleague making repeated errors or having impact on team deliverable quality. Action: chose private setting, used specific examples (not generalisations), focused on behaviour/impact not personality, asked for their perspective, collaborated on improvement plan. Result: colleague improved, professional relationship maintained. Show feedback is given with care and professionalism."),

    ("What are the main types of advisory services KPMG offers and how do they create value for clients?",
     QuestionCategory.general, Difficulty.medium, "advisory, risk consulting, management consulting, KPMG, value",
     "KPMG Advisory: 1) Management Consulting (strategy, operations, digital transformation). 2) Risk Consulting (enterprise risk, cyber security, internal audit, regulatory compliance). 3) Deal Advisory (M&A due diligence, valuation, restructuring). Value creation: helps clients reduce risk, improve efficiency, navigate regulation, execute transactions, and adapt to change. Differentiator: deep industry knowledge combined with technical expertise."),
]


# ─────────────────────────── Seed runner ─────────────────────────────────────

# Map: (question_list, company_pack_id)
ALL_PACKS = [
    (GOOGLE_QUESTIONS, "google"),
    (AMAZON_QUESTIONS, "amazon"),
    (MICROSOFT_QUESTIONS, "microsoft"),
    (TCS_QUESTIONS, "tcs"),
    (INFOSYS_QUESTIONS, "infosys"),
    (DELOITTE_QUESTIONS, "deloitte"),
    (ACCENTURE_QUESTIONS, "accenture"),
    (WIPRO_QUESTIONS, "wipro"),
    (EY_QUESTIONS, "ey"),
    (KPMG_QUESTIONS, "kpmg"),
    (GENERAL_QUESTIONS, None),
]

# All jobs to seed (including originals + 7 new roles)
ALL_JOBS = [
    # Original jobs
    {
        "title": "Graduate Software Engineer",
        "required_skills": ["python", "sql", "git", "javascript", "algorithms"],
    },
    {
        "title": "Data Analyst Intern",
        "required_skills": ["python", "sql", "excel", "statistics", "visualization"],
    },
    {
        "title": "Software Development Engineer",
        "required_skills": ["java", "algorithms", "system design", "aws", "distributed systems"],
    },
    {
        "title": "Frontend Developer",
        "required_skills": ["react", "javascript", "css", "typescript", "performance"],
    },
    # New diverse roles
    {
        "title": "Machine Learning Engineer",
        "required_skills": [
            "python", "machine learning", "deep learning", "tensorflow",
            "pytorch", "data pipelines", "model deployment", "statistics",
        ],
    },
    {
        "title": "DevOps Engineer",
        "required_skills": [
            "linux", "docker", "kubernetes", "ci/cd", "terraform",
            "ansible", "aws", "monitoring", "shell scripting",
        ],
    },
    {
        "title": "Cloud Architect",
        "required_skills": [
            "aws", "azure", "gcp", "cloud architecture", "networking",
            "security", "infrastructure as code", "cost optimization", "microservices",
        ],
    },
    {
        "title": "Business Analyst",
        "required_skills": [
            "requirements gathering", "stakeholder management", "sql",
            "data analysis", "process mapping", "agile", "communication",
            "excel", "business process improvement",
        ],
    },
    {
        "title": "Mobile Developer (Flutter)",
        "required_skills": [
            "flutter", "dart", "mobile development", "rest apis",
            "firebase", "ios", "android", "ui/ux", "state management",
        ],
    },
    {
        "title": "Cybersecurity Analyst",
        "required_skills": [
            "network security", "siem", "penetration testing", "vulnerability assessment",
            "incident response", "firewalls", "python", "security frameworks", "compliance",
        ],
    },
    {
        "title": "Full Stack Developer",
        "required_skills": [
            "react", "node.js", "python", "postgresql", "rest apis",
            "docker", "git", "typescript", "system design",
        ],
    },
]


def run():
    settings = get_settings()
    db = SessionLocal()
    try:
        # ── Create all tables first (works for fresh SQLite DB) ───────────────
        from app.db.base import Base
        from app.db.session import engine
        import app.db.models  # noqa: ensure all models are registered
        Base.metadata.create_all(bind=engine)
        print("Tables created/verified.")

        # ── Seed all question packs ────────────────────────────────────────────
        for questions, pack_id in ALL_PACKS:
            for text, cat, diff, kw, ref in questions:
                exists = db.query(Question).filter(Question.text == text).first()
                if not exists:
                    db.add(
                        Question(
                            text=text,
                            category=cat,
                            difficulty=diff,
                            keywords=kw,
                            reference_answer=ref,
                            company_pack=pack_id,
                        )
                    )

        db.commit()
        q_count = db.query(Question).count()
        print(f"Questions in DB: {q_count}")

        # ── Seed Jobs (skip if title already exists) ───────────────────────────
        added_jobs = 0
        for job_def in ALL_JOBS:
            exists = db.query(Job).filter(Job.title == job_def["title"]).first()
            if not exists:
                db.add(Job(title=job_def["title"], required_skills=job_def["required_skills"]))
                added_jobs += 1
        if added_jobs:
            db.commit()
            print(f"Seeded {added_jobs} new job(s). Total jobs: {db.query(Job).count()}")
        else:
            print(f"Jobs already seeded. Total jobs: {db.query(Job).count()}")

        # ── Seed Admin ─────────────────────────────────────────────────────────
        admin_email = settings.BOOTSTRAP_ADMIN_EMAIL.lower()
        if not db.query(User).filter(User.email == admin_email).first():
            db.add(
                User(
                    email=admin_email,
                    name="Admin",
                    password_hash=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
                    role=UserRole.admin,
                )
            )
            db.commit()
            print(f"Seeded admin: {admin_email}")

        # ── Seed Student ───────────────────────────────────────────────────────
        student_email = "student@iilm.edu"
        if not db.query(User).filter(User.email == student_email).first():
            db.add(
                User(
                    email=student_email,
                    name="Test Student",
                    password_hash=hash_password("Shourya@001"),
                    role=UserRole.student,
                )
            )
            db.commit()
            print(f"Seeded student: {student_email}")

        # ── Final summary ──────────────────────────────────────────────────────
        print("\n--- Seed Summary ---")
        print(f"  Questions : {db.query(Question).count()}")
        print(f"  Jobs      : {db.query(Job).count()}")
        print(f"  Users     : {db.query(User).count()}")
        packs_present = (
            db.query(Question.company_pack)
            .distinct()
            .filter(Question.company_pack.isnot(None))
            .all()
        )
        print(f"  Packs     : {sorted(p[0] for p in packs_present)}")

    finally:
        db.close()


if __name__ == "__main__":
    run()
