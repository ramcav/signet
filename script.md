Signet — Presentation Script
Target: ~13 minutes spoken + 2 minutes demo
Audience: Course jury + a web3 VC guest
Goal: Make the problem and market clear. Show we've built something real. Be ready for VC questions without leading with the raise.

How to use this
Each slide has two parts:

Say this — roughly. Don't memorise, internalise.
If asked — answers to have ready.

Italicised lines are the ones to slow down on.

§00 — Cover (15s)

Hi everyone. We're the Signet team — Juan Diego, Vako, Mattia, Ricardo, and Rawad. Over the next fifteen minutes we'll walk you through a problem we think is about to get much bigger, and what we've built for it.


§01 — The regulatory window (60s)

The problem starts with a clock. Three EU regulations land in the next eighteen months.
July 2026 — MiCA grandfathering expires. Every crypto service provider in Europe has to be fully compliant.
August 2026 — the EU AI Act kicks in for high-risk systems. This is the one that requires meaningful human oversight of AI making decisions that affect people.
December 2026 — the new Product Liability Directive makes AI systems legally "products." If an AI system causes harm, the company that deployed it is liable — and the burden of proof is on them to show they took reasonable care.
These three dates are real, they're fixed, and a lot of companies are not ready.

If asked:

Is the AI Act really coming in August? Yes — it's in the official text. Deadline is binding.


§02 — What's already breaking (60s)

Here's what the problem looks like today.
Freysa — November 2024. A public challenge: an autonomous AI agent holding a prize pool of real money, instructed never to release it. Anyone could pay to send it a message and try to break it. After hundreds of failed attempts, someone crafted an injection that convinced it to transfer the pool — forty-seven thousand dollars — out. The "game" was designed to prove a point, and it did: a motivated attacker will eventually talk an LLM into anything.
AIXBT — 2025. Another AI trading agent. Same pattern. A hundred thousand dollars.
Step Finance — January this year, on Solana. Attackers compromised devices belonging to the team's executives. That alone would have been bad — but the real damage came from the platform's AI trading agents: they had excessive permissions and no isolation, so once the attackers had a foothold, the agents executed the drain at machine speed. Forty million dollars. The AI agents didn't get jailbroken — they were just handed too many keys.
This isn't theoretical. OpenAI themselves admitted last December that prompt injection is unlikely to ever be fully solved. Meaning — you can't trust the AI to refuse bad instructions. You have to build a system where even if the AI gets fooled, nothing bad actually happens.


§03 — Why existing tools don't fit (45s)

The regulations say: you need human oversight, audit trails, and a "stop button" for AI systems.
But the current tools don't cover this. Analytics vendors like Chainalysis look at transactions after they happen. Custodians like Fireblocks have pre-trade controls but for humans, not AI agents. AI governance tools like Guardrails check what the AI says, not what it actually does with money.
Nobody is enforcing compliance at the moment money moves, for AI agents specifically. That's the gap.


§04 — The insight (30s — slow down)

So here's our idea.
Software middleware can be jailbroken. Cryptography cannot.
Instead of trying to make the AI better at saying no, we make it cryptographically impossible for the AI to send a transaction without being checked first. The rules are enforced by the blockchain itself — not by the AI, not by some software the AI could bypass.


§05 — How it works (75s)

Here's the architecture.
Left side — the AI agent. It has half of the key needed to send a transaction. Treat it as untrusted, because it can be jailbroken.
Right side — what we call the policy engine. It holds the other half of the key. It runs inside a secure enclave — like a black box the AI can't touch. It checks every transaction against a set of rules: how much, to whom, what asset, is the destination on the allowlist, does it pass sanctions checks.
Bottom — XRPL. Because of how XRPL's multi-signature works natively, both halves of the key are required. If the policy engine says no, there's no second signature, and the blockchain refuses to settle the transaction.
It's not a smart contract we have to maintain. It's not middleware. It's the protocol itself.

If asked:

Why XRPL and not Ethereum? On Ethereum we'd have to deploy a smart contract — $5-50 per transaction in gas, plus audit burden. XRPL has this as a native feature: no contract, sub-cent fees, rules enforced by the protocol.


§06 — A transaction, end to end (60s)

Quick walk-through. Six steps.
One — the AI proposes what it wants to do, in a structured format.
Two — the policy engine checks the rules.
Three — it decides: allow, deny, or escalate to a human.
Four — if allowed, it signs, inside the secure enclave.
Five — the transaction goes to XRPL, which enforces the two-signature requirement.
Six — a cryptographic summary of the AI's reasoning gets attached, so regulators can audit what the AI was thinking.
Every step produces something auditable. Compliance becomes automatic and verifiable.


§07 — Why XRPL, and why now (60s)

Why XRPL specifically? Four features we need, all live on mainnet:
Native multi-signature — been around for years. Rock solid.
Credentials — on-ledger identity attestations. Shipped September 2025.
Permissioned Domains — lets you control which accounts can transact with each other. Shipped February this year — literally two months ago.
And sub-cent fees, which matter because AI agents make a lot of transactions.
No other major blockchain has all four of these live today. That's why this product category didn't exist a year ago.


