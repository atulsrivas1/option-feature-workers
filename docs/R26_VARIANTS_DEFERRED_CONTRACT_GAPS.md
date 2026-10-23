# R26 variants1 worker layer: deferred contract gaps

Behaviour the contract states but gives no error code or pointer for. These
are not enforced; the current behaviour is kept until a clarification exists.

## Restore (CP3), not enforced
- A stamped suffix record must have a position strictly above the prior stream
  cursor and a known-at that does not regress (a record with a new identity at an
  already included position is accepted).
- A Request may not drop a stream retained by the prior cut.
- The Request must keep the prior operation ids, selection, policies, emit start
  and formula; baseline target and anchor lists may only extend.
- The supplied evaluator cohort scalar is not shape-checked beyond equality.

## Pointers chosen by analogy (to be confirmed)
- Stored history and prior Request admission errors (CP1a) reuse the batch codes
  with the path re-rooted under the checkpoint history and prior Request fields.
- A `policy_sha256s` mismatch reports the element index, or the list when its
  length differs.
- A repeated identity inside the suffix reports the batch uniqueness code and
  pointer, rooted at the suffix Snapshot.

## Cursor merge
Merged cursors keep the larger position per stream. Rejecting a regression is the
alternative; the contract gives no code for it.

## Output checkpoint
Produced only when the history is cut complete (every stamped record at or below
its stream cursor and known by K, history cursors equal to the Request cut
cursors); otherwise the run keeps valid results and a null checkpoint.
