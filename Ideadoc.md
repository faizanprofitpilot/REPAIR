# **REPAIR**

## **The Agent That Writes Its Own Missing Runtime Rules**

### **One-line concept**

**REPAIR is an enterprise agent that turns operational failures into machine-enforced runtime rules.**

When it encounters a failure its developers never anticipated, it:

**EXECUTES → FAILS → DIAGNOSES → RESEARCHES → SYNTHESIZES → TESTS → PROMOTES → ENFORCES → TRANSFERS**

The important distinction:

> **REPAIR does not just remember mistakes. It converts experience into executable policy.**

---

# **1\. The core experiment**

REPAIR answers one question:

> **Can an autonomous agent experience a real operational failure, synthesize a missing runtime rule from that experience, prove the rule is safe, and correctly apply it to a different real tool?**

The demo deliberately uses **real external software state**:

* Stripe test-mode refunds,  
* Linear issue creation,  
* One as the authenticated action layer,  
* You.com for live API semantics,  
* Daytona for deterministic candidate evaluation.

The failure injection is controlled.

The mutations are real.

The learned rule is not prewritten.

The evaluation is deterministic.

And the final transfer happens against a different real application.

---

# **2\. The problem**

Agents are increasingly allowed to take actions that create persistent external state:

* issue refunds,  
* cancel subscriptions,  
* create tickets,  
* place orders,  
* send messages,  
* provision resources,  
* update business systems.

These actions encounter ordinary distributed-systems ambiguity:

* a request succeeds but the response disappears,  
* an asynchronous action is accepted but state remains temporarily unknown,  
* a tool response times out after commit,  
* a connection drops,  
* external state cannot immediately be reconciled.

A naive agent may interpret:

> **“I didn't receive success.”**

as:

> **“The action did not happen.”**

Then it blindly repeats the action.

That can create:

* duplicate refunds,  
* duplicate tickets,  
* duplicate orders,  
* duplicate infrastructure,  
* duplicate messages,  
* inconsistent business state.

Human engineers know how to design around these failure modes.

REPAIR asks whether:

> **execution experience itself can generate the missing reliability control.**

---

# **3\. Demo context: a customer-support agent**

The starting workflow should feel completely ordinary.

A customer says:

> “Part of my order arrived damaged. Support approved a $12.90 partial refund and said I can keep the item. Can you process that?”

The agent validates:

Order total:          $38.90  
Approved refund:      $12.90  
Already refunded:      $0.00  
Refund authorized:       YES  
Return required:          NO

This is not an exotic financial operation.

It is exactly the type of routine consequential action autonomous support agents increasingly perform.

The danger is not one $12.90 mistake.

The danger is a flawed operating behavior being repeated across thousands of autonomous actions.

---

# **4\. Real execution substrate**

The refund is executed against:

# **STRIPE TEST MODE**

through:

# **ONE**

The agent does not mutate a fake in-memory payment database.

It sends a real authenticated Stripe test-mode refund through One.

The resulting refund object is visible in Stripe.

That matters because the audience can independently see that external state actually changed.

---

# **5\. Preflight: verify One preserves Stripe idempotency headers**

Before the demo architecture relies on Stripe's native safe-replay mechanism, REPAIR's implementation performs a concrete compatibility test.

Run the same Stripe test-mode refund request twice through One using the same:

Idempotency-Key: repair-preflight-001

through One's additional-header mechanism.

Expected result:

Request 1  
→ Stripe refund created

Request 2  
→ same idempotency identity  
→ no second refund created

Verify this in the Stripe dashboard.

This test determines whether the native-safe-replay branch is genuinely available through the actual One execution path.

If the header survives:

native\_safe\_replay \= AVAILABLE

If it does not:

native\_safe\_replay \= UNAVAILABLE  
authoritative\_state\_verification \= REQUIRED

The core learned policy does not change either way.

What changes is which recovery primitive the runtime can use.

This is an implementation preflight, not a demo assumption.

---

# **6\. Agent V1**

V1 is competent.

It knows to:

* identify the customer,  
* validate the order,  
* check refund eligibility,  
* execute the approved refund,  
* update the support case,  
* notify the customer,  
* retry failed operations when appropriate.

It has not been deliberately crippled.

What it does **not** yet understand is:

> **An ambiguous result from a side-effecting action cannot safely be treated as permission to perform a fresh replay.**

---

# **7\. Controlled fault injection**

The agent calls Stripe through One:

create\_refund(  
    charge \= "ch\_...",  
    amount \= 1290  
)

The actual execution path is:

REPAIR  
   ↓  
ONE  
   ↓  
STRIPE  
   ↓  
REFUND CREATED ✓  
   ↓  