§08 — The audit trail (45s)

One more technical piece. Every decision the AI makes — the prompt it got, what it was thinking, what tools it used, what it decided — gets hashed into a cryptographic fingerprint that goes on the blockchain.
The full reasoning stays off-chain, encrypted. When a regulator asks "what was your AI doing on March 15th," we can prove exactly what happened — without exposing our trading strategy or customer data.
This turns compliance from a cost into a defence. If something goes wrong, the company has cryptographic proof they exercised reasonable care — exactly what the new Product Liability Directive requires.


§09 — The market (60s)
Cue: Alex explicitly asked for market sizing. Slow down here.

How big is this market?
The broadest number — AI in financial services — is projected to grow from $38 billion today to $190 billion by 2030. Compliance automation is the fastest-growing piece of it.
Closer in — blockchain-specific RegTech — $7 billion growing to $30 billion by 2030.
And the most concrete number — our actual addressable customers — $982 billion in assets under management across 122 institutional crypto funds. 55% of traditional hedge funds now have crypto exposure, up from 29% in 2022. And roughly 102 crypto service providers in Europe are all hitting these new rules simultaneously.
We're not chasing everyone with crypto exposure. We're targeting the institutional players who legally cannot operate without this kind of infrastructure by 2027.

If asked:

Who specifically is the first customer? A MiCA-authorised crypto service provider running AI-driven trading. There are about 14 in the EU with full trading authorisation — concentrated in Germany, the Netherlands, and Malta. That's our beachhead.


§10 — Who we're competing with (45s)

Five categories already play nearby.
Blockchain analytics does post-trade monitoring. MPC custodians do pre-trade policy, but for humans. TradFi compliance tools don't work with crypto. Agentic wallets exist but mostly on Ethereum and Solana, not XRPL, and they don't integrate sanctions checks. AI governance tools operate on prompts, not transactions.
Nobody sits in the middle of all five. That's where we are.


§11 — How we'd go to market (30s)
Cue: Light touch — this is a course presentation, not a Series A. Don't linger.

Quick note on go-to-market.
We'd price as infrastructure — not per-seat like analytics tools. Distribution through the XRPL Accelerator (which Ripple runs with Tenity), Outlier Ventures' agentic-internet program, and Ripple's own enterprise channel — which already serves Citi, BBVA, HSBC, SocGen, and DBS.
The channels that reach the customers we want already exist. We just need to be in them.


§12 — How it maps to the regulations (60s)
Cue: This is the 10% compliance grade. Do it carefully.

Let me close the compliance loop.
MiCA requires secure IT systems for crypto service providers — our policy engine holds one of the two keys required to move funds, so no transaction settles without it.
DORA requires accountability can't be delegated to software. Whenever a trade crosses the autonomous threshold, it escalates to a named human approver whose signature is recorded on-chain — the ledger carries human accountability, not just a software decision. You'll see this live in scenario C.
AI Act Article 14 requires a "stop button." Ours is literally one on-chain transaction — a SignerListSet update that removes the agent's key and freezes the account instantly.
GDPR — personal data can't go on-chain. Ours doesn't — only a Merkle hash of the reasoning goes in the memo; the full trace stays off-chain.
Product Liability Directive — companies need defensible evidence of reasonable care. Every decision the agent makes produces a signed, timestamped trail anchored on the ledger. That's the evidence.
Every obligation maps to a specific feature already in the demo.


§13 — What we're honest about (45s)

Three things we're clear-eyed about.
One — the AI Act still requires a human. We make oversight possible at machine speed; we don't replace human judgment.
Two — the policy engine is a target. We handle this with formal verification and separate governance keys — compromising the runtime can't change the rules.
Three — some XRPL features we'd love to use (smart contracts called Hooks) aren't live yet. So our policy engine lives off-chain for now, using the on-chain primitives that are available.
Honest about the limits. Working within them.


§14 — Roadmap (45s)
Cue: Brief on the ask — Alex said optional but good to mention. Be ready to answer after.

Roadmap if we were to actually build this out.
Rest of 2026 — testnet with 2-3 pilot partners. Apply to the XRPL Accelerator.
End of 2026 — first paying customer. Go through the MiCA+DORA audit with them.
First half 2027 — the certifications enterprise customers expect: SOC 2, ISO 27001.
Second half 2027 — enough paying customers to sustain a real team.
For context, typical seed rounds for RegTech in this space are $2-5M, with ~$500K of that potentially from non-dilutive sources like the XRPL Accelerator grant and Outlier Ventures. But right now we're focused on shipping the MVP and finding the first pilot — the fundraising conversation comes later.

If asked by the VC (see Q&A section below for full answers).

§15 — Why now, why this (45s)

To wrap up:
The interesting thing about this moment isn't that "AI agents will trade crypto" — that's already happening. It's that it's happening outside any coherent compliance framework, and that's about to become legally untenable.
Regulation, technology, and competition all point to the same thing:
The next eighteen months are when somebody has to solve this. The technology to solve it just became available. And the people who should have solved it already — the analytics companies, the custodians, the TradFi vendors — are solving adjacent problems, not this one.
That's our opening.


