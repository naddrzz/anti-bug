# Finding template

The shape of a finding that survives scrutiny. Each field earns its place by
answering a question a skeptical reviewer will ask. If a field cannot be filled,
that is the signal the finding is `Suspected` rather than `Confirmed`.

```
ID:          F-0NN
Title:       [what is wrong, in the reader's terms - not "bad code in auth.py"]
Severity:    critical | high | medium | low     (by impact, not by irritation)
Category:    error-handling | security | correctness | concurrency |
             data-integrity | performance | config | test-quality
Status:      confirmed | suspected | false-positive | needs-decision |
             fixed | deferred | unverified
Location:    path/to/file.ext:LINE-LINE      (exact; a file name alone is not a location)

Impact:      Who is harmed, how badly, under what conditions. This is what
             decides severity and whether anyone acts.

Root cause:  The reason the defect exists, not the line where it shows up.
             "Null returned from findUser() is not checked" is a symptom;
             "findUser() signals absence with null while every caller assumes
             a record" is a cause - and points at all the other callers.

Evidence:    Either a reproduction (command + observed output) or a trace:
             entry point -> transform -> failure site, with file:line per hop.
             Evidence is what the reader re-runs to disagree with you.

Reproduction:
             $ [exact command]
             [actual observed output - never paraphrased, never predicted]

Expected:    [what should happen]
Actual:      [what does happen]

Siblings:    Every other place the same pattern occurs. A defect found once is
             usually a habit. An empty list here should be surprising.

Fix:         The change made, and why this one rather than the alternatives.
Tests:       The test that fails before and passes after, by path::name.
Revert-check: Confirmed the test fails when the fix is undone? (yes/no)
Commit:      [sha]
```

## Worked example

```
ID:          F-007
Title:       Order detail endpoint returns any user's order
Severity:    critical
Category:    security
Status:      fixed
Location:    src/api/orders.py:112-118

Impact:      Any authenticated user can read any other user's order, including
             shipping address, line items and the last four digits of the card.
             Reachable from the internet with a valid free account; enumerable
             because order IDs are sequential.

Root cause:  The handler authenticates but never scopes the query to the caller.
             Order.objects.get(pk=order_id) trusts the URL for identity. The
             list endpoint at line 84 scopes correctly, which is why this went
             unnoticed - the pattern exists in the file, it just was not applied here.

Evidence:    order_id arrives from the URL (orders.py:112) -> passed unmodified
             to Order.objects.get (orders.py:115) -> serialized and returned
             (orders.py:118). No ownership check on any path. CWE-639.

Reproduction:
             $ curl -H "Authorization: Bearer $USER_A_TOKEN" \
                 localhost:8000/api/orders/4471
             {"id":4471,"user_id":902,"address":"...","total":"189.00"}
             (token belongs to user 118; order 4471 belongs to user 902)

Expected:    404 for an order the caller does not own
Actual:      200 with the full order body

Siblings:    src/api/invoices.py:66  (same shape, same fix)
             src/api/shipments.py:41 (same shape, same fix)

Fix:         Scoped the lookup to the authenticated user in all three handlers:
             Order.objects.get(pk=order_id, user=request.user), which raises
             DoesNotExist and maps to 404. Used the ORM filter rather than an
             explicit permission branch so a future handler copying this code
             inherits the scoping.
Tests:       tests/api/test_orders.py::test_cannot_read_other_users_order
             tests/api/test_invoices.py::test_cannot_read_other_users_invoice
             tests/api/test_shipments.py::test_cannot_read_other_users_shipment
Revert-check: yes - reverting orders.py:115 turns the test red with 200 != 404
Commit:      a91f3c2
```