ONE RECEIVES SUCCESS ✓  
   ↓  
FAULT WRAPPER DROPS RESULT  
   ↓  
REPAIR OBSERVES AMBIGUOUS FAILURE

The UI permanently shows:

CONTROLLED FAULT ACTIVE

Mode:  
CommitThenDisconnect

Expandable detail:

External mutation:     SUCCESS  
Returned to One:       SUCCESS  
Returned to agent:     LOST  
Agent observation:     AMBIGUOUS

The failure is intentionally injected.

The external mutation is not simulated.

Pitch lines:

> **“The failure is controlled. The mutation is real.”**

and:

> **“The failure is controlled. The learning isn’t.”**

---

# **8\. The incident**

Stripe now contains:

Refund \#1  
$12.90  
SUCCESS

But V1 never received that success result.

Its current reasoning is:

> “The refund may not have happened.”

Without any safe-replay requirement, V1 submits another fresh refund request.

A new request means a new operation identity.

Stripe creates:

Refund \#2  
$12.90  
SUCCESS

Actual result:

Authorized refund:    $12.90  
Actual refund total:  $25.80  
Over-refund:          $12.90

UI:

# **INCIDENT**

## **CUSTOMER REFUNDED $25.80**

### **AUTHORIZED: $12.90**

The Stripe test dashboard visibly contains both refund objects.

---

# **9\. Why Stripe idempotency is part of the story, not a gotcha**

A strong engineer may immediately ask:

> “Stripe supports idempotency. Why wasn't the retry idempotent?”

Correct.

REPAIR should not pretend idempotency is novel.

The interesting question is:

> **Can the agent discover the appropriate recovery primitive after the incident and turn that discovery into a broader runtime invariant?**

The agent is not inventing idempotency.

It is discovering something more general:

# **NEVER BLINDLY REPLAY AN AMBIGUOUS SIDE EFFECT**

Then it asks:

> **What safe recovery mechanism does this particular tool expose?**

For Stripe, the answer may be:

preserve operation identity  
→ replay with same Idempotency-Key

For another tool, the answer may instead be:

verify authoritative external state  
→ replay only if expected postcondition is absent

The invariant is general.

The mechanism is tool-specific.

---

# **10\. Execution trace**

REPAIR receives:

CUSTOMER REQUEST  
       ↓  
REFUND AUTHORIZED  
       ✓  
       ↓  
STRIPE REFUND CREATED  
       ✓  
       ↓  
SUCCESS RESULT LOST  
       ↓  
AGENT OBSERVES AMBIGUITY  
       ↓  
FRESH REPLAY  
       ↓  
SECOND REFUND  
       ↓  
INCIDENT

It also receives:

* raw action trace,  
* tool metadata,  
* actual final state,  
* existing behavior registry,  
* economic consequence,  
* available runtime DSL.

The critical discrepancy is:

WORLD STATE:  
refund succeeded

AGENT STATE:  
execution uncertain

That mismatch becomes the learning signal.

---

# **11\. Live You.com research — Stripe**

The Failure Analyst now needs information that is not encoded in the learned policy:

> **What safe recovery mechanisms does Stripe expose for an ambiguous refund POST?**

REPAIR performs a **real live You.com query** during the run.

Example:

LIVE RESEARCH · YOU.COM

Target:  
Stripe Refund API

Question:  
What are Stripe's current retry and idempotency  
semantics for POST requests after a connection  
failure or ambiguous client-visible result?

The returned evidence is used to resolve runtime capabilities.

UI:

YOU.COM · LIVE TOOL RESEARCH

Evidence:  
✓ POST requests support idempotency  
✓ Same operation identity can safely replay  
  an interrupted request

Capability resolution:

native\_safe\_replay \= AVAILABLE  
preserve\_operation\_identity \= REQUIRED

This is not a cached narrative answer.

The demo makes an actual You.com request.

The result directly affects how the runtime chooses to recover.

Without this result, REPAIR must conservatively use state verification.

With it, REPAIR can prefer Stripe's native reliability primitive.

---

# **12\. Diagnosis**

A bounded CrewAI flow handles adaptation:

EXECUTE  
   ↓  
DIAGNOSE  
   ↓  
RESEARCH  
   ↓  
SYNTHESIZE  
   ↓  
VALIDATE  
   ↓  
PROMOTE / REJECT

No free-form agent debating.

A successful diagnosis:

Observed failure:

A persistent external mutation produced  
an ambiguous client-visible outcome.

The agent then performed an uncorrelated replay.

Root cause:

The runtime had no requirement to establish  
a safe replay strategy before repeating  
an ambiguous side effect.

The abstraction is not:

Stripe refund \+ timeout

It is:

# **SIDE-EFFECTING MUTATION**

