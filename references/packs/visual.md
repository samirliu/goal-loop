# Pack: visual acceptance (PROVE / BIND / FENCE)

Open from the **original request** when the deliverable must look convincing,
beautiful, realistic or faithful to a real subject. Do not wait for an author
to choose `judged`; all-green exit codes can omit the user's main objective.
An exact mechanical change such as moving a button by four pixels can keep
the ordinary deterministic path when no broader visual quality is claimed.

## Preserve the goal before building the ruler

Keep the user's words in Objective. Map the requested outcome to actual
observations: recognisable subject, complete massing/space, materials/light,
and the views or interactions that will be delivered. Choose dimensions that
matter to this request, not a fixed universal aesthetic checklist. A verifier
demonstration is additional to the artifact's quality, never its replacement.

For a real-world reconstruction, inspect credible reference photos/plans.
Record identifiable sources, observed features and approximations. A list of
"commonly published figures" without retrievable sources is not provenance.
For an original design, use the user's style brief and relevant visual anchors.
Do not silently restrict the task to procedural assets or avoid useful assets
unless the user or actual licensing/resource constraints require that choice.

Declare one calibrated **quality floor** covering the promised representative
views. Example, adapting the rubric and view names to the actual task:

```text
quality: visual AC-8 views=exterior,nave,dome,gallery

- AC-8 | Faithful overall silhouette and complete visible building envelope; interior space, materials and light match the named reference anchors; all four promised views are usable, with no missing masses, unintended sky leaks or blocked cameras | check: `python3 capture_views.py` | calib: good=references/target.jpg bad=references/near-miss.png | expected: judged
```

The check actually captures the current app's views under `.goal/evidence/`.
Keep technical checks (geometry, build, console, image nonblankness) as separate
floors. They do not judge fidelity. Add an existing independent requirement
check to the review when a user clause has no observable acceptance at all.

`quality:` binds the AC and view list at stamp. The controller also freezes the
Objective, available host-observed original request, and calibration bytes.
Common fidelity wording in Objective or a captured request requires this
declaration even if the author wrote only `exit=0` checks. This is a conservative
guard, not a complete language-understanding test; the agent still owes the
coverage review for wording the detector does not recognise. Hosts without
prompt capture pass the verbatim request with `begin/enter --request-stdin`;
Objective preserves it too. Reentry cannot overwrite an already captured request.

For "as realistic/good as possible", retain the improvement objective using
the existing [gradient/forge workflow](gradient.md). Do not invent a numeric
fidelity score from colour coverage or triangle counts. A calibrated judged
floor and evidence-backed completeness findings can guide improvement without
a fabricated score. Use the original budget; if quality remains inadequate
when it expires, report partial delivery and concrete remaining work.

## Calibrate against the failure you care about

Use the existing cold-seat calibration protocol from [instrument](instrument.md).
The good anchor must actually represent the requested quality. Include a
plausible **near miss** as the bad anchor: a textured but incomplete building,
incorrect spatial structure, exposed interior surfaces, or a blocked promised
view. Blank/solid images only calibrate renderer failure. Synthetic gold noise
does not become a known-good architectural render by satisfying pixel metrics.

Let the cold seat inspect the anchors and actual views against the original
brief/rubric, without producer reasoning or the producer's verdict. If it
accepts the near miss, repair the judge or rubric before trusting a PASS.
If it cannot inspect references or rendered artifacts, the quality floor is
unverified and cannot grant GO. Node and browser running the same assertions
provide execution coverage, not independent evidence that the ruler is right.

## Bind the observed views and unresolved findings

The cold seat returns its actual review JSON and PASS/FAIL/UNVERIFIABLE. The
controller saves that JSON verbatim under `.goal/evidence/`, for example:

```json
{
  "version": 1,
  "views": {
    "exterior": {"artifact": ".goal/evidence/exterior.png", "sha256": "<actual SHA-256>"},
    "nave": {"artifact": ".goal/evidence/nave.png", "sha256": "<actual SHA-256>"},
    "dome": {"artifact": ".goal/evidence/dome.png", "sha256": "<actual SHA-256>"},
    "gallery": {"artifact": ".goal/evidence/gallery.png", "sha256": "<actual SHA-256>"}
  },
  "findings": ["Exterior envelope is missing under the half-domes; the interior is visible from outside."],
  "summary": "Actual comparison to the original brief and identified reference anchors."
}
```

`findings` lists unresolved **goal-related** defects. Use `[]` only after real
review finds none. Put new defects in the work-plan and repair them. A limitation
that prevents the main request from being met is a finding, not an acceptable
blind spot. User-authorized scope changes use the existing contract-amendment
protocol; a producer cannot authorize its own waiver.

Do not edit away findings or supply a producer verdict when saving the report.
Bind the seat's existing quality AC verdict to **this JSON file's** actual hash using
`artifact: .goal/evidence/quality-review.json digest: <sha256>`. The ordinary
good/bad calibration verdicts remain required. The quality AC needs PASS;
the general allowance for UNVERIFIABLE does not waive this quality floor.
Original controller close/audit/Gate still decide completion.

Gate requires every declared view exactly once, distinct image evidence at
project-relative paths, matching image hashes, and no open findings. A bare
`adversarial=clear` cannot overrule a nonempty findings list. Changed screenshots
or a replaced review invalidate the verdict. Hashes establish which evidence
was reviewed; the cold seat, not the hashes, establishes visual quality.
Additional observations/provenance/validation-limit fields can be preserved
in the report and each view. They do not replace the required fields. If the
report also gives `verdict` or `completion_eligible`, FAIL/UNVERIFIABLE or false
cannot be hidden by an empty findings list and a separately bound PASS.
The same consistency check applies to an explicitly supplied verdict in each
declared view; an overall PASS cannot hide a failed or unverified camera.

The execution map exposes the required views and a review template with unknown
judgments left null. Do not copy a template or work-plan ticks into a PASS.
