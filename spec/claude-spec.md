# How I directed Claude

The case asks to see how I decomposed the problem, what I specified upfront,
and what I corrected afterwards. This file is that record. The five numbered
specs beside it carry the same split for their own layer.

## What I specified upfront

Before any code existed I wrote one instruction covering all five layers, and
required three things of every spec file: numbered requirements, concrete
pseudocode, and an explicit list of every assumption Claude had to make. That
last requirement mattered most. Left alone, an agent fills gaps silently. I
wanted the gaps written down so I could judge them myself.

The order was deliberate, working backwards from the output.

1. **The dashboard first**, because deciding what a person should be able to
   see is what fixes the data that has to exist.
2. **The data model and the ingestion next**, where I was most prescriptive:
   exact tables, exact columns, exact statuses, the exact weather variables,
   and the three safety properties stated separately so they could not be
   quietly conflated into one.
3. **The API last and loosest**, because by then both ends were fixed. I said
   only that responses need distinct structures depending on the outcome, and
   left the surface design open.

I also fixed a scope priority ranking upfront, so that if time ran out the
cuts would be decisions rather than accidents.

## What I corrected afterwards

**The dashboard's second panel.** The largest correction. I had asked for a
"target-time selector" without saying which view it drove, and got a small
table underneath the hourly chart. What I wanted was a panel of its own: pick
a future moment, see the current estimate first, then see how the estimate for
that exact moment moved over previous days. I kept the hourly chart as it was
and asked for the two to sit as separate panes.

Before agreeing to the rebuild I asked what the misreading had actually cost.
It was confined to the dashboard, because the database index and the API
endpoint had both been built for that question already. Worth establishing
before authorising a rewrite.

**The specs overstated my own contribution.** Reading them back, they sounded
as though I had reasoned through everything in them. I had not. I asked for
each file to be split into what I specified and what Claude derived from it,
which is how they now read.

**The README described the implementation rather than the thinking.** Its
architecture section listed table names, status codes and endpoints. I asked
for the principles behind the architecture instead, since the code already
states how those principles are filled in.

**Length, twice.** The first set of specs ran to roughly 1300 lines and the
second attempt to 426. Neither would have been read. They are now 250.

## Questions that changed the specs without correcting an error

Two behaviours of the weather service turned out to be assumed rather than
stated. Both surfaced because I did not understand the data source and asked.

**Does the seven-day history window grow each day?** No, it slides. Every call
returns seven days measured from its own date. Consecutive days overlap
heavily, and that overlap is what causes the same hour to appear under several
forecasts, which is what the revision history is made of. None of that was
written down until I asked.

**Is each forecast hour a separate request?** No. One call per city returns the
whole series, and a specific hour is one entry inside it. I had assumed the
opposite, which would have implied a very different ingestion design.

I also asked whether the system would ingest again the next day without me
touching it. It will, and answering it surfaced two gaps now recorded in the
specs: a missed run is never caught up, and the database is the only container
without an automatic restart policy.

## What I did not do

I verified behaviour by testing rather than by reading every line. The
functionality works and I can defend the design decisions, but I have not read
every file closely. That is the first thing I would fix with more time, and it
is why each source file carries a plain-language description of what it does
at the top.