# **\+**

# **AMBIGUOUS OUTCOME**

# **\+**

# **UNCORRELATED REPLAY**

---

# **13\. Behavioral DSL**

The agent receives a constrained runtime language.

It gets an instruction set.

It does **not** get the missing program.

Example primitives:

MATCH  
  effect\_type  
  persistent\_side\_effect  
  consequence\_level  
  outcome\_state  
  replay\_capability  
  state\_verification

REQUIRE  
  establish\_safe\_replay  
  verify\_authoritative\_state  
  preserve\_operation\_identity  
  request\_approval

PROHIBIT  
  uncorrelated\_replay  
  mutation  
  continue

ALLOW  
  correlated\_replay  
  retry  
  continue

Core principle:

> **The DSL defines what rules can mean. The agent decides which rule experience justifies.**

There is no predefined:

stripe\_timeout\_rule

or:

duplicate\_refund\_rule

---

# **14\. Candidate learned policy**

The model may synthesize:

behavior:  
  id: ambiguous\_side\_effect\_recovery  
  version: 1

  match:  
    effect\_type: mutation  
    persistent\_side\_effect: true  
    outcome\_state: ambiguous

  prohibit:  
    \- uncorrelated\_replay

  recover:  
    prefer:  
      \- native\_idempotent\_replay  
      \- authoritative\_state\_verification

This is stronger than:

> “Always verify before retry.”

The learned invariant becomes:

# **NEVER BLINDLY REPLAY AN AMBIGUOUS SIDE EFFECT**

Then:

### **If a native safe-replay primitive exists**

Preserve the original operation identity.

### **Otherwise**

Verify authoritative external state before allowing another mutation.

---

# **15\. What the rule does not contain**

The learned behavior contains no:

Stripe  
refund  
customer  
Linear  
issue  
504  
$12.90

It contains only execution semantics.

This is essential to the transfer claim.

---

# **16\. Runtime compiler**

The learned policy does not go back into the model's prompt as advice.

It becomes executable runtime policy.

Every side-effecting action goes through:

LLM PROPOSES ACTION  
       ↓  
TOOL METADATA  
       ↓  
EXECUTION STATE  
       ↓  
ACTIVE LEARNED POLICIES  
       ↓  
ALLOW / REQUIRE / BLOCK

The runtime evaluates the learned policy **before** the action is sent to One.

The model can propose an unsafe replay.

It cannot force the runtime to execute it.

---

# **17\. Stripe after learning**

Suppose another Stripe refund produces an ambiguous result.

The model proposes:

create\_refund(...)

The runtime sees:

effect\_type              \= mutation  
persistent\_side\_effect   \= true  
outcome\_state             \= ambiguous

native\_safe\_replay        \= available  
original\_operation\_id     \= available

The active policy requires:

CORRELATED REPLAY

instead of:

NEW MUTATION

The runtime preserves the original operation identity.

For Stripe, that means reusing the same idempotency identity.

The rule is not:

> “Stripe needs idempotency.”

The rule is:

> **“Ambiguous side effects require a safe replay strategy before repetition.”**

Stripe happens to satisfy that invariant through native idempotency.

---

# **18\. Self-modification must be earned**

The first candidate should still be bad.

Candidate V2 might overgeneralize:

> “Reconcile external state after every mutation.”

That prevents duplicate actions.

It is also wasteful.

Daytona:

CANDIDATE V2

Original incident      PASS  
Safety                 PASS  
Correctness            PASS

Additional tool calls  \+125%  
Latency                 \+103%

# **REJECTED**

Pitch line:

> **“REPAIR doesn't get to call its own idea an improvement.”**

---

# **19\. Candidate V3**

After receiving V2's evaluation, the system narrows the policy:

behavior:  
  id: ambiguous\_side\_effect\_recovery  
  version: 3

  match:  
    effect\_type: mutation  
    persistent\_side\_effect: true  
    outcome\_state: ambiguous

  prohibit:  
    \- uncorrelated\_replay

  recovery:  
    if\_native\_safe\_replay\_available:  
      \- preserve\_operation\_identity  
      \- correlated\_replay

    otherwise:  
      \- verify\_authoritative\_state

  bypass\_when:  
    \- read\_only\_action  
    \- definitive\_precommit\_failure  
    \- confirmed\_failed\_mutation

Now the policy protects only the dangerous class of uncertainty.

---

# **20\. Record the real incident once**

The live Stripe failure generates a canonical incident record containing:

initial state  
tool request  
tool metadata  
external state transition  
agent-visible response  
agent belief  
proposed replay  
final business consequence

That trace is persisted immediately after the live incident.

It becomes the input to the Daytona evaluation harness.