§16 — Demo + thanks (2 min)
Cue: Transition from pitch to proof. This is the 40% demo grade.

Alright — let us show you.
We built three scenarios on real XRPL testnet. Real AI, real signatures, real on-chain transactions.
First — a normal trade. The AI proposes it, the policy engine approves, both signatures land, the transaction settles. Happy path.
Second — a prompt injection. Same trade, but with a malicious instruction smuggled into the input. Watch the AI get fooled. And watch what happens when the policy engine sees the suspicious destination.
Third — a big trade, over our threshold. The AI proposes something legitimate but large. The policy engine doesn't auto-approve — it escalates to a human. That's the AI Act stop button, in UI form.

Cue: Run the demo. After scenario 2, pause:

This is the Freysa outcome — prevented, live, on testnet.

After all three:

And that's Signet. Thanks for listening — happy to take questions.


Q&A
From the jury / professor
Q: What's the problem in one sentence?
A: AI agents are moving money on blockchains, they can be jailbroken, and regulation is about to require controls that current tools don't provide.
Q: How big is the real market?
A: The immediate addressable market is ~100-150 EU crypto service providers hitting new regulations in 2026-2027. Broader market — institutional crypto plus AI-driven finance — in the tens of billions by 2030. But we're not selling to "the whole market" — we're selling to a specific, identifiable list of companies with a deadline-driven need.
Q: Will companies actually pay for this?
A: Two reasons yes. First, the penalties are existential — €35M or 7% of revenue under the AI Act alone. Second, we price in the same range as compliance tools they already pay for — Chainalysis, TRM, Elliptic. We're not asking them to expand their budget, just redirect part of it.
Q: Why you and not Ripple or Fireblocks?
A: Ripple would want this to exist in their ecosystem — we'd be a partner, not a competitor. Fireblocks has adjacent products but they're architecturally different (MPC, closed enclave, not on-chain verifiable). If we build this well, we get acquired by one of them. That's a fine outcome.
Q: What's next if this works?
A: Three things. Expand beyond XRPL as other chains mature. Add post-trade analytics for full lifecycle coverage. Eventually — extend the same approach to AI agents outside crypto: treasuries, traditional trading rails.
From the VC guest
Q: How much are you raising?
A: Target seed is $2-5M, with ~$500K of that potentially non-dilutive through accelerator programs.
Q: Valuation?
A: Too early to pin down precisely — depends on traction at raise time. Comparable early-stage RegTech seeds price around $8-15M post-money. We'd expect to sit in that range, depending on whether we have a design-partner LOI signed by then.
Q: Use of funds?
A: Roughly 60% engineering (2-3 hires plus contractor work on formal verification), 20% compliance infrastructure (SOC 2, ISO 27001), 10% design-partner BD, 10% reserve. 12-month runway to first paying customers.
Q: Exit scenario?
A: Realistically, acquisition by Ripple, Fireblocks, or an incumbent (Chainalysis, TRM) within 3-5 years. This is infrastructure — worth more inside a platform than as a standalone long-term.
Q: What could kill you?
A: Three things. Ripple shipping something like this natively — so we want to be close to them early. A competitor (like Cobo Pact) moving onto XRPL before we have a customer. Enforcement of 2026 regulations getting delayed by a year or two, thinning out urgency.
Q: Why not bootstrap?
A: The regulatory window closes in ~18 months. By the time we'd have revenue to self-fund, the opportunity would be partially captured. Timing-sensitive category.
From anyone
Q: Who on the team does what?
A: [Customise to actual split.] One of us focuses on the XRPL integration, one on the policy engine and security, one on the AI agent and reasoning, one on the frontend, and one on product and business. We've all contributed to the demo.
Q: How production-ready is the demo?
A: It's MVP — real multi-sig on testnet, real AI, real end-to-end flow. Not production-hardened (no SOC 2, no formal verification yet), but the cryptographic primitives are genuine.

Delivery notes

Slow down on §04 and §15. Those are the two "land the point" slides. Everything else can be conversational.
Don't read the slides. Look at the jury. The slides support you; they don't replace you.
Split roles. Sensible split: Speaker 1 does §00-04 (problem), Speaker 2 does §05-08 (architecture), Speaker 3 does §09-12 (market + compliance), Speaker 4 does §13-15 (honesty + close), Speaker 5 runs demo. Having everyone speak shows it's a real team.
Rehearse with a timer. First run-through will probably hit 17-18 minutes. Cut where the energy drops — usually §06, §07, or §10.
Be calm about the VC. He's there to observe, not grill. If he asks something you don't know, "honestly, we haven't modelled that yet — can we follow up after?" is a perfectly fine answer. Don't invent numbers.


Opening line (pick one)

"Hi everyone. We're the Signet team. Over the next fifteen minutes we'll walk you through a problem we think is about to get much bigger — and what we've built for it." (Warm, course-appropriate.)
"In 2024, an AI agent called Freysa was tricked into giving away its entire wallet. In 2026, a similar attack cost another company $40 million. We looked at what's coming next, and built something to stop it." (Story-led, more memorable.)