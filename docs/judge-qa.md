# Judge Q&A (spoken if time-constrained)

**Q: Why not just tell the LLM to check first?**  
A: Advice is not enforcement. The LLM can still propose an uncorrelated replay. The gateway is outside the model and can BLOCK before One.

**Q: Is the policy Stripe-specific?**  
A: No. Match/require/prohibit use effect type, persistence, outcome state, and replay type. The Linear holdout proves transfer.

**Q: How do you know Stripe is test mode?**  
A: Boot/preflight reads balance through One and asserts `livemode == false`. Live mode hard-stops mutations.

**Q: Same prompt for V1 and V3?**  
A: Yes. Shared base instruction + prompt hash. Only active policies differ.

**Q: What if You.com/Daytona keys are missing?**  
A: Labeled evidence cache and local harness fallbacks; metrics remain deterministic.