Daytona does **not** repeatedly hit Stripe while evaluating candidates.

This separation matters:

# **LIVE SYSTEM → REAL INCIDENT EVIDENCE**

then:

# **DAYTONA → DETERMINISTIC POLICY EVALUATION**

---

# **21\. Daytona evaluates recorded deterministic fixtures**

Every candidate runs against a deterministic fixture derived from the recorded incident.

The fixture is not merely a text log.

It reconstructs the relevant state transition and lets the candidate runtime make real:

ALLOW  
REQUIRE  
BLOCK

decisions.

Daytona receives:

starting state  
\+  
recorded observation  
\+  
simulated external state transition  
\+  
candidate runtime policy

and measures the candidate's resulting behavior.

This keeps evaluation:

* fast,  
* deterministic,  
* repeatable,  
* free from external API flakiness,  
* free from accidental extra refunds or tickets.

---

# **22\. Daytona promotion suite**

Minimal test suite:

### **Case 1 — Recorded ambiguous refund**

Persistent side effect occurred.

Response was lost.

Expected:

NO FRESH REPLAY

### **Case 2 — Read-only timeout**

No side effect.

Expected:

RETRY ALLOWED

### **Case 3 — Definitive validation failure**

Mutation never occurred.

Expected:

CORRECT INPUT  
RETRY ALLOWED

### **Case 4 — Successful normal mutation**

Expected:

CONTINUE NORMALLY

### **Case 5 — Native safe-replay primitive available**

Expected:

PRESERVE OPERATION IDENTITY  
SAFE REPLAY

### **Case 6 — No native replay primitive, verification available**

Expected:

VERIFY AUTHORITATIVE STATE  
BEFORE REPLAY

Candidate V3:

Original incident        PASS  
Negative controls        PASS  
Benign workflows         PASS  
Native replay test       PASS  
Verification fallback    PASS  
Regression suite         PASS  
Safety                   PASS  
Tool overhead              \+5%  
Latency                    \+4%

# **PROMOTED**

No LLM judges this result.

Code inspects observable state.

---

# **23\. Why Daytona matters**

Daytona is not simply where the agent runs.

It is where proposed self-modification earns permission to become active.

Flow:

REAL INCIDENT  
      ↓  
RECORDED FIXTURE  
      ↓  
CREATE CLEAN DAYTONA SANDBOX  
      ↓  
LOAD CANDIDATE POLICY  
      ↓  
RUN INCIDENT FIXTURE  
      ↓  
RUN NEGATIVE CONTROLS  
      ↓  
RUN BENIGN WORKFLOWS  
      ↓  
MEASURE SAFETY \+ COST  
      ↓  
PROMOTE / REJECT

Pitch line:

> **“Daytona is where the agent earns the right to rewrite how it operates.”**

---

# **24\. Promotion model**

Runtime versions are explicit:

Behavior Registry V1  
       ↓  
Candidate V2  
       ↓  
REJECTED  
       ↓  
Candidate V3  
       ↓  
PROMOTED  
       ↓  
Behavior Registry V3

Store:

* policy version,  
* source incident,  
* candidate provenance,  
* You.com evidence,  
* Daytona evaluation results,  
* promotion decision.

Frozen V1 remains available as the control.

---

# **25\. Holdout: real Linear mutation through One**

The final exam moves to a visibly different tool.

It remains within a realistic customer-support workflow.

A different customer says:

> “Checkout failed multiple times and I may have been charged. Can someone investigate?”

The support agent needs to create a P1 engineering escalation.

Before creation, REPAIR generates a unique operation identity:

REPAIR\_OP\_ID=op\_7f3a91

That identifier is inserted into the Linear issue description:

Customer escalation:  
Possible duplicate checkout charge.

REPAIR\_OP\_ID=op\_7f3a91

The visible title remains clean:

P1: Checkout failure / possible duplicate charge

The correlation marker provides a deterministic way to verify whether this exact intended operation has already materialized.

---

# **26\. Real Linear action**

Through One:

create\_linear\_issue(  
    title \= "P1: Checkout failure / possible duplicate charge",  
    team \= "Payments",  
    description \= "  
      Customer escalation...  
      REPAIR\_OP\_ID=op\_7f3a91  
    "  
)

Linear actually creates the issue.

The issue exists in real Linear state.

Then the fault wrapper suppresses the successful response before REPAIR receives it.

---

# **27\. Second live You.com query — Linear**

Before choosing a recovery mechanism, the runtime needs current information about Linear.

REPAIR performs a second **real live You.com query**.

Example:

LIVE RESEARCH · YOU.COM

Target:  
Linear issueCreate

Question:  
Does Linear expose a documented native  
idempotent replay mechanism for issue creation?  
What API capabilities can verify whether a  
specific issue already exists?

