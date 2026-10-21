# Products and side work

Kept here because "nothing lives only in a chat". Each entry says what is shipped, what is in
flight, and what could bite.

## Dualtooth - shipped (Forge-22 on Gemini, reported 2026-10-21)

- Standalone `.exe` built, 23/23 tests passing.
- GitHub release `v0.1.2` published; branding and assets done.
- Live Stripe payment link: https://buy.stripe.com/9B63cx3OWb9p6iPgFP9AA01

## SignalBlast - in flight (Forge-22, 2026-10-21)

Automated social listening and pain-point interception: monitors Reddit and Hacker News for active
dual-boot Bluetooth complaints, then drops a contextual solution carrying the Dualtooth link.
Strategy is to dogfood it on Dualtooth for distribution, then sell SignalBlast itself.

### The risk, stated plainly

The phrase "non-spam" is doing a lot of work in that description. Reddit and Hacker News both
prohibit undisclosed promotion, and both ban accounts for it faster than they ban the product. A bot
that posts a link into threads about a problem you sell a fix for is the classic pattern their
moderators watch for, and it will be judged by the community, not by intent.

What reduces the risk, in order of effect:
1. **Draft, do not post.** SignalBlast writes the reply and the human sends it, at least until it has
   a track record. This costs almost nothing to build and removes the ban path entirely.
2. **Disclose.** A one-line "I built the thing I am recommending" is the difference between a
   recommendation and astroturfing.
3. **Answer first, link second**, and only where the answer stands on its own without the link.
4. **Volume low enough to be human.** A dozen replies a day from one account looks like a person; a
   hundred looks like a bot, whatever the text says.
5. **Respect the APIs and their robots terms** rather than scraping around them.

### Open questions for Forge-22

- Does SignalBlast post automatically today, or draft for approval?
- Which accounts would it use, and is there a human gate before a link goes out?
- Where does the code live, so it can be reviewed rather than described?