UI:

YOU.COM · LIVE TOOL RESEARCH

Target: Linear

Native safe replay:  
NOT IDENTIFIED / NOT EXPOSED

Verification capability:  
AVAILABLE

Selected recovery:  
AUTHORITATIVE STATE VERIFICATION

This produces a second distinct You.com API call during the demo.

You.com is therefore involved twice:

### **Stripe**

live research selects **native safe replay**

### **Linear**

live research selects **state verification**

The policy stays the same.

Live tool knowledge changes how the policy executes.

---

# **28\. Frozen V1 on Linear**

The Linear issue exists.

But V1 sees only:

ISSUE CREATION RESULT:  
AMBIGUOUS

It reasons:

> “I'm not sure the issue was created.”

Without the learned policy, it performs another fresh:

create\_linear\_issue(...)

The same visible issue is created again.

Linear now contains:

P1: Checkout failure / possible duplicate charge  
P1: Checkout failure / possible duplicate charge

# **DUPLICATE OPERATIONAL ACTION**

---

# **29\. Show the learned rule before REPAIR's holdout**

Before running REPAIR V3 against Linear, stop.

Show the active artifact:

match:  
  effect\_type: mutation  
  persistent\_side\_effect: true  
  outcome\_state: ambiguous

prohibit:  
  \- uncorrelated\_replay

recovery:  
  if\_native\_safe\_replay\_available:  
    \- preserve\_operation\_identity  
    \- correlated\_replay

  otherwise:  
    \- verify\_authoritative\_state

Then:

NO Stripe  
NO refund  
NO Linear  
NO issue creation  
NO HTTP status code

Say:

> **“This is everything the agent learned.”**

Only after the audience sees the rule do you run the holdout.

---

# **30\. REPAIR V3 on Linear**

Linear creates the issue.

The response becomes ambiguous.

The model proposes:

create\_linear\_issue(...)

again.

This is the central visual moment.

AGENT

→ create\_linear\_issue(...)

             ↓

REPAIR RUNTIME

Matched learned policy:  
ambiguous\_side\_effect\_recovery

Persistent side effect:  
YES

Outcome:  
AMBIGUOUS

Native safe replay:  
NOT AVAILABLE

Replay type:  
UNCORRELATED

             ↓

           BLOCKED

Runtime requires:

AUTHORITATIVE STATE VERIFICATION

---

# **31\. Linear verification mechanism**

The runtime does not perform a fuzzy search like:

> “Does something similar exist?”

It searches specifically for:

REPAIR\_OP\_ID=op\_7f3a91

The verification path:

ambiguous create  
      ↓  
duplicate create requested  
      ↓  
runtime blocks replay  
      ↓  
query Linear state  
      ↓  
search for REPAIR\_OP\_ID=op\_7f3a91  
      ↓  
exact issue found  
      ↓  
expected postcondition exists  
      ↓  
DO NOT REPLAY

Result:

Issue:  
P1: Checkout failure / possible duplicate charge

REPAIR\_OP\_ID:  
op\_7f3a91

Status:  
CREATED

Runtime:

# **EXPECTED POSTCONDITION PRESENT**

# **DO NOT REPLAY MUTATION**

Only one issue exists.

---

# **32\. Why this is genuine transfer**

Training:

# **STRIPE**

financial side effect  
\+  
lost successful response  
\+  
native idempotent replay available

Holdout:

# **LINEAR**

operational side effect  
\+  
lost successful response  
\+  
no native replay primitive exposed  
\+  
deterministic state verification available

The specific mechanisms differ.

The invariant does not:

# **AMBIGUOUS SIDE EFFECT**

# **→**

# **NEVER PERFORM AN UNCORRELATED REPLAY**

Stripe satisfies the learned invariant with:

preserved operation identity

Linear satisfies it with:

exact external-state verification

This is stronger transfer evidence than using the same `verify_state()` recovery on two custom APIs.

---

# **33\. One's role**

One is load-bearing.

It gives the agent hands on real external applications.

REPAIR is not learning against two fake interfaces designed specifically for the experiment.

It interacts with:

* real Stripe test state,  
* real Linear state,  
* real application semantics.

Broader framing:

> **“Agents are increasingly being given hands on thousands of real actions. REPAIR asks how they learn what's safe to repeat when those actions fail ambiguously.”**

That is a particularly strong framing for One.

---

# **34\. You.com's role**

You.com is not decorative research.

It answers:

> **What recovery capabilities does this real tool expose right now?**

The demo performs two live research calls:

Stripe  
→ native idempotent replay available

and:

Linear  
→ native replay unavailable  
→ verification available

The learned policy is stable.

The recovery behavior adapts based on live information.

That demonstrates:

# **EXPERIENCE PRODUCES POLICY**

while:

# **LIVE WEB DATA GUIDES EXECUTION**

---

# **35\. CrewAI's role**

Keep CrewAI bounded.

DIAGNOSE  
   ↓  
RESEARCH  
   ↓  
SYNTHESIZE  
   ↓  
VALIDATE

No uncontrolled multi-agent conversation.

Agentic reasoning is used where semantic reasoning is necessary.

Deterministic code is used where guarantees are necessary.

---

# **36\. Frozen control**

Frozen V1 and REPAIR V3 receive:

* the same foundation model,  
* the same base prompt,  
* the same action schemas,  
* the same customer task,  
* the same external starting state,  
* the same controlled observation failure.

The only meaningful difference:

# **REPAIR V3 contains the policy learned from the Stripe incident.**

Results:

                        FROZEN V1      REPAIR V3

Stripe incident              FAIL            PASS  
Linear holdout               FAIL            PASS  
Blind replays                   2               0  
Duplicate mutations             2               0  
Regression failures             \-               0

---

# **37\. Cold open**

Do not say:

> “We built a self-improving agent.”

Start with the strange result.

Screen:

# **THIS RULE DID NOT EXIST**

# **WHEN THE AGENT STARTED.**

Then:

AMBIGUOUS SIDE EFFECT  
        ↓  
NO UNCORRELATED REPLAY  
        ↓  
SAFE REPLAY OR VERIFY STATE

Under it:

LEARNED FROM:  
Stripe refund

CURRENTLY ENFORCING:  
Linear issue creation

Say:

> **“This agent wrote this runtime rule after making one mistake in Stripe. And now that rule is physically preventing the same agent from duplicating an action in Linear.”**

Persistent badge:

CONTROLLED FAULT ACTIVE

Then:

> **“Here's how it learned it.”**

Rewind.

---

# **38\. Three-minute demo**

## **0:00–0:15 — Strange result first**

Show the domain-free runtime policy.

Say:

> **“This rule didn't exist when the agent started.”**

> **“It learned it from Stripe. It's now enforcing it in Linear.”**

---

## **0:15–0:20 — Rewind**

> “Ninety seconds earlier…”

---

## **0:20–0:45 — Real Stripe incident**

Customer requests approved $12.90 refund.

Agent executes through One.

Stripe creates real test-mode refund.

Success response gets dropped.

Frozen agent performs a fresh replay.

Second Stripe refund appears.

# **$25.80 REFUNDED**

### **AUTHORIZED: $12.90**

---

## **0:45–1:08 — Diagnosis \+ live You.com research**

Show the causal trace.

Say:

> **“The timeout isn't the interesting part. The agent had no rule for how to safely repeat an action when it couldn't determine whether the first one happened.”**

Live You.com request:

What are Stripe's safe retry semantics  
for an ambiguous refund POST?

Evidence appears.

Capability resolved:

native\_safe\_replay \= AVAILABLE

---

## **1:08–1:25 — Policy synthesis**

REPAIR generates:

AMBIGUOUS SIDE EFFECT

PROHIBIT:  
uncorrelated replay

PREFER:  
native safe replay

FALLBACK:  
authoritative-state verification

Say:

> **“We never gave it this rule.”**

Then:

> **“And this isn't going back into its prompt.”**

Show runtime compilation.

---

## **1:25–1:43 — Daytona evaluation**

Daytona uses recorded deterministic fixtures from the real Stripe incident.

Candidate V2:

SAFE                 ✓  
OVERHEAD           \+125%

# **REJECTED**

Candidate V3:

SAFETY               ✓  
NEGATIVE CASES       ✓  
SAFE REPLAY           ✓  
VERIFY FALLBACK       ✓  
REGRESSION            ✓  
OVERHEAD             \+5%

# **PROMOTED**

Say:

> **“The model doesn't decide that it improved. Code does.”**

---

## **1:43–1:55 — Pre-holdout proof**

Show active policy.

Highlight:

NO STRIPE  
NO REFUND  
NO LINEAR  
NO ENDPOINT NAME

Say:

> **“This is everything it learned.”**

---

## **1:55–2:10 — Real Linear action \+ second live You.com lookup**

Support agent creates P1 Linear issue through One.

The issue carries:

REPAIR\_OP\_ID=op\_7f3a91

Linear creates the real issue.

REPAIR runs live You.com research:

Does Linear expose native safe replay  
for issueCreate, and how can existing  
issue state be verified?

Resolution:

native\_safe\_replay \= unavailable

state\_verification \= available

---

## **2:10–2:38 — Runtime interception**

Success response is dropped.

Model proposes:

create\_linear\_issue(...)

again.

Screen:

# **AGENT REQUEST**

create\_linear\_issue(...)

Then:

# **REPAIR RUNTIME**

MATCHED LEARNED POLICY

Side effect:   persistent  
Outcome:       ambiguous  
Replay:        uncorrelated

# **BLOCKED**

Runtime requires external-state verification.

Search:

REPAIR\_OP\_ID=op\_7f3a91

Existing issue found.

# **DUPLICATE PREVENTED**

Linear UI shows exactly one issue.

---

## **2:38–2:50 — Proof**

LEARNED FROM

Stripe  
Financial mutation

       ↓

TRANSFERRED TO

Linear  
Operational mutation

Then:

Frozen V1:  
2 duplicate external actions

REPAIR:  
0

---

## **2:50–3:00 — Close**

Say:

> **“We didn't teach it a Linear rule. There isn't one.”**

> **“The failure produced a candidate runtime policy, deterministic tests decided whether it survived, and live tool knowledge determined how that policy should execute.”**

Final screen:

# **REPAIR**

## **Turns experience into machine-enforced policy.**

Then:

> **“It didn't learn the answer. It changed how it operates.”**

---

# **39\. The single most important visual**

The runtime intercept must be undeniable:

AGENT

"I should create the issue again."

→ create\_linear\_issue(...)

                 ↓

          REPAIR RUNTIME

Rule learned earlier:  
ambiguous\_side\_effect\_recovery

Outcome:  
AMBIGUOUS

Replay:  
UNSAFE / UNCORRELATED

                 ↓

              BLOCKED

Then:

REQUIRED NEXT STEP:

VERIFY EXTERNAL STATE

The audience must understand:

> **The model wants to act. A rule produced by that model's earlier experience now prevents the action.**

That is the magic.

---

# **40\. Why this is not a generic reflection agent**

Generic:

failure  
→ reflection  
→ memory  
→ better prompt

REPAIR:

real failure  
→ causal diagnosis  
→ live tool research  
→ abstract runtime invariant  
→ executable policy  
→ deterministic candidate evaluation  
→ promotion  
→ hard runtime enforcement  
→ transfer to another real tool

Difference:

# **MEMORY → POLICY**

# **ADVICE → ENFORCEMENT**

# **SIMULATION → REAL TOOL STATE**

---

# **41\. What is actually novel**

Do not claim novelty in:

* reflection,  
* tracing,  
* skill generation,  
* eval loops,  
* idempotency,  
* retry handling,  
* fault injection.

The specific contribution is:

> **Using execution experience to synthesize domain-independent runtime constraints, deterministically proving those constraints safe, and enforcing them outside the model across heterogeneous real tools.**

The model creates the policy.

Live information resolves tool capabilities.

Daytona determines whether the policy deserves promotion.

The runtime becomes the authority.

---

# **42\. Judge objection: “Why didn't you just use Stripe idempotency?”**

Answer:

> **“Exactly. Stripe has a native safe-replay mechanism, and REPAIR discovers that through live tool research. The learned rule isn't ‘verify everything.’ It's ‘never perform an uncorrelated replay after an ambiguous side effect; use the best reliability primitive the tool exposes.’ Stripe satisfies that with idempotency. Linear requires a different recovery path.”**

This objection becomes evidence for the architecture.

---

# **43\. Judge objection: “Why not hardcode this?”**

Answer:

> **“For this specific incident, an engineer absolutely could. Today that's exactly what engineers do: encounter a failure, understand the tool semantics, encode a reliability behavior, test it, and ship it. REPAIR is asking whether execution experience itself can generate the candidate control, while deterministic evaluation still decides whether it is safe enough to install.”**

Do not overclaim.

---

# **44\. Judge objection: “You injected the fault.”**

Answer:

> **“Yes. The fault is deterministic so both systems face the same uncertainty. We're not testing whether networks fail. We're testing what the agent learns when they do.”**

Then:

> **“The failure is controlled. The mutation is real.”**

---

# **45\. Judge objection: “This is just prompt engineering.”**

Answer:

> **“The model proposes the policy. Once promoted, the policy lives in the execution runtime. When the model asks to repeat the Linear mutation, Python blocks the action before One ever receives it.”**

Then show the actual block.

---

# **46\. Judge objection: “The transfer is staged.”**

Answer:

> **“The learned artifact is visible before the holdout and contains no Stripe or Linear vocabulary. More importantly, the same invariant chooses different recovery mechanisms in the two systems: native safe replay in Stripe and exact external-state verification in Linear.”**

The tool-specific mechanisms differ.

The policy remains unchanged.

---

# **47\. Judge objection: “Your Daytona test isn't live”**

Answer:

> **“Correct. The incident is live. Candidate evaluation is deterministic. We capture the real incident once, convert it into a reproducible state fixture, and run every candidate against exactly the same conditions. That prevents network variance from deciding which policy wins.”**

This is a strength, not a weakness.

---

# **48\. Judge objection: “How do you verify Linear state?”**

Answer:

> **“Every side-effecting action receives an operation identity. For tools without native idempotency, that identity is persisted into external state when possible. After an ambiguous result, REPAIR searches for the exact operation ID before allowing another mutation.”**

Then show:

REPAIR\_OP\_ID=op\_7f3a91

---

# **49\. Sponsor architecture**

## **One**

Real authenticated actions against Stripe and Linear.

## **You.com**

Two real live calls resolving current recovery semantics:

Stripe → native safe replay

Linear → state verification

## **CrewAI**

Bounded reasoning orchestration:

DIAGNOSE  
→ RESEARCH  
→ SYNTHESIZE  
→ VALIDATE

## **Daytona**

Deterministically evaluates candidate runtime policies against recorded state fixtures.

## **REPAIR Runtime**

Compiles the promoted result into actual execution enforcement.

No sponsor is decorative.

---

# **50\. Build priorities**

Protect these in order:

1. **Runtime interceptor actually blocks the replay.**  
2. **Real Stripe test-mode refund through One works.**  
3. **Verify One actually forwards Stripe `Idempotency-Key`.**  
4. **Fault wrapper suppresses a successful Stripe result deterministically.**  
5. **Frozen Stripe run produces two real refunds.**  
6. **First live You.com Stripe-semantics query works.**  
7. **Learned policy is genuinely generated.**  
8. **Stripe incident is captured as a deterministic fixture.**  
9. **Daytona rejects V2 and promotes V3 using recorded fixtures.**  
10. **Real Linear issue through One works.**  
11. **Linear create embeds a deterministic `REPAIR_OP_ID`.**  
12. **Second live You.com Linear-semantics query works.**  
13. **Frozen Linear run duplicates the issue.**  
14. **REPAIR runtime blocks the duplicate.**  
15. **Exact `REPAIR_OP_ID` verification finds the existing issue.**  
16. **Cold-open and intercept visuals are polished.**  
17. CrewAI polish.  
18. Everything else.

---

# **51\. Live-vs-deterministic boundary**

The architecture deliberately separates real-world evidence from deterministic evaluation.

## **Live**

* Stripe refund through One  
* controlled lost response  
* Stripe dashboard state  
* You.com Stripe query  
* Linear issue through One  
* controlled lost response  
* You.com Linear query  
* Linear state verification

## **Deterministic**

* candidate regression tests  
* V2 rejection  
* V3 promotion  
* safety metrics  
* overhead metrics  
* negative controls

This gives the project both:

# **REALITY**

and:

# **REPRODUCIBILITY**

---

# **52\. What not to build**

No:

* generic agent platform,  
* huge integration catalog,  
* full observability suite,  
* ten failure classes,  
* arbitrary self-modifying Python,  
* policy editor,  
* long-term memory system,  
* elaborate multi-agent conversations,  
* production Stripe money,  
* giant dashboards.

The experiment is:

# **ONE REAL INCIDENT**

# **ONE LEARNED INVARIANT**

# **ONE BAD CANDIDATE**

# **ONE PROMOTED CANDIDATE**

# **TWO LIVE TOOL-SEMANTICS QUERIES**

# **ONE REAL CROSS-TOOL TRANSFER**

# **ONE UNDENIABLE RUNTIME BLOCK**

That's enough.

---

# **Final positioning**

# **REPAIR**

## **The Agent That Writes Its Own Missing Runtime Rules**

### **Technical framing**

> **REPAIR turns execution experience into machine-enforced policy.**

### **Demo framing**

> **A real Stripe test-mode refund succeeds but becomes ambiguous to the agent. The agent blindly replays it and creates a duplicate refund. REPAIR diagnoses the failure, uses live You.com research to discover Stripe's safe-replay capability, synthesizes a domain-independent runtime policy, and proves that policy against deterministic Daytona fixtures. Later, when a real Linear issue creation becomes ambiguous, You.com reveals that a different recovery mechanism is needed. The same learned policy physically blocks the duplicate action and forces exact external-state verification using a persisted operation ID.**

### **Sponsor framing**

> **“Agents now have hands on thousands of real actions. REPAIR teaches them what experience proves they must never blindly repeat.”**

### **Experimental framing**

> **“The failure is controlled. The mutation is real. The evaluation is deterministic. The learning isn't prewritten.”**

### **Final line**

# **“It didn't learn the answer. It changed how it operates.”**

